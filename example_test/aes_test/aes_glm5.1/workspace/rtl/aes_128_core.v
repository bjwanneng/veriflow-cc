`resetall
`timescale 1ns / 1ps
`default_nettype none

module aes_128_core (
    input  wire         clk,
    input  wire         rst_n,
    input  wire         start,
    input  wire [127:0] data_in,
    input  wire [127:0] key_in,
    output wire [127:0] data_out,
    output wire         valid
);

    // -----------------------------------------------------------------------
    // FSM state encoding
    // -----------------------------------------------------------------------
    localparam [2:0] S_IDLE       = 3'd0,
                     S_ROUND_0   = 3'd1,
                     S_ROUND_1_9 = 3'd2,
                     S_ROUND_10  = 3'd3,
                     S_DONE      = 3'd4;

    // -----------------------------------------------------------------------
    // Internal registers
    // -----------------------------------------------------------------------
    reg [2:0]   state_fsm_reg;
    reg [127:0] state_reg;
    reg [127:0] key_reg;
    reg [3:0]   round_counter_reg;
    reg [127:0] data_out_reg;
    reg         valid_reg;

    // -----------------------------------------------------------------------
    // Output assignments (registered outputs)
    // -----------------------------------------------------------------------
    assign data_out = data_out_reg;
    assign valid    = valid_reg;

    // -----------------------------------------------------------------------
    // Combinational: round number fed to submodules
    // In ROUND_0 (counter=0): feed round_num=1 (round 1)
    // In ROUND_1_TO_9 (counter=1..9): feed round_num = counter+1
    //   When counter=9, round_num=10 (final round, skip MixColumns)
    // -----------------------------------------------------------------------
    wire [3:0]   round_num_wire;
    wire [127:0] round_key_wire;
    wire [127:0] round_result_wire;

    assign round_num_wire = round_counter_reg + 4'd1;

    // -----------------------------------------------------------------------
    // Submodule instances
    // -----------------------------------------------------------------------
    aes_key_expansion u_key_expansion (
        .key_in        (key_reg),
        .round_num     (round_num_wire),
        .round_key_out (round_key_wire)
    );

    aes_round_logic u_round_logic (
        .state_in  (state_reg),
        .round_key (round_key_wire),
        .round_num (round_num_wire),
        .state_out (round_result_wire)
    );

    // -----------------------------------------------------------------------
    // Sequential logic: FSM state + all register updates
    // -----------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_fsm_reg     <= S_IDLE;
            state_reg         <= 128'd0;
            key_reg           <= 128'd0;
            round_counter_reg <= 4'd0;
            data_out_reg      <= 128'd0;
            valid_reg         <= 1'b0;
        end else begin
            case (state_fsm_reg)
                S_IDLE: begin
                    valid_reg <= 1'b0;
                    if (start) begin
                        state_reg         <= data_in ^ key_in;
                        key_reg           <= key_in;
                        round_counter_reg <= 4'd0;
                        state_fsm_reg     <= S_ROUND_0;
                    end
                end

                S_ROUND_0: begin
                    // Round logic computes round 1 (SubBytes, ShiftRows,
                    // MixColumns, AddRoundKey with key_expansion(key, 1)).
                    // Result registered at this posedge.
                    state_reg         <= round_result_wire;
                    round_counter_reg <= 4'd1;
                    state_fsm_reg     <= S_ROUND_1_9;
                end

                S_ROUND_1_9: begin
                    // round_counter_reg is 1..9.
                    // round_num_wire = counter+1 gives 2..10.
                    // When counter=9, round_num=10 -> round_logic skips MixColumns.
                    state_reg         <= round_result_wire;
                    if (round_counter_reg == 4'd9) begin
                        round_counter_reg <= 4'd10;
                        state_fsm_reg     <= S_ROUND_10;
                    end else begin
                        round_counter_reg <= round_counter_reg + 4'd1;
                    end
                end

                S_ROUND_10: begin
                    // state_reg already holds the ciphertext from the
                    // previous posedge. Latch it into data_out_reg,
                    // assert valid for one cycle.
                    data_out_reg  <= state_reg;
                    valid_reg     <= 1'b1;
                    state_fsm_reg <= S_DONE;
                end

                S_DONE: begin
                    // Clear valid pulse, return to IDLE.
                    valid_reg     <= 1'b0;
                    state_fsm_reg <= S_IDLE;
                end

                default: begin
                    state_fsm_reg <= S_IDLE;
                    valid_reg     <= 1'b0;
                end
            endcase
        end
    end

endmodule

`resetall
