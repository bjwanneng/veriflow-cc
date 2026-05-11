// ============================================================================
// SM3 Core - Top-level structural wrapper
// Instantiates sm3_fsm (control), sm3_w_gen (message expansion),
// and sm3_compress (compression function).
// ============================================================================

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

    // -------------------------------------------------------------------------
    // Internal inter-module wiring
    // -------------------------------------------------------------------------
    wire        load_en;
    wire        calc_en;
    wire        update_v_en;
    wire [5:0]  round_cnt;
    wire [31:0] w_j;
    wire [31:0] w_prime_j;

    // -------------------------------------------------------------------------
    // sm3_fsm - FSM controller
    // -------------------------------------------------------------------------
    sm3_fsm u_sm3_fsm (
        .clk          (clk),
        .rst_n        (rst_n),
        .msg_valid    (msg_valid),
        .is_last      (is_last),
        .ready        (ready),
        .load_en      (load_en),
        .calc_en      (calc_en),
        .update_v_en  (update_v_en),
        .round_cnt    (round_cnt),
        .hash_valid   (hash_valid)
    );

    // -------------------------------------------------------------------------
    // sm3_w_gen - Message expansion
    // -------------------------------------------------------------------------
    sm3_w_gen u_sm3_w_gen (
        .clk         (clk),
        .rst_n       (rst_n),
        .load_en     (load_en),
        .calc_en     (calc_en),
        .msg_block   (msg_block),
        .round_cnt   (round_cnt),
        .w_j         (w_j),
        .w_prime_j   (w_prime_j)
    );

    // -------------------------------------------------------------------------
    // sm3_compress - Compression function
    // -------------------------------------------------------------------------
    sm3_compress u_sm3_compress (
        .clk          (clk),
        .rst_n        (rst_n),
        .load_en      (load_en),
        .calc_en      (calc_en),
        .update_v_en  (update_v_en),
        .round_cnt    (round_cnt),
        .w_j          (w_j),
        .w_prime_j    (w_prime_j),
        .hash_out     (hash_out)
    );

endmodule
