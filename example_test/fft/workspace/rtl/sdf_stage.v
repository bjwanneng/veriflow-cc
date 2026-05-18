`resetall
`timescale 1ns / 1ps
`default_nettype none

// sdf_stage.v -- Single SDF pipeline stage for radix-4 FFT.
//
// Uses a single shift register of depth DELAY3 = 3*N_s/4.
//
// Architecture: twiddles applied to BF4 outputs z1/z2/z3 during phase 3
// before feedback storage.  BF4 operates on raw (untwiddled) inputs.
//
// Internal datapath is DATA_W+2 bits wide (preserving BF4 growth bits).
// Only truncated to DATA_W at the stage output port.
//
// During phase 3 (last N_s/4 cycles of each N_s-period):
//   - BF4 computes on raw inputs from SR and current input
//   - z0 goes directly to output
//   - z1 * W^r, z2 * W^(2r), z3 * W^(3r) stored as feedback
//   - Feedback overwrites SR[0], SR[DELAY1], SR[DELAY2]
//
// During phases 0-2 (first 3*N_s/4 cycles):
//   - SR shifts normally
//   - Output from SR[DELAY3-1] (previously stored feedback emerges)
//
// Counter and SR shift only when in_valid=1 (synchronized stages).
// out_valid = in_valid && fill_done (1:1 throughput after fill).

module sdf_stage #(
    parameter STAGE_IDX   = 0,
    parameter FFT_N       = 64,
    parameter DATA_W      = 16,
    parameter TWIDDLE_W   = 16
)(
    input  wire                          clk,
    input  wire                          rst_n,
    input  wire                          in_valid,
    input  wire signed [DATA_W-1:0]      in_re,
    input  wire signed [DATA_W-1:0]      in_im,
    output wire                          out_valid,
    output wire signed [DATA_W-1:0]      out_re,
    output wire signed [DATA_W-1:0]      out_im,
    output wire [5:0]                    out_cnt
);

    // -----------------------------------------------------------------------
    // Local parameters
    // -----------------------------------------------------------------------
    localparam N_S      = FFT_N >> (2 * STAGE_IDX);
    localparam DELAY1   = N_S / 4;
    localparam DELAY2   = 2 * N_S / 4;
    localparam DELAY3   = 3 * N_S / 4;
    localparam CNT_W    = (STAGE_IDX == 0) ? 6 :
                          (STAGE_IDX == 1) ? 4 : 2;
    localparam BF_OUT_W = DATA_W + 2;

    // -----------------------------------------------------------------------
    // Counter (period = N_S, gated by in_valid)
    // -----------------------------------------------------------------------
    reg [CNT_W-1:0] cnt_reg = {CNT_W{1'b0}};

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            cnt_reg <= {CNT_W{1'b0}};
        else if (in_valid) begin
            if (cnt_reg == N_S[CNT_W-1:0] - {{(CNT_W-1){1'b0}}, 1'b1})
                cnt_reg <= {CNT_W{1'b0}};
            else
                cnt_reg <= cnt_reg + {{(CNT_W-1){1'b0}}, 1'b1};
        end
    end

    // Phase: upper 2 bits of counter
    wire [1:0] phase = cnt_reg >> (CNT_W - 2);

    // -----------------------------------------------------------------------
    // Fill counter
    // -----------------------------------------------------------------------
    localparam FILL_W = (STAGE_IDX == 0) ? 6 :
                        (STAGE_IDX == 1) ? 4 : 2;
    reg [FILL_W:0] fill_cnt_reg = {(FILL_W+1){1'b0}};
    reg            fill_done_reg = 1'b0;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            fill_cnt_reg <= {(FILL_W+1){1'b0}};
            fill_done_reg <= 1'b0;
        end else if (!fill_done_reg && in_valid) begin
            if (fill_cnt_reg == DELAY3[FILL_W:0] - {{FILL_W{1'b0}}, 1'b1})
                fill_done_reg <= 1'b1;
            else
                fill_cnt_reg <= fill_cnt_reg + {{FILL_W{1'b0}}, 1'b1};
        end
    end

    // -----------------------------------------------------------------------
    // Single shift register of depth DELAY3, INTERNAL width = BF_OUT_W (18 bit)
    // This preserves BF4 growth bits through the feedback path.
    // -----------------------------------------------------------------------
    reg signed [BF_OUT_W-1:0] sr_re [0:DELAY3-1];
    reg signed [BF_OUT_W-1:0] sr_im [0:DELAY3-1];

    // -----------------------------------------------------------------------
    // Saturate 18-bit SR values to 16-bit for BF4 inputs
    // BF4 inputs are DATA_W (16-bit); SR stores BF_OUT_W (18-bit).
    // Must saturate, NOT truncate, to preserve sign for overflow values.
    // -----------------------------------------------------------------------
    function signed [DATA_W-1:0] sat18to16;
        input signed [BF_OUT_W-1:0] val;
        begin
            if (val[BF_OUT_W-1:DATA_W-1] != {BF_OUT_W-DATA_W+1{val[DATA_W-1]}})
                sat18to16 = {val[BF_OUT_W-1], {DATA_W-1{~val[BF_OUT_W-1]}}};
            else
                sat18to16 = val[DATA_W-1:0];
        end
    endfunction

    wire signed [DATA_W-1:0] bf_x0_re = sat18to16(sr_re[DELAY3-1]);
    wire signed [DATA_W-1:0] bf_x0_im = sat18to16(sr_im[DELAY3-1]);
    wire signed [DATA_W-1:0] bf_x1_re = sat18to16(sr_re[DELAY2-1]);
    wire signed [DATA_W-1:0] bf_x1_im = sat18to16(sr_im[DELAY2-1]);
    wire signed [DATA_W-1:0] bf_x2_re = sat18to16(sr_re[DELAY1-1]);
    wire signed [DATA_W-1:0] bf_x2_im = sat18to16(sr_im[DELAY1-1]);
    wire signed [DATA_W-1:0] bf_x3_re = in_re;
    wire signed [DATA_W-1:0] bf_x3_im = in_im;

    wire signed [BF_OUT_W-1:0] z0_re, z0_im;
    wire signed [BF_OUT_W-1:0] z1_re, z1_im;
    wire signed [BF_OUT_W-1:0] z2_re, z2_im;
    wire signed [BF_OUT_W-1:0] z3_re, z3_im;

    bf4 #(.DATA_W(DATA_W)) u_bf4 (
        .x0_re(bf_x0_re), .x0_im(bf_x0_im),
        .x1_re(bf_x1_re), .x1_im(bf_x1_im),
        .x2_re(bf_x2_re), .x2_im(bf_x2_im),
        .x3_re(bf_x3_re), .x3_im(bf_x3_im),
        .z0_re(z0_re),  .z0_im(z0_im),
        .z1_re(z1_re),  .z1_im(z1_im),
        .z2_re(z2_re),  .z2_im(z2_im),
        .z3_re(z3_re),  .z3_im(z3_im)
    );

    // -----------------------------------------------------------------------
    // Saturate BF4 outputs from DATA_W+2 to DATA_W (for output port only)
    // z1/z2/z3 use full 18-bit values in twiddle multiply
    // -----------------------------------------------------------------------
    wire z0_of = (z0_re[BF_OUT_W-1:DATA_W-1] != {BF_OUT_W-DATA_W+1{z0_re[DATA_W-1]}});
    wire signed [DATA_W-1:0] z0_sat_re = z0_of ?
        {z0_re[BF_OUT_W-1], {DATA_W-1{~z0_re[BF_OUT_W-1]}}} : z0_re[DATA_W-1:0];
    wire signed [DATA_W-1:0] z0_sat_im = (z0_im[BF_OUT_W-1:DATA_W-1] !=
        {BF_OUT_W-DATA_W+1{z0_im[DATA_W-1]}}) ?
        {z0_im[BF_OUT_W-1], {DATA_W-1{~z0_im[BF_OUT_W-1]}}} : z0_im[DATA_W-1:0];

    // -----------------------------------------------------------------------
    // Twiddle ROM + complex multiply for feedback (stages 0,1 only)
    // Twiddle applied to full 18-bit BF4 OUTPUTS z1/z2/z3 before feedback.
    // Product is 18*16 = 34-bit; extract result with rounding to 18 bits.
    // -----------------------------------------------------------------------
    // Feedback output wires (driven by generate blocks below).
    // Declared as regs so both generate branches can drive them.
    // -----------------------------------------------------------------------
    reg signed [BF_OUT_W-1:0] fb1_final_re, fb1_final_im;
    reg signed [BF_OUT_W-1:0] fb2_final_re, fb2_final_im;
    reg signed [BF_OUT_W-1:0] fb3_final_re, fb3_final_im;

    generate
        if (STAGE_IDX < 2) begin : gen_twiddle
            wire [CNT_W-1:0] bf_offset = cnt_reg - DELAY3[CNT_W-1:0];
            localparam STRIDE = 1 << (2 * STAGE_IDX);

            // Twiddle addresses: r * bf_offset * stride, modulo N=64
            wire [5:0] tw1_addr;
            wire [5:0] tw2_addr;
            wire [5:0] tw3_addr;

            wire [5:0] bf6 = {{(6-CNT_W){1'b0}}, bf_offset};

            // tw1 = W^(1 * bf_offset * stride)
            assign tw1_addr = bf6 * STRIDE[5:0];

            // tw2 = W^(2 * bf_offset * stride)
            wire [6:0] tw2_addr_wide = {bf6, 1'b0} * STRIDE[5:0];
            assign tw2_addr = tw2_addr_wide[5:0];

            // tw3 = W^(3 * bf_offset * stride) = tw1 + tw2
            assign tw3_addr = tw1_addr + tw2_addr;

            // ROM for z1 twiddle: W^(1*b*s)
            wire signed [TWIDDLE_W-1:0] tw1_re, tw1_im;
            twiddle_rom #(
                .STAGE_IDX  (STAGE_IDX),
                .TWIDDLE_W  (TWIDDLE_W)
            ) u_twiddle_rom1 (
                .addr  (tw1_addr),
                .tw_re (tw1_re),
                .tw_im (tw1_im)
            );

            // ROM for z2 twiddle: W^(2*b*s)
            wire signed [TWIDDLE_W-1:0] tw2_re, tw2_im;
            twiddle_rom #(
                .STAGE_IDX  (STAGE_IDX),
                .TWIDDLE_W  (TWIDDLE_W)
            ) u_twiddle_rom2 (
                .addr  (tw2_addr),
                .tw_re (tw2_re),
                .tw_im (tw2_im)
            );

            // ROM for z3 twiddle: W^(3*b*s)
            wire signed [TWIDDLE_W-1:0] tw3_re, tw3_im;
            twiddle_rom #(
                .STAGE_IDX  (STAGE_IDX),
                .TWIDDLE_W  (TWIDDLE_W)
            ) u_twiddle_rom3 (
                .addr  (tw3_addr),
                .tw_re (tw3_re),
                .tw_im (tw3_im)
            );

            // Complex multiply with 18-bit data x 16-bit twiddle = 34-bit product.
            // Q format: data is Q1.17 (18-bit signed), twiddle is Q1.15 (16-bit signed).
            // Product is Q2.32 (34-bit signed). We need Q1.17 result.
            // Extract bits [32:15] with rounding: add (1<<14) before >>15.
            // Product width: BF_OUT_W + TWIDDLE_W = 34 bits.
            localparam PROD_W = BF_OUT_W + TWIDDLE_W;

            // z1 twiddled
            wire signed [PROD_W-1:0] fb1_re_full =
                $signed(z1_re) * $signed(tw1_re) -
                $signed(z1_im) * $signed(tw1_im);
            wire signed [PROD_W-1:0] fb1_im_full =
                $signed(z1_re) * $signed(tw1_im) +
                $signed(z1_im) * $signed(tw1_re);
            wire signed [BF_OUT_W-1:0] fb1_pre_re = (fb1_re_full + (1 <<< (DATA_W-2))) >>> (DATA_W-1);
            wire signed [BF_OUT_W-1:0] fb1_pre_im = (fb1_im_full + (1 <<< (DATA_W-2))) >>> (DATA_W-1);

            // z2 twiddled
            wire signed [PROD_W-1:0] fb2_re_full =
                $signed(z2_re) * $signed(tw2_re) -
                $signed(z2_im) * $signed(tw2_im);
            wire signed [PROD_W-1:0] fb2_im_full =
                $signed(z2_re) * $signed(tw2_im) +
                $signed(z2_im) * $signed(tw2_re);
            wire signed [BF_OUT_W-1:0] fb2_pre_re = (fb2_re_full + (1 <<< (DATA_W-2))) >>> (DATA_W-1);
            wire signed [BF_OUT_W-1:0] fb2_pre_im = (fb2_im_full + (1 <<< (DATA_W-2))) >>> (DATA_W-1);

            // z3 twiddled
            wire signed [PROD_W-1:0] fb3_re_full =
                $signed(z3_re) * $signed(tw3_re) -
                $signed(z3_im) * $signed(tw3_im);
            wire signed [PROD_W-1:0] fb3_im_full =
                $signed(z3_re) * $signed(tw3_im) +
                $signed(z3_im) * $signed(tw3_re);
            wire signed [BF_OUT_W-1:0] fb3_pre_re = (fb3_re_full + (1 <<< (DATA_W-2))) >>> (DATA_W-1);
            wire signed [BF_OUT_W-1:0] fb3_pre_im = (fb3_im_full + (1 <<< (DATA_W-2))) >>> (DATA_W-1);

            // Select: twiddle when phase==3 and bf_offset!=0, else untwiddled
            wire bf_offset_is_zero = (bf_offset == {CNT_W{1'b0}});
            wire use_twiddle = (phase == 2'd3) && !bf_offset_is_zero;

            // Drive module-scope feedback regs
            always @(*) begin
                fb1_final_re = use_twiddle ? fb1_pre_re : z1_re;
                fb1_final_im = use_twiddle ? fb1_pre_im : z1_im;
                fb2_final_re = use_twiddle ? fb2_pre_re : z2_re;
                fb2_final_im = use_twiddle ? fb2_pre_im : z2_im;
                fb3_final_re = use_twiddle ? fb3_pre_re : z3_re;
                fb3_final_im = use_twiddle ? fb3_pre_im : z3_im;
            end
        end else begin : gen_no_twiddle
            // Last stage: no twiddles, raw BF4 feedback
            always @(*) begin
                fb1_final_re = z1_re;
                fb1_final_im = z1_im;
                fb2_final_re = z2_re;
                fb2_final_im = z2_im;
                fb3_final_re = z3_re;
                fb3_final_im = z3_im;
            end
        end
    endgenerate

    // -----------------------------------------------------------------------
    // SR shift logic (gated by in_valid)
    // During phase 3 + fill_done: feedback twiddled z1/z2/z3 into SR
    // SR stores BF_OUT_W (18-bit) values for extra precision
    // -----------------------------------------------------------------------
    integer i;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (i = 0; i < DELAY3; i = i + 1) begin
                sr_re[i] <= {BF_OUT_W{1'b0}};
                sr_im[i] <= {BF_OUT_W{1'b0}};
            end
        end else if (in_valid) begin
            // Shift all positions
            for (i = 1; i < DELAY3; i = i + 1) begin
                sr_re[i] <= sr_re[i-1];
                sr_im[i] <= sr_im[i-1];
            end
            // New data at position 0 (sign-extend input to 18-bit)
            sr_re[0] <= {{(BF_OUT_W-DATA_W){in_re[DATA_W-1]}}, in_re};
            sr_im[0] <= {{(BF_OUT_W-DATA_W){in_im[DATA_W-1]}}, in_im};

            // During phase 3 after fill: overwrite section beginnings
            // with twiddled BF4 feedback (full 18-bit)
            if (phase == 2'd3 && fill_done_reg) begin
                sr_re[0]       <= fb3_final_re;
                sr_im[0]       <= fb3_final_im;
                sr_re[DELAY1]  <= fb2_final_re;
                sr_im[DELAY1]  <= fb2_final_im;
                sr_re[DELAY2]  <= fb1_final_re;
                sr_im[DELAY2]  <= fb1_final_im;
            end
        end
    end

    // -----------------------------------------------------------------------
    // Output selection (saturate 18-bit to 16-bit for output port)
    //   Phase 3 + fill_done: z0 from BF4
    //   Phases 0-2: SR[DELAY3-1] (feedback data emerging from SR)
    // -----------------------------------------------------------------------
    // Saturate SR output from 18-bit to 16-bit
    wire signed [BF_OUT_W-1:0] sr_out_re = sr_re[DELAY3-1];
    wire signed [BF_OUT_W-1:0] sr_out_im = sr_im[DELAY3-1];
    wire sr_out_re_of = (sr_out_re[BF_OUT_W-1:DATA_W-1] != {BF_OUT_W-DATA_W+1{sr_out_re[DATA_W-1]}});
    wire signed [DATA_W-1:0] sr_out_sat_re = sr_out_re_of ?
        {sr_out_re[BF_OUT_W-1], {DATA_W-1{~sr_out_re[BF_OUT_W-1]}}} : sr_out_re[DATA_W-1:0];
    wire sr_out_im_of = (sr_out_im[BF_OUT_W-1:DATA_W-1] != {BF_OUT_W-DATA_W+1{sr_out_im[DATA_W-1]}});
    wire signed [DATA_W-1:0] sr_out_sat_im = sr_out_im_of ?
        {sr_out_im[BF_OUT_W-1], {DATA_W-1{~sr_out_im[BF_OUT_W-1]}}} : sr_out_im[DATA_W-1:0];

    wire signed [DATA_W-1:0] stage_out_re = (phase == 2'd3 && fill_done_reg) ?
                                             z0_sat_re : sr_out_sat_re;
    wire signed [DATA_W-1:0] stage_out_im = (phase == 2'd3 && fill_done_reg) ?
                                             z0_sat_im : sr_out_sat_im;

    // -----------------------------------------------------------------------
    // Output register
    // -----------------------------------------------------------------------
    reg signed [DATA_W-1:0] out_re_reg    = {DATA_W{1'b0}};
    reg signed [DATA_W-1:0] out_im_reg    = {DATA_W{1'b0}};
    reg                      out_valid_reg = 1'b0;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            out_re_reg    <= {DATA_W{1'b0}};
            out_im_reg    <= {DATA_W{1'b0}};
            out_valid_reg <= 1'b0;
        end else begin
            out_re_reg    <= stage_out_re;
            out_im_reg    <= stage_out_im;
            out_valid_reg <= in_valid && fill_done_reg;
        end
    end

    assign out_re    = out_re_reg;
    assign out_im    = out_im_reg;
    assign out_valid = out_valid_reg;

    // -----------------------------------------------------------------------
    // Output counter (pipeline-delayed by 1)
    // -----------------------------------------------------------------------
    reg [5:0] out_cnt_pipe = 6'd0;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            out_cnt_pipe <= 6'd0;
        else
            out_cnt_pipe <= {{(6-CNT_W){1'b0}}, cnt_reg};
    end

    assign out_cnt = out_cnt_pipe;

endmodule

`resetall
