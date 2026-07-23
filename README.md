# RAGGuard — Agentic Red-Team / Blue-Team Pipeline for a Customer-Service RAG Chatbot

Trustworthy AI mini-project. We build a deliberately-vulnerable customer-support RAG
chatbot, **attack** it with an agentic suite, **defend** it, and measure the
accuracy–robustness tradeoff. See [`MINI_PROJECT_PLAN.md`](./MINI_PROJECT_PLAN.md) for
the full plan, rubric mapping, and threat model. Change history is in
[`CHANGELOG.md`](./CHANGELOG.md).

The suite covers **10 attacks** (A1–A6 + A8–A10, plus the A7 adaptive agent) across LLM/extraction/
poisoning/evasion + membership-inference & IP-fingerprinting, and **9 defenses** (D1–D9) at three
hook points — including **D7 visibility access-control** (fixes a real confidentiality gap), **D8**
rate-limiting, and **D9** semantic-leak/fingerprint filtering. Scope + architecture decisions for the
hardening pass are in [`HARDENING_DECISIONS.md`](./HARDENING_DECISIONS.md).

A **sophistication ladder** then sweeps attacks at three levels (**L0** blunt → **L1** one technique →
**L2** composed) against three defence levels (**D0** none → **D1** content filters → **D2**
defence-in-depth, adding controls D10 instruction-hierarchy + D11 decode-then-scan). The result — real
5090 numbers, overall ASR by (attack level × defence level): **L0 31/6/0% · L1 44/0/0% · L2 48/0/0%** —
shows smarter attacks raising ASR undefended and stronger defences driving it to 0% at no utility cost.
It's a phase of the full run (folded into `results.json`) and shown in the **Attack Lab** tab.

## Victim system

| Component | Model / tool |
|---|---|
| Generator | `Qwen/Qwen3-8B` (thinking mode disabled) |
| Embedder | `sentence-transformers/all-MiniLM-L6-v2` |
| Index | FAISS `IndexFlatIP` |
| Corpus | `bitext/Bitext-customer-support-llm-chatbot-training-dataset` + ~40 planted **canary** docs |

## Package layout

```
ragguard/
  schemas.py       # dataclasses & enums (Doc, AttackCase, Decision, RagResponse, RunRecord, ...)
  interfaces.py    # LLM / Retriever / Pipeline / Judge protocols; Attack / Defense base classes
  config.py        # model ids, sizes, paths, dials (FAST_MODE, N_PER_ATTACK), canary-token contract
  autotune.py      # detect GPU VRAM -> pick bf16 / 4-bit / smaller model; auto-install bitsandbytes
  cache.py         # CachedLLM — disk-backed generation cache (dedup + resume)
  testing.py       # offline test-doubles: ScriptedLLM, KeywordRetriever, tiny_corpus
  textnorm.py      # A6 obfuscation encoders <-> D6 normaliser (kept as inverses)
  metrics.py       # ASR / utility / FRR / Pareto frontier / knee point
  detect.py        # refusal detection, PII regexes, shared canary regex
  prompts.py       # victim system prompt (+ secrets), hardened prompt, context formatters
  canary.py        # planted confidential documents with unique canary tokens
  corpus.py        # load Bitext, subsample, build knowledge base + benign eval set
  rag.py           # QwenLLM, EmbeddingRetriever, RagPipeline
  judge.py         # RuleJudge — rule-based attack-success oracle
  attacks/         # A1-A6 + A8-A10 static attacks + A7 adaptive attacker agent
  defenses/        # D1-D9 defenses (3 hook points; D7 access-control, D8 rate-limit, D9 semantic-leak)
  fingerprint.py   # IP/ownership fingerprint bank (A9 / D9)
  orchestrator.py  # attack x defense sweep, two-stage stack search, Pareto selection
  governance.py    # NIST AI RMF scorecard (baseline vs defended)
  report.py        # tables & plots
  app.py           # Gradio UI (5 tabs: Live Demo · Attack Lab · Defense Lab · Governance · Run Pipeline)
```

## Design principle: models behind interfaces

The pipeline never imports a model directly — it depends on the `LLM` / `Retriever`
protocols. The real Qwen/FAISS classes implement them on Colab; the lightweight
`ScriptedLLM` / `KeywordRetriever` doubles implement them offline. This means the
**entire** attack→defense→judge→orchestrator logic can be run and tested without a GPU
or any heavy dependency.

## Running

### First-time setup (from a fresh clone)

Needs **Python 3.10–3.12** (not 3.13 — some GPU wheels lag on it). The first model run downloads
Qwen3-8B (~16 GB) + the embedder + corpus from HuggingFace, so the first time you also need
**internet + ~20 GB free disk** (cached afterwards; no HF token required).

**Local — Windows (PowerShell):**
```
git clone https://github.com/maxtonhuang/Week6_Mini_Project_Customer_Service_RAG_Support_Chatbot.git
cd Week6_Mini_Project_Customer_Service_RAG_Support_Chatbot
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install torch --index-url https://download.pytorch.org/whl/cu128   # GPU only; skip on CPU-only
```
**Local — macOS / Linux:** same, but `python3.12 -m venv .venv` then `source .venv/bin/activate`.

