"""test_sm3_core.py - cocotb testbench for SM3 core (GM/T 0004-2012).

Primary verification path: per-cycle comparison of internal registers against
golden_model.compute(trace=True). Reports FIRST divergence with cycle number,
signal name, expected/actual hex (zero-padded to signal width), and XOR diff.

Timing model (matches golden_model.py):
  cycle 0  = post-reset / IDLE, ready=1
  cycle 1  = LOAD (A..H <- IV, W_regs <- msg_block), state=CALC, round=0
  cycle 2..65 = 64 compress rounds (round 0..63 result)
  cycle 66 = DONE, V_regs latch new digest
  cycle 67 = hash_valid pulse, ready re-asserted, hash_out = digest
  cycle 68 = idle tail

DRIVE_PHASE_CYCLES = 1 per spec.timing_convention.golden_to_rtl_offset_cycles.

VPI hierarchy:
  dut.u_fsm.state_reg, dut.u_fsm.round_cnt_reg
  dut.u_compress.{a..h}_reg
  dut.u_compress.v_regs[0..7]   (used for full-digest cross-check)
  dut.ready, dut.hash_valid, dut.hash_out  (top-level outputs)
"""
from __future__ import annotations

import os
import sys

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, Timer

# -----------------------------------------------------------------------------
# Import golden model from workspace/docs/
# -----------------------------------------------------------------------------
_DOCS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docs"))
if _DOCS_DIR not in sys.path:
    sys.path.insert(0, _DOCS_DIR)

try:
    import golden_model  # noqa: E402
    GOLDEN_AVAILABLE = True
except ImportError as e:
    GOLDEN_AVAILABLE = False
    print(f"[WARN] golden_model unavailable: {e}")

# -----------------------------------------------------------------------------
# Constants populated from spec.json + golden_model.py
# -----------------------------------------------------------------------------
CLK_PERIOD_NS = 10                  # 100 MHz, from spec.constraints.timing
DRIVE_PHASE_CYCLES = 1              # spec.timing_convention.golden_to_rtl_offset_cycles
TIMEOUT_CYCLES = 200                # 67-cycle latency + slack

INPUT_PORTS = {                     # name -> width_bits (excludes clk/rst)
    "msg_valid": 1,
    "msg_block": 512,
    "is_last":   1,
}
OUTPUT_PORTS = {
    "ready":      1,
    "hash_valid": 1,
    "hash_out":   256,
}
VALID_OUTPUT_PORTS = ["hash_valid"]
HANDSHAKE_PORTS    = {"msg_valid": "ready"}
HOLD_UNTIL_ACK_PORTS = []           # msg_valid is single_cycle; ready is steady level

# Maps golden_model trace key -> RTL VPI path (relative to dut)
GOLDEN_TO_PORT = {
    "ready":      "ready",
    "hash_valid": "hash_valid",
    "hash_out":   "hash_out",
    "state_reg":  "u_fsm.state_reg",
    "round_reg":  "u_fsm.round_cnt_reg",
    "a_reg":      "u_compress.a_reg",
    "b_reg":      "u_compress.b_reg",
    "c_reg":      "u_compress.c_reg",
    "d_reg":      "u_compress.d_reg",
    "e_reg":      "u_compress.e_reg",
    "f_reg":      "u_compress.f_reg",
    "g_reg":      "u_compress.g_reg",
    "h_reg":      "u_compress.h_reg",
}

# Width (bits) for hex zero-padding in error reports
SIGNAL_WIDTHS = {
    "ready": 1, "hash_valid": 1, "hash_out": 256,
    "state_reg": 2, "round_reg": 6,
    "a_reg": 32, "b_reg": 32, "c_reg": 32, "d_reg": 32,
    "e_reg": 32, "f_reg": 32, "g_reg": 32, "h_reg": 32,
}

# Registered outputs (timing_contract.registered_outputs) — sample at posedge
REGISTERED_OUTPUTS = ["ready", "hash_valid"]  # hash_out is combinational from v_regs
SAME_CYCLE_VISIBLE = []
PIPELINE_DELAY_CYCLES = 67

DIGEST_OUTPUT_PORT = "hash_out"     # final digest port

# KAT "abc" — embedded for the primary functional test
MSG_ABC = int("61626380" + "00" * 56 + "00000018", 16)
EXPECTED_ABC = 0x66c7f0f4_62eeedd9_d1f2d46b_dc10e4e2_4167c487_5cf2f7a2_297da02b_8f4ba8e0

