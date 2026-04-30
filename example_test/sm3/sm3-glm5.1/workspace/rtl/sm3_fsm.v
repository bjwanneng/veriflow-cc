// -----------------------------------------------------------------------------
// File   : sm3_fsm.v
// Author : VeriFlow-CC
// Date   : 2026-04-27
// -----------------------------------------------------------------------------
// Description:
//   Control state machine for SM3 core. Manages 64-round iteration with
//   four states: IDLE, LOAD, CALC, UPDATE. Generates load_en, calc_en,
//   update_v_en, round_cnt, ready, and hash_valid control signals.
//   Uses synchronous active-low reset (rst_n) per microarchitecture spec.
// -----------------------------------------------------------------------------
// Change Log:
//   2026-04-27  VeriFlow-CC  v1.0  Initial release
// -----------------------------------------------------------------------------

`resetall
`timescale 1ns / 1ps
`default_nettype none

module sm3_fsm
(
    input  wire       clk,
    input  wire       rst_n,
    input  wire       msg_valid,
    input  wire       is_last,
    output wire       ready,
    output wire       load_en,
    output wire       calc_en,
    output wire       update_v_en,
    output wire [5:0] round_cnt,
    output wire       hash_valid
);

    /////////////////////////////////////////////////////////////////////////
    // State Encoding                                                     //
    /////////////////////////////////////////////////////////////////////////
    localparam [1:0]
        FSM_STATE_IDLE   = 2'b00,
        FSM_STATE_LOAD   = 2'b01,
        FSM_STATE_CALC   = 2'b10,
        FSM_STATE_UPDATE = 2'b11;

    /////////////////////////////////////////////////////////////////////////
    // Internal Registers                                                 //
    /////////////////////////////////////////////////////////////////////////
    reg [1:0] state_reg    = FSM_STATE_IDLE, state_next;
    reg [5:0] round_cnt_reg = 6'd0,          round_cnt_next;
    reg       is_last_reg  = 1'b0,           is_last_next;

    /////////////////////////////////////////////////////////////////////////
    // Output Registers                                                   //
    /////////////////////////////////////////////////////////////////////////
    reg ready_reg        = 1'b0, ready_next;
    reg load_en_reg      = 1'b0, load_en_next;
    reg calc_en_reg      = 1'b0, calc_en_next;
    reg update_v_en_reg  = 1'b0, update_v_en_next;
    reg hash_valid_reg   = 1'b0, hash_valid_next;

    /////////////////////////////////////////////////////////////////////////
    // Output Assignments                                                 //
    /////////////////////////////////////////////////////////////////////////
    assign ready       = ready_reg;
    assign load_en     = load_en_reg;
    assign calc_en     = calc_en_reg;
    assign update_v_en = update_v_en_reg;
    assign round_cnt   = round_cnt_reg;
    assign hash_valid  = hash_valid_reg;

    /////////////////////////////////////////////////////////////////////////
    // Combinational Logic — Next State and Output Decode                 //
    /////////////////////////////////////////////////////////////////////////
    always @* begin
        // Default values — prevent latches
        state_next       = state_reg;
        round_cnt_next   = round_cnt_reg;
        is_last_next     = is_last_reg;
        ready_next       = 1'b0;
        load_en_next     = 1'b0;
        calc_en_next     = 1'b0;
        update_v_en_next = 1'b0;
        hash_valid_next  = 1'b0;

        case (state_reg)
            FSM_STATE_IDLE: begin
                ready_next = 1'b1;
                if (msg_valid) begin
                    is_last_next = is_last;
                    load_en_next = 1'b1;
                    ready_next   = 1'b0;
                    state_next   = FSM_STATE_LOAD;
                end
            end

            FSM_STATE_LOAD: begin
                calc_en_next   = 1'b1;
                round_cnt_next = 6'd0;
                state_next     = FSM_STATE_CALC;
            end

            FSM_STATE_CALC: begin
                calc_en_next = 1'b1;
                if (round_cnt_reg == 6'd63) begin
                    calc_en_next   = 1'b0;
                    update_v_en_next = 1'b1;
                    state_next     = FSM_STATE_UPDATE;
                end else begin
                    round_cnt_next = round_cnt_reg + 6'd1;
                end
            end

            FSM_STATE_UPDATE: begin
                if (is_last_reg) begin
                    hash_valid_next = 1'b1;
                end else begin
                    ready_next = 1'b1;
                end
                state_next = FSM_STATE_IDLE;
            end

            default: state_next = FSM_STATE_IDLE;
        endcase
    end

    /////////////////////////////////////////////////////////////////////////
    // Sequential Logic — Register Update with Synchronous Active-Low Reset
    /////////////////////////////////////////////////////////////////////////
    always @(posedge clk) begin
        state_reg       <= state_next;
        round_cnt_reg   <= round_cnt_next;
        is_last_reg     <= is_last_next;
        ready_reg       <= ready_next;
        load_en_reg     <= load_en_next;
        calc_en_reg     <= calc_en_next;
        update_v_en_reg <= update_v_en_next;
        hash_valid_reg  <= hash_valid_next;

        if (!rst_n) begin
            state_reg       <= FSM_STATE_IDLE;
            round_cnt_reg   <= 6'd0;
            is_last_reg     <= 1'b0;
            ready_reg       <= 1'b0;
            load_en_reg     <= 1'b0;
            calc_en_reg     <= 1'b0;
            update_v_en_reg <= 1'b0;
            hash_valid_reg  <= 1'b0;
        end
    end

endmodule

`resetall
