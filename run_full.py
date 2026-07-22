"""FULL evaluation run — optimised & resumable.

Optimisations vs the naive 8h run:
  * batched GPU generation (RagPipeline.answer_many)
  * disk-backed generation cache (CachedLLM) — dedups + survives restarts
  * two-stage search: cheap benign screen, FULL benign only for finalists
  * capped eval length (config.EVAL_MAX_NEW_TOKENS)

Every phase is checkpointed to artifacts/full[/ _fast]/<phase>.json — re-running skips
completed phases, so a crash/disconnect costs at most the current phase.
Set RAGGUARD_FAST=1 for a quick end-to-end sanity run (separate checkpoint dir).
"""
import dataclasses, json, time
t0 = time.time()

import ragguard.config as C
from ragguard import corpus, rag, prompts, metrics, orchestrator, report, governance
from ragguard import canary as cm
from ragguard.cache import CachedLLM
from ragguard.judge import RuleJudge
from ragguard.attacks import build_all_attacks, AdaptiveAttacker, HeuristicAttackerLLM, adaptive_asr_curve
from ragguard.attacks.base import load_hf_prompts
from ragguard.defenses import build_all_defenses
from ragguard.schemas import RunRecord
from ragguard import autotune

autotune.apply()   # detect VRAM -> bf16 / 4-bit / smaller model (+ install bitsandbytes if needed)

ART = C.artifact_dir()
CK = ART / ("full_fast" if C.FAST_MODE else "full")
CK.mkdir(parents=True, exist_ok=True)
MATRIX_N = min(20, C.N_PER_ATTACK)

def log(m): print(f"[{time.time()-t0:7.0f}s] {m}", flush=True)
def recs_to(rs): return [dataclasses.asdict(r) for r in rs]
def recs_from(ds): return [RunRecord(**d) for d in ds]

def checkpoint(name, fn):
    p = CK / f"{name}.json"
    if p.exists():
        log(f"resume: {name} (already done)")
        return json.loads(p.read_text(encoding="utf-8"))
    out = fn()
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"checkpoint saved: {name}")
    return out

# ---------------- build ----------------
docs, benign = corpus.build_knowledge_base()
canaries = [d for d in docs if d.is_canary()]
llm = CachedLLM(rag.QwenLLM(max_new_tokens=C.EVAL_MAX_NEW_TOKENS), path=ART / "gen_cache.json")
pipe = rag.RagPipeline(rag.EmbeddingRetriever(docs), llm)
inj = load_hf_prompts(C.INJECTION_DATASET, "train", "text", "label", 1)
jbk = load_hf_prompts(C.JAILBREAK_DATASET, "train", "prompt", "type", "jailbreak")
judge = RuleJudge(canary_tokens=cm.canary_tokens(canaries),
                  system_prompt_secrets=prompts.SYSTEM_PROMPT_SECRETS)
attacks = build_all_attacks(canary_docs=canaries, injection_prompts=inj, jailbreak_prompts=jbk)
defenses = build_all_defenses(system_prompt_secrets=prompts.SYSTEM_PROMPT_SECRETS)
log(f"ready | KB {len(docs)} docs ({len(canaries)} canaries), benign {len(benign)}, "
    f"N={C.N_PER_ATTACK} screen_n={C.SCREEN_N} screen_benign={C.SCREEN_BENIGN}")

# ---------------- phases ----------------
undef = recs_from(checkpoint("undefended",
        lambda: recs_to(orchestrator.run_suite(pipe, attacks, judge, defenses=None, n=C.N_PER_ATTACK))))
llm.save(); log(f"undefended ASR {metrics.asr(undef):.0%} | cache {llm.stats()}")

full = recs_from(checkpoint("fullstack",
        lambda: recs_to(orchestrator.run_suite(pipe, attacks, judge, defenses=defenses, n=C.N_PER_ATTACK))))
llm.save(); log(f"full-stack ASR {metrics.asr(full):.0%}")

matrix = recs_from(checkpoint("matrix",
        lambda: recs_to(orchestrator.attack_defense_matrix(pipe, attacks, judge, defenses, n=MATRIX_N))))
llm.save(); log("matrix done")

search = checkpoint("search",
        lambda: orchestrator.two_stage_search(pipe, attacks, judge, defenses, benign,
                                              screen_n=C.SCREEN_N, screen_benign=C.SCREEN_BENIGN,
                                              confirm_top=C.CONFIRM_TOP))
llm.save()
best = search["best"]
best_ids = [i for i in best["stack"].split("+") if i and i != "none"]
best_defs = [d for d in defenses if d.id in best_ids]
log(f"BEST [{best['stack']}] robustness={best['robustness']:.0%} "
    f"utility={best['utility']:.2f} frr={best['frr']:.0%} | cache {llm.stats()}")

# --- Optuna: tune the continuous thresholds of the best stack ---
_space = {}
if "D2" in best_ids: _space["D2"] = (0.3, 0.9)          # injection-classifier cutoff
if "D3" in best_ids: _space["D3_floor"] = (0.0, 0.5)    # retrieval similarity floor
if "D5" in best_ids: _space["D5"] = (0.05, 0.4)         # groundedness threshold
def _factory(params):
    alld = build_all_defenses(system_prompt_secrets=prompts.SYSTEM_PROMPT_SECRETS, thresholds=dict(params))
    return [d for d in alld if d.id in best_ids]
