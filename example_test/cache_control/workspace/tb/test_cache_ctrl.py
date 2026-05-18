#!/usr/bin/env python3
"""Cocotb testbench for 4-way set-associative write-back cache controller.

Compares DUT behaviour against the golden model on all TEST_VECTORS.
Memory model: combinational read (0-latency), sequential write capture.
"""

import os
import sys

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ReadOnly, Timer

# ---------------------------------------------------------------------------
# Golden model import
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "workspace", "docs"))
from golden_model import CacheModel, TEST_VECTORS, compute, decode_addr

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------
CLK_PERIOD_NS = 5
RST_CYCLES    = 5

# ---------------------------------------------------------------------------
# Backing memory model
# ---------------------------------------------------------------------------
class BackingMemory:
    def __init__(self):
        self.mem = {}

    def write_line(self, base_addr, data128):
        for w in range(4):
            word_addr = base_addr + w * 4
            shift = (3 - w) * 32
            self.mem[word_addr] = (data128 >> shift) & 0xFFFFFFFF

    def read_line(self, base_addr):
        line = 0
        for w in range(4):
            word_addr = base_addr + w * 4
            word_val = self.mem.get(word_addr, 0)
            shift = (3 - w) * 32
            line |= (word_val & 0xFFFFFFFF) << shift
        return line

# ---------------------------------------------------------------------------
# Memory responder coroutine (combinational read model)
# ---------------------------------------------------------------------------
async def memory_responder(dut, bkmem):
    """Continuously drive m_rdata based on m_addr (combinational read).
    Also captures writes (m_wr_en) into the backing memory.
    """
    while True:
        await RisingEdge(dut.clk)
        # After posedge: NBA values are now visible
        # Capture write-back data
        if int(dut.m_wr_en.value):
            bkmem.write_line(int(dut.m_addr.value), int(dut.m_wdata.value))
        # Provide read data for next posedge (0-cycle latency model)
        addr = int(dut.m_addr.value)
        dut.m_rdata.value = bkmem.read_line(addr) & ((1 << 128) - 1)

# ---------------------------------------------------------------------------
# DUT driver helpers
# ---------------------------------------------------------------------------
async def reset_dut(dut):
    dut.rst.value = 1
    dut.addr.value = 0
    dut.wdata.value = 0
    dut.byte_en.value = 0
    dut.mem_read.value = 0
    dut.mem_write.value = 0
    dut.m_rdata.value = 0
    for _ in range(RST_CYCLES):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)


async def drive_operation(dut, bkmem, addr, wdata, byte_en, is_read, is_write):
    """Drive a single cache request and wait until ready == 1.

    Returns the rdata value sampled when ready first goes high.
    """
    dut.addr.value = addr & 0xFFFFFFFF
    dut.wdata.value = wdata & 0xFFFFFFFF
    dut.byte_en.value = byte_en & 0xF
    dut.mem_read.value = int(is_read)
    dut.mem_write.value = int(is_write)

    await RisingEdge(dut.clk)

    dut.mem_read.value = 0
    dut.mem_write.value = 0

    max_wait = 50
    for _ in range(max_wait):
        await ReadOnly()
        if int(dut.ready.value):
            return int(dut.rdata.value)
        await RisingEdge(dut.clk)

    raise TimeoutError("ready never went high within timeout")

# ---------------------------------------------------------------------------
# Per-vector test runner
# ---------------------------------------------------------------------------
async def run_test_vector(dut, tv_name, tv):
    bkmem = BackingMemory()
    cocotb.start_soon(memory_responder(dut, bkmem))

    golden_ops = tv["ops"]
    expected = compute(golden_ops, trace=False)

    await reset_dut(dut)

    got_results = []
    for op in golden_ops:
        addr    = op["addr"] & 0xFFFFFFFF
        wdata   = op.get("wdata", 0) & 0xFFFFFFFF
        byte_en = op.get("byte_en", 0) & 0xF
        is_read  = (op["op"] == "read")
        is_write = (op["op"] == "write")

        rdata = await drive_operation(dut, bkmem, addr, wdata, byte_en,
                                      is_read, is_write)
        got_results.append({"addr": addr, "rdata": rdata, "ready": 1})

    all_ok = True
    msgs = []
    for i, (got, want) in enumerate(zip(got_results, expected)):
        if got["rdata"] != want["rdata"]:
            all_ok = False
            msgs.append(
                f"  op[{i}] addr=0x{want['addr']:08X}: "
                f"rdata got=0x{got['rdata']:08X}, want=0x{want['rdata']:08X}"
            )

    status = "PASS" if all_ok else "FAIL"
    dut._log.info(f"[{status}] {tv_name}: {tv['description']}")
    for m in msgs:
        dut._log.info(m)

    assert all_ok, f"{tv_name} FAILED"

# ---------------------------------------------------------------------------
# Top-level test
# ---------------------------------------------------------------------------
@cocotb.test(timeout_time=200, timeout_unit="ms")
async def test_all_vectors(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())

    total_pass = 0
    total_fail = 0
    for tv_name, tv in TEST_VECTORS.items():
        try:
            await run_test_vector(dut, tv_name, tv)
            total_pass += 1
        except AssertionError:
            total_fail += 1

    dut._log.info("=" * 60)
    dut._log.info(f"SUMMARY: {total_pass} PASS, {total_fail} FAIL out of "
                  f"{total_pass + total_fail} test vectors")
    dut._log.info("=" * 60)
    assert total_fail == 0, f"{total_fail} test vector(s) FAILED"

# ---------------------------------------------------------------------------
# Individual per-vector tests
# ---------------------------------------------------------------------------
def _make_test(tv_name):
    async def _test(dut):
        cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
        await run_test_vector(dut, tv_name, TEST_VECTORS[tv_name])
    _test.__name__ = f"test_{tv_name}"
    _test.__qualname__ = f"test_{tv_name}"
    return cocotb.test(timeout_time=50, timeout_unit="ms")(_test)

for _tv_name in TEST_VECTORS:
    globals()[f"test_{_tv_name}"] = _make_test(_tv_name)