**Colab — nothing to install by hand.** In Colab: **File → Open notebook → GitHub**, paste this repo's
URL, and open **`01_DEMO.ipynb`** (UI) or **`00_MAIN.ipynb`** (full pipeline). Set **Runtime → Change
runtime type → GPU**, then **Runtime → Run all**. The notebook's first cell clones the repo into the VM
and installs the dependencies automatically — and it's safe to re-run (it detects an existing clone and
skips it).

### Run the notebook (real models)
1. Open `00_MAIN.ipynb` (on Colab set the runtime to a GPU).
2. Run all. The first cell **auto-detects the GPU's VRAM** and picks the best path —
   full bf16, 4-bit, or a smaller model — installing `bitsandbytes` automatically if a
   4-bit path is chosen. It prints its choice (`model=… 4bit=… batch=…`). No manual setup.
3. `FAST=True` validates the whole pipeline in minutes; `FAST=False` produces the report numbers.

### Launch the Gradio UI
- **Local:** `.venv\Scripts\python serve_app.py` (Windows) or `./.venv/bin/python serve_app.py` (macOS/Linux) → open **http://127.0.0.1:7860**.
- **Colab:** open `01_DEMO.ipynb` from the **GitHub** tab, set the runtime to GPU, **Run all** (the first cell self-clones + installs), then click the `…gradio.live` link it prints.

The results/plots are committed, so the Governance tab and charts show real numbers immediately; the
**Live Demo / Attack Lab / Defense Lab** tabs run the real pipeline live — no `run_full.py` needed first.

![RAGGuard Live Demo — an A1 direct-prompt-injection attack succeeding with no defences](artifacts/ui_v2_livedemo_attack.png)

*Live Demo tab: pick an attack (here **A1**), leave defences off, and **Ask** — the red **ATTACK SUCCEEDED** badge appears; tick **D4 + D5** and Ask again to see it **BLOCKED**. Full walkthrough with per-tab screenshots in [`UI_GUIDE.md`](./UI_GUIDE.md).*

**GPU auto-configuration (handled for you by `ragguard.autotune`):**

| Detected VRAM | Path chosen |
|---|---|
| ≥ 30 GB (high-VRAM GPU) | Qwen3-8B bf16, batch 4 |
| 20–30 GB (24 GB GPU, e.g. Colab L4) | Qwen3-8B bf16, sequential |
| 10–20 GB (12–16 GB GPU) | Qwen3-8B **4-bit** (auto-installs bitsandbytes) |
| 6–10 GB | Qwen2.5-3B bf16 |
| < 6 GB / no GPU | Qwen2.5-3B 4-bit / 0.5B on CPU |

Batched generation also **backs off automatically on CUDA OOM** (batch → sequential), so it
degrades in speed rather than crashing. Override any choice with the env vars below.

**Using the UI:** see [`UI_GUIDE.md`](./UI_GUIDE.md) for a new-user walkthrough (the four-beat demo, what each control does, how to read the verdict badges). There's also an "ℹ️ How to use" panel inside the Live Demo tab itself.

**Run everything from the UI:** the **5 · Run Pipeline** tab has a one-click run button whose label follows the profile — **▶ Run Quick pipeline** (~minutes) or **▶ Run Full pipeline** (~hours, resumable); a live log streams each phase, and when it finishes the Attack/Defense/Governance tabs refresh automatically. Every phase is checkpointed, so a re-run **resumes** from the last completed phase — if a run already finished it completes in seconds and the button reads **↻ Resume … (n/6 saved)**; tick **Start fresh** to recompute from scratch. A **⏹ Stop run** button cancels a run in progress without overwriting your saved results (it stops at the next phase/step boundary; completed phases stay checkpointed so you can resume). The run continues if you switch tabs (it re-shows when you come back), and it reuses the already-loaded model (no VRAM doubling) wrapped in a disk generation cache (`gen_cache.json`) so repeated prompts across runs aren't recomputed. On Colab, set `USE_DRIVE = True` (the optional Drive cell in the notebook) to persist results + the model cache to Google Drive so they survive a reload — the UI auto-loads the last saved results on startup.

![RAGGuard Run Pipeline tab — Quick/Full profile selector and a one-click run button](artifacts/ui_v3_run.png)

*The UI is **theme-aware** (light + dark). See [`UI_GUIDE.md`](./UI_GUIDE.md) for per-tab screenshots including a dark-mode view.*

### Offline logic tests (no network, no heavy deps)
```
python run_tests.py            # run every test with stdlib only
python run_tests.py test_rag   # run one module
```
On Colab you can instead use `pytest` (see `requirements.txt`).

## Tuning dials (env vars)
- `RAGGUARD_FAST=1` — small sample sizes for quick end-to-end validation
- `RAGGUARD_N=50` — attack cases per attack
- `RAGGUARD_4BIT=1` — force 4-bit quantization (for a < 16 GB GPU; needs bitsandbytes)
- `RAGGUARD_BATCH=2` — generation batch size (lower to 1 if you hit CUDA OOM)
- `RAGGUARD_ARTIFACTS=/path` — where indexes/results are persisted
