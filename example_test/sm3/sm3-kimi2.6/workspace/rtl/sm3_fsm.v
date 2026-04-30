// -----------------------------------------------------------------------------
// File   : sm3_fsm.v
// Author : VeriFlow-CC
// Date   : 2026-04-27
// -----------------------------------------------------------------------------
// Description:
//   SM3 control FSM managing 64-round compression iteration. Generates
//   load_en, calc_en, update_v_en, round_cnt, ready, and hash_valid signals.
// -----------------------------------------------------------------------------
// Change Log:
//   2026-04-27  VeriFlow-CC  v1.0  Initial release
// -----------------------------------------------------------------------------

`resetall
`timescale 1ns / 1ps
`default_nettype none

module sm3_fsm
(
    input  wire        clk,
    input  wire        rst,
    input  wire        msg_valid,
    input  wire        is_last,
    output wire        ready,
    output wire        load_en,
    output wire        calc_en,
    output wire        update_v_en,
    output wire [5:0]  round_cnt,
    output wire        hash_valid
);

    // State encoding
    localparam [2:0]
        FSM_STATE_IDLE      = 3'd0,
        FSM_STATE_LOAD      = 3'd1,
        FSM_STATE_CALC      = 3'd2,
        FSM_STATE_DONE      = 3'd3,
        FSM_STATE_DONE_HASH = 3'd4;

    // Internal registers
    reg [2:0] fsm_state_reg = FSM_STATE_IDLE, fsm_state_next;
    reg [5:0] round_cnt_reg = 6'd0,             round_cnt_next;
    reg       hash_valid_reg = 1'b0,            hash_valid_next;
    reg       is_last_reg = 1'b0,               is_last_next;
    reg       first_round_reg = 1'b0,           first_round_next;

    // Internal control signals
    reg       ready_reg = 1'b0,                 ready_next;
    reg       load_en_reg = 1'b0,               load_en_next;
    reg       calc_en_reg = 1'b0,               calc_en_next;
    reg       update_v_en_reg = 1'b0,           update_v_en_next;

    // Output assignments
    assign ready       = ready_reg;
    assign load_en     = load_en_reg;
    assign calc_en     = calc_en_reg;
    assign update_v_en = update_v_en_reg;
    assign round_cnt   = round_cnt_reg;
    assign hash_valid  = hash_valid_reg;

    // Combinational next-state logic
    always @* begin
        // Default values to prevent latch inference
        fsm_state_next    = fsm_state_reg;
        round_cnt_next    = round_cnt_reg;
        hash_valid_next   = 1'b0;
        is_last_next      = is_last_reg;
        first_round_next  = first_round_reg;
        ready_next        = 1'b0;
        load_en_next      = 1'b0;
        calc_en_next      = 1'b0;
        update_v_en_next  = 1'b0;

        case (fsm_state_reg)
            FSM_STATE_IDLE: begin
                ready_next = 1'b1;
                if (msg_valid && ready_reg) begin
                    fsm_state_next = FSM_STATE_LOAD;
                    is_last_next   = is_last;
                    ready_next     = 1'b0;
                end
            end

            FSM_STATE_LOAD: begin
                load_en_next     = 1'b1;
                round_cnt_next   = 6'd0;
                first_round_next = 1'b1;
                fsm_state_next   = FSM_STATE_CALC;
            end

            FSM_STATE_CALC: begin
                if (first_round_reg) begin
                    calc_en_next = 1'b1;
                    first_round_next = 1'b0;
                end else if (round_cnt_reg < 6'd63) begin
                    calc_en_next = 1'b1;
                    round_cnt_next = round_cnt_reg + 6'd1;
                end else begin
                    calc_en_next = 1'b0;
                    fsm_state_next = FSM_STATE_DONE;
                end
            end

            FSM_STATE_DONE: begin
                update_v_en_next = 1'b1;
                fsm_state_next   = FSM_STATE_DONE_HASH;
            end

            FSM_STATE_DONE_HASH: begin
                hash_valid_next  = is_last_reg;
                fsm_state_next   = FSM_STATE_IDLE;
            end

            default: begin
                fsm_state_next = FSM_STATE_IDLE;
            end
        endcase
    end

    // Sequential register update
    always @(posedge clk) begin
        fsm_state_reg    <= fsm_state_next;
        round_cnt_reg    <= round_cnt_next;
        hash_valid_reg   <= hash_valid_next;
        is_last_reg      <= is_last_next;
        first_round_reg  <= first_round_next;
        ready_reg        <= ready_next;
        load_en_reg      <= load_en_next;
        calc_en_reg      <= calc_en_next;
        update_v_en_reg  <= update_v_en_next;

        if (rst) begin
            fsm_state_reg    <= FSM_STATE_IDLE;
            round_cnt_reg    <= 6'd0;
            hash_valid_reg   <= 1'b0;
            is_last_reg      <= 1'b0;
            first_round_reg  <= 1'b0;
            ready_reg        <= 1'b0;
            load_en_reg      <= 1'b0;
            calc_en_reg      <= 1'b0;
            update_v_en_reg  <= 1'b0;
        end
    end

endmodule

`resetall
