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

    localparam [2:0] STATE_IDLE   = 3'd0;
    localparam [2:0] STATE_LOAD   = 3'd1;
    localparam [2:0] STATE_CALC   = 3'd2;
    localparam [2:0] STATE_UPDATE = 3'd3;
    localparam [2:0] STATE_DONE   = 3'd4;

    reg [2:0] state_reg = STATE_IDLE;
    reg [2:0] next_state;

    reg         is_last_latched_reg = 1'b0;
    reg         hash_valid_reg = 1'b0;
    reg [5:0]   round_cnt_reg = 6'd0;

    // =========================================================================
    // Combinational: next-state decode (Moore FSM)
    // =========================================================================
    always @* begin
        next_state = state_reg;
        case (state_reg)
            STATE_IDLE: begin
                if (msg_valid)
                    next_state = STATE_LOAD;
            end
            STATE_LOAD: begin
                next_state = STATE_CALC;
            end
            STATE_CALC: begin
                if (round_cnt_reg == 6'd63)
                    next_state = STATE_UPDATE;
            end
            STATE_UPDATE: begin
                next_state = STATE_DONE;
            end
            STATE_DONE: begin
                next_state = STATE_IDLE;
            end
            default: begin
                next_state = STATE_IDLE;
            end
        endcase
    end

    // =========================================================================
    // Combinational outputs (Moore: decode from state_reg)
    // =========================================================================
    assign ready       = (state_reg == STATE_IDLE) || (state_reg == STATE_DONE);
    assign load_en     = (state_reg == STATE_LOAD);
    assign calc_en     = (state_reg == STATE_CALC);
    assign update_v_en = (state_reg == STATE_UPDATE);

    // =========================================================================
    // Registered outputs
    // =========================================================================
    assign round_cnt  = round_cnt_reg;
    assign hash_valid = hash_valid_reg;

    // =========================================================================
    // Sequential: state update, counters, registered outputs
    // =========================================================================
    always @(posedge clk) begin
        if (!rst_n) begin
            state_reg           <= STATE_IDLE;
            round_cnt_reg       <= 6'd0;
            hash_valid_reg      <= 1'b0;
            is_last_latched_reg <= 1'b0;
        end else begin
            state_reg <= next_state;

            // round_cnt: reset entering CALC, increment in CALC, hold 0 otherwise
            if (state_reg == STATE_LOAD)
                round_cnt_reg <= 6'd0;
            else if (state_reg == STATE_CALC)
                round_cnt_reg <= round_cnt_reg + 6'd1;
            else
                round_cnt_reg <= 6'd0;

            // hash_valid: set when entering DONE, clear when leaving DONE
            if (state_reg == STATE_UPDATE)
                hash_valid_reg <= is_last_latched_reg;
            else if (state_reg == STATE_DONE)
                hash_valid_reg <= 1'b0;

            // Latch is_last at IDLE→LOAD handshake for use at DONE
            if (state_reg == STATE_IDLE && msg_valid)
                is_last_latched_reg <= is_last;
        end
    end

endmodule

`resetall
