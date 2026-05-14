// ============================================================
// sm3_core - SM3 hash core (GM/T 0004-2012) TOP
//   - Sync active-LOW reset rst_n
//   - 67-cycle latency per 512-bit block
//   - Instantiates sm3_fsm + sm3_w_gen + sm3_compress
//   - Top outputs ready/hash_valid/hash_out declared `output reg`
//     per requirement.md frozen interface (driven combinationally
//     from internal wires - zero added latency)
// ============================================================
`resetall
`timescale 1ns / 1ps
`default_nettype none

module sm3_core (
    input  wire         clk,
    input  wire         rst_n,
    input  wire         msg_valid,
    input  wire [511:0] msg_block,
    input  wire         is_last,
    output reg          ready,
    output reg          hash_valid,
    output reg  [255:0] hash_out
);

    // -----------------------------------------------------------------
    // Internal wires connecting submodules
    // -----------------------------------------------------------------
    wire        w_ready;
    wire        w_load_en;
    wire        w_calc_en;
    wire        w_update_v_en;
    wire [5:0]  w_round_cnt;
    wire        w_hash_valid;

    wire [31:0] w_w_j;
    wire [31:0] w_w_prime_j;

    wire [255:0] w_hash_out;

    // -----------------------------------------------------------------
    // FSM: generates control signals and round counter
    // -----------------------------------------------------------------
    sm3_fsm u_fsm (
        .clk         (clk),
        .rst_n       (rst_n),
        .msg_valid   (msg_valid),
        .is_last     (is_last),
        .ready       (w_ready),
        .load_en     (w_load_en),
        .calc_en     (w_calc_en),
        .update_v_en (w_update_v_en),
        .round_cnt   (w_round_cnt),
        .hash_valid  (w_hash_valid)
    );

    // -----------------------------------------------------------------
    // Message expansion: produces W_j and W'_j per round
    // -----------------------------------------------------------------
    sm3_w_gen u_w_gen (
        .clk        (clk),
        .rst_n      (rst_n),
        .load_en    (w_load_en),
        .calc_en    (w_calc_en),
        .msg_block  (msg_block),
        .round_cnt  (w_round_cnt),
        .w_j        (w_w_j),
        .w_prime_j  (w_w_prime_j)
    );

    // -----------------------------------------------------------------
    // Compression function: produces 256-bit hash output
    // -----------------------------------------------------------------
    sm3_compress u_compress (
        .clk         (clk),
        .rst_n       (rst_n),
        .load_en     (w_load_en),
        .calc_en     (w_calc_en),
        .update_v_en (w_update_v_en),
        .round_cnt   (w_round_cnt),
        .w_j         (w_w_j),
        .w_prime_j   (w_w_prime_j),
        .hash_out    (w_hash_out)
    );

    // -----------------------------------------------------------------
    // Drive top output regs combinationally from internal wires.
    // This complies with the frozen `output reg` interface while
    // adding zero latency (functionally equivalent to wire assign).
    // -----------------------------------------------------------------
    always @* begin
        ready      = w_ready;
        hash_valid = w_hash_valid;
        hash_out   = w_hash_out;
    end

endmodule

`resetall
