"""Central configuration: model ids, sizes, paths, runtime dials.

Everything tunable lives here or in env vars so notebooks/agents never hardcode.
No heavy imports at module load; ``device()`` imports torch lazily.
"""
from __future__ import annotations

import os
import pathlib
import re

# --- Canary token contract (SHARED: canary generator, judge, and D4 must all agree) ---
# Format: CANARY-<4 uppercase alnum>-<TOPIC>, e.g. CANARY-7F3A-REFUND-OVERRIDE
CANARY_RE = re.compile(r"CANARY-[A-Z0-9]{4}-[A-Z0-9-]+")


def make_canary_token(slot_id: str, topic: str) -> str:
    """Build a canonical canary token. ``slot_id`` should be 4 uppercase alnum chars."""
    topic_clean = re.sub(r"[^A-Za-z0-9]+", "-", topic).strip("-").upper()
    return f"CANARY-{slot_id.upper()}-{topic_clean}"


# --- Verified Hugging Face model ids (checked live 21 Jul 2026) ---
GEN_MODEL = "Qwen/Qwen3-8B"   # aligned chat model (Qwen3 drops the -Instruct suffix); ~16GB bf16
EMB_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
GUARD_MODEL = "protectai/deberta-v3-base-prompt-injection-v2"

# --- Datasets ---
CORPUS_DATASET = "bitext/Bitext-customer-support-llm-chatbot-training-dataset"
INJECTION_DATASET = "deepset/prompt-injections"
JAILBREAK_DATASET = "jackhhao/jailbreak-classification"

# --- Sizes / reproducibility ---
SEED = 42
TOP_K = 4
CORPUS_SIZE = 8_000        # subsample of the 26.9k Bitext rows (under the 10k cap)
N_BENIGN_EVAL = 150        # held-out benign eval questions (utility + FRR)
N_CANARIES = 40            # planted confidential documents


def _env_flag(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


# FAST_MODE: small sample sizes for end-to-end validation (~minutes).
FAST_MODE = _env_flag("RAGGUARD_FAST", default=False)

# Attack cases generated per attack. Dial down for FAST_MODE / quick sweeps.
N_PER_ATTACK = int(os.environ.get("RAGGUARD_N", "8" if FAST_MODE else "50"))

# Adaptive attacker: max mutation rounds per seed.
ADAPTIVE_ROUNDS = int(os.environ.get("RAGGUARD_ROUNDS", "3" if FAST_MODE else "6"))

# Two-stage defense-stack search.
SCREEN_N = int(os.environ.get("RAGGUARD_SCREEN_N", "6" if FAST_MODE else "15"))
CONFIRM_TOP = int(os.environ.get("RAGGUARD_CONFIRM_TOP", "5"))

# Benign-eval sizing: small during the cheap screen, full only for finalists.
SCREEN_BENIGN = int(os.environ.get("RAGGUARD_SCREEN_BENIGN", "8" if FAST_MODE else "20"))
# Batched generation + capped eval length (speed; ASR/utility unaffected in practice).
BATCH_SIZE = int(os.environ.get("RAGGUARD_BATCH", "8"))
EVAL_MAX_NEW_TOKENS = int(os.environ.get("RAGGUARD_MAXNEW", "128"))


def repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent


def artifact_dir() -> pathlib.Path:
    """Where indexes, caches and result tables are persisted.

    Priority: RAGGUARD_ARTIFACTS env var -> Google Drive (if mounted) -> ./artifacts
    """
    override = os.environ.get("RAGGUARD_ARTIFACTS")
    if override:
        base = pathlib.Path(override)
    else:
        drive = pathlib.Path("/content/drive/MyDrive/ragguard")
        base = drive if drive.parent.exists() else repo_root() / "artifacts"
    base.mkdir(parents=True, exist_ok=True)
    return base


def cache_dir() -> pathlib.Path:
    d = artifact_dir() / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def device() -> str:
    """Best available device string. Lazy torch import so tests don't need torch."""
    try:
        import torch  # type: ignore
        if torch.cuda.is_available():
            return "cuda"
        mps = getattr(torch.backends, "mps", None)
        if mps is not None and mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"
