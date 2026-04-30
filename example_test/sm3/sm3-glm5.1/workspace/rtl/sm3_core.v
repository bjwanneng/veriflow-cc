// -----------------------------------------------------------------------------
// File   : sm3_core.v
// Author : VeriFlow-CC
// Date   : 2026-04-27
// -----------------------------------------------------------------------------
// Description:
//   Top-level wrapper for SM3 cryptographic hash core. Instantiates and
//   connects sm3_fsm (control), sm3_w_gen (message expansion), and
//   sm3_compress (compression datapath). Exposes valid/ready handshake
//   interface for external integration.
// -----------------------------------------------------------------------------
// Change Log:
//   2026-04-27  VeriFlow-CC  v1.0  Initial release
// -----------------------------------------------------------------------------

`resetall
`timescale 1ns / 1ps
`default_nettype none

module sm3_core
(
    input  wire          clk,
    input  wire          rst_n,
    input  wire          msg_valid,
    input  wire [511:0]  msg_block,
    input  wire          is_last,
    output wire          ready,
    output wire          hash_valid,
    output wire [255:0]  hash_out
);

    /////////////////////////////////////////////////////////////////////////
    // Internal wires between submodules                                  //
    /////////////////////////////////////////////////////////////////////////
    wire       load_en;
    wire       calc_en;
    wire       update_v_en;
    wire [5:0] round_cnt;
    wire [31:0] w_j;
    wire [31:0] w_prime_j;

    /////////////////////////////////////////////////////////////////////////
    // FSM instance — control state machine                               //
    /////////////////////////////////////////////////////////////////////////
    sm3_fsm sm3_fsm_inst
    (
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

    /////////////////////////////////////////////////////////////////////////
    // Message expansion instance                                         //
    /////////////////////////////////////////////////////////////////////////
    sm3_w_gen sm3_w_gen_inst
    (
        .clk       (clk),
        .rst_n     (rst_n),
        .load_en   (load_en),
        .calc_en   (calc_en),
        .msg_block (msg_block),
        .round_cnt (round_cnt),
        .w_j       (w_j),
        .w_prime_j (w_prime_j)
    );

    /////////////////////////////////////////////////////////////////////////
    // Compression datapath instance                                      //
    /////////////////////////////////////////////////////////////////////////
    sm3_compress sm3_compress_inst
    (
        .clk        (clk),
        .rst_n      (rst_n),
        .load_en    (load_en),
        .calc_en    (calc_en),
        .update_v_en(update_v_en),
        .round_cnt  (round_cnt),
        .w_j        (w_j),
        .w_prime_j  (w_prime_j),
        .hash_out   (hash_out)
    );

endmodule

`resetall
