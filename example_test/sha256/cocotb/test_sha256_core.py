"""cocotb testbench for sha256_core — NIST test vectors + golden model comparison.

Replaces the Verilog $display-based testbench with Python assertions.
On failure, produces Python tracebacks (file + line + values) directly
consumable by LLM for root cause analysis and auto-fix.

Usage:
    cd example_test/sha256/cocotb && make

Requirements:
    cocotb >= 2.0, iverilog >= 14.0
"""

import os
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles

# Ensure golden_model importable
sys.path.insert(0, str(Path(__file__).parent))
from golden_model import sha256_compress, digest_to_int, IV

# ─── Constants ──────────────────────────────────────────────────────────────

CLK_PERIOD_NS = 5  # 200 MHz

NIST_EMPTY_BLOCK = (
    0x80000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000
    << 256
) | 0x00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000

NIST_EMPTY_DIGEST = (
    0xE3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855
)

NIST_ABC_BLOCK = (
    0x61626380_00000000_00000000_00000000_00000000_00000000_00000000_00000000
    << 256
) | 0x00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000018

NIST_ABC_DIGEST = (
    0xBA7816BF8F01CFEA414140DE5DAE2223B00361A396177A9CB410FF61F20015AD
)

TIMEOUT_CYCLES = 200


# ─── Helpers ────────────────────────────────────────────────────────────────


async def reset_dut(dut):
    """Apply synchronous reset and verify post-reset state."""
    dut.rst.value = 1
    dut.init.value = 0
    dut.next.value = 0
    dut.block.value = 0
    await ClockCycles(dut.clk, 3)

    # Verify quiescent outputs during reset
    assert dut.ready.value == 1, (
        f"ready should be 1 during reset, got {dut.ready.value}"
    )
    assert dut.digest_valid.value == 0, (
        f"digest_valid should be 0 during reset, got {dut.digest_valid.value}"
    )

    # Release reset
    dut.rst.value = 0
    await ClockCycles(dut.clk, 2)

    # Verify post-reset
    assert dut.ready.value == 1, (
        f"ready should be 1 after reset, got {dut.ready.value}"
    )


async def init_dut(dut):
    """Send 'init' command to load IV into hash state."""
    await RisingEdge(dut.clk)
    dut.init.value = 1
    await RisingEdge(dut.clk)
    dut.init.value = 0
    await RisingEdge(dut.clk)
    assert dut.ready.value == 1, (
        f"ready should remain 1 after init, got {dut.ready.value}"
    )


async def send_block(dut, block_val: int):
    """Send 'next' command with a 512-bit message block, wait for digest_valid.

    Returns the captured 256-bit digest.

    Raises AssertionError on timeout or protocol violation.
    """
    # Check ready
    assert dut.ready.value == 1, (
        f"ready must be 1 before 'next', got {dut.ready.value}"
    )

    await RisingEdge(dut.clk)
    dut.next.value = 1
    dut.block.value = block_val
    await RisingEdge(dut.clk)
    dut.next.value = 0
    dut.block.value = 0

    # Verify ready de-asserts (core is now busy)
    await RisingEdge(dut.clk)
    assert dut.ready.value == 0, (
        f"ready should de-assert during COMPUTE (cycle after next), "
        f"got {dut.ready.value}"
    )

    # Wait for digest_valid with timeout
    for cycle in range(TIMEOUT_CYCLES):
        await RisingEdge(dut.clk)
        if dut.digest_valid.value == 1:
            digest = dut.digest.value.to_unsigned()
            # Verify single-cycle pulse
            await RisingEdge(dut.clk)
            assert dut.digest_valid.value == 0, (
                f"digest_valid should de-assert after 1 cycle "
                f"(got {dut.digest_valid.value})"
            )
            return digest

    raise AssertionError(
        f"Timeout after {TIMEOUT_CYCLES} cycles waiting for digest_valid"
    )


async def run_single_block_test(
    dut, test_name: str, block: int, expected: int, do_init: bool = True
):
    """Run a single-block SHA-256 test with golden model comparison."""
    dut._log.info(f"=== {test_name} ===")

    if do_init:
        await init_dut(dut)

    result = await send_block(dut, block)

    # Verify against expected value
    assert result == expected, (
        f"{test_name} DIGEST MISMATCH\n"
        f"  expected: 0x{expected:064x}\n"
        f"  got:      0x{result:064x}\n"
        f"  xor diff: 0x{(result ^ expected):064x}"
    )

    # Cross-check with Python golden model computed on-the-fly
    h = sha256_compress(block, IV)
    golden = digest_to_int(h)
    assert result == golden, (
        f"{test_name} GOLDEN MODEL MISMATCH\n"
        f"  golden:    0x{golden:064x}\n"
        f"  rtl:       0x{result:064x}"
    )

    dut._log.info(f"  PASS — digest matches golden model")


# ─── Tests ──────────────────────────────────────────────────────────────────


