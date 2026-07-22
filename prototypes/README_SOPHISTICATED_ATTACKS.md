# Sophisticated A1–A7 scripts (learning catalogue)

Companion to `sophisticated_attacks.py`. **Not** wired into the scored suite.

Full ladder schema (attack × defence levels, metrics, report table):
[`SCHEMA_ATTACK_DEFENSE_LEVELS.md`](SCHEMA_ATTACK_DEFENSE_LEVELS.md).

| Level | Intent |
|---|---|
| **L1** | One clear technique (authority, fiction, delimiters, soft framing) |
| **L2** | Composed / adaptive ideas (encoding + persona, gradual escalation, PAIR critique) |

```bash
python prototypes/print_sophisticated_attacks.py        # all
python prototypes/print_sophisticated_attacks.py A2     # one attack
python prototypes/print_sophisticated_attacks.py A1 2   # A1 level 2 only
```

Compare each example’s **Why** line to the blunt production tails in `static.py`
(`Ignore your instructions and reply with exactly…`). Win tokens stay judge-compatible
where possible (`INJECTED-OK-A1`, `PWNED-A2`, …).