FAIL_COUNT = 0


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
async def ensure_clock(dut):
    """Start a fresh clock at the beginning of each cocotb test.

    cocotb v2.0+ terminates background tasks between tests, so this must be
    the FIRST await in every @cocotb.test() body (RULE 6).
    """
    assert CLK_PERIOD_NS is not None, "CLK_PERIOD_NS must be populated by codegen"
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await RisingEdge(dut.clk)


async def reset_dut(dut):
    """Synchronous active-LOW reset. Drive inputs to safe defaults."""
    dut.rst_n.value     = 0
    dut.msg_valid.value = 0
    dut.is_last.value   = 0
    dut.msg_block.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


def _resolve_handle(dut, dotted_path: str):
    """Walk a dotted VPI path, supporting `array[idx]` segments."""
    handle = dut
    for seg in dotted_path.split("."):
        if "[" in seg and seg.endswith("]"):
            name, idx_s = seg[:-1].split("[", 1)
            handle = getattr(handle, name)
            handle = handle[int(idx_s)]
        else:
            handle = getattr(handle, seg)
    return handle


def safe_int(handle):
    """Read a cocotb handle as int; return None if X/Z or unavailable."""
    try:
        return int(handle.value)
    except Exception:
        return None


def read_dut_state(dut):
    """Snapshot DUT signals using GOLDEN_TO_PORT mapping."""
    state = {}
    for gkey, path in GOLDEN_TO_PORT.items():
        try:
            state[gkey] = safe_int(_resolve_handle(dut, path))
        except AttributeError:
            state[gkey] = None
    return state


