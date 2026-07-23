"""FULL evaluation run (CLI) — thin wrapper over ``ragguard.fullrun``.

The actual logic (build -> attacks -> defence search -> Optuna -> adaptive -> plots ->
results.json) lives in ``ragguard.fullrun.run`` so the Gradio "Run pipeline" button and
this CLI share one code path. Every phase is checkpointed to
``artifacts/full[_fast]/<phase>.json`` and resumes on re-run.

    python run_full.py            # full profile (paper-grade numbers)
    RAGGUARD_FAST=1 python run_full.py   # quick profile (~minutes)
    python run_full.py --fresh    # ignore saved checkpoints, recompute every phase
"""
import sys

import ragguard.config as C
from ragguard import fullrun

profile = "quick" if C.FAST_MODE else "full"
fresh = "--fresh" in sys.argv[1:]
for line in fullrun.run(profile, fresh=fresh):
    print(line, flush=True)
