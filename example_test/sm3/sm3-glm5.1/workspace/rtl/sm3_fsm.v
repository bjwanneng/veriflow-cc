`resetall
`timescale 1ns/1ps
`default_nettype none

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
    output wire       hash_valid
);

    localparam [1:0] IDLE = 2'b00;
    localparam [1:0] CALC = 2'b01;
    localparam [1:0] DONE = 2'b10;

    // Registered state and outputs
    reg [1:0] state_reg;
    reg       ready_reg;
    reg       load_en_reg;
    reg       calc_en_reg;
    reg       update_v_en_reg;
    reg [5:0] round_cnt_reg;
    reg       hash_valid_reg;
    reg       first_calc_reg;
    reg       is_last_reg;

    // Combinational next-state
    reg [1:0] state_next;
    reg       ready_next;
    reg       load_en_next;
    reg       calc_en_next;
    reg       update_v_en_next;
    reg [5:0] round_cnt_next;
    reg       hash_valid_next;
    reg       first_calc_next;
    reg       is_last_next;

    // Drive ready combinationally from state_reg (immediate, no NBA delay)
    assign ready       = (state_reg == IDLE);
    assign load_en     = load_en_reg;
    assign calc_en     = calc_en_reg;
    assign update_v_en = update_v_en_reg;
    assign round_cnt   = round_cnt_reg;
    assign hash_valid  = hash_valid_reg;

    // Combinational next-state logic
    always @* begin
        // Defaults: hold state, deassert one-shot signals
        state_next       = state_reg;
        ready_next       = 1'b0;
        load_en_next     = 1'b0;
        calc_en_next     = 1'b0;
        update_v_en_next = 1'b0;
        round_cnt_next   = round_cnt_reg;
        hash_valid_next  = 1'b0;
        first_calc_next  = first_calc_reg;
        is_last_next     = is_last_reg;

        case (state_reg)
            IDLE: begin
                ready_next = 1'b1;
                round_cnt_next = 6'd0;
                if (msg_valid) begin
                    state_next       = CALC;
                    ready_next       = 1'b0;
                    load_en_next     = 1'b1;
                    first_calc_next  = 1'b1;
                    is_last_next     = is_last;
                end
            end

            CALC: begin
                calc_en_next = 1'b1;
                if (first_calc_reg) begin
                    first_calc_next = 1'b0;
                    // round_cnt stays 0 for the first full CALC cycle
                end else if (round_cnt_reg == 6'd63) begin
                    state_next       = DONE;
                    calc_en_next     = 1'b0;
                    update_v_en_next = 1'b1;
                end else begin
                    round_cnt_next = round_cnt_reg + 6'd1;
                end
            end

            DONE: begin
                state_next = IDLE;
                ready_next = 1'b1;
                if (is_last_reg) begin
                    hash_valid_next = 1'b1;
                end
            end

            default: begin
                state_next = IDLE;
            end
        endcase
    end

    // Sequential state register
    always @(posedge clk) begin
        if (!rst_n) begin
            state_reg       <= IDLE;
            ready_reg       <= 1'b0;
            load_en_reg     <= 1'b0;
            calc_en_reg     <= 1'b0;
            update_v_en_reg <= 1'b0;
            round_cnt_reg   <= 6'd0;
            hash_valid_reg  <= 1'b0;
            first_calc_reg  <= 1'b0;
            is_last_reg     <= 1'b0;
        end else begin
            state_reg       <= state_next;
            ready_reg       <= ready_next;
            load_en_reg     <= load_en_next;
            calc_en_reg     <= calc_en_next;
            update_v_en_reg <= update_v_en_next;
            round_cnt_reg   <= round_cnt_next;
            hash_valid_reg  <= hash_valid_next;
            first_calc_reg  <= first_calc_next;
            is_last_reg     <= is_last_next;
        end
    end

endmodule

`default_nettype wire
