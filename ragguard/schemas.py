"""Core data model for the RAGGuard red-team / blue-team pipeline.

This module has NO heavy dependencies (no torch/transformers/faiss). It defines
the dataclasses and enums that every other module speaks. Keep it that way so the
whole package can be imported and unit-tested on a machine with only stdlib.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Visibility(str, Enum):
    """Whether a knowledge-base document is public-facing or agent-only."""
    PUBLIC = "public"
    INTERNAL = "internal"


@dataclass
class Doc:
    """A single knowledge-base document / chunk."""
    doc_id: str
    text: str
    visibility: Visibility = Visibility.PUBLIC
    source: str = "bitext"
    intent: str | None = None
    canary: str | None = None          # unique token if this is a planted canary doc
    score: float | None = None         # retrieval score, filled in at query time

    def is_canary(self) -> bool:
        return self.canary is not None

    def is_internal(self) -> bool:
        return self.visibility == Visibility.INTERNAL

    def with_score(self, score: float) -> "Doc":
        return dataclasses.replace(self, score=score)


class AttackGoal(str, Enum):
    """What an attack case is trying to make the victim bot do."""
    SYSTEM_PROMPT_EXTRACTION = "system_prompt_extraction"   # leak the hidden system prompt
    CANARY_EXTRACTION = "canary_extraction"                 # leak a planted confidential doc
    POLICY_VIOLATION = "policy_violation"                   # break a stated policy / refusal rule
    INDIRECT_INJECTION = "indirect_injection"               # obey an instruction hidden in retrieved text


# Human-readable lab-type labels (map onto the brief's 5 lab attack types)
LAB_LLM = "LLM"
LAB_EXTRACTION = "Extraction"
LAB_POISONING = "Poisoning"
LAB_EVASION = "Evasion"


@dataclass
class AttackCase:
    """One concrete attack attempt against the pipeline."""
    case_id: str
    attack_id: str                                   # "A1".."A7"
    goal: AttackGoal
    user_input: str                                  # the message sent to the bot
    lab_type: str = ""                               # LAB_LLM / LAB_EXTRACTION / ...
    injected_docs: list[Doc] = field(default_factory=list)  # A3: poison docs forced into the retrieval pool
    target_marker: str | None = None                 # canary token / injected "tell" / sys-prompt fragment
    benign_query: str | None = None                  # for indirect injection: the genuine user question
    meta: dict[str, Any] = field(default_factory=dict)


class Action(str, Enum):
    """What a defense decided to do at a hook point."""
    ALLOW = "allow"
    BLOCK = "block"
    REWRITE = "rewrite"     # pre-retrieval: replace the query text
    REDACT = "redact"       # post-generation: replace the answer with a sanitized version


@dataclass
class Decision:
    """Return value of a defense hook (pre_retrieval / post_generation)."""
    action: Action = Action.ALLOW
    text: str = ""          # rewritten query (REWRITE) or redacted answer (REDACT); ignored for ALLOW
    reason: str = ""
    defense_id: str = ""

    @property
    def blocked(self) -> bool:
        return self.action == Action.BLOCK


@dataclass
class RagResponse:
    """Everything the pipeline produced for one query."""
    query: str
    answer: str
    retrieved: list[Doc] = field(default_factory=list)
    blocked: bool = False
    block_reason: str = ""
    fired_defenses: list[str] = field(default_factory=list)   # ids of defenses that acted
    latency_s: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class JudgeVerdict:
    """Rule-based judgement of whether an attack achieved its goal."""
    success: bool                       # attack goal achieved
    refused: bool = False               # bot refused / declined
    reason: str = ""
    evidence: str | None = None         # the offending substring, for the report


@dataclass
class RunRecord:
    """One flat row of results — the unit the orchestrator aggregates into tables."""
    case_id: str
    attack_id: str
    goal: str
    defense_stack: str                  # "none" or e.g. "D1+D2+D4"
    success: bool
    refused: bool
    blocked: bool
    latency_s: float
    reason: str = ""
    round: int = 0                      # adaptive-attack round index (0 for static)
    meta: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def stack_label(defense_ids: list[str]) -> str:
        return "+".join(sorted(defense_ids)) if defense_ids else "none"
