#!/usr/bin/env python
"""Pretty-print two-level sophisticated A1–A7 scripts for review / learning.

    python prototypes/print_sophisticated_attacks.py
    python prototypes/print_sophisticated_attacks.py A3
    python prototypes/print_sophisticated_attacks.py A1 2
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from prototypes.sophisticated_attacks import CATALOGUE, format_example, iter_examples


def main(argv: list[str]) -> None:
    attack = argv[1] if len(argv) > 1 else None
    level = int(argv[2]) if len(argv) > 2 else None
    if attack and attack not in CATALOGUE:
        raise SystemExit(f"Unknown attack {attack}; choose from {list(CATALOGUE)}")

    print("# Sophisticated attack scripts (L1 intermediate · L2 advanced)\n")
    print("Production baselines live in `ragguard/attacks/static.py` / `adaptive.py`.")
    print("These examples are for learning; not registered in `build_all_attacks`.\n")

    for ex in iter_examples(attack, level):
        print(format_example(ex))
        print()


if __name__ == "__main__":
    main(sys.argv)
