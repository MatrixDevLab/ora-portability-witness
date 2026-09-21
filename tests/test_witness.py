import json
import contextlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from ora_witness import main, validate  # noqa: E402


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + bytes.fromhex("00000001000000010802000000") + b"\x00\x00\x00\x00IEND\xaeB\x60\x82"


def archive(path: Path, stack: str, *, mimetype: bytes = b"image/openraster", compressed: bool = False, order=None):
    members = {
        "mimetype": mimetype,
        "stack.xml": stack.encode(),
        "mergedimage.png": PNG,
        "Thumbnails/thumbnail.png": PNG,
        "data/layer.png": PNG,
    }
    order = order or list(members)
    with zipfile.ZipFile(path, "w") as zf:
        for name in order:
            info = zipfile.ZipInfo(name)
            info.compress_type = zipfile.ZIP_DEFLATED if compressed else zipfile.ZIP_STORED
            zf.writestr(info, members[name])


VALID_STACK = """<?xml version='1.0' encoding='UTF-8'?>
<image version='0.0.6' w='1' h='1'><stack><layer name='one' src='data/layer.png'/></stack></image>
"""


class WitnessTests(unittest.TestCase):
    def test_clean_archive_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clean.ora"
            archive(path, VALID_STACK)
            report = validate(str(path))
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["summary"], {"errors": 0, "warnings": 0, "findings": 0})

    def test_required_layout_and_png_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.ora"
            archive(path, VALID_STACK, mimetype=b"wrong", compressed=True, order=["stack.xml", "mimetype", "mergedimage.png", "Thumbnails/thumbnail.png", "data/layer.png"])
            report = validate(str(path))
            codes = {item["code"] for item in report["findings"]}
            self.assertEqual(report["status"], "error")
            self.assertTrue({"ORA_MIMETYPE_NOT_FIRST", "ORA_MIMETYPE_COMPRESSED", "ORA_MIMETYPE_INVALID"} <= codes)

    def test_missing_layer_and_orphan_data_are_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "refs.ora"
            stack = VALID_STACK.replace("data/layer.png", "data/missing.png")
            archive(path, stack)
            report = validate(str(path))
            codes = [item["code"] for item in report["findings"]]
            self.assertIn("ORA_LAYER_SOURCE_MISSING", codes)
            self.assertIn("ORA_ORPHAN_DATA_MEMBER", codes)

    def test_group_and_extension_risks_are_typed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "risk.ora"
            stack = """<image version='0.0.6' w='1' h='1'><stack><stack isolation='wat' x='1'><layer src='data/layer.png' composite-op='mypaint:spectral'/><layer src='data/layer.png' composite-op='svg:src-over' alpha-preserve='true'/></stack></stack></image>"""
            archive(path, stack)
            report = validate(str(path))
            codes = {item["code"] for item in report["findings"]}
            self.assertEqual(report["status"], "error")
            self.assertTrue({"ORA_ISOLATION_INVALID", "ORA_STACK_OFFSET_DEPRECATED", "ORA_COMPOSITE_OP_NON_BASELINE", "ORA_ALPHA_PRESERVE_REDUNDANT"} <= codes)

    def test_deterministic_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "same.ora"
            archive(path, VALID_STACK.replace("src='data/layer.png'", "src='data/layer.png' composite-op='mypaint:spectral'"))
            first = json.dumps(validate(str(path)), sort_keys=True)
            second = json.dumps(validate(str(path)), sort_keys=True)
            self.assertEqual(first, second)

    def test_strict_cli_fails_on_warning(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "warning.ora"
            archive(path, VALID_STACK.replace("src='data/layer.png'", "src='data/layer.png' composite-op='mypaint:spectral'"))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = main(["--strict", str(path)])
            self.assertEqual(result, 1)
            self.assertEqual(json.loads(output.getvalue())["status"], "warning")

    def test_malformed_xml_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "xml.ora"
            archive(path, "<image>")
            report = validate(str(path))
            self.assertEqual(report["status"], "error")
            self.assertIn("ORA_STACK_XML_INVALID", {item["code"] for item in report["findings"]})


if __name__ == "__main__":
    unittest.main()
