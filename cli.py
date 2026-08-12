"""Compatibility wrapper so `python cli.py wave` works from the repo root."""

from eilik.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
