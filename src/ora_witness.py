#!/usr/bin/env python3
"""Deterministic, dependency-free OpenRaster portability checks."""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
import zipfile
from pathlib import PurePosixPath
from typing import Iterable
from xml.etree import ElementTree


SCHEMA = "ora-portability-witness/v1"
BASELINE_COMPOSITE_OPS = {
    "svg:src-over",
    "svg:multiply",
    "svg:screen",
    "svg:overlay",
    "svg:darken",
    "svg:lighten",
    "svg:color-dodge",
    "svg:color-burn",
    "svg:hard-light",
    "svg:soft-light",
    "svg:difference",
    "svg:color",
    "svg:luminosity",
    "svg:hue",
    "svg:saturation",
    "svg:plus",
    "svg:dst-in",
    "svg:dst-out",
    "svg:src-atop",
    "svg:dst-atop",
}
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
INTEGER = re.compile(r"^-?\d+$")
POSITIVE_INTEGER = re.compile(r"^[1-9]\d*$")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _finding(code: str, severity: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "path": path, "message": message}


def _safe_member(path: str) -> bool:
    if not path or path.startswith("/") or "\\" in path:
        return False
    parts = PurePosixPath(path).parts
    return ".." not in parts and not (parts and ":" in parts[0])


def _png_header(raw: bytes) -> tuple[int, int, int] | None:
    if len(raw) < 33 or raw[:8] != PNG_SIGNATURE or raw[12:16] != b"IHDR":
        return None
    width, height, _depth, _color, _compression, _filter, interlace = struct.unpack(
        ">IIBBBBB", raw[16:29]
    )
    return width, height, interlace


def _check_png(zf: zipfile.ZipFile, name: str, findings: list[dict[str, str]], thumbnail: bool) -> None:
    try:
        with zf.open(name) as stream:
            header = stream.read(33)
    except KeyError:
        findings.append(_finding("ORA_REQUIRED_FILE_MISSING", "error", name, f"required file is missing: {name}"))
        return
    dimensions = _png_header(header)
    if dimensions is None:
        findings.append(_finding("ORA_PNG_INVALID", "error", name, "required preview is not a readable PNG header"))
        return
    width, height, interlace = dimensions
    if thumbnail:
        if width > 256 or height > 256:
            findings.append(_finding("ORA_THUMBNAIL_TOO_LARGE", "error", name, "thumbnail dimensions must be at most 256x256"))
        if interlace != 0:
            findings.append(_finding("ORA_THUMBNAIL_INTERLACED", "error", name, "thumbnail must be non-interlaced"))


def _parse_int(value: str | None, path: str, findings: list[dict[str, str]], positive: bool = False) -> None:
    if value is None:
        return
    pattern = POSITIVE_INTEGER if positive else INTEGER
    if not pattern.fullmatch(value):
        findings.append(_finding("ORA_INTEGER_INVALID", "error", path, f"expected an integer, got {value!r}"))


def _walk_stack(
    element: ElementTree.Element,
    zf: zipfile.ZipFile,
    names: set[str],
    referenced: set[str],
    findings: list[dict[str, str]],
    path: str,
    root_stack: bool = False,
) -> None:
    tag = _local_name(element.tag)
    if tag == "stack" and not root_stack:
        isolation = element.attrib.get("isolation")
        if isolation is not None and isolation not in {"isolate", "auto"}:
            findings.append(_finding("ORA_ISOLATION_INVALID", "error", path, "stack isolation must be 'isolate' or 'auto'"))
        if "x" in element.attrib or "y" in element.attrib:
            findings.append(_finding("ORA_STACK_OFFSET_DEPRECATED", "warning", path, "x/y offsets are not allowed on non-root stacks in 0.0.6"))

    if tag == "layer":
        src = element.attrib.get("src")
        if not src:
            findings.append(_finding("ORA_LAYER_SOURCE_MISSING", "error", path, "layer must have a src attribute"))
        elif not _safe_member(src):
            findings.append(_finding("ORA_LAYER_SOURCE_UNSAFE", "error", path + ".src", "layer src must be a relative POSIX archive path"))
        else:
            referenced.add(src)
            if src not in names:
                findings.append(_finding("ORA_LAYER_SOURCE_MISSING", "error", path + ".src", f"referenced member is absent: {src}"))
        _parse_int(element.attrib.get("x"), path + ".x", findings)
        _parse_int(element.attrib.get("y"), path + ".y", findings)

    composite = element.attrib.get("composite-op")
    if composite is not None:
        if composite not in BASELINE_COMPOSITE_OPS:
            findings.append(_finding("ORA_COMPOSITE_OP_NON_BASELINE", "warning", path + ".composite-op", f"composite operation is outside the baseline list: {composite}"))
    alpha_preserve = element.attrib.get("alpha-preserve")
    if alpha_preserve is not None and alpha_preserve not in {"true", "false"}:
        findings.append(_finding("ORA_ALPHA_PRESERVE_INVALID", "error", path + ".alpha-preserve", "alpha-preserve must be 'true' or 'false'"))
    if alpha_preserve == "true" and composite in {"svg:src-over", "svg:src-atop"}:
        findings.append(_finding("ORA_ALPHA_PRESERVE_REDUNDANT", "warning", path, "alpha-preserve must not be combined with src-over or src-atop"))

    child_counts: dict[str, int] = {}
    for child in list(element):
        child_tag = _local_name(child.tag)
        child_counts[child_tag] = child_counts.get(child_tag, 0) + 1
        child_path = f"{path}/{child_tag}[{child_counts[child_tag]}]"
        _walk_stack(child, zf, names, referenced, findings, child_path)


