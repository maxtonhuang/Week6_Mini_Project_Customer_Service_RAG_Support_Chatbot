#!/usr/bin/env python
"""Local GPU run for the light fingerprint prototype (4-bit / autotune).

Uses a real generator via ``ragguard.autotune`` (on ~8 GB that usually means
Qwen2.5-3B bf16, *or* force Qwen3-8B 4-bit — see flags below).

From repo root::

    # Autotune (recommended first)
    RAGGUARD_FAST=1 python prototypes/run_fingerprint_gpu.py

    # Force Qwen3-8B NF4 on an 8 GB card
    RAGGUARD_FAST=1 RAGGUARD_FORCE_8B_4BIT=1 python prototypes/run_fingerprint_gpu.py

Expect several minutes for model load + ~10 generations. Numbers are illustrative;
Max should re-run FULL bf16 for report tables.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("RAGGUARD_FAST", "1")


def main() -> None:
    t0 = time.time()
    from ragguard import autotune, config as C, corpus, prompts, rag
    from ragguard.cache import CachedLLM

    from prototypes.fingerprint_light import (
        FingerprintOutputFilter,
        build_fingerprint_bank,
        fingerprint_docs,
        run_ownership_check,
        save_report,
    )

    plan = autotune.apply()
    # Optional override: keep the 8B victim in 4-bit even on 6–10 GB cards.
    if os.environ.get("RAGGUARD_FORCE_8B_4BIT", "").strip().lower() in ("1", "true", "yes", "on"):
        C.GEN_MODEL = "Qwen/Qwen3-8B"
        C.LOAD_IN_4BIT = True
        C.BATCH_SIZE = 1
        print("[fingerprint] forcing Qwen3-8B 4-bit", flush=True)

    # Smaller KB for local embed speed (does not affect Max's committed artefacts).
    if C.LOAD_IN_4BIT or "3B" in C.GEN_MODEL:
        C.CORPUS_SIZE = int(os.environ.get("RAGGUARD_CORPUS_SIZE", "1500"))

    keys = build_fingerprint_bank(n=int(os.environ.get("RAGGUARD_FP_N", "5")), seed=C.SEED)
    plants = fingerprint_docs(keys)

    print(f"[{time.time()-t0:.0f}s] building KBs (corpus={C.CORPUS_SIZE}, plants={len(plants)})...",
          flush=True)
    public_canaries, _benign = corpus.build_knowledge_base(seed=C.SEED)
    victim_docs = list(public_canaries) + plants
    innocent_docs = list(public_canaries)  # same index, no ownership plants

    print(f"[{time.time()-t0:.0f}s] loading {C.GEN_MODEL} (4bit={C.LOAD_IN_4BIT})...", flush=True)
    llm = CachedLLM(rag.QwenLLM(max_new_tokens=min(96, C.EVAL_MAX_NEW_TOKENS)))
    victim = rag.RagPipeline(
        rag.EmbeddingRetriever(victim_docs), llm, system_prompt=prompts.SYSTEM_PROMPT)
    # Share the same weights; only the retriever / index differs.
    innocent = rag.RagPipeline(
        rag.EmbeddingRetriever(innocent_docs), llm, system_prompt=prompts.SYSTEM_PROMPT)

    print(f"[{time.time()-t0:.0f}s] probing {len(keys)} fingerprint keys...", flush=True)
    report = run_ownership_check(victim, innocent, keys=keys)
    print(f"victim KRR   = {report.victim_krr:.0%}  ({report.victim_hits}/{report.n_keys})")
    print(f"innocent KRR = {report.innocent_krr:.0%}  ({report.innocent_hits}/{report.n_keys})")
    print(f"separation   = {report.separation:+.0%}")

    d7 = FingerprintOutputFilter(phrases=[k.expected_phrase for k in keys])
    blocked = 0
    for k in keys:
        r = victim.answer(k.trigger_query, defenses=[d7])
        if r.blocked or (k.expected_phrase not in (r.answer or "")):
            blocked += 1
    print(f"D7 public-API blocks/suppresses = {blocked}/{len(keys)}")

    out = C.artifact_dir() / "fingerprint_light_gpu.json"
    save_report(report, out)
    print(f"[{time.time()-t0:.0f}s] wrote {out}")
    print(f"autotune plan was: {plan['reason']}")
    print("NOTE: local GPU numbers are illustrative — use Max FULL bf16 for the report.")


if __name__ == "__main__":
    main()
