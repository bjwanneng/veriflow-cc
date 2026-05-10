# Makefile for cocotb SM3 verification
MODULE ?= test_sm3_core
TOPLEVEL := sm3_core
TOPLEVEL_LANG ?= verilog

VERILOG_SOURCES := $(PWD)/../rtl/sm3_core.v \
                   $(PWD)/../rtl/sm3_fsm.v \
                   $(PWD)/../rtl/sm3_w_gen.v \
                   $(PWD)/../rtl/sm3_compress.v

COMPILE_ARGS := -g2005 -Wall

SIM ?= icarus

include $(shell cocotb-config --makefiles)/Makefile.sim
