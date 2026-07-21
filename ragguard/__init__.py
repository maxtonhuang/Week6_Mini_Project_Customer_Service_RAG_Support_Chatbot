"""RAGGuard — an agentic red-team / blue-team pipeline for a customer-service RAG bot.

Only light modules are re-exported here so ``import ragguard`` never pulls torch.
"""
from __future__ import annotations

from . import config
from .interfaces import LLM, Attack, Defense, Judge, Pipeline, Retriever
from .schemas import (
    Action,
    AttackCase,
    AttackGoal,
    Decision,
    Doc,
    JudgeVerdict,
    LAB_EVASION,
    LAB_EXTRACTION,
    LAB_LLM,
    LAB_POISONING,
    RagResponse,
    RunRecord,
    Visibility,
)

__version__ = "0.1.0"

__all__ = [
    "config",
    "LLM", "Retriever", "Pipeline", "Judge", "Attack", "Defense",
    "Doc", "Visibility", "AttackGoal", "AttackCase", "Action", "Decision",
    "RagResponse", "JudgeVerdict", "RunRecord",
    "LAB_LLM", "LAB_EXTRACTION", "LAB_POISONING", "LAB_EVASION",
    "__version__",
]
