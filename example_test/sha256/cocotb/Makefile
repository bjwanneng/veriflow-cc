# Makefile for cocotb simulation of sha256_core
#
# Usage:
#   make              # Run all tests
#   make SIM=icarus   # Explicitly use Icarus Verilog
#   make clean        # Remove build artifacts
#
# Prerequisites:
#   cocotb >= 2.0, iverilog >= 14.0
#
# Note: Ensure iverilog/vvp are on PATH before running make.
#   export PATH="/c/oss-cad-suite/bin:$PATH"

# ─── Tool paths ───────────────────────────────────────────────────────────

COCOTB_CONFIG = /c/Users/wanneng.zhang/AppData/Roaming/Python/Python313/Scripts/cocotb-config

# ─── cocotb Configuration ─────────────────────────────────────────────────

TOPLEVEL_LANG ?= verilog
TOPLEVEL = sha256_core
MODULE = test_sha256_core

# RTL source (absolute path)
RTL_DIR = $(PWD)/../workspace/rtl
VERILOG_SOURCES = $(RTL_DIR)/sha256_core.v

# cocotb 2.0: enable VCD dumping
export COCOTB_VCD_DUMP = 1

# Use single-threaded test execution
export COCOTB_MAX_PARALLEL_TESTS = 1

# ─── iverilog-specific ────────────────────────────────────────────────────

COMPILE_ARGS = -g2012
SIM_ARGS =

# ─── Include cocotb Makefile ──────────────────────────────────────────────

include $(shell $(COCOTB_CONFIG) --makefiles)/Makefile.sim
