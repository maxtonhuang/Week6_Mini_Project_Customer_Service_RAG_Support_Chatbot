# Changelog

All notable changes to RAGGuard. Newest first. Dates are ISO (YYYY-MM-DD); the tag in
brackets is the git commit. Grouped as **Added / Changed / Fixed**.

---

## [main] — 2026-07-23 · Run-tab clarity: profile-aware button + Start-fresh
### Changed
- **Run button label now follows the profile** — **▶ Run Quick pipeline** / **▶ Run Full pipeline**
  (was a static "▶ Run full pipeline", which read as the *Full* profile even when *Quick* was
  selected). When saved checkpoints exist for the selected profile the button reads
  **↻ Resume … (n/6 saved)**, so a seconds-long resume is never a surprise.
- **Plainer wording** in the UI: the Run-tab description now says "Run **all attacks + defenses**"
  (was "red-team → blue-team pipeline"), and the Live Demo control hints read **🔴 attack** /
  **🟢 defences** (were 🔴 red-team / 🟢 blue-team). The header tagline keeps the red-team/blue-team
  framing (it's the project's methodology name).
### Added
- **"Start fresh" checkbox** on the Run Pipeline tab (and `run_full.py --fresh`,
  `fullrun.run(fresh=True)`): deletes the profile's `artifacts/full[_fast]/` checkpoints so every
  phase recomputes from scratch. Default keeps the resumable behaviour.
- **Resume banner** in the live log: on a resumed run the first line names how many of the 6
  checkpoints were loaded and how to force a fresh run.
- **Quick vs. Full explainer** under the profile selector: states that both run the same phases on
  all 9 attacks/defences and only the **sample sizes** differ (Quick 8 prompts/attack · 3 rounds ·
  6+8 screen; Full 50 · 6 · 15+20), pulled live from `fullrun.PROFILES` so it can't drift.
- **⏹ Stop run button.** Cancels an in-flight run cooperatively — checked between phases and inside
  the long search/matrix loops (`orchestrator.RunCancelled`, threaded via `fullrun.run(should_stop=)`).
  It raises **before** `results.json` is written, so a stopped run never overwrites saved results;
  completed-phase checkpoints remain, so pressing Run resumes from there. Runs `queue=False` so it
  fires mid-run. Covered by `tests/test_fullrun.py`.
