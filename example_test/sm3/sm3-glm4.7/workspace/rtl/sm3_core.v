// -----------------------------------------------------------------------------
// File   : sm3_core.v
// Author : VeriFlow
// Date   : 2026-05-09
// -----------------------------------------------------------------------------
// Description: Top-level wrapper for SM3 cryptographic hash core (GM/T 0004-2012).
//              Instantiates sm3_fsm, sm3_w_gen, and sm3_compress.
//              Exposes valid-ready handshake interface externally.
// -----------------------------------------------------------------------------

`resetall
`timescale 1ns / 1ps
`default_nettype none

module sm3_core
(
    input  wire         clk,
    input  wire         rst,
    input  wire         msg_valid,
    input  wire [511:0] msg_block,
    input  wire         is_last,
    output wire         ready,
    output wire         hash_valid,
    output wire [255:0] hash_out
);

    // ---------------------------------------------------------------------
    // Internal wires — FSM outputs
    // ---------------------------------------------------------------------
    wire        load_en;
    wire        calc_en;
    wire        update_v_en;
    wire [5:0]  round_cnt;

    // ---------------------------------------------------------------------
    // Internal wires — W-gen outputs
    // ---------------------------------------------------------------------
    wire [31:0] w;
    wire [31:0] w_prime;

    // ---------------------------------------------------------------------
    // Submodule instantiation: sm3_fsm
    // ---------------------------------------------------------------------
    sm3_fsm u_sm3_fsm
    (
        .clk            (clk),
        .rst            (rst),
        .msg_valid      (msg_valid),
        .is_last        (is_last),
        .ready          (ready),
        .load_en        (load_en),
        .calc_en        (calc_en),
        .update_v_en    (update_v_en),
        .round_cnt      (round_cnt),
        .hash_valid     (hash_valid)
    );

    // ---------------------------------------------------------------------
    // Submodule instantiation: sm3_w_gen
    // ---------------------------------------------------------------------
    sm3_w_gen u_sm3_w_gen
    (
        .clk            (clk),
        .rst            (rst),
        .load_en        (load_en),
        .calc_en        (calc_en),
        .msg_block      (msg_block),
        .round_cnt      (round_cnt),
        .w              (w),
        .w_prime        (w_prime)
    );

    // ---------------------------------------------------------------------
    // Submodule instantiation: sm3_compress
    // ---------------------------------------------------------------------
    sm3_compress u_sm3_compress
    (
        .clk            (clk),
        .rst            (rst),
        .load_en        (load_en),
        .calc_en        (calc_en),
        .update_v_en    (update_v_en),
        .round_cnt      (round_cnt),
        .w              (w),
        .w_prime        (w_prime),
        .hash_out       (hash_out)
    );

endmodule

`resetall
