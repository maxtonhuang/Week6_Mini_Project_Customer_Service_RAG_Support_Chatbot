"""The victim RAG pipeline plus concrete Qwen/FAISS backends.

`RagPipeline` is pure-Python orchestration and imports no heavy deps. `QwenLLM` and
`EmbeddingRetriever` import torch/transformers/sentence-transformers/faiss LAZILY, so
this module imports fine on a stdlib-only machine and is fully testable with the
`ragguard.testing` doubles.
"""
from __future__ import annotations

import time
from typing import Sequence

from . import config, prompts
from .corpus import build_knowledge_base
from .interfaces import LLM, Defense, Retriever
from .schemas import Action, Doc, RagResponse

__all__ = ["QwenLLM", "EmbeddingRetriever", "RagPipeline",
           "build_offline_pipeline", "build_pipeline"]


# ============================ concrete backends ============================

class QwenLLM:
    """Chat generation via a Qwen instruct model (transformers). Deterministic.
    For Qwen3 models, 'thinking' mode is disabled so the support bot answers directly."""

    def __init__(self, model_id: str | None = None, device: str | None = None,
                 max_new_tokens: int = 256, seed: int = config.SEED,
                 load_in_4bit: bool | None = None):
        import torch  # lazy
        from transformers import AutoModelForCausalLM, AutoTokenizer  # lazy

        if model_id is None:
            model_id = config.GEN_MODEL      # read at call time so autotune's model choice applies
        self.model_id = model_id
        self.max_new_tokens = max_new_tokens
        torch.manual_seed(seed)
        self.tokenizer = AutoTokenizer.from_pretrained(model_id)

        if load_in_4bit is None:
            load_in_4bit = config.LOAD_IN_4BIT
        if load_in_4bit:
            # 4-bit NF4: an 8B model fits in ~6-8 GB -> runs on a 12 GB GPU.
            # Requires bitsandbytes. Slightly lower quality; a bit slower per token.
            from transformers import BitsAndBytesConfig  # lazy
            qcfg = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                      bnb_4bit_compute_dtype=torch.bfloat16,
                                      bnb_4bit_use_double_quant=True)
            self.model = AutoModelForCausalLM.from_pretrained(
                model_id, quantization_config=qcfg, device_map={"": 0},
                torch_dtype=torch.bfloat16)
            self.device = next(self.model.parameters()).device
        else:
            self.device = device or config.device()
            self.model = AutoModelForCausalLM.from_pretrained(
                model_id, torch_dtype="auto").to(self.device)
        self.model.eval()
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

    def _decode_new(self, output_ids, input_len: int) -> str:
        return self.tokenizer.decode(output_ids[input_len:], skip_special_tokens=True).strip()

    def generate(self, messages: list[dict], **kw) -> str:
        import re  # lazy stdlib
        import torch  # lazy
        tmpl_kw = {}
        if "qwen3" in self.model_id.lower():
            tmpl_kw["enable_thinking"] = False   # direct answers, no <think> traces
        text = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True, **tmpl_kw
        )
        inputs = self.tokenizer(text, return_tensors="pt").to(self.device)
        with torch.no_grad():
            out = self.model.generate(
                **inputs, max_new_tokens=kw.get("max_new_tokens", self.max_new_tokens),
                do_sample=False, pad_token_id=self.tokenizer.pad_token_id,
            )
        ans = self._decode_new(out[0], inputs["input_ids"].shape[1])
        # Defensive: strip any residual thinking block.
        return re.sub(r"<think>.*?</think>", "", ans, flags=re.DOTALL).strip()

    def generate_batch(self, batch: list[list[dict]], **kw) -> list[str]:
        """Padded-batch generation (left-padding) in chunks, for throughput.

        OOM-resilient: if a chunk runs out of GPU memory it is retried at half the
        batch size (down to 1 = sequential), so it degrades in speed rather than
        crashing on smaller GPUs.
        """
        import re  # lazy stdlib
        import torch  # lazy
        if not batch:
            return []
        bs = int(kw.get("batch_size", getattr(config, "BATCH_SIZE", 4)))
        mnt = kw.get("max_new_tokens", self.max_new_tokens)
        tmpl_kw = {"enable_thinking": False} if "qwen3" in self.model_id.lower() else {}
        self.tokenizer.padding_side = "left"   # required for decoder-only batch generation

        def _run(chunk: list[list[dict]]) -> list[str]:
            texts = [self.tokenizer.apply_chat_template(
                m, tokenize=False, add_generation_prompt=True, **tmpl_kw) for m in chunk]
            inputs = self.tokenizer(texts, return_tensors="pt", padding=True).to(self.device)
            with torch.no_grad():
                out = self.model.generate(
                    **inputs, max_new_tokens=mnt, do_sample=False,
                    pad_token_id=self.tokenizer.pad_token_id,
                )
            in_len = inputs["input_ids"].shape[1]
            outs = []
            for row in out:
                text = self.tokenizer.decode(row[in_len:], skip_special_tokens=True).strip()
                outs.append(re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip())
            return outs

        results: list[str] = []
        i = 0
        cur_bs = max(1, bs)
        while i < len(batch):
            chunk = batch[i:i + cur_bs]
            try:
                results.extend(_run(chunk))
                i += cur_bs
            except torch.cuda.OutOfMemoryError:
                torch.cuda.empty_cache()
                if cur_bs == 1:
                    raise                      # a single prompt won't fit — genuinely OOM
                cur_bs = max(1, cur_bs // 2)   # back off and retry this chunk smaller
        return results


class EmbeddingRetriever:
    """Dense retriever: all-MiniLM-L6-v2 embeddings + FAISS IndexFlatIP (cosine)."""

    def __init__(self, docs: list[Doc], model_id: str = config.EMB_MODEL,
                 device: str | None = None):
        import faiss  # lazy
        import numpy as np  # lazy
        from sentence_transformers import SentenceTransformer  # lazy

        self.docs = list(docs)
        self.model_id = model_id
        self.encoder = SentenceTransformer(model_id, device=device or config.device())
        emb = self.encoder.encode(
            [d.text for d in self.docs], convert_to_numpy=True,
            normalize_embeddings=True, show_progress_bar=False,
        ).astype(np.float32)
        self.index = faiss.IndexFlatIP(emb.shape[1])
        self.index.add(emb)

    def search(self, query: str, k: int = config.TOP_K) -> list[Doc]:
        import numpy as np  # lazy
        k = min(k, len(self.docs))
        if k == 0:
            return []
        q = self.encoder.encode([query], convert_to_numpy=True,
                                 normalize_embeddings=True).astype(np.float32)
        scores, idx = self.index.search(q, k)
        return [self.docs[i].with_score(float(s)) for s, i in zip(scores[0], idx[0]) if i >= 0]


# ============================== the pipeline ==============================

class RagPipeline:
    """The victim RAG system. Implements the ``Pipeline`` protocol."""

    def __init__(self, retriever: Retriever, llm: LLM,
                 system_prompt: str = prompts.SYSTEM_PROMPT,
                 defenses: Sequence[Defense] = (), top_k: int = config.TOP_K,
                 refusal: str = prompts.REFUSAL):
        self.retriever = retriever
        self.llm = llm
        self.system_prompt = system_prompt
        self.defenses: list[Defense] = list(defenses)
        self.top_k = top_k
        self.refusal = refusal

    @staticmethod
    def _pre_order(active: list[Defense]) -> list[Defense]:
        """D6 (normalisation) must run before D2 (classifier) in the pre-retrieval phase."""
        return [d for d in active if getattr(d, "id", "") == "D6"] + \
               [d for d in active if getattr(d, "id", "") != "D6"]

    def _prepare(self, query: str, injected_docs, active: list[Defense]) -> dict:
        """Everything up to (but not including) the model call. Returns either
        {"short": RagResponse} for a pre-retrieval block, or the state + messages."""
        t0 = time.perf_counter()
        original = query
        q = query
        fired: list[str] = []

        # phase 1: pre-retrieval (D6 first)
        for d in self._pre_order(active):
            dec = d.pre_retrieval(q)
            if dec is None:
                continue
            if dec.action == Action.BLOCK:
                fired.append(d.id)
                resp = RagResponse(
                    query=original, answer=self.refusal, retrieved=[], blocked=True,
                    block_reason=dec.reason or f"blocked by {d.id}",
                    fired_defenses=_dedupe(fired), latency_s=time.perf_counter() - t0,
                    meta={"phase": "pre_retrieval", "query_used": q},
                )
                return {"short": resp}
            if dec.action == Action.REWRITE and dec.text and dec.text != q:
                q = dec.text
                fired.append(d.id)

        # phase 2: retrieve (+ inject poison into candidate pool)
        docs = list(self.retriever.search(q, self.top_k))
        injected = list(injected_docs or [])
        docs = docs + injected

        # phase 3: post-retrieval sanitisation
        for d in active:
            new = d.post_retrieval(q, docs)
            if list(new) != list(docs):
                fired.append(d.id)
            docs = new

        # phase 4: build prompt (system-prompt chain + context last-wins)
        sp = self.system_prompt
        for d in active:
            sp = d.transform_system_prompt(sp)
        ctx = None
        for d in active:
            c = d.format_context(docs)
            if c is not None:
                ctx = c
        if ctx is None:
            ctx = prompts.format_context(docs)

        messages = [
            {"role": "system", "content": sp},
            {"role": "user", "content": ctx + "\n\nUser question: " + q},
        ]
        return {"t0": t0, "original": original, "q": q, "docs": docs,
                "injected": injected, "fired": fired, "messages": messages}

    def _finalize(self, prep: dict, answer: str, active: list[Defense]) -> RagResponse:
        """Post-generation filtering + assemble the RagResponse."""
        q, docs = prep["q"], prep["docs"]
        fired = list(prep["fired"])
        blocked = False
        block_reason = ""
        for d in active:
            dec = d.post_generation(q, answer, docs)
            if dec is None:
                continue
            if dec.action == Action.BLOCK:
                answer = self.refusal
                blocked = True
                block_reason = dec.reason or f"blocked by {d.id}"
                fired.append(d.id)
                break
            if dec.action == Action.REDACT and dec.text != answer:
                answer = dec.text
                fired.append(d.id)
        return RagResponse(
            query=prep["original"], answer=answer, retrieved=docs, blocked=blocked,
            block_reason=block_reason, fired_defenses=_dedupe(fired),
            latency_s=time.perf_counter() - prep["t0"],
            meta={"query_used": q, "n_injected": len(prep["injected"])},
        )

    def answer(self, query: str, injected_docs: list[Doc] | None = None,
               defenses: Sequence[Defense] | None = None) -> RagResponse:
        active = list(defenses) if defenses is not None else list(self.defenses)
        prep = self._prepare(query, injected_docs, active)
        if "short" in prep:
            return prep["short"]
        ans = self.llm.generate(prep["messages"])
        return self._finalize(prep, ans, active)

    def answer_many(self, queries: list[str], injected_docs_list=None,
                    defenses: Sequence[Defense] | None = None) -> list[RagResponse]:
        """Batched equivalent of ``answer`` — same results, one batched model call for
        all queries that reach generation. Order-preserving."""
        active = list(defenses) if defenses is not None else list(self.defenses)
        inj = injected_docs_list if injected_docs_list is not None else [None] * len(queries)
        preps = [self._prepare(q, inj[i], active) for i, q in enumerate(queries)]
        gen_idx = [i for i, p in enumerate(preps) if "short" not in p]
        if gen_idx:
            outs = self.llm.generate_batch([preps[i]["messages"] for i in gen_idx])
            for i, o in zip(gen_idx, outs):
                preps[i]["_ans"] = o
        return [p["short"] if "short" in p else self._finalize(p, p["_ans"], active)
                for p in preps]


def _dedupe(xs: list[str]) -> list[str]:
    return list(dict.fromkeys(xs))


# ============================== builders ==============================

def build_offline_pipeline(seed: int = config.SEED, defenses: Sequence[Defense] = ()) -> RagPipeline:
    """Offline pipeline (ScriptedLLM + KeywordRetriever) over the real KB — for the
    offline demo and tests. No heavy deps."""
    from .testing import KeywordRetriever, ScriptedLLM
    docs, _ = build_knowledge_base(seed)
    return RagPipeline(KeywordRetriever(docs), ScriptedLLM(),
                       system_prompt=prompts.SYSTEM_PROMPT, defenses=defenses)


def build_pipeline(defenses: Sequence[Defense] = (), offline: bool = False,
                   seed: int = config.SEED) -> RagPipeline:
    """Full pipeline. ``offline=True`` uses the doubles; otherwise Qwen + FAISS (Colab)."""
    if offline:
        return build_offline_pipeline(seed=seed, defenses=defenses)
    docs, _ = build_knowledge_base(seed)
    return RagPipeline(EmbeddingRetriever(docs), QwenLLM(),
                       system_prompt=prompts.SYSTEM_PROMPT, defenses=defenses)
