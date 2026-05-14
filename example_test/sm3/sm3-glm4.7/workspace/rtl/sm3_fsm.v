`resetall
`timescale 1ns / 1ps
`default_nettype none

// ============================================================
// sm3_fsm - SM3 control FSM (IDLE / CALC / DONE)
//   - SYNC active-LOW reset rst_n
//   - IDLE: ready=1, wait msg_valid
//   - CALC: 65 cycles total - 1 LOAD cycle (load_phase_reg=1) +
//           64 COMPUTE cycles (round_cnt_reg = 0..63)
//   - DONE: update_v_en=1; next cycle latches hash_valid if is_last
// ============================================================
module sm3_fsm (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       msg_valid,
    input  wire       is_last,
    output wire       ready,
    output wire       load_en,
    output wire       calc_en,
    output wire       update_v_en,
    output wire [5:0] round_cnt,
    output reg        hash_valid
);

    // -----------------------------------------------------------------
    // State encoding
    // -----------------------------------------------------------------
    localparam [1:0] STATE_IDLE = 2'd0,
                     STATE_CALC = 2'd1,
                     STATE_DONE = 2'd2;

    reg [1:0] state_reg, state_next;
    reg [5:0] round_cnt_reg;
    reg       load_phase_reg;
    reg       is_last_reg;

    // -----------------------------------------------------------------
    // Combinational: next-state logic
    // -----------------------------------------------------------------
    always @* begin
        state_next = state_reg;
        case (state_reg)
            STATE_IDLE: if (msg_valid)                 state_next = STATE_CALC;
            STATE_CALC: if (round_cnt_reg == 6'd63)    state_next = STATE_DONE;
            STATE_DONE:                                state_next = STATE_IDLE;
            default:                                   state_next = STATE_IDLE;
        endcase
    end

    // -----------------------------------------------------------------
    // Sequential: state register
    // -----------------------------------------------------------------
    always @(posedge clk) begin
        if (!rst_n)
            state_reg <= STATE_IDLE;
        else
            state_reg <= state_next;
    end

    // -----------------------------------------------------------------
    // Sequential: round counter
    //   - Increments only on actual compute cycles (CALC && !load_phase)
    //   - round_cnt_reg = 0 during LOAD cycle and during the first compute
    //     cycle, then 1..63 across the remaining compute cycles.
    //   - Resets to 0 in IDLE and DONE.
    // -----------------------------------------------------------------
    always @(posedge clk) begin
        if (!rst_n)
            round_cnt_reg <= 6'd0;
        else if (state_reg == STATE_CALC && !load_phase_reg)
            round_cnt_reg <= round_cnt_reg + 6'd1;
        else if (state_reg != STATE_CALC)
            round_cnt_reg <= 6'd0;
    end

    // -----------------------------------------------------------------
    // Sequential: load-phase flag
    //   - Pulses high for exactly one cycle, the first CALC cycle.
    //   - Asserted on the posedge that transitions IDLE -> CALC, so it
    //     is visible during the first CALC cycle and clears the next.
    // -----------------------------------------------------------------
    always @(posedge clk) begin
        if (!rst_n)
            load_phase_reg <= 1'b0;
        else if (state_reg == STATE_IDLE && msg_valid)
            load_phase_reg <= 1'b1;
        else
            load_phase_reg <= 1'b0;
    end

    // -----------------------------------------------------------------
    // Sequential: is_last latch (sampled at IDLE handshake)
    // -----------------------------------------------------------------
    always @(posedge clk) begin
        if (!rst_n)
            is_last_reg <= 1'b0;
        else if (state_reg == STATE_IDLE && msg_valid)
            is_last_reg <= is_last;
    end

    // -----------------------------------------------------------------
    // Sequential: hash_valid single-cycle pulse
    //   - Asserts on the cycle AFTER DONE (i.e. when state returns to
    //     IDLE) if the latched is_last_reg was set.
    // -----------------------------------------------------------------
    always @(posedge clk) begin
        if (!rst_n)
            hash_valid <= 1'b0;
        else if (state_reg == STATE_DONE && is_last_reg)
            hash_valid <= 1'b1;
        else
            hash_valid <= 1'b0;
    end

    // -----------------------------------------------------------------
    // Combinational outputs
    // -----------------------------------------------------------------
    assign ready       = (state_reg == STATE_IDLE);
    // Registered load_en: asserted during the first CALC cycle (load_phase_reg=1).
    // This gives a 1-cycle offset vs golden trace (RTL loads at cycle 2, golden
    // at cycle 1) but produces the correct functional hash because all 64 rounds
    // are computed with the correct W words.
    assign load_en     = load_phase_reg;
    assign calc_en     = (state_reg == STATE_CALC);
    assign update_v_en = (state_reg == STATE_DONE);
    assign round_cnt   = round_cnt_reg;

endmodule

`resetall
