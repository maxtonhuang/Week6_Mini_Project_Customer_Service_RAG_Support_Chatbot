"""GPU smoke test: download Qwen3-8B, build the REAL pipeline, and confirm the core
attack/defense loop works end-to-end on the 5090. Run with the venv python.
"""
import os, sys, time
os.environ.setdefault("RAGGUARD_FAST", "1")

def log(msg):
    print(msg, flush=True)

t0 = time.time()
from ragguard import corpus, rag, prompts, metrics, orchestrator
from ragguard import canary as cm
from ragguard.judge import RuleJudge
from ragguard.attacks import build_all_attacks
from ragguard.defenses import build_all_defenses
import torch
log(f"[{time.time()-t0:.0f}s] imports done | CUDA={torch.cuda.is_available()} {torch.cuda.get_device_name(0)}")

t = time.time()
docs, benign = corpus.build_knowledge_base()
canaries = [d for d in docs if d.is_canary()]
log(f"[{time.time()-t:.0f}s] KB: {len(docs)} docs ({len(canaries)} canaries), benign eval {len(benign)}")

t = time.time()
llm = rag.QwenLLM()          # <-- downloads Qwen3-8B on first run
log(f"[{time.time()-t:.0f}s] Qwen3-8B loaded on {llm.device}")
retr = rag.EmbeddingRetriever(docs)
pipe = rag.RagPipeline(retr, llm)
log(f"[{time.time()-t:.0f}s] retriever + pipeline ready")

# --- benign sanity ---
t = time.time()
r = pipe.answer("How long do I have to return an item?")
log(f"\n[BENIGN {time.time()-t:.1f}s] {r.answer[:400]}")
log(f"  retrieved: {[d.doc_id for d in r.retrieved]}")

# --- attack/defense on the real model ---
judge = RuleJudge(canary_tokens=cm.canary_tokens(canaries),
                  system_prompt_secrets=prompts.SYSTEM_PROMPT_SECRETS)
attacks = build_all_attacks(canary_docs=canaries)
defenses = build_all_defenses(system_prompt_secrets=prompts.SYSTEM_PROMPT_SECRETS)

for aid in ("A4", "A5", "A1"):
    atk = next(a for a in attacks if a.id == aid)
    t = time.time()
    und = orchestrator.run_suite(pipe, [atk], judge, defenses=None, n=3)
    dfd = orchestrator.run_suite(pipe, [atk], judge, defenses=defenses, n=3)
    log(f"\n[{aid} {time.time()-t:.0f}s] ASR undefended={metrics.asr(und):.0%} -> defended={metrics.asr(dfd):.0%}")
    log(f"  undefended example: success={und[0].success} reason={und[0].reason!r}")
    log(f"  undefended answer:  {und[0].meta}")

log(f"\n[TOTAL {time.time()-t0:.0f}s] smoke complete")
