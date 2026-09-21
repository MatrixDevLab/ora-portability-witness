# Validation method

The checker is validated with synthetic archives built in the test process.
The corpus covers:

1. a clean baseline archive;
2. required-file, MIME ordering, compression, and PNG-header failures;
3. malformed XML and invalid root metadata;
4. missing layer sources and orphaned `data/` members;
5. invalid group isolation and deprecated stack offsets;
6. non-baseline composite operations and alpha-preserve combinations; and
7. deterministic report ordering and repeated output.

The smallest meaningful local check is:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m py_compile src/ora_witness.py
git diff --check
```

No network, image renderer, or external package is required.
