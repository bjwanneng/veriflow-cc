`resetall
`timescale 1ns / 1ps
`default_nettype none

// fft64_radix4_sdf.v -- Top-level 64-point radix-4 SDF pipeline FFT.
//
// Accepts natural-order complex samples at 1/clock, outputs digit-reversed
// FFT results after pipeline latency.
// All outputs are registered.  Async active-low reset.
//
// Pipeline latency: 67 cycles from first in_valid to first out_valid.
// Output ordering: radix-4 digit-reversed index on out_index.
//
// After external in_valid drops, the pipeline auto-flushes by driving
// zeros into stage 0 for 48 additional cycles.  This ensures all feedback
// data (z1/z2/z3) from the SDF stages is pushed through the pipeline.

module fft64_radix4_sdf #(
    parameter FFT_SIZE  = 64,
    parameter DATA_W    = 16,
    parameter TWIDDLE_W = 16
)(
    input  wire                clk,
    input  wire                rst_n,
    input  wire                in_valid,
    input  wire signed [15:0]  in_data_re,
    input  wire                signed [15:0] in_data_im,
    output wire                out_valid,
    output wire signed [15:0]  out_data_re,
    output wire signed [15:0]  out_data_im,
    output wire [5:0]          out_index
);

    // -----------------------------------------------------------------------
    // Auto-flush logic: after in_valid drops following fill, extend with
    // zeros for FLUSH_LEN cycles to push feedback data through pipeline.
    // -----------------------------------------------------------------------
    localparam FLUSH_LEN = 48;  // enough for DELAY3 of stage 0

    reg [5:0] flush_cnt = 6'd0;
    reg       flushing  = 1'b0;
    reg       seen_valid = 1'b0;

    wire ext_valid = in_valid || flushing;
    wire [DATA_W-1:0] ext_re = in_valid ? in_data_re : {DATA_W{1'b0}};
    wire [DATA_W-1:0] ext_im = in_valid ? in_data_im : {DATA_W{1'b0}};

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            flushing   <= 1'b0;
            flush_cnt  <= 6'd0;
            seen_valid <= 1'b0;
        end else begin
            if (in_valid)
                seen_valid <= 1'b1;

            // Start flushing when in_valid drops after we've seen valid data
            if (seen_valid && !in_valid && !flushing) begin
                flushing  <= 1'b1;
                flush_cnt <= 6'd0;
            end else if (flushing) begin
                if (flush_cnt == FLUSH_LEN[5:0])
                    flushing <= 1'b0;
                else
                    flush_cnt <= flush_cnt + 6'd1;
            end
        end
    end

    // -----------------------------------------------------------------------
    // Stage 0 (N=64, DL delay=48, has twiddle)
    // -----------------------------------------------------------------------
    wire        s0_out_valid;
    wire [DATA_W-1:0] s0_out_re;
    wire [DATA_W-1:0] s0_out_im;
    wire [5:0]  s0_out_cnt;

    sdf_stage #(
        .STAGE_IDX  (0),
        .FFT_N      (FFT_SIZE),
        .DATA_W     (DATA_W),
        .TWIDDLE_W  (TWIDDLE_W)
    ) u_sdf_stage0 (
        .clk      (clk),
        .rst_n    (rst_n),
        .in_valid (ext_valid),
        .in_re    (ext_re),
        .in_im    (ext_im),
        .out_valid(s0_out_valid),
        .out_re   (s0_out_re),
        .out_im   (s0_out_im),
        .out_cnt  (s0_out_cnt)
    );

    // -----------------------------------------------------------------------
    // Stage 1 (N=16, DL delay=12, has twiddle)
    // -----------------------------------------------------------------------
    wire        s1_out_valid;
    wire [DATA_W-1:0] s1_out_re;
    wire [DATA_W-1:0] s1_out_im;
    wire [5:0]  s1_out_cnt;

    sdf_stage #(
        .STAGE_IDX  (1),
        .FFT_N      (FFT_SIZE),
        .DATA_W     (DATA_W),
        .TWIDDLE_W  (TWIDDLE_W)
    ) u_sdf_stage1 (
        .clk      (clk),
        .rst_n    (rst_n),
        .in_valid (s0_out_valid),
        .in_re    (s0_out_re),
        .in_im    (s0_out_im),
        .out_valid(s1_out_valid),
        .out_re   (s1_out_re),
        .out_im   (s1_out_im),
        .out_cnt  (s1_out_cnt)
    );

    // -----------------------------------------------------------------------
    // Stage 2 (N=4, DL delay=3, no twiddle)
    // -----------------------------------------------------------------------
    wire        s2_out_valid;
    wire [DATA_W-1:0] s2_out_re;
    wire [DATA_W-1:0] s2_out_im;
    wire [5:0]  s2_out_cnt;

    sdf_stage #(
        .STAGE_IDX  (2),
        .FFT_N      (FFT_SIZE),
        .DATA_W     (DATA_W),
        .TWIDDLE_W  (TWIDDLE_W)
    ) u_sdf_stage2 (
        .clk      (clk),
        .rst_n    (rst_n),
        .in_valid (s1_out_valid),
        .in_re    (s1_out_re),
        .in_im    (s1_out_im),
        .out_valid(s2_out_valid),
        .out_re   (s2_out_re),
        .out_im   (s2_out_im),
        .out_cnt  (s2_out_cnt)
    );

    // -----------------------------------------------------------------------
    // Output register stage + output index counter
    // Pipeline outputs in SDF natural order (digit-reversed index order).
    // Use a sequential output counter for the bin index.
    // -----------------------------------------------------------------------
    reg signed [DATA_W-1:0] out_data_re_reg = {DATA_W{1'b0}};
    reg signed [DATA_W-1:0] out_data_im_reg = {DATA_W{1'b0}};
    reg [5:0]                out_index_reg   = 6'd0;
    reg                      out_valid_reg   = 1'b0;
    reg [6:0]                out_count       = 7'd0;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            out_data_re_reg <= {DATA_W{1'b0}};
            out_data_im_reg <= {DATA_W{1'b0}};
            out_index_reg   <= 6'd0;
            out_valid_reg   <= 1'b0;
            out_count       <= 7'd0;
        end else begin
            out_data_re_reg <= s2_out_re;
            out_data_im_reg <= s2_out_im;
            out_valid_reg   <= s2_out_valid;
            if (s2_out_valid) begin
                out_index_reg <= out_count[5:0];
                if (out_count == 7'd63)
                    out_count <= 7'd0;
                else
                    out_count <= out_count + 7'd1;
            end
        end
    end

    assign out_data_re = out_data_re_reg;
    assign out_data_im = out_data_im_reg;
    assign out_index   = out_index_reg;
    assign out_valid   = out_valid_reg;

endmodule

`resetall
