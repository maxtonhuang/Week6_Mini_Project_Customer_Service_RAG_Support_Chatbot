"""Full evaluation run as a reusable **generator** — powers both ``run_full.py`` (CLI)
and the Gradio "Run pipeline" button.

``run(profile)`` yields human-readable progress lines while it works, and writes
``results.json`` + plots + resumable per-phase checkpoints to ``config.artifact_dir()``
(which auto-targets Google Drive when Drive is mounted). Because every phase is
checkpointed, a re-run resumes where a crash/disconnect left off.

It runs with the real Qwen pipeline when the heavy deps are importable, and falls back
to the offline test-doubles otherwise — so the whole flow is testable without a GPU.
"""
from __future__ import annotations
import dataclasses, importlib.util, json, time

import ragguard.config as C

# profile -> FAST_MODE flag + sample-size dials
PROFILES = {
    "quick": dict(fast=True,  n=8,  rounds=3, screen_n=6,  screen_benign=8),
    "full":  dict(fast=False, n=50, rounds=6, screen_n=15, screen_benign=20),
}


def _heavy_deps() -> bool:
    return all(importlib.util.find_spec(m) for m in
               ("torch", "transformers", "sentence_transformers", "faiss"))


def load_saved_results() -> dict:
    """Read the last run's results.json from the (possibly Drive-backed) artifact dir."""
    p = C.artifact_dir() / "results.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def run(profile: str = "quick", offline: bool | None = None, controller=None):
    """Generator. Runs the whole red-team/blue-team pipeline, yielding progress strings.

    Writes results.json (+ plots, CSVs, checkpoints) to config.artifact_dir().

    ``controller`` (the Gradio ``DemoController``) lets the UI **reuse its already-loaded
    pipeline** instead of loading a second copy of the model — avoiding VRAM doubling. The
    CLI passes no controller and builds its own (with the disk generation cache + HF prompts).
    """
    if profile not in PROFILES:
        profile = "quick"
    d = PROFILES[profile]
    C.FAST_MODE, C.N_PER_ATTACK = d["fast"], d["n"]
    C.ADAPTIVE_ROUNDS, C.SCREEN_N, C.SCREEN_BENIGN = d["rounds"], d["screen_n"], d["screen_benign"]

    if offline is None:
        offline = not _heavy_deps()

    t0 = time.time()
    def stamp(m): return f"[{time.time()-t0:6.0f}s] {m}"

    from ragguard import corpus, rag, prompts, metrics, orchestrator, report, governance
    from ragguard import canary as cm
    from ragguard.judge import RuleJudge
    from ragguard.attacks import (build_all_attacks, AdaptiveAttacker,
                                  HeuristicAttackerLLM, adaptive_asr_curve)
    from ragguard.defenses import build_all_defenses, SEARCH_DEFENSE_IDS
    from ragguard.schemas import RunRecord

    yield stamp(f"profile={profile} offline={offline} "
                f"(N={C.N_PER_ATTACK}, screen_n={C.SCREEN_N}, rounds={C.ADAPTIVE_ROUNDS})")

    if controller is None and not offline:
        from ragguard import autotune
        autotune.apply()
        yield stamp(f"autotuned: model={C.GEN_MODEL} 4bit={C.LOAD_IN_4BIT} batch={C.BATCH_SIZE}")

    ART = C.artifact_dir()
    CK = ART / ("full_fast" if C.FAST_MODE else "full")
    CK.mkdir(parents=True, exist_ok=True)
    MATRIX_N = min(20, C.N_PER_ATTACK)
    yield stamp(f"artifacts -> {ART}")

    def recs_to(rs): return [dataclasses.asdict(r) for r in rs]
    def recs_from(ds): return [RunRecord(**x) for x in ds]

    def checkpoint(name, fn):
        p = CK / f"{name}.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8")), True
        out = fn()
        p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        return out, False

    # ---------------- build (or reuse the UI's already-loaded pipeline) ----------------
    if controller is not None:
        pipe, attacks, judge = controller.pipeline, controller.attacks, controller.judge
        defenses, canaries, benign = controller.all_defenses, controller.canaries, controller.benign
        llm = getattr(pipe, "llm", None)                 # reuse the model the UI already loaded
        _save = getattr(llm, "save", lambda: None)
        yield stamp(f"reusing loaded pipeline | {len(attacks)} attacks, {len(defenses)} defences, "
                    f"{len(canaries)} canaries, benign {len(benign)}")
    else:
        docs, benign = corpus.build_knowledge_base()
        canaries = [x for x in docs if x.is_canary()]
        if offline:
            from ragguard.testing import ScriptedLLM, KeywordRetriever
            llm, retr, inj, jbk = ScriptedLLM(), KeywordRetriever(docs), None, None
        else:
            from ragguard.cache import CachedLLM
            from ragguard.attacks.base import load_hf_prompts
            llm = CachedLLM(rag.QwenLLM(max_new_tokens=C.EVAL_MAX_NEW_TOKENS),
                            path=ART / "gen_cache.json")
            retr = rag.EmbeddingRetriever(docs)
            try:
                inj = load_hf_prompts(C.INJECTION_DATASET, "train", "text", "label", 1)
                jbk = load_hf_prompts(C.JAILBREAK_DATASET, "train", "prompt", "type", "jailbreak")
            except Exception:
                inj = jbk = None
        _save = getattr(llm, "save", lambda: None)
        pipe = rag.RagPipeline(retr, llm)
        judge = RuleJudge(canary_tokens=cm.canary_tokens(canaries),
                          system_prompt_secrets=prompts.SYSTEM_PROMPT_SECRETS)
        attacks = build_all_attacks(canary_docs=canaries, injection_prompts=inj, jailbreak_prompts=jbk)
        defenses = build_all_defenses(system_prompt_secrets=prompts.SYSTEM_PROMPT_SECRETS)
        yield stamp(f"ready | KB {len(docs)} docs ({len(canaries)} canaries), benign {len(benign)}")

    # ---------------- phases ----------------
    yield stamp(f"-> undefended attack suite ({len(attacks)} attacks x N={C.N_PER_ATTACK})...")
    raw, hit = checkpoint("undefended",
        lambda: recs_to(orchestrator.run_suite(pipe, attacks, judge, defenses=None, n=C.N_PER_ATTACK)))
    undef = recs_from(raw); _save()
    yield stamp(f"undefended ASR {metrics.asr(undef):.0%}" + (" (resumed)" if hit else ""))

    yield stamp("-> full-stack attack suite (all defences on)...")
    raw, hit = checkpoint("fullstack",
        lambda: recs_to(orchestrator.run_suite(pipe, attacks, judge, defenses=defenses, n=C.N_PER_ATTACK)))
    full = recs_from(raw); _save()
    yield stamp(f"full-stack ASR {metrics.asr(full):.0%}" + (" (resumed)" if hit else ""))

    yield stamp(f"-> attack x defence matrix (N={MATRIX_N})...")
    raw, hit = checkpoint("matrix",
        lambda: recs_to(orchestrator.attack_defense_matrix(pipe, attacks, judge, defenses, n=MATRIX_N)))
    matrix = recs_from(raw); _save()
    yield stamp("attack x defence matrix done" + (" (resumed)" if hit else ""))

    # Exhaustive Pareto search over the original content filters D1-D6 (64 stacks). D7-D9 are
    # targeted/deployment controls (A8/A9/A10) evaluated in the full stack + labs, not searched.
    search_defenses = [d for d in defenses if d.id in SEARCH_DEFENSE_IDS]
    yield stamp("-> defence-stack search (screening all 64 D1-D6 stacks -- the long phase)...")
    search, hit = checkpoint("search",
        lambda: orchestrator.two_stage_search(pipe, attacks, judge, search_defenses, benign,
                                              screen_n=C.SCREEN_N, screen_benign=C.SCREEN_BENIGN,
                                              confirm_top=C.CONFIRM_TOP))
    _save()
    best = search["best"]
    best_ids = [i for i in best["stack"].split("+") if i and i != "none"]
    best_defs = [x for x in defenses if x.id in best_ids]
    yield stamp(f"BEST [{best['stack']}] robustness={best['robustness']:.0%} "
                f"utility={best['utility']:.2f} frr={best['frr']:.0%}")

    # Optuna threshold tuning of the best stack's continuous knobs
    _space = {}
    if "D2" in best_ids: _space["D2"] = (0.3, 0.9)
    if "D3" in best_ids: _space["D3_floor"] = (0.0, 0.5)
    if "D5" in best_ids: _space["D5"] = (0.05, 0.4)
    def _factory(params):
        alld = build_all_defenses(system_prompt_secrets=prompts.SYSTEM_PROMPT_SECRETS,
                                  thresholds=dict(params))
        return [x for x in alld if x.id in best_ids]
    if _space:
        yield stamp("-> Optuna threshold tuning (15 trials)...")
        try:
            tuned, hit = checkpoint("tuned", lambda: orchestrator.tune_thresholds(
                pipe, attacks, judge, _factory, benign, _space, n_trials=15, benign_k=C.SCREEN_BENIGN))
            yield stamp(f"Optuna tuned {best['stack']}: {tuned['best_params']}")
        except Exception as e:
            tuned = {"best_params": {}, "tuned_metrics": best, "note": f"tuning skipped: {e}"}
            yield stamp(f"Optuna skipped: {e}")
    else:
        tuned = {"best_params": {}, "tuned_metrics": best,
                 "note": f"stack {best['stack']} has no continuous thresholds to tune"}
        yield stamp(f"Optuna: {best['stack']} has no continuous thresholds")
    _save()

    # A7 adaptive attacker vs the best stack: LLM-driven + heuristic baseline
    def _adaptive():
        seeds = [c for aid in ("A1", "A2", "A5")
                 for c in next(a for a in attacks if a.id == aid).generate(3)]
        adv = AdaptiveAttacker(llm, rounds=C.ADAPTIVE_ROUNDS)
        recs_llm = adv.run(seeds, pipe, judge, defenses=best_defs)
        adv_h = AdaptiveAttacker(HeuristicAttackerLLM(), rounds=C.ADAPTIVE_ROUNDS)
        recs_h = adv_h.run(seeds, pipe, judge, defenses=best_defs)
        return {"vs_stack": best["stack"],
                "llm": {"records": recs_to(recs_llm), "curve": adaptive_asr_curve(recs_llm)},
                "heuristic": {"records": recs_to(recs_h), "curve": adaptive_asr_curve(recs_h)}}
    yield stamp(f"-> adaptive attacker ({C.ADAPTIVE_ROUNDS} rounds vs best stack)...")
    adaptive, hit = checkpoint("adaptive", _adaptive)
    _save()
    curve = adaptive["llm"]["curve"]
    yield stamp(f"adaptive vs {best['stack']} | LLM {[f'{x:.0%}' for x in curve]}")

    # ---------------- plots + governance + results ----------------
    try:
        report.asr_bar(undef, ART / "asr_undefended.png")
        report.attack_defense_heatmap(matrix, ART / "heatmap.png")
        report.pareto_plot(search["pareto"], ART / "pareto.png", knee=search.get("knee"))
        report.adaptive_curve_plot(curve, ART / "adaptive_curve.png")
        report.records_to_csv(undef, ART / "records_undefended.csv")
        report.records_to_csv(matrix, ART / "records_matrix.csv")
        yield stamp("plots + CSVs written")
    except Exception as e:
        yield stamp(f"WARN plots skipped ({e})")

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
        "elapsed_s": round(time.time() - t0, 1),
    }
    (ART / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    _save()

    gu = metrics.group_asr(undef, "attack_id"); gf = metrics.group_asr(full, "attack_id")
    yield stamp(f"DONE in {(time.time()-t0)/60:.1f} min — "
                f"undefended {metrics.asr(undef):.0%} -> full-stack {metrics.asr(full):.0%}, "
                f"best [{best['stack']}]")
    yield "  per-attack: " + " · ".join(f"{a} {gu[a]:.0%}->{gf.get(a,0):.0%}" for a in sorted(gu))
