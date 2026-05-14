`resetall
`timescale 1ns / 1ps
`default_nettype none

// =============================================================================
// aes_128_core — AES-128 Encryption Core (Top Module)
//
// Architecture: FSM + round-iterative (not fully pipelined).
//   1 cycle per round, 10 rounds total + 1 initial AddRoundKey.
//   Total pipeline delay: 11 cycles (start to valid).
//
// FSM: IDLE -> ROUND_0 -> ROUND_1TO9 -> ROUND_10 -> DONE -> IDLE
//
// Submodules: aes_key_expansion (on-the-fly round key), aes_round_logic
//   (SubBytes + ShiftRows + MixColumns + AddRoundKey, combinational).
// =============================================================================

module aes_128_core(
    input  wire          clk,
    input  wire          rst_n,       // async reset, active LOW
    input  wire          start,       // pulse: 1 cycle to start encryption
    input  wire [127:0]  data_in,     // 128-bit plaintext
    input  wire [127:0]  key_in,      // 128-bit cipher key
    output wire [127:0]  data_out,    // 128-bit ciphertext (registered)
    output wire          valid        // pulse: 1 cycle when data_out is valid (registered)
);

    // =========================================================================
    // FSM State Encoding
    // =========================================================================
    localparam [2:0] STATE_IDLE       = 3'd0;
    localparam [2:0] STATE_ROUND_0    = 3'd1;
    localparam [2:0] STATE_ROUND_1TO9 = 3'd2;
    localparam [2:0] STATE_ROUND_10   = 3'd3;
    localparam [2:0] STATE_DONE       = 3'd4;

    // =========================================================================
    // Internal Registers
    // =========================================================================
    reg [127:0] state_reg;
    reg [127:0] key_reg;
    reg [3:0]   round_reg;
    reg         valid_reg;
    reg [127:0] data_out_reg;
    reg [2:0]   fsm_reg;

    // =========================================================================
    // Next-State Wires (driven by combinational always @*)
    // =========================================================================
    reg [127:0] state_next;
    reg [127:0] key_next;
    reg [3:0]   round_next;
    reg         valid_next;
    reg [127:0] data_out_next;
    reg [2:0]   fsm_next;

    // =========================================================================
    // Submodule Interconnect Wires
    // =========================================================================
    wire [127:0] round_key;        // from aes_key_expansion
    wire [127:0] round_state_out;  // from aes_round_logic

    // =========================================================================
    // Submodule Instantiations
    // =========================================================================

    // On-the-fly key expansion: computes round key for current round_reg
    aes_key_expansion u_key_exp (
        .key_in    (key_reg),
        .round     (round_reg),
        .round_key (round_key)
    );

    // Combinational round logic: SubBytes -> ShiftRows -> (MixColumns) -> AddRoundKey
    aes_round_logic u_round_logic (
        .state_in  (state_reg),
        .round_key (round_key),
        .round     (round_reg),
        .state_out (round_state_out)
    );

    // =========================================================================
    // Combinational Next-State Logic (always @*)
    //
    // Blocking assignments (=) for all next-state wires.
    // Default: hold current register value. Each state overrides as needed.
    // =========================================================================
    always @* begin
        // Default: hold current values
        fsm_next      = STATE_IDLE;
        state_next    = state_reg;
        key_next      = key_reg;
        round_next    = round_reg;
        valid_next    = valid_reg;
        data_out_next = data_out_reg;

        case (fsm_reg)
            // -----------------------------------------------------------------
            // IDLE: wait for start pulse. On start, capture plaintext + key.
            // -----------------------------------------------------------------
            STATE_IDLE: begin
                if (start) begin
                    fsm_next   = STATE_ROUND_0;
                    state_next = data_in;
                    key_next   = key_in;
                    round_next = 4'd0;
                end else begin
                    fsm_next = STATE_IDLE;
                end
            end

            // -----------------------------------------------------------------
            // ROUND_0: initial AddRoundKey only (XOR state with original key).
            //   round_key = key_exp(key_reg, 0) = key_reg (identity)
            //   state_next = state_reg ^ round_key = data_in ^ key_in
            // -----------------------------------------------------------------
            STATE_ROUND_0: begin
                fsm_next   = STATE_ROUND_1TO9;
                state_next = state_reg ^ round_key;
                round_next = 4'd1;
            end

            // -----------------------------------------------------------------
            // ROUND_1TO9: full rounds 1 through 9 (each includes MixColumns).
            //   round_reg increments 1->9. At round_reg==9, next is ROUND_10.
            // -----------------------------------------------------------------
            STATE_ROUND_1TO9: begin
                state_next = round_state_out;
                round_next = round_reg + 4'd1;
                if (round_reg == 4'd9) begin
                    fsm_next = STATE_ROUND_10;
                end else begin
                    fsm_next = STATE_ROUND_1TO9;
                end
            end

            // -----------------------------------------------------------------
            // ROUND_10: final round (NO MixColumns in round_logic when round=10).
            //   Capture final cipher into data_out_next. Assert valid_next.
            // -----------------------------------------------------------------
            STATE_ROUND_10: begin
                fsm_next      = STATE_DONE;
                state_next    = round_state_out;
                data_out_next = round_state_out;
                valid_next    = 1'b1;
                round_next    = 4'd0;
            end

            // -----------------------------------------------------------------
            // DONE: data_out_reg holds final cipher, valid_reg=1.
            //   Deassert valid_next for return to IDLE. Hold data_out.
            // -----------------------------------------------------------------
            STATE_DONE: begin
                fsm_next   = STATE_IDLE;
                valid_next = 1'b0;
            end

            default: begin
                fsm_next = STATE_IDLE;
            end
        endcase
    end

    // =========================================================================
    // Sequential Register Block (async reset, active LOW)
    //
    // Non-blocking assignments (<=) for all registered state.
    // =========================================================================
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_reg    <= 128'd0;
            key_reg      <= 128'd0;
            round_reg    <= 4'd0;
            valid_reg    <= 1'b0;
            data_out_reg <= 128'd0;
            fsm_reg      <= STATE_IDLE;
        end else begin
            state_reg    <= state_next;
            key_reg      <= key_next;
            round_reg    <= round_next;
            valid_reg    <= valid_next;
            data_out_reg <= data_out_next;
            fsm_reg      <= fsm_next;
        end
    end

    // =========================================================================
    // Registered Outputs
    // =========================================================================
    assign data_out = data_out_reg;
    assign valid    = valid_reg;

endmodule

`resetall
