// -----------------------------------------------------------------------------
// File   : sm3_fsm.v
// Author : Zhang Wei
// Date   : 2026-04-27
// -----------------------------------------------------------------------------
// Description:
//   SM3 compression core control state machine. Manages the 64-round iteration
//   with IDLE/CALC/DONE/DONE_HOLD states. Generates load_en, calc_en, update_v_en,
//   and round_cnt control signals for the sm3_w_gen and sm3_compress datapath
//   modules. Handles the valid/ready/ack external handshake protocol.
// -----------------------------------------------------------------------------
// Change Log:
//   2026-04-27  Zhang Wei  v1.0  Initial release
// -----------------------------------------------------------------------------

`resetall
`timescale 1ns / 1ps
`default_nettype none

module sm3_fsm
(
    input  wire       clk,
    input  wire       rst,
    input  wire       msg_valid,
    input  wire       is_last,
    input  wire       ack,
    output wire       ready,
    output wire       load_en,
    output wire       calc_en,
    output wire       update_v_en,
    output wire [5:0] round_cnt,
    output wire       hash_valid
);

    // FSM state encoding
    localparam [1:0]
        STATE_IDLE      = 2'd0,
        STATE_CALC      = 2'd1,
        STATE_DONE      = 2'd2,
        STATE_DONE_HOLD = 2'd3;

    // Register declarations
    reg [1:0] state_reg       = STATE_IDLE, state_next;
    reg       ready_reg       = 1'b0,       ready_next;
    reg       load_en_reg     = 1'b0,       load_en_next;
    reg       calc_en_reg     = 1'b0,       calc_en_next;
    reg       update_v_en_reg = 1'b0,       update_v_en_next;
    reg       hash_valid_reg  = 1'b0,       hash_valid_next;
    reg [5:0] round_cnt_reg   = 6'd0,       round_cnt_next;
    reg       hash_pending_reg = 1'b0,      hash_pending_next;

    ////////////////////////////////////////////////////////////////////////////////
    // Combinational logic — next-state decode and output computation            //
    ////////////////////////////////////////////////////////////////////////////////

    always @* begin
        // Default values at top prevent latch inference
        state_next        = state_reg;
        ready_next        = 1'b0;
        load_en_next      = 1'b0;
        calc_en_next      = 1'b0;
        update_v_en_next  = 1'b0;
        hash_valid_next   = 1'b0;
        round_cnt_next    = round_cnt_reg;
        hash_pending_next = hash_pending_reg;

        case (state_reg)
            STATE_IDLE: begin
                ready_next     = 1'b1;
                round_cnt_next = 6'd0;
                if (msg_valid && ready_reg) begin
                    state_next   = STATE_CALC;
                    load_en_next = 1'b1;
                    ready_next   = 1'b0;
                end
            end

            STATE_CALC: begin
                calc_en_next = 1'b1;
                if (round_cnt_reg < 6'd63) begin
                    if (!load_en_reg) begin
                        round_cnt_next = round_cnt_reg + 6'd1;
                    end
                end else begin
                    state_next   = STATE_DONE;
                    calc_en_next = 1'b0;
                end
            end

            STATE_DONE: begin
                update_v_en_next  = 1'b1;
                hash_pending_next = 1'b0;
                if (is_last) begin
                    state_next = STATE_DONE_HOLD;
                end else begin
                    state_next = STATE_IDLE;
                end
            end

            STATE_DONE_HOLD: begin
                ready_next       = 1'b1;
                round_cnt_next   = 6'd0;
                if (!hash_pending_reg) begin
                    // First cycle in DONE_HOLD: wait for V update to settle
                    hash_valid_next   = 1'b0;
                    hash_pending_next = 1'b1;
                end else begin
                    // Subsequent cycles: assert hash_valid until ack
                    hash_valid_next = 1'b1;
                    if (ack) begin
                        hash_valid_next   = 1'b0;
                        hash_pending_next = 1'b0;
                        state_next        = STATE_IDLE;
                    end
                end
            end

            default: begin
                state_next = STATE_IDLE;
            end
        endcase
    end

    ////////////////////////////////////////////////////////////////////////////////
    // Sequential logic — register update with synchronous reset at end          //
    ////////////////////////////////////////////////////////////////////////////////

    always @(posedge clk) begin
        state_reg        <= state_next;
        ready_reg        <= ready_next;
        load_en_reg      <= load_en_next;
        calc_en_reg      <= calc_en_next;
        update_v_en_reg  <= update_v_en_next;
        hash_valid_reg   <= hash_valid_next;
        round_cnt_reg    <= round_cnt_next;
        hash_pending_reg <= hash_pending_next;

        if (rst) begin
            state_reg        <= STATE_IDLE;
            ready_reg        <= 1'b0;
            load_en_reg      <= 1'b0;
            calc_en_reg      <= 1'b0;
            update_v_en_reg  <= 1'b0;
            hash_valid_reg   <= 1'b0;
            round_cnt_reg    <= 6'd0;
            hash_pending_reg <= 1'b0;
        end
    end

    ////////////////////////////////////////////////////////////////////////////////
    // Output port assignments — drive outputs from internal _reg signals        //
    ////////////////////////////////////////////////////////////////////////////////

    assign ready       = ready_reg;
    assign load_en     = load_en_reg;
    assign calc_en     = calc_en_reg;
    assign update_v_en = update_v_en_reg;
    assign round_cnt   = round_cnt_reg;
    assign hash_valid  = hash_valid_reg;

endmodule

`resetall
