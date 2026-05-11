//=============================================================================
// sm3_fsm -- Control FSM for SM3 hash core
// Verilog-2005, synthesizable, two-block FSM with registered outputs
//=============================================================================

`timescale 1ns / 1ps
`default_nettype none

module sm3_fsm (
    input  wire       clk,
    input  wire       rst_n,          // active-low synchronous reset
    input  wire       msg_valid,
    input  wire       is_last,
    output wire       ready,
    output wire       load_en,
    output wire       calc_en,
    output wire       update_v_en,
    output wire [5:0] round_cnt,      // 0-63 during CALC
    output wire       hash_valid
);

    //-------------------------------------------------------------------------
    // State encoding
    //-------------------------------------------------------------------------
    localparam [1:0] STATE_IDLE = 2'd0;
    localparam [1:0] STATE_CALC = 2'd1;
    localparam [1:0] STATE_DONE = 2'd2;

    //-------------------------------------------------------------------------
    // Internal registers
    //-------------------------------------------------------------------------
    reg [1:0] state_reg, state_next;
    reg [6:0] cal_cycle_reg, cal_cycle_next;   // 0-65 (65 CALC cycles total)
    reg [5:0] round_cnt_reg, round_cnt_next;   // 0-63
    reg       is_last_latched_reg, is_last_latched_next;
    reg       ready_reg, ready_next;
    reg       load_en_reg, load_en_next;
    reg       calc_en_reg, calc_en_next;
    reg       update_v_en_reg, update_v_en_next;
    reg       hash_valid_reg, hash_valid_next;

    //-------------------------------------------------------------------------
    // Combinational next-state / output decode
    //-------------------------------------------------------------------------
    always @* begin
        // defaults: hold state, deassert strobes
        state_next        = state_reg;
        cal_cycle_next    = cal_cycle_reg;
        round_cnt_next    = round_cnt_reg;
        is_last_latched_next = is_last_latched_reg;
        ready_next        = 1'b0;
        load_en_next      = 1'b0;
        calc_en_next      = 1'b0;
        update_v_en_next  = 1'b0;
        hash_valid_next   = 1'b0;

        case (state_reg)

            STATE_IDLE: begin
                ready_next = 1'b1;
                // Assert hash_valid for 1 cycle in IDLE if last block was processed.
                // This happens after DONE→IDLE transition — V registers are already
                // updated by update_v_en in DONE cycle, so hash_out is valid now.
                if (is_last_latched_reg) begin
                    hash_valid_next   = 1'b1;
                    is_last_latched_next = 1'b0;  // clear after pulse
                end
                if (msg_valid && ready_reg) begin
                    state_next     = STATE_CALC;
                    cal_cycle_next = 7'd0;
                    round_cnt_next = 6'd0;
                    is_last_latched_next = is_last;
                end
            end

            STATE_CALC: begin
                if (cal_cycle_reg == 7'd0) begin
                    load_en_next = 1'b1;                    // cycle 0: load message
                end else if (cal_cycle_reg <= 7'd64) begin
                    calc_en_next   = 1'b1;                  // cycles 1-64: calculate
                    round_cnt_next = cal_cycle_reg - 7'd1;  // 0..63
                end
                cal_cycle_next = cal_cycle_reg + 7'd1;
                if (cal_cycle_reg == 7'd65) begin
                    state_next = STATE_DONE;
                end
            end

            STATE_DONE: begin
                update_v_en_next = 1'b1;                    // one cycle: update V registers (NBA)
                state_next       = STATE_IDLE;
                // hash_valid delayed to IDLE so V update is visible first
            end

            default: begin
                state_next = STATE_IDLE;
            end

        endcase
    end

    //-------------------------------------------------------------------------
    // Sequential register update
    //-------------------------------------------------------------------------
    always @(posedge clk) begin
        state_reg        <= state_next;
        cal_cycle_reg    <= cal_cycle_next;
        round_cnt_reg    <= round_cnt_next;
        is_last_latched_reg <= is_last_latched_next;
        ready_reg        <= ready_next;
        load_en_reg      <= load_en_next;
        calc_en_reg      <= calc_en_next;
        update_v_en_reg  <= update_v_en_next;
        hash_valid_reg   <= hash_valid_next;

        if (!rst_n) begin
            state_reg        <= STATE_IDLE;
            cal_cycle_reg    <= 7'd0;
            round_cnt_reg    <= 6'd0;
            is_last_latched_reg <= 1'b0;
            ready_reg        <= 1'b1;   // ready asserted in IDLE
            load_en_reg      <= 1'b0;
            calc_en_reg      <= 1'b0;
            update_v_en_reg  <= 1'b0;
            hash_valid_reg   <= 1'b0;
        end
    end

    //-------------------------------------------------------------------------
    // Output assignments
    //-------------------------------------------------------------------------
    assign ready      = ready_reg;
    assign load_en    = load_en_reg;
    assign calc_en    = calc_en_reg;
    assign update_v_en = update_v_en_reg;
    assign round_cnt  = round_cnt_reg;
    assign hash_valid = hash_valid_reg;

endmodule

`default_nettype wire