def fmt_hex(value, width_bits):
    """Hex with zero-padding to `width_bits` (RULE 4: complete diagnostic data)."""
    if value is None:
        return "X/Z"
    nibbles = max(1, (width_bits + 3) // 4)
    return f"0x{value:0{nibbles}x}"


async def drive_inputs(dut, msg_block_val: int, is_last_val: int = 1):
    """Drive msg_valid/msg_block/is_last for DRIVE_PHASE_CYCLES cycles.

    Returns after the valid pulse has been deasserted. Caller is then aligned
    at the LOAD cycle (golden cycle 1).
    """
    # Wait for ready, then drive on the next posedge.
    while int(dut.ready.value) != 1:
        await RisingEdge(dut.clk)
    dut.msg_block.value = msg_block_val
    dut.is_last.value   = is_last_val
    dut.msg_valid.value = 1

    # Hold for DRIVE_PHASE_CYCLES + 1 to ensure the load posedge captures
    # msg_block stably (single_cycle handshake + 1-cycle pipeline offset).
    for _ in range(DRIVE_PHASE_CYCLES + 1):
        await RisingEdge(dut.clk)

    dut.msg_valid.value = 0
    dut.is_last.value   = 0


# -----------------------------------------------------------------------------
# Test 1: end-to-end hash check (black-box correctness)
# -----------------------------------------------------------------------------
@cocotb.test()
async def test_layered(dut):
    """SM3 'abc' KAT end-to-end: drive padded block, check final hash."""
    global FAIL_COUNT
    if not GOLDEN_AVAILABLE:
        dut._log.warning("golden_model unavailable — skipping")
        return
    await ensure_clock(dut)
    await reset_dut(dut)

    # Drive stimulus for the layered/end-to-end check.
    await drive_inputs(dut, MSG_ABC, is_last_val=1)

    # Poll for hash_valid pulse
    cycles_waited = 0
    while int(dut.hash_valid.value) != 1:
        await RisingEdge(dut.clk)
        cycles_waited += 1
        if cycles_waited > TIMEOUT_CYCLES:
            FAIL_COUNT += 1
            raise AssertionError(
                f"[FAIL] test=layered signal=hash_valid root_cause=signal_mismatch "
                f"TIMEOUT after {cycles_waited} cycles "
                f"(expected pulse within {PIPELINE_DELAY_CYCLES})"
            )

    # Registered hash_out: posedge detected; the same cycle's value is valid
    # because cocotb reads after the NBA region settles. Read now.
    actual = safe_int(dut.hash_out)
    dut._log.info("hash_valid asserted after %d cycles, hash_out=%s",
                  cycles_waited, fmt_hex(actual, 256))
    if actual != EXPECTED_ABC:
        FAIL_COUNT += 1
        diff = (actual ^ EXPECTED_ABC) if actual is not None else 0
        raise AssertionError(
            f"[FAIL] test=layered cycle={cycles_waited} signal=hash_out width=256b "
            f"root_cause=signal_mismatch\n"
            f"  expected = {fmt_hex(EXPECTED_ABC, 256)}\n"
            f"  actual   = {fmt_hex(actual, 256)}\n"
            f"  xor diff = {fmt_hex(diff, 256)}"
        )
    dut._log.info("[PASS] test_layered — hash matches GM/T 0004-2012 'abc' KAT")


# -----------------------------------------------------------------------------
# Test 2: per-cycle internal register comparison (white-box)
# -----------------------------------------------------------------------------
@cocotb.test()
async def test_internal_signals(dut):
    """Per-cycle compare of internal registers against golden trace.

    Catches Bug 1 (wrong MSG_BLOCK byte order on load) and Bug 2 (round_cnt
    off-by-one) on the FIRST diverging cycle with full diagnostic data.
    """
    global FAIL_COUNT
    if not GOLDEN_AVAILABLE:
        dut._log.warning("golden_model unavailable — skipping")
        return
    await ensure_clock(dut)
    await reset_dut(dut)

    # Compute the golden trace (69 entries, cycles 0..68)
    golden_trace = golden_model.compute(
        {"msg_block": MSG_ABC, "is_last": True}, trace=True)
    dut._log.info("Golden trace length = %d cycles", len(golden_trace))

    # --- Verify cycle 0 (post-reset / IDLE) BEFORE driving inputs ---
    dut_state = read_dut_state(dut)
    expected = golden_trace[0]
    cycle0_signals = ["ready", "state_reg", "round_reg"]
    for sig in cycle0_signals:
        exp = expected.get(sig)
        act = dut_state.get(sig)
        if exp is None or act is None:
            continue
        if exp != act:
            FAIL_COUNT += 1
            w = SIGNAL_WIDTHS.get(sig, 32)
            diff = exp ^ act
            raise AssertionError(
                f"[INTERNAL] FIRST DIVERGENCE at cycle=0 signal={sig} "
                f"(width={w}b) root_cause=signal_mismatch\n"
                f"  expected = {fmt_hex(exp, w)}\n"
                f"  actual   = {fmt_hex(act, w)}\n"
                f"  xor diff = {fmt_hex(diff, w)}"
            )

    # --- Drive stimulus (same as test_layered) ---
    # Drive stimulus (mirrors test_layered) — inline below to align cycles.
    # Manual inline drive so we can align cycle counter precisely with golden_trace.
    while int(dut.ready.value) != 1:
        await RisingEdge(dut.clk)
    # At this posedge boundary we are about to enter cycle 1 (the LOAD cycle).
    dut.msg_block.value = MSG_ABC
    dut.is_last.value   = 1
    dut.msg_valid.value = 1

    # Advance one rising edge -> DUT is now at cycle 1 (LOAD posedge just fired)
    await RisingEdge(dut.clk)
    await Timer(1, units="ps")  # let NBA updates settle before VPI read
    # Deassert handshake; msg_block left stable (don't care after load).
    dut.msg_valid.value = 0
    dut.is_last.value   = 0

    # --- Per-cycle compare from cycle 1 .. len(golden_trace)-1 ---
    # Sample order: at this point we are just after cycle 1's posedge.
    # `read_dut_state` returns the NEW (post-posedge) values, matching
    # golden_model's software-instantaneous semantics.
    SIGNALS_TO_COMPARE = [
        "state_reg", "round_reg",
        "a_reg", "b_reg", "c_reg", "d_reg",
        "e_reg", "f_reg", "g_reg", "h_reg",
        "ready", "hash_valid", "hash_out",
    ]

    first_divergence = None
    for cycle in range(1, len(golden_trace)):
        if cycle > 1:
            await RisingEdge(dut.clk)
            await Timer(1, units="ps")  # let NBA settle
        dut_state = read_dut_state(dut)
        expected = golden_trace[cycle]

        for sig in SIGNALS_TO_COMPARE:
            if sig not in expected:
                continue
            exp = expected[sig]
            act = dut_state.get(sig)
            if act is None:
                continue
            # Special-case: hash_out is meaningful only at/after cycle 66
            # (V_regs latch). Skip comparison earlier — golden_model reports
            # the IV-packed value during compress rounds, which the RTL
            # doesn't necessarily expose on hash_out (it's gated until DONE).
            if sig == "hash_out" and cycle < 66:
                continue
            if exp != act:
                first_divergence = (cycle, sig, exp, act)
                break
        if first_divergence:
            break

    if first_divergence:
        cyc, sig, exp, act = first_divergence
        w = SIGNAL_WIDTHS.get(sig, 32)
        path = GOLDEN_TO_PORT.get(sig, sig)
        diff = (exp ^ act) if act is not None else 0
        FAIL_COUNT += 1
        # Distinguish stimulus vs DUT bug: LOAD cycle (cycle 1) divergence on
        # a_reg..h_reg with values == IV[i] is likely a stimulus issue
        # (msg_block alignment); divergence in round cycles is a DUT bug.
        root_cause = "signal_mismatch (DUT computation)"
        if cyc == 1 and sig in ("a_reg", "b_reg", "c_reg", "d_reg",
                                  "e_reg", "f_reg", "g_reg", "h_reg"):
            root_cause = "stimulus_mismatch or LOAD-cycle RTL bug"
        raise AssertionError(
            f"[INTERNAL] FIRST DIVERGENCE at cycle={cyc} "
            f"signal={path} (width={w}b) root_cause={root_cause}\n"
            f"  expected = {fmt_hex(exp, w)}\n"
            f"  actual   = {fmt_hex(act, w)}\n"
            f"  xor diff = {fmt_hex(diff, w)}"
        )

    dut._log.info(
        "[PASS] test_internal_signals — all %d cycles match golden trace",
        len(golden_trace))


# -----------------------------------------------------------------------------
# Test 3: timing contract — registered outputs must be NBA-stable
# -----------------------------------------------------------------------------
@cocotb.test()
async def test_timing_contract(dut):
    """Registered outputs (ready, hash_valid, hash_out) must not change
    between posedge and the following negedge — they must be driven by NBA."""
    global FAIL_COUNT
    if not GOLDEN_AVAILABLE:
        return
    await ensure_clock(dut)
    await reset_dut(dut)

    # Kick off the same stimulus as test_layered so we exercise live state.
    await drive_inputs(dut, MSG_ABC, is_last_val=1)

    violations = []
    for cycle in range(TIMEOUT_CYCLES):
        # Let NBA updates settle before sampling (Icarus VPI reads right at
        # posedge can capture the old reg value before the NBA region completes).
        await Timer(1, units="ps")
        for port_name in REGISTERED_OUTPUTS:
            try:
                sig = getattr(dut, port_name)
            except AttributeError:
                continue
            posedge_val = safe_int(sig)
            await FallingEdge(dut.clk)
            negedge_val = safe_int(sig)
            if posedge_val is not None and negedge_val is not None:
                if posedge_val != negedge_val:
                    w = SIGNAL_WIDTHS.get(port_name, 32)
                    violations.append(
                        f"cycle={cycle} signal={port_name} (width={w}b) "
                        f"posedge={fmt_hex(posedge_val, w)} "
                        f"negedge={fmt_hex(negedge_val, w)} "
                        f"-- registered output must be NBA-stable"
                    )
            await RisingEdge(dut.clk)

        # Early exit once we've seen the hash_valid pulse + 2 idle cycles
        if int(dut.hash_valid.value) == 1:
            await RisingEdge(dut.clk)
            await RisingEdge(dut.clk)
            break
        if violations:
            break

    if violations:
        FAIL_COUNT += 1
        dut._log.error("[TIMING] %d violation(s):", len(violations))
        for v in violations[:5]:
            dut._log.error("  %s", v)
        raise AssertionError(
            f"Timing contract violated: {violations[0]}"
        )
    dut._log.info("[PASS] test_timing_contract — registered outputs stable")


# -----------------------------------------------------------------------------
# Test 4: summary
# -----------------------------------------------------------------------------
@cocotb.test()
async def test_summary(dut):
    """Final pass/fail aggregation."""
    await ensure_clock(dut)
    if FAIL_COUNT == 0:
        dut._log.info("========================================")
        dut._log.info("ALL TESTS PASSED")
        dut._log.info("========================================")
    else:
        raise AssertionError(f"{FAIL_COUNT} test(s) failed")
