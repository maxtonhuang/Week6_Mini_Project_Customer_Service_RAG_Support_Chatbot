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

# Supply-chain integrity: pin exact HF revisions (commit SHA / tag) rather than a bare id, so a
# swapped model/guardrail can't silently become a backdoor. None = latest (default). Recommended:
# set these to the commit SHAs you validated for the report run. Overridable via env.
GEN_REVISION = os.environ.get("RAGGUARD_GEN_REVISION") or None
EMB_REVISION = os.environ.get("RAGGUARD_EMB_REVISION") or None
GUARD_REVISION = os.environ.get("RAGGUARD_GUARD_REVISION") or None

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

# D8 rate limit: max queries per session before it starts blocking (deployment control).
RATE_BUDGET = int(os.environ.get("RAGGUARD_RATE_BUDGET", "12"))

# Benign-eval sizing: small during the cheap screen, full only for finalists.
SCREEN_BENIGN = int(os.environ.get("RAGGUARD_SCREEN_BENIGN", "8" if FAST_MODE else "20"))
# Batched generation + capped eval length (speed; ASR/utility unaffected in practice).
BATCH_SIZE = int(os.environ.get("RAGGUARD_BATCH", "4"))   # lower to 2/1 for small GPUs
# 4-bit weights (needs bitsandbytes) so the 8B fits a GPU under ~16 GB.
LOAD_IN_4BIT = _env_flag("RAGGUARD_4BIT", default=False)
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


# Committed view-artifacts a fresh clone ships (results + plots + tables). Copied into an
# empty active artifact_dir so the UI shows the shipped numbers even on Colab with an empty Drive.
_SEED_FILES = ("results.json", "governance.md")
_SEED_GLOBS = ("*.png", "*.csv")


def seed_artifacts_from_repo() -> bool:
    """Seed the active ``artifact_dir()`` from the repo's committed ``./artifacts`` when it has
    no ``results.json`` of its own.

    Fixes the Colab case where ``USE_DRIVE=True`` mounts Drive, so ``artifact_dir()`` points at
    an *empty* ``/content/drive/MyDrive/ragguard`` and the UI shows blank graphs even though the
    cloned repo's ``./artifacts`` holds the shipped results + plots. Copies them across once;
    a later real run still overwrites them (and persists to Drive). No-op locally (where the
    active dir already IS ``./artifacts``) or once the active dir has its own results. Returns
    True iff it copied anything.
    """
    import shutil
    dst = artifact_dir()
    src = repo_root() / "artifacts"
    if (dst / "results.json").exists():
        return False                      # active dir already has real results
    if dst.resolve() == src.resolve():
        return False                      # active dir IS the repo artifacts (local) — nothing to do
    if not (src / "results.json").exists():
        return False                      # nothing shipped to seed from
    copied = False
    for name in _SEED_FILES:
        f = src / name
        if f.exists():
            try:
                shutil.copy2(f, dst / f.name); copied = True
            except OSError:
                pass
    for pattern in _SEED_GLOBS:
        for f in src.glob(pattern):
            try:
                shutil.copy2(f, dst / f.name); copied = True
            except OSError:
                pass
    return copied


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
