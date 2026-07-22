# RAGGuard — Agentic Red-Team / Blue-Team Pipeline for a Customer-Service RAG Chatbot

Trustworthy AI mini-project. We build a deliberately-vulnerable customer-support RAG
chatbot, **attack** it with an agentic suite, **defend** it, and measure the
accuracy–robustness tradeoff. See [`MINI_PROJECT_PLAN.md`](./MINI_PROJECT_PLAN.md) for
the full plan, rubric mapping, and threat model.

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
  attacks/         # A1-A6 static attacks + A7 adaptive attacker agent
  defenses/        # D1-D6 defenses (3 hook points)
  orchestrator.py  # attack x defense sweep, two-stage stack search, Pareto selection
  governance.py    # NIST AI RMF scorecard (baseline vs defended)
  report.py        # tables & plots
  app.py           # Gradio UI (4 tabs)
```

## Design principle: models behind interfaces

The pipeline never imports a model directly — it depends on the `LLM` / `Retriever`
protocols. The real Qwen/FAISS classes implement them on Colab; the lightweight
`ScriptedLLM` / `KeywordRetriever` doubles implement them offline. This means the
**entire** attack→defense→judge→orchestrator logic can be run and tested without a GPU
or any heavy dependency.

## Running

### With real models (Colab or a local GPU)
1. Clone/upload this folder; open `00_MAIN.ipynb` (on Colab set the runtime to a GPU).
2. `pip install -r requirements.txt`. For a **local NVIDIA GPU** also install a CUDA build
   of torch, e.g. `pip install torch --index-url https://download.pytorch.org/whl/cu128`.
3. Run all. The first cell **auto-detects your GPU's VRAM** and picks the best path —
   full bf16, 4-bit, or a smaller model — installing `bitsandbytes` automatically if a
   4-bit path is chosen. It prints its choice (`model=… 4bit=… batch=…`). No manual setup.
4. `FAST=True` validates the whole pipeline in minutes; `FAST=False` produces the report numbers.
5. `01_DEMO.ipynb` (or `python serve_app.py`) launches the Gradio UI from the cached artefacts.

**GPU auto-configuration (handled for you by `ragguard.autotune`):**

| Detected VRAM | Path chosen |
|---|---|
| ≥ 30 GB (RTX 5090, A100) | Qwen3-8B bf16, batch 4 |
| 20–30 GB (L4 24 GB, 3090/4090) | Qwen3-8B bf16, sequential |
| 10–20 GB (RTX 5070 12 GB, 4080) | Qwen3-8B **4-bit** (auto-installs bitsandbytes) |
| 6–10 GB | Qwen2.5-3B bf16 |
| < 6 GB / no GPU | Qwen2.5-3B 4-bit / 0.5B on CPU |

Batched generation also **backs off automatically on CUDA OOM** (batch → sequential), so it
degrades in speed rather than crashing. Override any choice with the env vars below.

**Using the UI:** see [`UI_GUIDE.md`](./UI_GUIDE.md) for a new-user walkthrough (the four-beat demo, what each control does, how to read the verdict badges). There's also an "ℹ️ How to use" panel inside the Live Demo tab itself.

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
