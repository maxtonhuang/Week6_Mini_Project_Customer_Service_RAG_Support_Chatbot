"""Auto-detect GPU VRAM and pick the best generation path — full bf16, 4-bit, a smaller
victim model, or CPU — installing any extra package (bitsandbytes) only when needed.

Call ``autotune.apply()`` once before building the pipeline. It sets
``config.GEN_MODEL`` / ``config.LOAD_IN_4BIT`` / ``config.BATCH_SIZE`` accordingly.

Tiers (target victim is an ~8B model whose bf16 weights are ~16 GB):
    ≥30 GB : bf16, batch 8
    20-30  : bf16, batch 4
    10-20  : 4-bit (weights don't fit bf16), batch 4 (≥16) / 2  -> needs bitsandbytes
    6-10   : smaller victim (Qwen2.5-3B-Instruct) bf16, batch 2
    <6     : Qwen2.5-3B 4-bit, batch 1  -> needs bitsandbytes
    no GPU : tiny model on CPU (prefer the offline UI / Colab)
"""
from __future__ import annotations

from . import config

SMALL_MODEL = "Qwen/Qwen2.5-3B-Instruct"
TINY_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"


def vram_gb() -> float | None:
    """Total VRAM of GPU 0 in GB, or None if there is no CUDA GPU."""
    try:
        import torch  # lazy
        if not torch.cuda.is_available():
            return None
        return torch.cuda.get_device_properties(0).total_memory / 1e9
    except Exception:
        return None


def recommend(model_id: str | None = None, vram: float | None = None) -> dict:
    """Return a plan dict: {device, model_id, load_in_4bit, batch_size, needs, reason}.
    Pass ``vram`` (GB) to override detection (used in tests)."""
    model_id = model_id or config.GEN_MODEL
    if vram is None:
        vram = vram_gb()

    if vram is None:
        return {"device": "cpu", "model_id": TINY_MODEL, "load_in_4bit": False,
                "batch_size": 1, "needs": [],
                "reason": "no CUDA GPU -> tiny model on CPU (slow; prefer the offline UI or Colab)"}

    # Batch sizes are deliberately conservative: an 8B's KV cache over long RAG contexts
    # is large, and spilling into shared system RAM (silent, no OOM) is worse than a
    # smaller batch. Raise C.BATCH_SIZE manually if you have headroom.
    if vram >= 30:
        plan, why = dict(model_id=model_id, load_in_4bit=False, batch_size=4, needs=[]), "full bf16"
    elif vram >= 20:
        # 24 GB (e.g. L4) is tight for an 8B in bf16 -> sequential to stay safely under.
        # On Linux/Colab the OOM-backoff self-heals; 4-bit (RAGGUARD_4BIT=1) is faster if preferred.
        plan, why = dict(model_id=model_id, load_in_4bit=False, batch_size=1, needs=[]), "full bf16 (sequential)"
    elif vram >= 10:
        plan = dict(model_id=model_id, load_in_4bit=True, batch_size=2, needs=["bitsandbytes"])
        why = "4-bit (bf16 weights don't fit)"
    elif vram >= 6:
        plan, why = dict(model_id=SMALL_MODEL, load_in_4bit=False, batch_size=2, needs=[]), \
            f"smaller victim {SMALL_MODEL} in bf16"
    else:
        plan = dict(model_id=SMALL_MODEL, load_in_4bit=True, batch_size=1, needs=["bitsandbytes"])
        why = f"{SMALL_MODEL} in 4-bit (very tight)"

    plan["device"] = "cuda"
    plan["reason"] = f"{vram:.0f} GB VRAM -> {why}"
    return plan


def ensure_installed(pkgs, verbose: bool = True) -> list[str]:
    """pip-install any package in ``pkgs`` that isn't importable. Returns those installed.
    Failures warn (with a manual command) rather than raise."""
    import importlib.util
    import subprocess
    import sys

    installed = []
    for p in pkgs:
        mod = p.replace("-", "_")
        if importlib.util.find_spec(mod) is not None:
            continue
        if verbose:
            print(f"[autotune] installing {p} ...", flush=True)
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", p])
            installed.append(p)
        except Exception as e:  # noqa: BLE001
            print(f"[autotune] WARNING: could not install {p} ({e}). "
                  f"Run manually: pip install {p}", flush=True)
    return installed


def apply(model_id: str | None = None, install: bool = True, verbose: bool = True) -> dict:
    """Detect VRAM, choose the path, install any needed package, and write the choice
    into ``config``. Returns the plan."""
    plan = recommend(model_id)
    if verbose:
        print(f"[autotune] {plan['reason']}  (model={plan['model_id']}, "
              f"4bit={plan['load_in_4bit']}, batch={plan['batch_size']})", flush=True)
    if install and plan["needs"]:
        ensure_installed(plan["needs"], verbose=verbose)
    config.GEN_MODEL = plan["model_id"]
    config.LOAD_IN_4BIT = plan["load_in_4bit"]
    config.BATCH_SIZE = plan["batch_size"]
    return plan
