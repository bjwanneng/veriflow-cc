"""Match observed divergences against the known bug catalog.

Reads a list of divergence dicts (cycle / signal / classification /
expected / actual / offset_cycles) and surfaces matching patterns from
`bug_patterns.md`. Each matcher returns a `PatternMatch` with a numeric
confidence and a human-readable reason; the top matches are returned
ranked by confidence.

CLI (used by SKILL.md Error Recovery Step 1.5):
  python bug_pattern_match.py \\
      --divergences logs/divergences.json \\
      --output      logs/pattern_match.json

Library use:
  from bug_pattern_match import match_patterns
  matches = match_patterns([
      {"signal": "V0", "classification": "A",
       "expected": 0xabc, "actual": 0xdef, "cycle": 66},
  ])
  # matches[0].pattern_id   -> 10
  # matches[0].prevention_rule -> "DONE state must use _reg, not _new"

The matcher only uses features derivable from the divergence list:
  - signal name (substring / regex)
  - classification (A / B_late / B_early / D)
  - offset_cycles
  - expected / actual values and their XOR
  - cycle index
  - count of co-occurring divergences (multi-divergence patterns)

It does NOT read RTL source or spec.json; that gating is delegated to
the LLM consuming the suggestions. False positives are expected — every
match must come with a clear reason so the human/agent can dismiss it.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path


# --------------------------------------------------------------------------
# Result container
# --------------------------------------------------------------------------

@dataclass
class PatternMatch:
    pattern_id: int
    title: str
    confidence: float          # 0.0 to 1.0
    reason: str                # why this pattern matched (signal-level evidence)
    prevention_rule: str       # one-line summary of how to avoid this bug

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

_V_REGISTER_RE = re.compile(r"(?:^|\.)V\d+(?:_reg)?$|(?:^|\.)V\d+\b")
_HASH_SIGNAL_RE = re.compile(r"hash|digest|message_digest|output", re.IGNORECASE)
_VALID_SIGNAL_RE = re.compile(r"valid|done|message_valid", re.IGNORECASE)
_LATCH_SIGNAL_RE = re.compile(r"latch|latched", re.IGNORECASE)
_REGISTERED_OUTPUT_RE = re.compile(r"(ready|valid|done)(_reg)?$", re.IGNORECASE)


def _short(sig: str) -> str:
    """Strip module-qualified prefix and trailing array suffix."""
    s = sig.rsplit(".", 1)[-1]
    s = s.split("[", 1)[0]
    return s


def _popcount(x: int) -> int:
    return bin(x & ((1 << 256) - 1)).count("1")


def _xor_magnitude(div: dict) -> int:
    return (div.get("expected", 0) ^ div.get("actual", 0))


# --------------------------------------------------------------------------
# Pattern matchers
# --------------------------------------------------------------------------

def _match_pattern_1_latch_race(divs: list[dict]) -> PatternMatch | None:
    """Pattern 1: Latch-Then-Load Race (Cross-Module).

    Signature: very-early-cycle D-class divergence on a `*_latch*` signal
    (actual=0 while expected!=0).
    """
    for d in divs:
        sig = _short(d["signal"])
        if not _LATCH_SIGNAL_RE.search(sig):
            continue
        if d.get("classification") != "D":
            continue
        if d.get("cycle", 0) > 3:
            continue
        return PatternMatch(
            pattern_id=1,
            title="Latch-Then-Load Race (Cross-Module)",
            confidence=0.75,
            reason=(
                f"signal={sig!r} matched `*latch*` pattern, classified D "
                f"(actual=0 expected={d['expected']:#x}), at cycle {d['cycle']} — "
                "submodule likely reads latched register on the same posedge "
                "the top latches the input (NBA race)."
            ),
            prevention_rule=(
                "Connect the submodule's data port to the EXTERNAL input "
                "(combinational path) instead of a latched register when the "
                "load enable fires on the same cycle as the latch write."
            ),
        )
    return None


def _match_pattern_10_finalize_leak(divs: list[dict]) -> PatternMatch | None:
    """Pattern 10: Finalize-State Combinational Leak.

    Signature: accumulator or output register (e.g., V0..V7 or result_out) diverges with
    classification A and the XOR has many bits set (suggesting an extra
    round of computation, not zero/init error).
    """
    for d in divs:
        sig = _short(d["signal"])
        is_v = bool(_V_REGISTER_RE.search(d["signal"])) or bool(_V_REGISTER_RE.search(sig))
        is_hash = bool(_HASH_SIGNAL_RE.search(sig))
        if not (is_v or is_hash):
            continue
        if d.get("classification") != "A":
            continue
        if d.get("expected", 0) == 0 or d.get("actual", 0) == 0:
            continue  # P3/P11 territory, not P10
        if _popcount(_xor_magnitude(d)) < 4:
            continue  # tiny diff is more likely arithmetic, not extra round
        return PatternMatch(
            pattern_id=10,
            title="Finalize-State Combinational Leak (uses _new instead of _reg)",
            confidence=0.65,
            reason=(
                f"signal={sig!r} is a chaining/hash register, classification A, "
                f"expected={d['expected']:#x} actual={d['actual']:#x} "
                f"(XOR popcount={_popcount(_xor_magnitude(d))}, ~one extra round). "
                "DONE state likely reads `_new` combinational wire instead of `_reg`."
            ),
            prevention_rule=(
                "In DONE/finalize FSM states, all output computations and register "
                "updates MUST use `_reg` values, never `_new` combinational wires."
            ),
        )
    return None


def _match_pattern_11_merkle_damgard_reset(divs: list[dict]) -> PatternMatch | None:
    """Pattern 11: Merkle-Damgård Chaining Register Reset.

    Signature: 3+ V0..V7 registers all diverge in the same divergence batch,
    suggesting the chaining state carried over from a previous message.
    """
    v_regs: list[str] = []
    for d in divs:
        sig = _short(d["signal"])
        if re.match(r"V\d+(?:_reg)?$", sig):
            v_regs.append(sig)
    if len(v_regs) < 3:
        return None
    return PatternMatch(
        pattern_id=11,
        title="Merkle-Damgård Chaining Register Reset",
        confidence=0.8,
        reason=(
            f"{len(v_regs)} chaining registers diverge simultaneously: {v_regs[:4]}"
            f"{'...' if len(v_regs) > 4 else ''}. "
            "Chaining V registers are likely not re-initialized for a new message."
        ),
        prevention_rule=(
            "When starting a new message (is_first_block), re-initialize BOTH the "
            "working registers (A-H) AND the chaining registers (V0-V7) to the IV."
        ),
    )


def _match_pattern_13_bitslice_truncation(divs: list[dict]) -> PatternMatch | None:
    """Pattern 13: Bit-Slice Concatenation Width Truncation.

    Signature: A-class divergence where the actual value has its upper half
    forced to all-zero (or all-one), indicating silent truncation of a wide
    concatenation assigned to a narrower target.
    """
    for d in divs:
        if d.get("classification") != "A":
            continue
        expected = d.get("expected", 0)
        actual = d.get("actual", 0)
        if expected == 0 or actual == 0:
            continue
        # Guess width from expected value (round up to nearest power-of-2 byte)
        bit_len = max(expected.bit_length(), actual.bit_length(), 8)
        # snap up to 8/16/32/64/128/256
        for w in (8, 16, 32, 64, 128, 256):
            if bit_len <= w:
                width = w
                break
        else:
            width = bit_len
        upper_mask = ((1 << width) - 1) ^ ((1 << (width // 2)) - 1)
        lower_mask = (1 << (width // 2)) - 1
        upper_actual = actual & upper_mask
        lower_actual = actual & lower_mask
        upper_expected = expected & upper_mask
        lower_expected = expected & lower_mask
        # Upper bits zero in actual but nonzero in expected, lower bits match
        if upper_actual == 0 and upper_expected != 0 and lower_actual == lower_expected:
            sig = _short(d["signal"])
            return PatternMatch(
                pattern_id=13,
                title="Bit-Slice Concatenation Width Truncation",
                confidence=0.7,
                reason=(
                    f"signal={sig!r} actual={actual:#x} has upper {width // 2} bits "
                    f"zero while expected={expected:#x} has them set; lower halves match. "
                    "Suggests `{a, b}` slice sum > target width — silent truncation."
                ),
                prevention_rule=(
                    "For every `{a, b}` concatenation assigned to an N-bit target, "
                    "verify `$bits(a) + $bits(b) == N`. ROL(x, k) for WIDTH-bit x is "
                    "`{x[WIDTH-1-k:0], x[WIDTH-1:WIDTH-k]}` — second slice is k bits, "
                    "NOT WIDTH-k bits."
                ),
            )
    return None


def _match_pattern_14_multiblock_valid(divs: list[dict]) -> PatternMatch | None:
    """Pattern 14: Multi-Block Valid Signal Not Gated.

    Signature: a `valid`/`done` signal asserts (actual=1) when the golden
    expects 0, mid-simulation (cycle > 1).
    """
    for d in divs:
        sig = _short(d["signal"])
        if not _VALID_SIGNAL_RE.search(sig):
            continue
        expected = d.get("expected", 0)
        actual = d.get("actual", 0)
        if expected == 0 and actual == 1 and d.get("cycle", 0) > 1:
            return PatternMatch(
                pattern_id=14,
                title="Multi-Block Valid Signal Not Gated by is_last",
                confidence=0.7,
                reason=(
                    f"signal={sig!r} asserted (actual=1) at cycle {d['cycle']} but "
                    "golden expects 0 — valid fires after intermediate block, "
                    "missing `is_last` gating."
                ),
                prevention_rule=(
                    "Gate `valid_out`/`done` with `is_last` (or equivalent) so it "
                    "asserts only after the final block, not after every block."
                ),
            )
    return None


def _match_pattern_15_cocotb_vcd_timing(divs: list[dict]) -> PatternMatch | None:
    """Pattern 15: Cocotb-vs-Verilog Timing Divergence.

    Signature: a registered output (`ready_reg`, `valid_reg`, etc.) classified
    B_late with offset_cycles=1 at cycle ≤ 2 — the canonical 1-cycle VPI lag.
    """
    for d in divs:
        sig = _short(d["signal"])
        if not _REGISTERED_OUTPUT_RE.search(sig):
            continue
        if d.get("classification") != "B_late":
            continue
        if d.get("offset_cycles") != 1:
            continue
        if d.get("cycle", 0) > 2:
            continue
        return PatternMatch(
            pattern_id=15,
            title="Cocotb-vs-Verilog Timing Divergence (1-cycle VPI lag)",
            confidence=0.85,
            reason=(
                f"signal={sig!r} classified B_late offset=1 at cycle {d['cycle']} — "
                "cocotb+iverilog VPI reads register values from the PREVIOUS posedge's "
                "NBA, so registered outputs appear one cycle late."
            ),
            prevention_rule=(
                "Golden model must track `_next` vs `_reg` for registered outputs. "
                "At cycle 0/1, ready/valid reflect the IDLE-state's `_next` from the "
                "previous posedge — NOT the new state."
            ),
        )
    return None


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

_PATTERN_MATCHERS = [
    _match_pattern_11_merkle_damgard_reset,  # multi-divergence first (highest signal)
    _match_pattern_15_cocotb_vcd_timing,
    _match_pattern_1_latch_race,
    _match_pattern_10_finalize_leak,
    _match_pattern_13_bitslice_truncation,
    _match_pattern_14_multiblock_valid,
]


def match_patterns(divergences: list[dict]) -> list[PatternMatch]:
    """Match a list of divergence dicts against the bug catalog.

    Returns up to N matches ranked by confidence (descending). Each
    divergence dict expects: `signal`, `classification`, `expected`,
    `actual`, `cycle`; optional `offset_cycles`, `kind`.
    """
    matches: list[PatternMatch] = []
    for matcher in _PATTERN_MATCHERS:
        try:
            m = matcher(divergences)
        except Exception as e:
            print(f"[bug_pattern_match] matcher {matcher.__name__} raised: {e}",
                  file=sys.stderr)
            continue
        if m is not None:
            matches.append(m)
    matches.sort(key=lambda m: m.confidence, reverse=True)
    return matches


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Match observed RTL divergences "
                                            "against known bug patterns")
    p.add_argument("--divergences", required=True,
                   help="Path to a JSON file (list of divergence dicts)")
    p.add_argument("--output", default=None,
                   help="Write matched patterns JSON here (default: stdout)")
    args = p.parse_args(argv)

    src = Path(args.divergences)
    if not src.exists():
        print(f"divergences file not found: {src}", file=sys.stderr)
        return 2
    divs = json.loads(src.read_text())
    if not isinstance(divs, list):
        print("divergences JSON must be a list of objects", file=sys.stderr)
        return 2

    matches = match_patterns(divs)
    out = {
        "match_count": len(matches),
        "matches": [m.to_dict() for m in matches],
    }
    text = json.dumps(out, indent=2)
    if args.output:
        Path(args.output).write_text(text)
        print(f"[bug_pattern_match] -> {args.output} ({len(matches)} matches)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
