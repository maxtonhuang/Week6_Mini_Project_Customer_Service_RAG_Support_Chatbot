#!/usr/bin/env python
"""Offline, dependency-free test runner.

The sandbox has no network (no pytest), so this discovers ``test_*`` functions in
``tests/test_*.py`` and runs them with plain asserts. On Colab you can instead use
``pytest`` (see requirements.txt) — the test files are compatible with both.

Usage:
    python run_tests.py                # run everything
    python run_tests.py test_foundation  # run one module (by stem or substring)
"""
from __future__ import annotations

import importlib.util
import os
import pathlib
import sys
import traceback

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Hermetic offline testing: force the synthetic corpus so tests never touch the
# network (real Bitext is used by the notebooks / pytest on Colab, where this is unset).
os.environ.setdefault("RAGGUARD_SYNTHETIC", "1")


def load_module(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def main(argv: list[str]) -> int:
    test_dir = ROOT / "tests"
    files = sorted(test_dir.glob("test_*.py"))
    if argv:
        needle = argv[0].replace(".py", "")
        files = [f for f in files if needle in f.stem]
    if not files:
        print("no test files found")
        return 1

    total = passed = 0
    failures: list[str] = []
    for f in files:
        try:
            mod = load_module(f)
        except Exception:
            failures.append(f"{f.stem}: IMPORT ERROR\n{traceback.format_exc()}")
            print(f"[IMPORT FAIL] {f.stem}")
            continue
        fns = [(n, o) for n, o in vars(mod).items()
               if n.startswith("test_") and callable(o)]
        for name, fn in fns:
            total += 1
            try:
                fn()
                passed += 1
                print(f"  PASS {f.stem}::{name}")
            except Exception:
                failures.append(f"{f.stem}::{name}\n{traceback.format_exc()}")
                print(f"  FAIL {f.stem}::{name}")

    print("\n" + "=" * 60)
    print(f"{passed}/{total} passed")
    if failures:
        print("=" * 60)
        for fail in failures:
            print("\n--- FAILURE ---")
            print(fail)
        return 1
    print("ALL GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
