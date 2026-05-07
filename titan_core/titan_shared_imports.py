"""Local Titan-shared import helper for side-by-side development checkouts."""

from __future__ import annotations

import sys
from pathlib import Path


def ensure_titan_shared_on_path() -> None:
    current_file = Path(__file__).resolve()
    dev_root = current_file.parents[2]
    titan_shared_root = dev_root / "Titan-shared"

    if titan_shared_root.exists():
        shared_path = str(titan_shared_root)
        if shared_path not in sys.path:
            sys.path.insert(0, shared_path)

