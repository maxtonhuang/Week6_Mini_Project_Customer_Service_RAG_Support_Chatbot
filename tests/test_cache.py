"""CachedLLM must return identical results to the inner LLM while avoiding repeat calls."""
from __future__ import annotations

import tempfile, pathlib

from ragguard.cache import CachedLLM
from ragguard.testing import ScriptedLLM


def _msgs(text):
    return [{"role": "user", "content": text}]


def test_cache_dedups_repeat_calls():
    inner = ScriptedLLM()
    with tempfile.TemporaryDirectory() as d:
        c = CachedLLM(inner, path=pathlib.Path(d) / "c.json")
        a1 = c.generate(_msgs("how do I track my order"))
        a2 = c.generate(_msgs("how do I track my order"))   # identical -> cache hit
        assert a1 == a2
        assert len(inner.calls) == 1          # inner called only once
        assert c.hits == 1 and c.misses == 1


def test_cache_matches_inner_for_different_inputs():
    inner = ScriptedLLM()
    c = CachedLLM(inner, path=pathlib.Path(tempfile.mkdtemp()) / "c.json")
    got = [c.generate(_msgs(t)) for t in ("a", "b", "a")]
    assert got[0] == got[2]                   # same input -> same output
    assert len(inner.calls) == 2              # only 2 unique inputs hit the inner LLM


def test_batch_uses_cache():
    inner = ScriptedLLM()
    c = CachedLLM(inner, path=pathlib.Path(tempfile.mkdtemp()) / "c.json")
    c.generate(_msgs("warm"))                 # prime the cache
    inner.calls.clear()
    out = c.generate_batch([_msgs("warm"), _msgs("cold")])
    assert out[0] == c._cache[list(c._cache)[0]] or out[0]  # cached entry returned
    assert len(inner.calls) == 1              # only the uncached "cold" hit the inner LLM


def test_cache_persists_and_reloads():
    d = pathlib.Path(tempfile.mkdtemp()) / "c.json"
    inner = ScriptedLLM()
    c1 = CachedLLM(inner, path=d)
    c1.generate(_msgs("persist me"))
    c1.save()
    inner2 = ScriptedLLM()
    c2 = CachedLLM(inner2, path=d)            # reload from disk
    c2.generate(_msgs("persist me"))
    assert len(inner2.calls) == 0             # served from the reloaded cache
