"""Run locally without installing a package or changing PYTHONPATH."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))

from ontime.__main__ import main

if __name__ == '__main__':
    raise SystemExit(main())

