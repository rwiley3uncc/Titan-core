"""Local Titan-AI import helper for sibling development checkouts.

This keeps Titan-core able to import Titan-AI while both projects live side by
side under the same DEV root. Once Titan-AI is installed as a normal package,
this helper can be removed or reduced.
"""

from __future__ import annotations

import sys
from pathlib import Path


def enable_titan_ai_imports() -> None:
    dev_root = Path(__file__).resolve().parents[2]
    titan_ai_root = dev_root / "Titan-AI"

    if titan_ai_root.exists():
        titan_ai_root_str = str(titan_ai_root)
        if titan_ai_root_str not in sys.path:
            sys.path.insert(0, titan_ai_root_str)

