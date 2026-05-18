`resetall
`timescale 1ns / 1ps
`default_nettype none

module conv3x3 #(
    parameter WIDTH     = 16,
    parameter HEIGHT    = 16,
    parameter DATA_BITS = 8,
    parameter ACC_BITS  = 32
)(
    input  wire                  clk,
    input  wire                  rst,
    input  wire                  in_valid_i,
    input  wire [DATA_BITS-1:0]  in_data_i,
    output wire                  out_valid_o,
    output wire [ACC_BITS-1:0]   out_data_o
);

    // -------------------------------------------------------------------------
    // Internal wires from line_buffer_3x3
    // -------------------------------------------------------------------------
    wire                  lb_valid;
    wire [72-1:0]         lb_window;

    // -------------------------------------------------------------------------
    // Extract 9 pixels from 72-bit window
    // -------------------------------------------------------------------------
    wire signed [DATA_BITS-1:0] pix0;
    wire signed [DATA_BITS-1:0] pix1;
    wire signed [DATA_BITS-1:0] pix2;
    wire signed [DATA_BITS-1:0] pix3;
    wire signed [DATA_BITS-1:0] pix4;
    wire signed [DATA_BITS-1:0] pix5;
    wire signed [DATA_BITS-1:0] pix6;
    wire signed [DATA_BITS-1:0] pix7;
    wire signed [DATA_BITS-1:0] pix8;

    assign pix0 = lb_window[7:0];
    assign pix1 = lb_window[15:8];
    assign pix2 = lb_window[23:16];
    assign pix3 = lb_window[31:24];
    assign pix4 = lb_window[39:32];
    assign pix5 = lb_window[47:40];
    assign pix6 = lb_window[55:48];
    assign pix7 = lb_window[63:56];
    assign pix8 = lb_window[71:64];

    // -------------------------------------------------------------------------
    // Stage 1: line_buffer_3x3 submodule
    //   Produces valid + window (1-cycle pipeline delay internally)
    // -------------------------------------------------------------------------
    line_buffer_3x3 #(
        .WIDTH     (WIDTH),
        .HEIGHT    (HEIGHT),
        .DATA_BITS (DATA_BITS)
    ) u_line_buffer (
        .clk           (clk),
        .rst           (rst),
        .in_valid_i    (in_valid_i),
        .in_data_i     (in_data_i),
        .out_valid_o   (lb_valid),
        .out_window_o  (lb_window)
    );

    // -------------------------------------------------------------------------
    // Stage 2: Multiply each pixel by weight 1
    //   Since weight == 1, product = sign-extended pixel.
    //   Keep explicit structure for clarity.
    // -------------------------------------------------------------------------
    wire signed [ACC_BITS-1:0] prod0;
    wire signed [ACC_BITS-1:0] prod1;
    wire signed [ACC_BITS-1:0] prod2;
    wire signed [ACC_BITS-1:0] prod3;
    wire signed [ACC_BITS-1:0] prod4;
    wire signed [ACC_BITS-1:0] prod5;
    wire signed [ACC_BITS-1:0] prod6;
    wire signed [ACC_BITS-1:0] prod7;
    wire signed [ACC_BITS-1:0] prod8;

    assign prod0 = {{(ACC_BITS-DATA_BITS){pix0[DATA_BITS-1]}}, pix0};
    assign prod1 = {{(ACC_BITS-DATA_BITS){pix1[DATA_BITS-1]}}, pix1};
    assign prod2 = {{(ACC_BITS-DATA_BITS){pix2[DATA_BITS-1]}}, pix2};
    assign prod3 = {{(ACC_BITS-DATA_BITS){pix3[DATA_BITS-1]}}, pix3};
    assign prod4 = {{(ACC_BITS-DATA_BITS){pix4[DATA_BITS-1]}}, pix4};
    assign prod5 = {{(ACC_BITS-DATA_BITS){pix5[DATA_BITS-1]}}, pix5};
    assign prod6 = {{(ACC_BITS-DATA_BITS){pix6[DATA_BITS-1]}}, pix6};
    assign prod7 = {{(ACC_BITS-DATA_BITS){pix7[DATA_BITS-1]}}, pix7};
    assign prod8 = {{(ACC_BITS-DATA_BITS){pix8[DATA_BITS-1]}}, pix8};

    // -------------------------------------------------------------------------
    // Stage 2 pipeline registers: products + valid
    // -------------------------------------------------------------------------
    reg signed [ACC_BITS-1:0] prod0_reg = {ACC_BITS{1'b0}};
    reg signed [ACC_BITS-1:0] prod1_reg = {ACC_BITS{1'b0}};
    reg signed [ACC_BITS-1:0] prod2_reg = {ACC_BITS{1'b0}};
    reg signed [ACC_BITS-1:0] prod3_reg = {ACC_BITS{1'b0}};
    reg signed [ACC_BITS-1:0] prod4_reg = {ACC_BITS{1'b0}};
    reg signed [ACC_BITS-1:0] prod5_reg = {ACC_BITS{1'b0}};
    reg signed [ACC_BITS-1:0] prod6_reg = {ACC_BITS{1'b0}};
    reg signed [ACC_BITS-1:0] prod7_reg = {ACC_BITS{1'b0}};
    reg signed [ACC_BITS-1:0] prod8_reg = {ACC_BITS{1'b0}};
    reg                       prod_valid_reg = 1'b0;

    // -------------------------------------------------------------------------
    // Stage 3: Adder tree (combinational from prod_reg)
    // -------------------------------------------------------------------------
    wire signed [ACC_BITS-1:0] sum_level1_0;
    wire signed [ACC_BITS-1:0] sum_level1_1;
    wire signed [ACC_BITS-1:0] sum_level1_2;
    wire signed [ACC_BITS-1:0] sum_level1_3;
    wire signed [ACC_BITS-1:0] sum_level1_4;

    wire signed [ACC_BITS-1:0] sum_level2_0;
    wire signed [ACC_BITS-1:0] sum_level2_1;

    wire signed [ACC_BITS-1:0] sum_level3;

    assign sum_level1_0 = prod0_reg + prod1_reg;
    assign sum_level1_1 = prod2_reg + prod3_reg;
    assign sum_level1_2 = prod4_reg + prod5_reg;
    assign sum_level1_3 = prod6_reg + prod7_reg;
    assign sum_level1_4 = prod8_reg;

    assign sum_level2_0 = sum_level1_0 + sum_level1_1;
    assign sum_level2_1 = sum_level1_2 + sum_level1_3;

    assign sum_level3 = sum_level2_0 + sum_level2_1 + sum_level1_4;

    // -------------------------------------------------------------------------
    // Stage 3 pipeline registers: final sum + valid
    // -------------------------------------------------------------------------
    reg signed [ACC_BITS-1:0] sum_reg = {ACC_BITS{1'b0}};
    reg                       sum_valid_reg = 1'b0;

    // -------------------------------------------------------------------------
    // Sequential block: all pipeline registers, reset-first
    // -------------------------------------------------------------------------
    always @(posedge clk) begin
        if (rst) begin
            prod0_reg      <= {ACC_BITS{1'b0}};
            prod1_reg      <= {ACC_BITS{1'b0}};
            prod2_reg      <= {ACC_BITS{1'b0}};
            prod3_reg      <= {ACC_BITS{1'b0}};
            prod4_reg      <= {ACC_BITS{1'b0}};
            prod5_reg      <= {ACC_BITS{1'b0}};
            prod6_reg      <= {ACC_BITS{1'b0}};
            prod7_reg      <= {ACC_BITS{1'b0}};
            prod8_reg      <= {ACC_BITS{1'b0}};
            prod_valid_reg <= 1'b0;
            sum_reg        <= {ACC_BITS{1'b0}};
            sum_valid_reg  <= 1'b0;
        end else begin
            prod0_reg      <= prod0;
            prod1_reg      <= prod1;
            prod2_reg      <= prod2;
            prod3_reg      <= prod3;
            prod4_reg      <= prod4;
            prod5_reg      <= prod5;
            prod6_reg      <= prod6;
            prod7_reg      <= prod7;
            prod8_reg      <= prod8;
            prod_valid_reg <= lb_valid;

            sum_reg        <= sum_level3;
            sum_valid_reg  <= prod_valid_reg;
        end
    end

    // -------------------------------------------------------------------------
    // Output assignments
    // -------------------------------------------------------------------------
    assign out_valid_o = sum_valid_reg;
    assign out_data_o  = sum_reg;

endmodule

`resetall
