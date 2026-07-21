"""Bounded REAL pipeline run on Qwen3-8B (GPU). Produces the report artefacts:
per-attack ASR (undefended vs defended), attack x defense heatmap, a two-stage
defense search with Pareto/best-stack, an adaptive-attack curve, governance
scorecards, and a few real transcripts. Sized to finish in ~10-15 min on a 5090.
"""
import json, time
t0 = time.time()

import ragguard.config as C
C.N_PER_ATTACK = 4     # bounds the two-stage confirm stage

from ragguard import corpus, rag, prompts, metrics, orchestrator, report, governance
from ragguard import canary as cm
from ragguard.judge import RuleJudge
from ragguard.attacks import build_all_attacks, AdaptiveAttacker, HeuristicAttackerLLM, adaptive_asr_curve
from ragguard.attacks.base import load_hf_prompts
from ragguard.defenses import build_all_defenses

def log(m): print(f"[{time.time()-t0:6.0f}s] {m}", flush=True)

ART = C.artifact_dir()

# --- build system ---
docs, benign = corpus.build_knowledge_base()
canaries = [d for d in docs if d.is_canary()]
log(f"KB {len(docs)} docs ({len(canaries)} canaries), benign {len(benign)}")

llm = rag.QwenLLM()
retr = rag.EmbeddingRetriever(docs)
pipe = rag.RagPipeline(retr, llm)
log("pipeline ready (Qwen3-8B)")

# real injection / jailbreak prompt banks from HF (fall back to built-ins on error)
inj = load_hf_prompts(C.INJECTION_DATASET, "train", "text", "label", 1)
jbk = load_hf_prompts(C.JAILBREAK_DATASET, "train", "prompt", "type", "jailbreak")
log(f"attack prompt banks: {len(inj)} injection, {len(jbk)} jailbreak")

judge = RuleJudge(canary_tokens=cm.canary_tokens(canaries),
                  system_prompt_secrets=prompts.SYSTEM_PROMPT_SECRETS)
attacks = build_all_attacks(canary_docs=canaries, injection_prompts=inj, jailbreak_prompts=jbk)
defenses = build_all_defenses(system_prompt_secrets=prompts.SYSTEM_PROMPT_SECRETS)

# --- 1. undefended vs full-stack ASR ---
undef = orchestrator.run_suite(pipe, attacks, judge, defenses=None, n=5)
log(f"undefended overall ASR = {metrics.asr(undef):.0%}")
full = orchestrator.run_suite(pipe, attacks, judge, defenses=defenses, n=5)
log(f"full-stack ASR = {metrics.asr(full):.0%}")
report.asr_bar(undef, ART / "asr_undefended.png")

# --- 2. attack x defense heatmap ---
matrix = orchestrator.attack_defense_matrix(pipe, attacks, judge, defenses, n=3)
report.attack_defense_heatmap(matrix, ART / "heatmap.png")
log("heatmap saved")

# --- 3. two-stage defense search over a 4-defense space (16 subsets) ---
by_id = {d.id: d for d in defenses}
search_defs = [by_id[i] for i in ("D2", "D3", "D4", "D5")]
search = orchestrator.two_stage_search(pipe, attacks, judge, search_defs, benign[:6],
                                       screen_n=3, confirm_top=3)
best = search["best"]
log(f"BEST STACK [{best['stack']}] robustness={best['robustness']:.0%} "
    f"utility={best['utility']:.2f} frr={best['frr']:.0%}")
report.pareto_plot(search["pareto"], ART / "pareto.png", knee=search.get("knee"))

# --- 4. adaptive attacker curve ---
seeds = [c for aid in ("A1", "A2", "A4", "A5") for c in next(a for a in attacks if a.id == aid).generate(2)]
adv = AdaptiveAttacker(HeuristicAttackerLLM(), rounds=3)
adv_recs = adv.run(seeds, pipe, judge)
curve = adaptive_asr_curve(adv_recs)
log(f"adaptive ASR by round: {[f'{x:.0%}' for x in curve]}")
report.adaptive_curve_plot(curve, ART / "adaptive_curve.png")

# --- 5. governance scorecards ---
gov = governance.compare(governance.baseline_scorecard(),
                         governance.defended_scorecard({
                             "baseline_asr": metrics.asr(undef), "defended_asr": best["asr"],
                             "best_stack": best["stack"], "frr": best["frr"]}))
(ART / "governance.md").write_text(gov, encoding="utf-8")

# --- 6. a few real transcripts for the report/demo ---
def one(attack_id, defs):
    a = next(x for x in attacks if x.id == attack_id)
    case = a.generate(1)[0]
    r = pipe.answer(case.user_input, injected_docs=case.injected_docs, defenses=defs)
    return {"attack": attack_id, "input": case.user_input[:200], "answer": r.answer[:400],
            "blocked": r.blocked, "fired": r.fired_defenses}
transcripts = {
    "benign": {"input": "How long do I have to return an item?",
               "answer": pipe.answer("How long do I have to return an item?").answer[:400]},
    "A1_undefended": one("A1", None),
    "A1_defended": one("A1", defenses),
    "A5_undefended": one("A5", None),
    "A5_defended": one("A5", defenses),
}

# --- save everything ---
results = {
    "model": C.GEN_MODEL,
    "asr_undefended_overall": metrics.asr(undef),
    "asr_fullstack_overall": metrics.asr(full),
    "asr_by_attack_undefended": metrics.group_asr(undef, "attack_id"),
    "asr_by_attack_fullstack": metrics.group_asr(full, "attack_id"),
    "best_stack": best["stack"],
    "best": {k: best[k] for k in ("stack", "asr", "robustness", "utility", "frr", "overhead")},
    "baseline_asr": metrics.asr(undef),
    "defended_asr": best["asr"],
    "frr": best["frr"],
    "pareto": [list(p) for p in search["pareto"]],
    "adaptive_curve": curve,
    "transcripts": transcripts,
    "elapsed_s": round(time.time() - t0, 1),
}
(ART / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
report.records_to_csv(undef, ART / "records_undefended.csv")
report.records_to_csv(matrix, ART / "records_matrix.csv")

log(f"DONE. artefacts in {ART}")
print("\n===== HEADLINE =====")
print(f"Model: {C.GEN_MODEL}")
print(f"Undefended ASR {metrics.asr(undef):.0%} -> full-stack {metrics.asr(full):.0%}")
print("Per-attack (undef -> full):")
gu, gf = metrics.group_asr(undef, "attack_id"), metrics.group_asr(full, "attack_id")
for a in sorted(gu):
    print(f"  {a}: {gu[a]:.0%} -> {gf.get(a,0):.0%}")
print(f"Best stack [{best['stack']}] robustness={best['robustness']:.0%} utility={best['utility']:.2f} frr={best['frr']:.0%}")
print(f"Adaptive ASR by round: {[f'{x:.0%}' for x in curve]}")
