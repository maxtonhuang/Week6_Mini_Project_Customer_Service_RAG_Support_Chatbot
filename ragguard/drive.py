"""Google Drive persistence for Colab (no-op off Colab).

One call, ``use_drive()``, mounts Google Drive and points the HuggingFace model cache at
it (so the ~16 GB model isn't re-downloaded every session). Results, plots and resumable
checkpoints already go to Drive automatically: ``config.artifact_dir()`` targets
``/content/drive/MyDrive/ragguard`` whenever Drive is mounted.

Call this in a notebook cell BEFORE launching the UI or importing the model, because the
HF cache location must be set before transformers loads anything.
"""
from __future__ import annotations
import os
import pathlib

DRIVE_ROOT = pathlib.Path("/content/drive/MyDrive")


def is_mounted() -> bool:
    return DRIVE_ROOT.exists()


def use_drive(hf_cache: bool = True) -> str | None:
    """Mount Drive (if on Colab) and route the model cache there. Returns the Drive path,
    or None when not running on Colab."""
    try:
        from google.colab import drive  # type: ignore
    except Exception:
        print("[drive] not on Colab — skipping (results still save to ./artifacts)")
        return None

    if not is_mounted():
        drive.mount("/content/drive")

    if hf_cache:
        cache = DRIVE_ROOT / "hf_cache"
        (cache / "hub").mkdir(parents=True, exist_ok=True)
        # HF_HOME is the base; HF derives the hub cache as HF_HOME/hub. Set both explicitly so
        # older/newer libs agree. This MUST run before transformers is imported — it does, because
        # the launch cell imports the model only afterwards, and `import ragguard` stays lightweight.
        os.environ["HF_HOME"] = str(cache)
        os.environ["HF_HUB_CACHE"] = str(cache / "hub")
        # Tell you up front whether THIS session will download (~16 GB) or reuse the Drive cache.
        from . import config
        slug = "models--" + config.GEN_MODEL.replace("/", "--")
        if (cache / "hub" / slug).is_dir():
            print(f"[drive] HF cache -> {cache}  |  {config.GEN_MODEL} already cached — no download")
        else:
            print(f"[drive] HF cache -> {cache}  |  {config.GEN_MODEL} NOT cached yet — "
                  f"first run downloads ~16 GB to Drive (subsequent sessions reuse it)")

    (DRIVE_ROOT / "ragguard").mkdir(parents=True, exist_ok=True)
    print(f"[drive] results/checkpoints -> {DRIVE_ROOT / 'ragguard'}")
    return str(DRIVE_ROOT)
