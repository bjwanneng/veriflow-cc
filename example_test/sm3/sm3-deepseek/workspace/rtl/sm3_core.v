`resetall
`timescale 1ns/1ps
`default_nettype none

module sm3_core (
    input  wire         clk,
    input  wire         rst_n,
    input  wire         msg_valid,
    input  wire [511:0] msg_block,
    input  wire         is_last,
    output wire         ready,
    output wire         hash_valid,
    output wire [255:0] hash_out
);

    // ── Internal wires ──────────────────────────────────────────
    wire        load_en;
    wire        calc_en;
    wire        update_v_en;
    wire [5:0]  round_cnt;
    wire [31:0] w_j;
    wire [31:0] w_prime_j;

    // ── sm3_fsm (control FSM) ───────────────────────────────────
    sm3_fsm u_fsm (
        .clk         (clk),
        .rst_n       (rst_n),
        .msg_valid   (msg_valid),
        .is_last     (is_last),
        .ready       (ready),
        .load_en     (load_en),
        .calc_en     (calc_en),
        .update_v_en (update_v_en),
        .round_cnt   (round_cnt),
        .hash_valid  (hash_valid)
    );

    // ── sm3_w_gen (message expansion) ───────────────────────────
    sm3_w_gen u_w_gen (
        .clk       (clk),
        .rst_n     (rst_n),
        .load_en   (load_en),
        .calc_en   (calc_en),
        .msg_block (msg_block),
        .round_cnt (round_cnt),
        .w_j       (w_j),
        .w_prime_j (w_prime_j)
    );

    // ── sm3_compress (compression datapath) ─────────────────────
    sm3_compress u_compress (
        .clk         (clk),
        .rst_n       (rst_n),
        .load_en     (load_en),
        .calc_en     (calc_en),
        .update_v_en (update_v_en),
        .round_cnt   (round_cnt),
        .w_j         (w_j),
        .w_prime_j   (w_prime_j),
        .hash_out    (hash_out)
    );

endmodule

`default_nettype wire
