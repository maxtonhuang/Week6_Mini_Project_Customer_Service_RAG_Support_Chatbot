#!/usr/bin/env python
"""Generate 00_MAIN.ipynb and 01_DEMO.ipynb (valid nbformat v4 JSON, stdlib only).

Re-run this to regenerate the notebooks after code changes.
"""
from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n") + "\n"}


def code(text: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "execution_count": None,
            "outputs": [], "source": text.strip("\n") + "\n"}


def notebook(cells: list[dict]) -> dict:
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.11"},
            "colab": {"provenance": []},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


# ============================== 00_MAIN.ipynb ==============================
MAIN = [
    md("""
# 🛡️ RAGGuard — Main Pipeline (`00_MAIN.ipynb`)
**Trustworthy AI mini-project — Customer-service RAG chatbot: Evaluate → Attack → Defend.**

This notebook runs the whole graded pipeline end-to-end and produces every table/plot
for the report. Target: Colab with an L4 GPU. Set `FAST=True` for a ~8-min validation
run; `FAST=False` for the numbers that go in the report.
"""),
    code("""
# --- Colab setup (skip the pip line if running locally with deps installed) ---
import os, sys, pathlib
# If on Colab, upload/clone the project folder and point REPO at it:
REPO = pathlib.Path.cwd()
if (REPO / "ragguard").exists():
    sys.path.insert(0, str(REPO))
try:
    import google.colab  # noqa
    !pip -q install -r requirements.txt
    # from google.colab import drive; drive.mount('/content/drive')  # optional persistence
except ImportError:
    pass
print("repo:", REPO)
"""),
    code("""
# --- Auto-configure for THIS machine's GPU: picks bf16 / 4-bit / smaller model by VRAM
#     and pip-installs bitsandbytes only if a 4-bit path is chosen ---
from ragguard import autotune
autotune.apply()                 # sets GEN_MODEL / LOAD_IN_4BIT / BATCH_SIZE automatically

# --- Runtime dials (override autotune below if you want) ---
FAST = True                      # True = quick validation; False = full report run
import ragguard.config as C
C.N_PER_ATTACK   = 8  if FAST else 50
C.ADAPTIVE_ROUNDS= 3  if FAST else 6
C.SCREEN_N       = 6  if FAST else 15
# C.BATCH_SIZE = 2       # force a smaller batch if you still hit CUDA OOM
SEED = C.SEED
print(f"FAST={FAST}  model={C.GEN_MODEL}  4bit={C.LOAD_IN_4BIT}  batch={C.BATCH_SIZE}  device={C.device()}")
"""),
    md("## §1 — System build & threat model (Criterion 1)"),
    code("""
from ragguard import corpus, prompts, rag
from ragguard import canary as canary_mod

docs, benign = corpus.build_knowledge_base(seed=SEED)
canaries = [d for d in docs if d.is_canary()]
canary_mod.save_registry(canaries)
print(f"Knowledge base: {len(docs)} docs  ({len(canaries)} planted canaries)")
print(f"Benign eval set: {len(benign)} held-out Q&A")
print("Example canary token:", canaries[0].canary)
"""),
    code("""
# Build the victim RAG pipeline. Wrap the model in CachedLLM so the 64-stack search in
# §3 reuses generations instead of recomputing them (turns a ~hour into minutes).
from ragguard.cache import CachedLLM
llm = CachedLLM(rag.QwenLLM(max_new_tokens=C.EVAL_MAX_NEW_TOKENS))
retriever = rag.EmbeddingRetriever(docs)
pipe = rag.RagPipeline(retriever, llm)

# Sanity check: a benign question should get a helpful answer
resp = pipe.answer("How long do I have to return an item?")
print("A:", resp.answer)
print("retrieved:", [d.doc_id for d in resp.retrieved])
"""),
    code("""
# NIST AI RMF baseline scorecard (undefended system)
from ragguard import governance
from IPython.display import Markdown, display
baseline = governance.baseline_scorecard()
display(Markdown(governance.render_markdown(baseline)))
"""),
    md("## §2 — Attacks & evidence (Criterion 2)"),
    code("""
from ragguard.judge import RuleJudge
from ragguard.attacks import build_all_attacks
from ragguard.attacks.base import load_hf_prompts
from ragguard import orchestrator, metrics, report

# Optionally load real injection/jailbreak prompts from HF (falls back to built-ins offline)
inj = load_hf_prompts(C.INJECTION_DATASET, "train", "text", "label", 1)
jbk = load_hf_prompts(C.JAILBREAK_DATASET, "train", "prompt", "type", "jailbreak")

judge = RuleJudge(canary_tokens=canary_mod.canary_tokens(canaries),
                  system_prompt_secrets=prompts.SYSTEM_PROMPT_SECRETS)
attacks = build_all_attacks(canary_docs=canaries, injection_prompts=inj, jailbreak_prompts=jbk)

undef = orchestrator.run_suite(pipe, attacks, judge, defenses=None)
print(f"Undefended overall ASR = {metrics.asr(undef):.0%}")
for a, v in sorted(metrics.group_asr(undef, 'attack_id').items()):
    print(f"  {a}: {v:.0%}")
"""),
    code("""
# ASR bar chart + results table
report.asr_bar(undef, C.artifact_dir() / "asr_undefended.png")
print(report.results_table(undef)[:1500])
"""),
    code("""
# A7 — adaptive attacker agent (mutate-retry loop). Uses Qwen as the attacker on Colab.
from ragguard.attacks import AdaptiveAttacker, HeuristicAttackerLLM, adaptive_asr_curve
attacker = HeuristicAttackerLLM()     # swap for rag.QwenLLM() for an LLM-driven attacker
seeds = [c for atk in attacks for c in atk.generate(3)]
adv = AdaptiveAttacker(attacker, rounds=C.ADAPTIVE_ROUNDS)
adv_recs = adv.run(seeds, pipe, judge)
curve = adaptive_asr_curve(adv_recs)
print("Adaptive ASR by round:", [f"{x:.0%}" for x in curve])
report.adaptive_curve_plot(curve, C.artifact_dir() / "adaptive_curve.png")
"""),
    md("## §3 — Trustworthy AI design (Criterion 3)"),
    code("""
from ragguard.defenses import build_all_defenses
defenses = build_all_defenses(system_prompt_secrets=prompts.SYSTEM_PROMPT_SECRETS)

# Attack x defense matrix -> heatmap
matrix = orchestrator.attack_defense_matrix(pipe, attacks, judge, defenses)
report.attack_defense_heatmap(matrix, C.artifact_dir() / "heatmap.png")
print(f"Full-stack ASR = {metrics.asr([r for r in matrix if '+' in r.defense_stack]):.0%}")
"""),
    code("""
# Two-stage search over all 64 defense stacks -> best tradeoff
search = orchestrator.two_stage_search(pipe, attacks, judge, defenses, benign)
best = search['best']
print(f"BEST STACK: [{best['stack']}]  robustness={best['robustness']:.0%} "
      f"utility={best['utility']:.2f} FRR={best['frr']:.0%}")
report.pareto_plot(search['pareto'], C.artifact_dir() / "pareto.png", knee=search['knee'])
"""),
    code("""
# NIST AI RMF re-score (defended) + before/after comparison
undef_asr = metrics.asr(undef)
defended = governance.defended_scorecard({
    "baseline_asr": undef_asr, "defended_asr": best['asr'],
    "best_stack": best['stack'], "frr": best['frr']})
display(Markdown(governance.compare(baseline, defended)))
"""),
    md("## §4 — Persist artefacts (for `01_DEMO.ipynb` and the report)"),
    code("""
import json
results = {
    "baseline_asr": metrics.asr(undef),
    "defended_asr": best['asr'],
    "best_stack": best['stack'],
    "frr": best['frr'],
    "utility": best['utility'],
    "asr_by_attack": metrics.group_asr(undef, 'attack_id'),
    "adaptive_curve": curve,
    "pareto": [list(p) for p in search['pareto']],
}
(C.artifact_dir() / "results.json").write_text(json.dumps(results, indent=2))
report.records_to_csv(undef, C.artifact_dir() / "records_undefended.csv")
report.records_to_csv(matrix, C.artifact_dir() / "records_matrix.csv")
print("Saved artefacts to", C.artifact_dir())
"""),
]

# ============================== 01_DEMO.ipynb ==============================
DEMO = [
    md("""
# 🎬 RAGGuard — Live Demo (`01_DEMO.ipynb`)
Loads the built system and launches the **Gradio UI** for the presentation.
Run `00_MAIN.ipynb` first (it persists the results this reads). Read-only: it
does not recompute the heavy sweeps.
"""),
    code("""
import os, sys, pathlib
REPO = pathlib.Path.cwd()
if (REPO / "ragguard").exists():
    sys.path.insert(0, str(REPO))
try:
    import google.colab  # noqa
    !pip -q install -r requirements.txt
except ImportError:
    pass
"""),
    code("""
# Launch the UI. offline=None auto-detects: real models if installed, else the
# lightweight offline doubles (so the UI always runs).
from ragguard.app import launch
launch(share=True)
"""),
]

for name, cells in [("00_MAIN.ipynb", MAIN), ("01_DEMO.ipynb", DEMO)]:
    path = ROOT / name
    path.write_text(json.dumps(notebook(cells), indent=1), encoding="utf-8")
    # validate round-trips as JSON
    json.loads(path.read_text(encoding="utf-8"))
    print(f"wrote {name}  ({len(cells)} cells)")
