"""Disk-backed generation cache. Wrapping an LLM in ``CachedLLM`` dedups identical
deterministic model calls (e.g. the same benign query under stacks that don't change
the prompt) and lets a long run resume without recomputing. Pure stdlib.
"""
from __future__ import annotations

import hashlib
import json
import pathlib

from . import config
from .interfaces import Message


def _key(messages: list[Message], max_new_tokens) -> str:
    blob = json.dumps({"m": messages, "t": max_new_tokens}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class CachedLLM:
    """Wraps any LLM (implements the same interface). Caches to memory + a JSON file."""

    def __init__(self, inner, path=None, max_new_tokens=None):
        self.inner = inner
        self.path = pathlib.Path(path) if path else (config.cache_dir() / "gen_cache.json")
        self.max_new_tokens = max_new_tokens
        self.hits = 0
        self.misses = 0
        self._cache: dict[str, str] = {}
        if self.path.exists():
            try:
                self._cache = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self._cache = {}

    def _mnt(self, kw):
        return kw.get("max_new_tokens", self.max_new_tokens)

    def generate(self, messages: list[Message], **kw) -> str:
        k = _key(messages, self._mnt(kw))
        if k in self._cache:
            self.hits += 1
            return self._cache[k]
        self.misses += 1
        out = self.inner.generate(messages, **kw)
        self._cache[k] = out
        return out

    def generate_batch(self, batch: list[list[Message]], **kw) -> list[str]:
        mnt = self._mnt(kw)
        keys = [_key(m, mnt) for m in batch]
        results: list[str | None] = [None] * len(batch)
        todo_idx, todo_msgs = [], []
        for i, k in enumerate(keys):
            if k in self._cache:
                self.hits += 1
                results[i] = self._cache[k]
            else:
                todo_idx.append(i)
                todo_msgs.append(batch[i])
        if todo_msgs:
            self.misses += len(todo_msgs)
            outs = self.inner.generate_batch(todo_msgs, **kw)
            for i, o in zip(todo_idx, outs):
                results[i] = o
                self._cache[keys[i]] = o
        return results  # type: ignore[return-value]

    def save(self) -> pathlib.Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._cache, ensure_ascii=False), encoding="utf-8")
        return self.path

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {"hits": self.hits, "misses": self.misses,
                "hit_rate": (self.hits / total) if total else 0.0, "size": len(self._cache)}
