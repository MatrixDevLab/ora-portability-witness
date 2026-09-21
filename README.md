# ORA Portability Witness

`ora-portability-witness` is a dependency-free, offline checker for the
portable boundary of OpenRaster (`.ora`) files.

It reports deterministic, location-rich findings for ZIP layout, the required
`stack.xml` layer references, baseline layer-stack values, and a small set of
known loss-risk signals. It does not render pixels, repair archives, or claim
that two painting applications will produce identical images.

## Why this exists

OpenRaster is intended as an interchange format, but its applications have
diverged around group isolation, blend/compositing extensions, color handling,
and alpha-preserve behavior. The witness makes the part that can be checked
without an application explicit before a file is handed to another editor.

## Usage

```sh
PYTHONPATH=src python3 -m ora_witness artwork.ora
PYTHONPATH=src python3 -m ora_witness --strict artwork.ora
```

The command writes JSON to stdout. Exit status is `0` for a clean report, `2`
for baseline errors, and `1` in `--strict` mode when portability warnings are
present.

## Scope boundary

The first release checks only local archive/XML evidence. It deliberately does
not decode or compare rendered images, infer an application's compositing
implementation, validate proprietary extensions, or decide whether a file is
safe for archival intent.

See [the problem statement](docs/problem-statement.md), [validation method](docs/validation.md),
[roadmap](docs/roadmap.md), and [stopping point](docs/stopping-point.md).
