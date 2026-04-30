// -----------------------------------------------------------------------------
// File   : sm3_core.v
// Author : VeriFlow-CC Pipeline
// Date   : 2026-04-27
// -----------------------------------------------------------------------------
// Description:
//   SM3 cryptographic hash algorithm core compression module (GM/T 0004-2012).
//   64-cycle single-iteration architecture processing one 512-bit message block
//   per 66+ cycles. Top-level wrapper instantiating sm3_fsm (control), sm3_w_gen
//   (message expansion), and sm3_compress (compression datapath), providing the
//   external valid/ready/ack interface with reliable hash handoff.
// -----------------------------------------------------------------------------
// Change Log:
//   2026-04-27  VeriFlow-CC  v1.0  Initial release
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
    input  wire         ack,
    output wire         ready,
    output wire         hash_valid,
    output wire [255:0] hash_out
);

    ///////////////////////////////////////
    // Internal Signals                  //
    ///////////////////////////////////////

    wire        ready_int;
    wire        hash_valid_int;
    wire [255:0] hash_out_int;
    wire        load_en;
    wire        calc_en;
    wire        update_v_en;
    wire [5:0]  round_cnt;
    wire [31:0] w_j;
    wire [31:0] w_prime_j;

    ///////////////////////////////////////
    // Output Assignments                //
    ///////////////////////////////////////

    assign ready      = ready_int;
    assign hash_valid = hash_valid_int;
    assign hash_out   = hash_out_int;

    ///////////////////////////////////////
    // FSM Controller                    //
    ///////////////////////////////////////

    sm3_fsm sm3_fsm_inst (
        .clk         (clk),
        .rst         (rst),
        .msg_valid   (msg_valid),
        .is_last     (is_last),
        .ack         (ack),
        .ready       (ready_int),
        .load_en     (load_en),
        .calc_en     (calc_en),
        .update_v_en (update_v_en),
        .round_cnt   (round_cnt),
        .hash_valid  (hash_valid_int)
    );

    ///////////////////////////////////////
    // Message Expansion                 //
    ///////////////////////////////////////

    sm3_w_gen sm3_w_gen_inst (
        .clk         (clk),
        .rst         (rst),
        .load_en     (load_en),
        .calc_en     (calc_en),
        .msg_block   (msg_block),
        .round_cnt   (round_cnt),
        .w_j         (w_j),
        .w_prime_j   (w_prime_j)
    );

    ///////////////////////////////////////
    // Compression Datapath              //
    ///////////////////////////////////////

    sm3_compress sm3_compress_inst (
        .clk         (clk),
        .rst         (rst),
        .load_en     (load_en),
        .calc_en     (calc_en),
        .update_v_en (update_v_en),
        .round_cnt   (round_cnt),
        .w_j         (w_j),
        .w_prime_j   (w_prime_j),
        .hash_out    (hash_out_int)
    );

endmodule

`resetall
