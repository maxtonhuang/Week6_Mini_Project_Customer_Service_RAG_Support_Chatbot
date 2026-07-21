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

### On Google Colab (real models — recommended)
1. Upload this folder (or clone), open `00_MAIN.ipynb`.
2. Runtime → change to a GPU (L4). `pip install -r requirements.txt`.
3. Run all. `FAST_MODE` validates the whole pipeline in ~8 min; the full run produces
   the report numbers. Artefacts persist to Drive.
4. `01_DEMO.ipynb` loads the cached artefacts and launches the Gradio UI in ~2 min.

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
- `RAGGUARD_ARTIFACTS=/path` — where indexes/results are persisted
