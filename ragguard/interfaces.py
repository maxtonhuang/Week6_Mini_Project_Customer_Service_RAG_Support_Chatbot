"""Interfaces (protocols + base classes) that decouple the pipeline from concrete
models. Concrete LLMs/retrievers (Qwen, FAISS) implement these on Colab; lightweight
test-doubles in ``ragguard.testing`` implement them offline.

NO heavy imports here. Concrete implementations import torch/transformers lazily.
"""
from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from .schemas import (
    Action,
    AttackCase,
    AttackGoal,
    Decision,
    Doc,
    JudgeVerdict,
    RagResponse,
)

Message = dict          # {"role": "system"|"user"|"assistant", "content": str}


@runtime_checkable
class LLM(Protocol):
    """A chat language model."""
    def generate(self, messages: list[Message], **kw) -> str: ...
    def generate_batch(self, batch: list[list[Message]], **kw) -> list[str]: ...


@runtime_checkable
class Retriever(Protocol):
    """Dense/keyword retriever over the knowledge base."""
    def search(self, query: str, k: int = 4) -> list[Doc]: ...


@runtime_checkable
class Pipeline(Protocol):
    """The victim RAG system.

    Contract for ``answer``:
      * retrieve top-k docs for ``query``
      * append ``injected_docs`` to the candidate pool (models a poisoned KB / indirect injection)
      * apply the given ``defenses`` (or ``self.defenses`` if None) in three phases:
          pre_retrieval  -> may BLOCK or REWRITE the query
          post_retrieval -> may filter/sanitize the doc list
          post_generation-> may BLOCK or REDACT the answer
      * return a fully-populated RagResponse
    Passing ``defenses`` per-call lets the orchestrator sweep stacks without rebuilding.
    """
    system_prompt: str
    def answer(
        self,
        query: str,
        injected_docs: list[Doc] | None = None,
        defenses: "Sequence[Defense] | None" = None,
    ) -> RagResponse: ...


@runtime_checkable
class Judge(Protocol):
    """Rule-based oracle: did this response satisfy the attack's goal?"""
    def verdict(self, case: AttackCase, resp: RagResponse) -> JudgeVerdict: ...


class Attack:
    """Base class for attacks. Subclasses set the class attributes and implement generate()."""
    id: str = "A?"
    name: str = "unnamed attack"
    goal: AttackGoal = AttackGoal.POLICY_VIOLATION
    lab_type: str = ""

    def generate(self, n: int) -> list[AttackCase]:
        """Produce up to ``n`` attack cases."""
        raise NotImplementedError


class Defense:
    """Base class for defenses. Override only the hooks you need; the rest pass through.

    Ordering note (enforced by the pipeline, not here): D6 (normalisation) must be
    registered before D2 (classifier) so the classifier sees decoded text.
    """
    id: str = "D?"
    name: str = "unnamed defense"

    def pre_retrieval(self, query: str) -> Decision:
        """Inspect/normalise/block the incoming query. Default: allow unchanged."""
        return Decision(action=Action.ALLOW, text=query, defense_id=self.id)

    def post_retrieval(self, query: str, docs: list[Doc]) -> list[Doc]:
        """Filter/sanitise retrieved docs. Default: identity."""
        return docs

    def post_generation(self, query: str, answer: str, docs: list[Doc]) -> Decision:
        """Inspect/redact/block the generated answer. Default: allow unchanged."""
        return Decision(text=answer, defense_id=self.id)

    def reset(self) -> None:
        """Reset any per-session state (e.g. D8's rate counter). Default: no-op.
        The pipeline calls this per case when ``reset_session=True`` so stateful defenses
        don't leak state across independent attack cases in the batched sweep."""
        return None

    # --- Prompt-construction hooks (used by D1 spotlighting) ---
    def transform_system_prompt(self, system_prompt: str) -> str:
        """Optionally harden/replace the system prompt. Default: unchanged.
        The pipeline chains this across all active defenses (in order)."""
        return system_prompt

    def format_context(self, docs: list[Doc]) -> str | None:
        """Optionally control how retrieved docs are rendered into the prompt
        (e.g. spotlighting delimiters). Return None to use the pipeline default;
        if several defenses return non-None, the pipeline uses the last one."""
        return None
