"""Entrypoint de `python -m tms.ingest`."""

from tms.ingest.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
