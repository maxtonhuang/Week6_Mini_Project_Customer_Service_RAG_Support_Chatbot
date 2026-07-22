"""Launch the Gradio UI with the REAL Qwen3-8B pipeline, wired to the precomputed
results.json (so the Governance tab shows real numbers). Binds localhost so Playwright
can drive it. Auto-exits after a while to release VRAM.
"""
import json, os, time
from ragguard import config, corpus, prompts, rag
from ragguard import canary as cm
from ragguard.app import DemoController, build_app
from ragguard.attacks import build_all_attacks
from ragguard.defenses import build_all_defenses
from ragguard.judge import RuleJudge

from ragguard import autotune
autotune.apply()   # detect VRAM -> bf16 / 4-bit / smaller model (+ install bitsandbytes if needed)
print("building real pipeline...", flush=True)
docs, benign = corpus.build_knowledge_base()
canaries = [d for d in docs if d.is_canary()]
llm = rag.QwenLLM()
retr = rag.EmbeddingRetriever(docs)
pipe = rag.RagPipeline(retr, llm)
judge = RuleJudge(canary_tokens=cm.canary_tokens(canaries),
                  system_prompt_secrets=prompts.SYSTEM_PROMPT_SECRETS)
attacks = build_all_attacks(canary_docs=canaries)
defenses = build_all_defenses(system_prompt_secrets=prompts.SYSTEM_PROMPT_SECRETS)

res_path = config.artifact_dir() / "results.json"
results = json.loads(res_path.read_text(encoding="utf-8")) if res_path.exists() else {}
ctrl = DemoController(pipe, attacks, judge, defenses, canaries, benign, results=results)

app = build_app(ctrl)
app.launch(server_name="127.0.0.1", server_port=7860, share=False, prevent_thread_lock=True)
print("GRADIO_UP http://127.0.0.1:7860", flush=True)
keepalive = int(os.environ.get("RAGGUARD_UI_KEEPALIVE", "21600"))  # default 6h
time.sleep(keepalive)   # stay up for the user, then auto-release VRAM
print("shutting down", flush=True)
