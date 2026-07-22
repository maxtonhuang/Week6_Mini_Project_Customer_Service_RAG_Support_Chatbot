#!/usr/bin/env python
"""Pretty-print L0/L1/L2 defence catalogue for review.

    python prototypes/print_sophisticated_defenses.py
    python prototypes/print_sophisticated_defenses.py D2
    python prototypes/print_sophisticated_defenses.py STACK 2
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from prototypes.sophisticated_defenses import EXPERIMENT_PLAN, format_example, iter_examples


def main(argv: list[str]) -> None:
    defense = argv[1] if len(argv) > 1 else None
    level = int(argv[2]) if len(argv) > 2 else None

    print("# Defence levels L0 (production) · L1 · L2\n")
    print(EXPERIMENT_PLAN)
    print()
    if defense is None:
        print("## L0 — production baseline\n")
    for ex in iter_examples(defense, level):
        print(format_example(ex))
        print()


if __name__ == "__main__":
    main(sys.argv)