if _space:
    tuned = checkpoint("tuned", lambda: orchestrator.tune_thresholds(
        pipe, attacks, judge, _factory, benign, _space, n_trials=15, benign_k=C.SCREEN_BENIGN))
    log(f"Optuna tuned {best['stack']}: {tuned['best_params']} -> "
        f"ASR {tuned['tuned_metrics']['asr']:.0%} FRR {tuned['tuned_metrics']['frr']:.0%}")
else:
    tuned = {"best_params": {}, "tuned_metrics": best,
             "note": f"stack {best['stack']} has no continuous thresholds to tune"}
    log(f"Optuna: {best['stack']} has no continuous thresholds")
llm.save()

# --- A7 adaptive attacker vs the BEST defence stack: LLM-driven vs heuristic ---
def _adaptive():
    seeds = [c for aid in ("A1", "A2", "A5")
             for c in next(a for a in attacks if a.id == aid).generate(3)]
    adv_llm = AdaptiveAttacker(llm, rounds=C.ADAPTIVE_ROUNDS)          # real Qwen3-8B red-teams
    recs_llm = adv_llm.run(seeds, pipe, judge, defenses=best_defs)
    adv_h = AdaptiveAttacker(HeuristicAttackerLLM(), rounds=C.ADAPTIVE_ROUNDS)
    recs_h = adv_h.run(seeds, pipe, judge, defenses=best_defs)
    return {"vs_stack": best["stack"],
            "llm": {"records": recs_to(recs_llm), "curve": adaptive_asr_curve(recs_llm)},
            "heuristic": {"records": recs_to(recs_h), "curve": adaptive_asr_curve(recs_h)}}
adaptive = checkpoint("adaptive", _adaptive)
llm.save()
curve = adaptive["llm"]["curve"]
log(f"adaptive vs {best['stack']} | LLM {[f'{x:.0%}' for x in curve]} | "
    f"heuristic {[f'{x:.0%}' for x in adaptive['heuristic']['curve']]}")

# ---------------- plots + governance + results ----------------
report.asr_bar(undef, ART / "asr_undefended.png")
report.attack_defense_heatmap(matrix, ART / "heatmap.png")
report.pareto_plot(search["pareto"], ART / "pareto.png", knee=search.get("knee"))
report.adaptive_curve_plot(curve, ART / "adaptive_curve.png")
(ART / "governance.md").write_text(
    governance.compare(governance.baseline_scorecard(),
                       governance.defended_scorecard({
                           "baseline_asr": metrics.asr(undef), "defended_asr": best["asr"],
                           "best_stack": best["stack"], "frr": best["frr"]})),
    encoding="utf-8")

results = {
    "model": C.GEN_MODEL, "mode": "FAST" if C.FAST_MODE else "FULL",
    "asr_undefended_overall": metrics.asr(undef),
    "asr_fullstack_overall": metrics.asr(full),
    "asr_by_attack_undefended": metrics.group_asr(undef, "attack_id"),
    "asr_by_attack_fullstack": metrics.group_asr(full, "attack_id"),
    "best_stack": best["stack"], "best": best,
    "baseline_asr": metrics.asr(undef), "defended_asr": best["asr"], "frr": best["frr"],
    "pareto": [list(p) for p in search["pareto"]],
    "adaptive_curve": curve,
    "adaptive_vs_stack": adaptive["vs_stack"],
    "adaptive_curve_heuristic": adaptive["heuristic"]["curve"],
    "tuned_thresholds": tuned["best_params"],
    "tuned_metrics": tuned["tuned_metrics"],
    "n_stacks_screened": len(search["screened"]),
    "cache_stats": llm.stats(),
    "elapsed_s": round(time.time() - t0, 1),
}
(ART / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
report.records_to_csv(undef, ART / "records_undefended.csv")
report.records_to_csv(matrix, ART / "records_matrix.csv")
llm.save()

log(f"DONE in {(time.time()-t0)/60:.1f} min")
print("\n===== FULL RUN HEADLINE =====")
print(f"Model {C.GEN_MODEL} | mode {results['mode']} | {len(search['screened'])} stacks screened")
print(f"Undefended ASR {metrics.asr(undef):.0%} -> full-stack {metrics.asr(full):.0%}")
gu, gf = metrics.group_asr(undef, "attack_id"), metrics.group_asr(full, "attack_id")
for a in sorted(gu): print(f"  {a}: {gu[a]:.0%} -> {gf.get(a,0):.0%}")
print(f"Best stack [{best['stack']}] robustness={best['robustness']:.0%} "
      f"utility={best['utility']:.2f} frr={best['frr']:.0%}")
print(f"Optuna-tuned thresholds: {tuned['best_params']} -> "
      f"ASR {tuned['tuned_metrics']['asr']:.0%} FRR {tuned['tuned_metrics']['frr']:.0%}")
print(f"Adaptive vs [{best['stack']}]  LLM: {[f'{x:.0%}' for x in curve]}  "
      f"heuristic: {[f'{x:.0%}' for x in adaptive['heuristic']['curve']]}")
print(f"Cache: {llm.stats()}")