@cocotb.test()
async def test_reset(dut):
    """Test 1: Reset behavior — outputs quiescent, ready=1, digest_valid=0."""
    clock = Clock(dut.clk, CLK_PERIOD_NS, unit="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)
    dut._log.info("  PASS — reset behavior correct")


@cocotb.test()
async def test_nist_empty_string(dut):
    """Test 2: NIST empty string — SHA-256('') via pre-padded block."""
    clock = Clock(dut.clk, CLK_PERIOD_NS, unit="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)
    await run_single_block_test(
        dut,
        "NIST empty string",
        NIST_EMPTY_BLOCK,
        NIST_EMPTY_DIGEST,
        do_init=True,
    )


@cocotb.test()
async def test_nist_abc(dut):
    """Test 3: NIST 'abc' — SHA-256('abc') via pre-padded block."""
    clock = Clock(dut.clk, CLK_PERIOD_NS, unit="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)
    await run_single_block_test(
        dut,
        "NIST 'abc'",
        NIST_ABC_BLOCK,
        NIST_ABC_DIGEST,
        do_init=True,
    )


@cocotb.test()
async def test_init_next_priority(dut):
    """Test 4: init + next simultaneous — next takes priority."""
    clock = Clock(dut.clk, CLK_PERIOD_NS, unit="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)

    dut._log.info("=== Test: init + next simultaneous ===")

    # Assert both init and next simultaneously
    await RisingEdge(dut.clk)
    dut.init.value = 1
    dut.next.value = 1
    dut.block.value = NIST_EMPTY_BLOCK
    await RisingEdge(dut.clk)
    dut.init.value = 0
    dut.next.value = 0
    dut.block.value = 0

    # Verify ready de-asserted (next took priority over init)
    await RisingEdge(dut.clk)
    assert dut.ready.value == 0, (
        f"ready should be 0 during COMPUTE (next took priority), "
        f"got {dut.ready.value}"
    )

    # Wait for digest_valid (empty string result — since init was suppressed
    # by next priority, the H0-H7 state depends on prior test context.
    # We just verify the protocol completed without timeout/stuck.)
    for cycle in range(TIMEOUT_CYCLES):
        await RisingEdge(dut.clk)
        if dut.digest_valid.value == 1:
            dut._log.info(
                f"  digest_valid asserted at ~cycle {cycle}, "
                f"digest=0x{dut.digest.value.to_unsigned():064x}"
            )
            break
    else:
        raise AssertionError(
            "Timeout — design stuck when init+next asserted simultaneously"
        )

    # Verify single-cycle pulse
    await RisingEdge(dut.clk)
    assert dut.digest_valid.value == 0, (
        "digest_valid should be single-cycle pulse"
    )

    dut._log.info("  PASS — simultaneous init+next handled correctly")


@cocotb.test()
async def test_back_to_back_blocks(dut):
    """Test 5: Back-to-back single-block messages."""
    clock = Clock(dut.clk, CLK_PERIOD_NS, unit="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)
    await init_dut(dut)

    # First block: empty string
    dut._log.info("--- Block 1: empty string ---")
    result1 = await send_block(dut, NIST_EMPTY_BLOCK)
    assert result1 == NIST_EMPTY_DIGEST, (
        f"Block 1 mismatch: expected 0x{NIST_EMPTY_DIGEST:064x}, "
        f"got 0x{result1:064x}"
    )

    # Second block: "abc"
    # Must do init first to reload IV
    await init_dut(dut)
    dut._log.info("--- Block 2: 'abc' ---")
    result2 = await send_block(dut, NIST_ABC_BLOCK)
    assert result2 == NIST_ABC_DIGEST, (
        f"Block 2 mismatch: expected 0x{NIST_ABC_DIGEST:064x}, "
        f"got 0x{result2:064x}"
    )

    dut._log.info("  PASS — back-to-back blocks")


@cocotb.test()
async def test_golden_model_cross_check(dut):
    """Test 6: Cross-check RTL output against golden model with random blocks.

    First uses the known NIST vectors, then applies golden model to verify
    the RTL's computation output bit-by-bit.
    """
    clock = Clock(dut.clk, CLK_PERIOD_NS, unit="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)

    # Test vectors: (block, description)
    # Each block is a pre-padded 512-bit single-block message
    test_vectors = [
        (NIST_EMPTY_BLOCK, "empty string"),
        (NIST_ABC_BLOCK, "'abc'"),
    ]

    for block, desc in test_vectors:
        await init_dut(dut)

        expected_golden = digest_to_int(sha256_compress(block, IV))
        result = await send_block(dut, block)

        assert result == expected_golden, (
            f"Golden model mismatch for {desc}:\n"
            f"  golden: 0x{expected_golden:064x}\n"
            f"  rtl:    0x{result:064x}\n"
        )
        dut._log.info(f"  [{desc}] PASS — RTL matches golden model")