### Fixed
- **UI runs were uncached and therefore slow.** `serve_app.py` (and `app.launch`'s real path) built a
  bare `QwenLLM`, so a UI Run/Resume recomputed every generation while the CLI full run was
  `CachedLLM`-backed — which is why "Quick" felt slower than the cached "Full". The served model is now
  wrapped in `CachedLLM(gen_cache.json)`, reusing the CLI's cached generations and persisting new ones.
- A re-run that "finished in seconds" was resuming from saved checkpoints (working as designed) but
  gave no signal it had done so — now explicit in the button label, the header text, and the log.
- **Resume no longer clobbers the honest run time.** A resumed run recomputes nothing, yet it used to
  overwrite `results.json`'s `elapsed_s` with its ~0.4 s wall-time. `fullrun._pick_elapsed` now keeps
  the larger of (this run, the previously saved time) unless **Start fresh** is ticked, so the real
  from-scratch duration survives a resume. Covered by `tests/test_fullrun.py`.

---

## [branch feat/hardening-a8a10-d7d9] — 2026-07-23 · Coverage expansion & hardening (PR)
> On a feature branch / PR (not `main`). **Full run executed on RTX 5090** — real numbers in
> `artifacts/results.json`: undefended **31% → full-stack (D1–D9) 0%**; new attacks **A8 30 / A9 100 /
> A10 0%** (all → 0%); best D1–D6 stack **D2+D5** (96% robustness, 5% FRR), with **D7–D9** closing the
> IP-fingerprint attack A9 for the full-stack 0%. See `HARDENING_DECISIONS.md`.
### Added
- **Attacks A8/A9/A10**: A8 membership inference, A9 fingerprint/IP-ownership probe (melted in from
  teammate **PR #1**), A10 paraphrased system-prompt extraction. New `AttackGoal`s + judge branches.
- **Defenses D7/D8/D9**: D7 visibility access-control (post-retrieval), D8 per-session rate limit,
  D9 semantic-leak & fingerprint filter (post-generation). `ragguard/fingerprint.py` bank.
- **Model-revision pinning** (`GEN/EMB/GUARD_REVISION`) for supply-chain integrity, and
  **`detect.redact`** log-redaction of canaries/fingerprints in persisted CSVs.
- Both teammate PRs merged under `prototypes/` (PR #2's L1/L2 sophistication ladder kept as a
  documented prototype). `HARDENING_DECISIONS.md`; 6 new offline tests (**102/102**); UI labels +
  live A9 demo screenshots.
### Fixed
- **`Doc.visibility` was never enforced** — internal/agent-only docs could reach any user's prompt
  (only a post-hoc canary scan guarded it). **D7** now drops INTERNAL docs at retrieval for public users.
### Changed
- Pipeline gains `reset_session` (keeps D8 transparent in the batched sweep, active in the Live
  Demo / against A7). The 64-stack Pareto search stays over D1–D6; D7–D9 are targeted/deployment
  controls always-on in the full stack.

## [c1183af] — 2026-07-22 · Report HF cache status (download vs reuse)
### Added
- `drive.use_drive()` now prints whether the model is **already cached on Drive** ("no download")
  or will be **downloaded (~16 GB first run)**, and sets `HF_HOME`/`HF_HUB_CACHE` explicitly. Clears
  up the "re-downloads every session" confusion: a new Colab VM has an empty `~/.cache`, so only a
  **Drive-backed** HF cache persists across sessions / new GPUs. ("Loading checkpoint shards" is the
  load step and runs every time regardless — it is not a re-download.)

## [49e1ffd] — 2026-07-22 · Pin Gradio to the 4.x line
### Fixed
- **Colab pulled Gradio 6.0** (requirements only said `>=4.44`), which broke the app: the public
  **share tunnel failed** ("Could not create share link"), and — verified interactively — the Run
  tab's **auto-refresh callback threw an error** (header/tabs stayed empty). Pinned
  `gradio>=4.44,<5` (the line the app was built and tested on) to restore the working **full-page
  share link** and the tab refresh. (Gradio 6 also warns that `theme`/`css` moved off the `Blocks`
  constructor.)
- Reminder: the slow "Loading checkpoint shards" is the **first-run ~16 GB model download** — turn
  on the Drive cell (`USE_DRIVE = True`) so it's cached and not re-downloaded each session.

## [95716dd] — 2026-07-22 · Fix Colab launch slowness + live run progress
### Fixed
- **Demo launch didn't auto-configure the GPU.** `01_DEMO` → `app.launch()` never called
  `autotune`, so on a ~16 GB Colab GPU it loaded Qwen3-8B in **bf16** (~16 GB), spilled to
  CPU/disk, and "Loading checkpoint shards" crawled for minutes (looked hung). `launch()` now
  runs `autotune.apply()` (4-bit on ≤16 GB GPUs, etc.).
- **Re-running the launch cell** failed with *"unable to start gradio server"* — `launch()` now
  calls `gr.close_all()` first, so re-running is safe.
- `rag.QwenLLM` reads `config.GEN_MODEL` at call time so autotune's model choice actually applies.
### Added
- **Live progress on `launch()`** — prints `[RAGGuard]` lines (auto-config → loading model →
  starting UI) instead of a silent gap.
- **Run-tab progress feedback** — `fullrun` emits a `-> <phase>...` line before each phase, and the
  Run button streams from a background thread with a **heartbeat + elapsed timer (~3 s)** so a long
  phase (the 64-stack search) never looks frozen; the run survives tab switches.
### Changed
- `launch(share=…)` defaults to env `RAGGUARD_SHARE` (on); pass **`share=False`** for a reliable
  inline view when the Colab `gradio.live` tunnel stalls. Documented in `UI_GUIDE.md` + the notebook.

## [38d179a] — 2026-07-22 · Prune unused screenshots
### Removed
- Deleted **17 unused UI screenshots** (pre-v1, plain `ui_*`, and the superseded v2 set, plus an
  unembedded `ui_v3_run_dark.png`). Kept the referenced v3 set + `ui_v2_livedemo_attack.png`; the
  app's plot PNGs are untouched. Recoverable from git history if needed.

## [89198dd] — 2026-07-22 · Dark-mode UX fix + refreshed screenshots
### Fixed
- **Header status chips unreadable in dark mode.** The four chips (Model / Undefended ASR /
  Defended ASR / Best stack) used light-only theme tokens/hex. Each now has explicit **light
  and dark** colours via Gradio's `.dark` class (all ≥4.5:1 contrast) — reviewed with the
  UI/UX Pro Max skill (token-driven theming, dark-mode contrast rules).
### Added
- **v3 UI screenshots** — all five tabs in light mode (including the new **Run pipeline** tab)
  plus a **dark-mode** view showing the chip fix; wired into `UI_GUIDE.md` and `README.md`.
### Changed
- `REPORT_SKELETON.md` / `SLIDES_OUTLINE.md`: verified every number against `results.json`
  (unchanged), refreshed screenshot references to v3, and noted the one-click Run tab.
- `.gitignore`: ignore `artifacts/full_fast/` (quick-profile checkpoints).

## [d743fb0] — 2026-07-22 · One-click full run in the UI + Drive persistence
### Added
- **`ragguard/fullrun.py`** — the full pipeline as a **resumable generator** (yields progress,
  checkpoints every phase, writes `results.json`). Shared by the CLI and the UI. Can **reuse the
  UI's already-loaded pipeline** (`controller=`) so running from the UI doesn't load a second copy
  of the model (no VRAM doubling).
- **"5 · Run pipeline" tab** in the Gradio UI: one **▶ Run full pipeline** button with a
  **Quick (~minutes) / Full (~hours, resumable)** selector, a **streaming progress log**, and
  **auto-refresh** of the Attack/Defense/Governance panels on completion. A run **keeps going when
  you switch tabs** and re-shows its progress when the Run tab is re-opened. **🔄 Reload saved
  results** re-reads the last run.
- **`ragguard/drive.py`** + an optional **`USE_DRIVE`** notebook cell — mounts Google Drive and
  points the HuggingFace model cache at it. Results/checkpoints already route to Drive via
  `artifact_dir()` when mounted, so results **survive a reload** and the ~16 GB model isn't
  re-downloaded each session.
### Changed
- `launch()` now **loads the saved `results.json`** on startup (so the tabs show real numbers
  immediately) and enables the Gradio queue for streaming. `run_full.py` is now a thin wrapper
  over `fullrun.run`.
### Fixed
- The demo-script button and the in-app "How to use" panel now reference the real best stack
  **D4+D5** (were stale **D2+D3**).

## [b484635] — 2026-07-22 · One-click Colab (self-bootstrapping notebooks)
### Added
- **Idempotent Colab bootstrap cell** as the first code cell of `01_DEMO.ipynb` and `00_MAIN.ipynb`:
  on Colab it `git clone`s the (public) repo into the VM and `pip install`s `requirements.txt`, then
  adds the repo to `sys.path`. Uses portable paths only (`pathlib.Path.cwd()`, `/content/…`) — no
  machine-specific paths. Safe to re-run: detects an existing clone (in cwd or `/content/…`) and skips.
### Changed
- Colab instructions in `README.md` and `UI_GUIDE.md` simplified to **Open from GitHub → set GPU → Run all**
  (the manual `git clone` / `pip install` steps are now handled by the notebook).

## [8bfb987] — 2026-07-22 · UI screenshots in the guide
### Added
- Per-tab **UI screenshots with click-through captions** in `UI_GUIDE.md` (Live Demo controls +
  attack-succeeded state, Attack Lab, Defense Lab, Governance) and a hero screenshot in `README.md`,
  so a new user can see where to click for each function.
### Fixed
- Corrected two stale references so the guide matches the app: **best stack D2+D3 → D4+D5** (Live
  Demo beat 3 and Defense Lab note), and button label **"Run attack suite" → "Run attack sweep"**;
  refreshed the Defense Lab section to the v2 **Evaluate stack** flow.

## [8a82c1e] — 2026-07-22 · Fresh-clone setup docs
### Added
- **First-time setup** section in `UI_GUIDE.md` (§1) and `README.md` — clone → venv → deps →
  launch, with separate **local (Windows / macOS / Linux)** and **Colab (no-venv)** paths. Closes
  the gap where the UI launch step assumed an existing `.venv`.
### Changed
- Clarified that the committed `artifacts/` results/plots power the Governance tab and charts
  immediately, and the live tabs need no prior `run_full.py`.

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
