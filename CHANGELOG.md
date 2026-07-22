# Changelog

All notable changes to RAGGuard. Newest first. Dates are ISO (YYYY-MM-DD); the tag in
brackets is the git commit. Grouped as **Added / Changed / Fixed**.

---

## [c60f4c3] — 2026-07-22 · Documentation neutrality
### Changed
- Generalized every GPU reference in docs, comments, notebooks, and scripts — removed
  specific card names and "this machine" phrasing so the repo reads as vendor-neutral.

## [3590d0e] — 2026-07-22 · Docs + UI reflect auto-config
### Added
- Gradio header now shows the **auto-detected runtime** — `model · precision · device · batch`.
### Changed
- `README.md`, `UI_GUIDE.md`, `MINI_PROJECT_PLAN.md`, `BUILD_STATUS.md` updated with the
  GPU auto-configuration tier table and the new env vars.

## [2865685] — 2026-07-22 · Run on any GPU (auto-detection)
### Added
- **`ragguard/autotune.py`** — detects GPU VRAM and picks the path (full bf16 / 4-bit /
  smaller victim / CPU), **installing `bitsandbytes` on demand**. Wired into `00_MAIN.ipynb`,
  `serve_app.py`, and `run_full.py`.
- **4-bit (NF4) quantization** in `QwenLLM` (`load_in_4bit`, env `RAGGUARD_4BIT`) so the 8B
  fits GPUs under ~16 GB.
- Env dials `RAGGUARD_BATCH`; optional `bitsandbytes` in `requirements.txt`.
### Changed
- Batched generation is **OOM-resilient** — backs off batch size to sequential on CUDA OOM
  instead of crashing.
- The notebook wraps the model in `CachedLLM`, turning the §3 64-stack search from ~an hour
  into minutes.
- Default generation batch size lowered (8 → 4) and tiers made conservative to avoid
  spilling into shared system RAM.
### Fixed
- **§2 crash on smaller GPUs** (CUDA OOM — the 8B needs ~30 GB in bf16, doesn't fit ≤24 GB):
  resolved by autotune (4-bit / smaller model) + the OOM backoff.
- Headless notebook **timeout** (the un-cached search was too slow) — fixed by the notebook cache.
- **VRAM overflow into system RAM** at large batch — fixed by conservative batch tiers.

## [4f975a3] — 2026-07-22 · Reviewer gap fixes
Three gaps a reviewer flagged, all fixed (see `tests/test_gaps.py`):
### Added
- **`orchestrator.tune_thresholds()`** — real **Optuna (TPE)** tuning of the best stack's
  continuous thresholds (tuned D5 groundedness → 0.18).
- `tests/test_gaps.py` (Optuna, LLM-driven A7, benign disjointness).
### Changed
- **A7 adaptive attacker is now LLM-driven** — uses the real Qwen3-8B as the mutator (plus a
  heuristic baseline) and runs **against the best defence stack** (result: 0% ASR across 6
  rounds — the defences hold under adaptive attack).
### Fixed
- **Benign eval set now guaranteed disjoint from the KB** (was ~30% overlap; the docstring
  had wrongly claimed disjointness). Utility/FRR now measure true generalisation.

## [da90be2] — 2026-07-21 · Slide-deck outline
### Added
- `SLIDES_OUTLINE.md` — slide-by-slide plan for the 10-min talk + 2–3 min demo + Q&A prep.

## [1ddbcd2] — 2026-07-21 · Report skeleton
### Added
- `REPORT_SKELETON.md` — 4-section report scaffold with pre-filled facts/tables/figures and
  guided `✍️ WRITE` blocks for the team.

## [3132994] — 2026-07-21 · Initial pipeline
### Added
- Full **`ragguard`** package: victim RAG system (Qwen3-8B + MiniLM + FAISS + planted
  canaries), attacks **A1–A6 + adaptive A7**, defences **D1–D6** (3 hook points),
  two-stage 64-stack defence search, NIST AI RMF governance, report plots, and a 4-tab
  **Gradio UI**.
- `00_MAIN.ipynb` / `01_DEMO.ipynb`, offline test suite + `run_tests.py`, and docs
  (`MINI_PROJECT_PLAN.md`, `BUILD_STATUS.md`, `UI_GUIDE.md`, `README.md`).
- First full run on GPU: **undefended ASR 25% → 0%**, best stack **[D4+D5]** (100%
  robustness, 0% false-refusal).
