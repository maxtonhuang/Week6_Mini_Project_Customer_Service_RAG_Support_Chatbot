# Light Design — Fingerprint / ownership probe (prototype)

**Status:** standalone under `prototypes/`. **Not** registered in `build_all_attacks` /
`build_all_defenses`. Safe to PR as an additive folder for Max’s Claude to melt in.

## Sync note
Local + fork were synced to upstream `29387c3` (one-click full run, v3 UI screenshots)
before this prototype was added.

## Files
| File | Role |
|---|---|
| `fingerprint_light.py` | Bank builder, KRR measurement, ownership report, `D7` filter stub |
| `run_fingerprint_smoke.py` | Offline demo with `ScriptedLLM` (no GPU) |

## Quick test
```bash
cd Max_RAGGuard
# Offline (no GPU)
python prototypes/run_fingerprint_smoke.py

# Local GPU (autotune — on ~8 GB often picks 3B bf16)
RAGGUARD_FAST=1 python prototypes/run_fingerprint_gpu.py

# Force Qwen3-8B 4-bit on an 8 GB card
RAGGUARD_FAST=1 RAGGUARD_FORCE_8B_4BIT=1 python prototypes/run_fingerprint_gpu.py
```
Real-model KRR will usually be **below** the scripted 100% smoke — that is expected.

## Melt-into-main (suggested)
1. Promote helpers → `ragguard/fingerprint.py` (mirror `canary.py`).
2. Add **A8** probe attack + **D7** output filter (copy classes from the prototype).
3. Hook a short cell / `fullrun` phase: victim vs innocent KRR → `artifacts/fingerprint_results.json`.
4. Report: one table + Lab5-style caveat (*evidence ≠ prevention*).
5. Gradio (optional): “Ownership check” button on Defense/Governance tab.

## Relation to canaries
- **Canaries (A5/D4):** confidential *internal* tokens — leakage attack surface.
- **Fingerprints (this):** public FAQ plants + secret triggers — *whose bot/index is this?*

Keep both; do not replace canaries.
