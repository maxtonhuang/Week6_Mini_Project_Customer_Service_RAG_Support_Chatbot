"""Tests for the sophistication-ladder defence levels (D0/D1/D2) and the two new
defence-in-depth controls: D10 (instruction hierarchy) and D11 (decode-then-scan output
filter). stdlib-only, offline — mirrors the style of tests/test_defenses.py and
tests/test_hardening.py."""
from __future__ import annotations

from ragguard.defenses import (
    build_defense_level,
    defense_level_stack_label,
    DEFENSE_LEVEL_LABELS,
    D10InstructionHierarchy,
    D11DecodeScan,
)
from ragguard.schemas import Action


def test_build_defense_level():
    from ragguard.defenses import build_defense_level, defense_level_stack_label
    assert build_defense_level(0) == []
    ids1 = [d.id for d in build_defense_level(1)]
    ids2 = [d.id for d in build_defense_level(2)]
    assert ids1 == ["D1", "D2", "D4", "D6"]
    assert set(ids1).issubset(set(ids2)) and {"D10", "D11"}.issubset(set(ids2))
    assert defense_level_stack_label(0) == "none"
    assert defense_level_stack_label(1) == "D1+D2+D4+D6"


def test_build_defense_level_k2_label_and_validation():
    ids2 = [d.id for d in build_defense_level(2)]
    assert ids2 == ["D1", "D2", "D3", "D4", "D5", "D6", "D7", "D9", "D10", "D11"]
    assert defense_level_stack_label(2) == "D1+D2+D3+D4+D5+D6+D7+D9+D10+D11"
    assert DEFENSE_LEVEL_LABELS == {
        0: "D0 · none", 1: "D1 · content filters", 2: "D2 · defence-in-depth",
    }
    try:
        build_defense_level(3)
        assert False, "expected ValueError for an invalid level"
    except ValueError:
        pass


def test_d10_hardens_system_prompt():
    d10 = D10InstructionHierarchy()
    assert d10.id == "D10" and d10.name
    out = d10.transform_system_prompt("BASE")
    assert "BASE" in out
    assert len(out) > len("BASE")


def test_d11_blocks_surviving_secret():
    d11 = D11DecodeScan(system_prompt_secrets=["ACME-SECRET-XYZ"])
    assert d11.id == "D11" and d11.name
    dec = d11.post_generation("q", "... ACME-SECRET-XYZ ...", [])
    assert "ACME-SECRET-XYZ" not in dec.text or dec.action == Action.BLOCK

    clean = d11.post_generation("q", "The refund window is 30 days.", [])
    assert clean.action == Action.ALLOW
    assert clean.text == "The refund window is 30 days."


def test_d11_decodes_before_scanning():
    """The defence-in-depth point of D11: a secret survives naive raw-text scanning once
    obfuscated (zero-width chars break a literal/regex match), but D11 decodes first
    (reusing D6Normalizer's decode helper, textnorm.normalize) so it still catches it."""
    from ragguard import textnorm

    secret = "internal escalation passphrase orion"
    obfuscated = textnorm.insert_zero_width(secret)
    assert secret not in obfuscated  # sanity: raw substring scan would miss it

    d11 = D11DecodeScan(system_prompt_secrets=[secret])
    dec = d11.post_generation("q", f"Sure, the {obfuscated} is used internally.", [])
    assert dec.action == Action.BLOCK