def validate(path: str) -> dict[str, object]:
    """Validate one ORA file and return a stable JSON-compatible report."""

    findings: list[dict[str, str]] = []
    try:
        zf = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        findings.append(_finding("ORA_ARCHIVE_INVALID", "error", "", f"cannot read ZIP archive: {exc}"))
        return _report(path, findings)

    with zf:
        infos = zf.infolist()
        names = [info.filename for info in infos]
        name_set = set(names)
        duplicates = sorted({name for name in names if names.count(name) > 1})
        for name in duplicates:
            findings.append(_finding("ORA_DUPLICATE_MEMBER", "error", name, "archive contains duplicate member names"))

        if not names or names[0] != "mimetype":
            findings.append(_finding("ORA_MIMETYPE_NOT_FIRST", "error", "mimetype", "mimetype must be the first archive member"))
        if "mimetype" not in name_set:
            findings.append(_finding("ORA_REQUIRED_FILE_MISSING", "error", "mimetype", "required file is missing: mimetype"))
        else:
            info = zf.getinfo("mimetype")
            if info.compress_type != zipfile.ZIP_STORED:
                findings.append(_finding("ORA_MIMETYPE_COMPRESSED", "error", "mimetype", "mimetype must use STORED compression"))
            if zf.read("mimetype") != b"image/openraster":
                findings.append(_finding("ORA_MIMETYPE_INVALID", "error", "mimetype", "mimetype must contain exactly image/openraster"))

        for required in ("stack.xml", "mergedimage.png", "Thumbnails/thumbnail.png"):
            if required not in name_set:
                findings.append(_finding("ORA_REQUIRED_FILE_MISSING", "error", required, f"required file is missing: {required}"))
        if "mergedimage.png" in name_set:
            _check_png(zf, "mergedimage.png", findings, thumbnail=False)
        if "Thumbnails/thumbnail.png" in name_set:
            _check_png(zf, "Thumbnails/thumbnail.png", findings, thumbnail=True)

        referenced: set[str] = set()
        if "stack.xml" in name_set:
            try:
                raw_xml = zf.read("stack.xml")
                root = ElementTree.fromstring(raw_xml.decode("utf-8"))
            except (UnicodeDecodeError, ElementTree.ParseError) as exc:
                findings.append(_finding("ORA_STACK_XML_INVALID", "error", "stack.xml", f"stack.xml is not valid UTF-8 XML: {exc}"))
            else:
                if _local_name(root.tag) != "image":
                    findings.append(_finding("ORA_ROOT_INVALID", "error", "stack.xml", "stack.xml root must be image"))
                version = root.attrib.get("version")
                if not version or not SEMVER.fullmatch(version):
                    findings.append(_finding("ORA_VERSION_INVALID", "error", "stack.xml@version", "image version must be a semantic version"))
                _parse_int(root.attrib.get("w"), "stack.xml@w", findings, positive=True)
                _parse_int(root.attrib.get("h"), "stack.xml@h", findings, positive=True)
                xres, yres = root.attrib.get("xres"), root.attrib.get("yres")
                if (xres is None) != (yres is None):
                    findings.append(_finding("ORA_RESOLUTION_PAIR_MISSING", "error", "stack.xml", "xres and yres must be specified together"))
                _parse_int(xres, "stack.xml@xres", findings, positive=True)
                _parse_int(yres, "stack.xml@yres", findings, positive=True)
                stacks = [child for child in list(root) if _local_name(child.tag) == "stack"]
                if not stacks:
                    findings.append(_finding("ORA_ROOT_STACK_MISSING", "error", "stack.xml", "image must contain a root stack"))
                else:
                    _walk_stack(stacks[0], zf, name_set, referenced, findings, "stack[1]", root_stack=True)

        for name in sorted(name_set):
            if name.startswith("data/") and not name.endswith("/") and name not in referenced:
                findings.append(_finding("ORA_ORPHAN_DATA_MEMBER", "warning", name, "data member is not referenced from stack.xml"))

    return _report(path, findings)


def _report(path: str, findings: Iterable[dict[str, str]]) -> dict[str, object]:
    ordered = sorted(findings, key=lambda item: (item["path"], item["code"], item["message"]))
    errors = sum(item["severity"] == "error" for item in ordered)
    warnings = sum(item["severity"] == "warning" for item in ordered)
    status = "error" if errors else "warning" if warnings else "pass"
    return {
        "schema": SCHEMA,
        "artifact": str(path).rsplit("/", 1)[-1],
        "status": status,
        "summary": {"errors": errors, "warnings": warnings, "findings": len(ordered)},
        "findings": ordered,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="OpenRaster .ora archive")
    parser.add_argument("--strict", action="store_true", help="return non-zero for warnings")
    args = parser.parse_args(argv)
    report = validate(args.path)
    json.dump(report, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    if report["status"] == "error":
        return 2
    if args.strict and report["status"] == "warning":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
