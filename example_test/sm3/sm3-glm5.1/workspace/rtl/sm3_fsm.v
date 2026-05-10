// -----------------------------------------------------------------------------
// File   : sm3_fsm.v
// Author : VeriFlow-CC (vf-coder)
// Date   : 2026-05-09
// -----------------------------------------------------------------------------
// Description: FSM controller for SM3 hash core. Manages IDLE->LOAD->CALC->DONE
//              state transitions and generates load_en, calc_en, update_v_en
//              control pulses plus round_cnt[5:0] counter.
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

    // ---------------------------------------------------------------------
    // State encoding (one-hot compatible, binary encoded)
    // ---------------------------------------------------------------------
    localparam [1:0]
        STATE_IDLE = 2'd0,
        STATE_LOAD = 2'd1,
        STATE_CALC = 2'd2,
        STATE_DONE = 2'd3;

    // ---------------------------------------------------------------------
    // Internal registers (output wire + _reg pattern)
    // ---------------------------------------------------------------------
    reg [1:0] state_reg    = STATE_IDLE, state_next;
    reg       ready_reg    = 1'b1,       ready_next;
    reg       load_en_reg  = 1'b0,       load_en_next;
    reg       calc_en_reg  = 1'b0,       calc_en_next;
    reg       update_v_reg = 1'b0,       update_v_next;
    reg [5:0] round_cnt_reg = 6'd0,      round_cnt_next;
    reg       hash_valid_reg = 1'b0,     hash_valid_next;
    reg       is_last_reg  = 1'b0,       is_last_next;

    // ---------------------------------------------------------------------
    // Output wire assignments
    // ---------------------------------------------------------------------
    assign ready       = ready_reg;
    assign load_en     = load_en_reg;
    assign calc_en     = calc_en_reg;
    assign update_v_en = update_v_reg;
    assign round_cnt   = round_cnt_reg;
    assign hash_valid  = hash_valid_reg;

    // ---------------------------------------------------------------------
    // Block 1: Combinational next-state decode + output logic
    // ---------------------------------------------------------------------
    always @* begin
        // Default: hold current values (latch elimination)
        state_next      = state_reg;
        ready_next      = ready_reg;
        load_en_next    = 1'b0;
        calc_en_next    = 1'b0;
        update_v_next   = 1'b0;
        round_cnt_next  = round_cnt_reg;
        hash_valid_next = 1'b0;
        is_last_next    = is_last_reg;

        case (state_reg)
            STATE_IDLE: begin
                ready_next = 1'b1;
                if (msg_valid) begin
                    state_next   = STATE_LOAD;
                    ready_next   = 1'b0;
                    is_last_next = is_last;
                end
            end

            STATE_LOAD: begin
                load_en_next   = 1'b1;
                round_cnt_next = 6'd0;
                state_next     = STATE_CALC;
            end

            STATE_CALC: begin
                if (round_cnt_reg == 6'd63) begin
                    state_next = STATE_DONE;
                end else begin
                    calc_en_next = 1'b1;
                    if (calc_en_reg) begin
                        round_cnt_next = round_cnt_reg + 6'd1;
                    end
                end
            end

            STATE_DONE: begin
                update_v_next   = 1'b1;
                hash_valid_next = is_last_reg;
                state_next      = STATE_IDLE;
            end

            default: begin
                state_next = STATE_IDLE;
            end
        endcase
    end

    // ---------------------------------------------------------------------
    // Block 2: Sequential register update (async active-low reset)
    // ---------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_reg      <= STATE_IDLE;
            ready_reg      <= 1'b1;
            load_en_reg    <= 1'b0;
            calc_en_reg    <= 1'b0;
            update_v_reg   <= 1'b0;
            round_cnt_reg  <= 6'd0;
            hash_valid_reg <= 1'b0;
            is_last_reg    <= 1'b0;
        end else begin
            state_reg      <= state_next;
            ready_reg      <= ready_next;
            load_en_reg    <= load_en_next;
            calc_en_reg    <= calc_en_next;
            update_v_reg   <= update_v_next;
            round_cnt_reg  <= round_cnt_next;
            hash_valid_reg <= hash_valid_next;
            is_last_reg    <= is_last_next;
        end
    end

endmodule

`resetall
