"""Test new NBA lint rules L11/L12 — timing contract violations.

Bug patterns from SM3:
  L11: hash_valid asserted same cycle as hash_out_reg NBA update
  L12: hash_valid pulse and V registers updated in same NBA block
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from veriflow_dsl.lint_nba import (
    _check_valid_data_same_cycle_nba,
    _check_pulse_clears_data_same_cycle,
    LintError,
)


# ---------------------------------------------------------------------------
# L11: valid signal and data register updated in same always @(posedge clk)
# ---------------------------------------------------------------------------

L11_BAD_HASH = '''
module sm3_core;
    reg [255:0] V_reg;
    reg hash_valid_reg;

    always @(posedge clk) begin
        if (state == DONE) begin
            V_reg <= V_next;
            hash_valid_reg <= 1'b1;
        end
    end
endmodule
'''

L11_GOOD_SEPARATED = '''
module sm3_core;
    reg [255:0] V_reg;
    reg hash_valid_reg;

    always @(posedge clk) begin
        if (update_v_en)
            V_reg <= V_next;
    end

    always @(posedge clk) begin
        if (state == DONE)
            hash_valid_reg <= 1'b1;
    end
endmodule
'''

L11_GOOD_NO_VALID = '''
module sm3_core;
    reg [255:0] V_reg;

    always @(posedge clk) begin
        if (update_v_en)
            V_reg <= V_next;
    end
endmodule
'''


def test_l11_catches_hash_valid_same_cycle():
    errs = _check_valid_data_same_cycle_nba(L11_BAD_HASH)
    assert len(errs) >= 1, f"Expected L11 error, got: {errs}"
    assert any(e.rule == "L11_valid_data_same_cycle_nba" for e in errs)


def test_l11_passes_separated_blocks():
    errs = _check_valid_data_same_cycle_nba(L11_GOOD_SEPARATED)
    assert len(errs) == 0, f"Unexpected L11 errors: {errs}"


def test_l11_passes_no_valid_signal():
    errs = _check_valid_data_same_cycle_nba(L11_GOOD_NO_VALID)
    assert len(errs) == 0


# ---------------------------------------------------------------------------
# L12: pulse signal (valid/done) and data cleared/updated same cycle
# ---------------------------------------------------------------------------

L12_BAD_PULSE_CLEARS_DATA = '''
module sm3_core;
    reg [255:0] hash_out_reg;
    reg hash_valid_reg;

    always @(posedge clk) begin
        if (state == DONE) begin
            hash_valid_reg <= 1'b1;
            hash_out_reg <= hash_next;
        end
        else begin
            hash_valid_reg <= 1'b0;
        end
    end
endmodule
'''

L12_GOOD_PULSE_LATE_DATA = '''
module sm3_core;
    reg [255:0] hash_out_reg;
    reg hash_valid_reg;

    always @(posedge clk) begin
        if (state == DONE)
            hash_valid_reg <= 1'b1;
        else
            hash_valid_reg <= 1'b0;
    end

    always @(posedge clk) begin
        hash_out_reg <= hash_next;
    end
endmodule
'''


def test_l12_catches_pulse_data_same_cycle():
    errs = _check_pulse_clears_data_same_cycle(L12_BAD_PULSE_CLEARS_DATA)
    assert len(errs) >= 1, f"Expected L12 error, got: {errs}"
    assert any(e.rule == "L12_pulse_clears_data_same_cycle" for e in errs)


def test_l12_passes_separated():
    errs = _check_pulse_clears_data_same_cycle(L12_GOOD_PULSE_LATE_DATA)
    assert len(errs) == 0, f"Unexpected L12 errors: {errs}"


if __name__ == "__main__":
    test_l11_catches_hash_valid_same_cycle()
    print("[PASS] test_l11_catches_hash_valid_same_cycle")

    test_l11_passes_separated_blocks()
    print("[PASS] test_l11_passes_separated_blocks")

    test_l11_passes_no_valid_signal()
    print("[PASS] test_l11_passes_no_valid_signal")

    test_l12_catches_pulse_data_same_cycle()
    print("[PASS] test_l12_catches_pulse_data_same_cycle")

    test_l12_passes_separated()
    print("[PASS] test_l12_passes_separated")

    print("ALL LINT TIMING CONTRACT TESTS PASSED")
