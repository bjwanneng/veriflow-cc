#!/usr/bin/env python3
"""
Cocotb testbench for sm3_core module

Tests the SM3 cryptographic hash function implementation using the golden model.
"""

import cocotb
from cocotb.triggers import Timer, ClockCycles, FallingEdge, ReadOnly
from cocotb.clock import Clock
import sys
import os

# Add the golden model to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../docs'))
import golden_model


def sm3_pad_message(msg: bytes) -> list:
    """Pad message according to SM3 specification and return 512-bit blocks.

    Args:
        msg: Input message as bytes

    Returns:
        List of 512-bit blocks (each as 512-bit integer, big-endian)
    """
    # Padding following SM3 spec
    msg_len = len(msg) * 8  # Message length in bits
    msg = msg + bytes([0x80])  # Append '1' bit
    k = (448 - (len(msg) * 8) % 512) % 512  # Pad with zeros
    msg = msg + bytes(k // 8)
    msg += msg_len.to_bytes(8, 'big')  # Append length (64-bit big-endian)

    # Split into 512-bit blocks
    blocks = []
    for i in range(0, len(msg), 64):
        block = msg[i:i+64]
        # Convert to 512-bit integer (big-endian)
        block_int = int.from_bytes(block, 'big')
        blocks.append(block_int)

    return blocks


async def reset_dut(dut):
    """Reset the DUT"""
    dut.rst.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0
    await ClockCycles(dut.clk, 2)


async def wait_for_ready(dut):
    """Wait until the DUT is ready"""
    while dut.ready.value != 1:
        await ClockCycles(dut.clk, 1)


async def send_block(dut, block: int, is_last: bool):
    """Send a 512-bit message block to the DUT.

    Args:
        dut: Device under test
        block: 512-bit block as integer
        is_last: True if this is the last block

    Returns:
        None
    """
    # Wait for ready
    await wait_for_ready(dut)

    # Drive inputs (big-endian: MSB first)
    dut.msg_block.value = block
    dut.is_last.value = int(is_last)
    dut.msg_valid.value = 1

    # Hold for 1 cycle (min hold time = max_pipeline_delay + 1 = 0 + 1 = 1)
    await ClockCycles(dut.clk, 1)

    # Deassert valid but keep data stable for 1 more cycle
    dut.msg_valid.value = 0
    await ClockCycles(dut.clk, 1)


async def get_hash(dut) -> int:
    """Wait for hash_valid and read the hash output.

    Args:
        dut: Device under test

    Returns:
        256-bit hash value as integer
    """
    # Wait for hash_valid
    timeout = 1000
    while dut.hash_valid.value != 1 and timeout > 0:
        await ClockCycles(dut.clk, 1)
        timeout -= 1

    if timeout == 0:
        raise TimeoutError("Timeout waiting for hash_valid")

    # Read hash output (big-endian: MSB first from the module)
    hash_value = int(dut.hash_out.value)

    return hash_value


async def sm3_hash_dut(dut, msg: bytes) -> int:
    """Compute SM3 hash using the DUT.

    Args:
        dut: Device under test
        msg: Input message as bytes

    Returns:
        256-bit hash value as integer
    """
    # Pad message into 512-bit blocks
    blocks = sm3_pad_message(msg)

    # Send all blocks
    for i, block in enumerate(blocks):
        is_last = (i == len(blocks) - 1)
        await send_block(dut, block, is_last)

    # Get result
    hash_value = await get_hash(dut)

    return hash_value


@cocotb.test()
async def test_sm3_abc(dut):
    """Test SM3 with 'abc' input"""
    # Create clock
    clock = Clock(dut.clk, 2, units="ns")
    cocotb.start_soon(clock.start())

    # Reset
    await reset_dut(dut)

    # Test vector
    msg = b"abc"
    expected = golden_model.sm3_hash(msg)

    # Compute hash using DUT
    result = await sm3_hash_dut(dut, msg)

    # Compare
    dut._log.info(f"Message: {msg!r}")
    dut._log.info(f"Expected hash: 0x{expected:064x}")
    dut._log.info(f"Got hash     : 0x{result:064x}")

    assert result == expected, f"Hash mismatch! Expected 0x{expected:064x}, got 0x{result:064x}"

    dut._log.info("Test PASSED")


@cocotb.test()
async def test_sm3_16_bytes(dut):
    """Test SM3 with 16-byte input"""
    clock = Clock(dut.clk, 2, units="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)

    msg = b"abcd" * 4
    expected = golden_model.sm3_hash(msg)
    result = await sm3_hash_dut(dut, msg)

    dut._log.info(f"Message: {msg!r} (16 bytes)")
    dut._log.info(f"Expected hash: 0x{expected:064x}")
    dut._log.info(f"Got hash     : 0x{result:064x}")

    assert result == expected, f"Hash mismatch! Expected 0x{expected:064x}, got 0x{result:064x}"
    dut._log.info("Test PASSED")


@cocotb.test()
async def test_sm3_32_bytes(dut):
    """Test SM3 with 32-byte input (one 512-bit block after padding)"""
    clock = Clock(dut.clk, 2, units="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)

    msg = b"abcd" * 8
    expected = golden_model.sm3_hash(msg)
    result = await sm3_hash_dut(dut, msg)

    dut._log.info(f"Message: {msg!r} (32 bytes)")
    dut._log.info(f"Expected hash: 0x{expected:064x}")
    dut._log.info(f"Got hash     : 0x{result:064x}")

    assert result == expected, f"Hash mismatch! Expected 0x{expected:064x}, got 0x{result:064x}"
    dut._log.info("Test PASSED")


@cocotb.test()
async def test_sm3_64_bytes(dut):
    """Test SM3 with 64-byte input (two 512-bit blocks after padding)"""
    clock = Clock(dut.clk, 2, units="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)

    msg = b"abcd" * 16
    expected = golden_model.sm3_hash(msg)
    result = await sm3_hash_dut(dut, msg)

    dut._log.info(f"Message: {msg!r} (64 bytes)")
    dut._log.info(f"Expected hash: 0x{expected:064x}")
    dut._log.info(f"Got hash     : 0x{result:064x}")

    assert result == expected, f"Hash mismatch! Expected 0x{expected:064x}, got 0x{result:064x}"
    dut._log.info("Test PASSED")


@cocotb.test()
async def test_sm3_all_test_vectors(dut):
    """Run all test vectors from golden model"""
    clock = Clock(dut.clk, 2, units="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)

    all_passed = True

    for tv in golden_model.TEST_VECTORS:
        dut._log.info(f"Running test: {tv['name']}")
        dut._log.info(f"  Description: {tv['description']}")

        msg = tv['input']
        expected = tv['expected_int']

        result = await sm3_hash_dut(dut, msg)

        dut._log.info(f"  Expected hash: 0x{expected:064x}")
        dut._log.info(f"  Got hash     : 0x{result:064x}")

        if result == expected:
            dut._log.info(f"  Status: PASS")
        else:
            dut._log.info(f"  Status: FAIL")
            all_passed = False

        # Reset for next test
        await reset_dut(dut)

    assert all_passed, "Some test vectors failed!"
    dut._log.info("All test vectors PASSED")
