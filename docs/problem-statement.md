# Problem statement

OpenRaster 0.0.6 defines a ZIP container, a required `stack.xml`, required
preview files, and a baseline layer-stack profile intended to make files
interoperate between image editors. The format also permits extensions, and
the specification distinguishes baseline-safe content from application-specific
behavior.

Public maintainer evidence shows why a producer needs a preflight boundary:

- Krita merged a fix because groups without an explicit `isolation` attribute
  were being treated as pass-through even though the baseline default is
  `isolate`.
- MyPaint's issue tracker records non-baseline blend-mode namespace use and
  missing color/compositing intent that made compatibility with GIMP and Krita
  difficult.
- Drawpile documented that alpha-preserve information was not representable in
  the base ORA format and was lost when round-tripping through Krita.

The first useful artifact is therefore a **witness**, not a renderer: it should
identify malformed baseline files and make known portability hazards visible,
while leaving application behavior and unsupported extensions as explicit
unknowns.

## Non-goals

- no pixel rendering or image-difference claim;
- no application-specific compatibility certification;
- no repair or rewrite of user archives;
- no network access or third-party dependencies;
- no archival-intent certification.

## Sources

- OpenRaster [file layout specification](https://www.openraster.org/baseline/file-layout-spec.html)
- OpenRaster [layer stack specification](https://www.openraster.org/baseline/layer-stack-spec.html)
- Krita [OpenRaster merge request !2387](https://invent.kde.org/graphics/krita/-/merge_requests/2387)
- MyPaint [out-of-spec ORA changes #958](https://github.com/mypaint/mypaint/issues/958)
- Drawpile [Layer Alpha Preserve in ORA Files](https://docs.drawpile.net/devblog/2023/08/23/ora-alpha-preserve.html)
