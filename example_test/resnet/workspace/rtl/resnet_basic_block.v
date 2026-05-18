`resetall
`timescale 1ns / 1ps
`default_nettype none

module resnet_basic_block #(
    parameter CHANNELS = 16,
    parameter WIDTH    = 16,
    parameter HEIGHT   = 16,
    parameter DATA_BITS = 8
)(
    input  wire clk,
    input  wire rst,
    input  wire in_valid_i,
    input  wire [DATA_BITS-1:0] in_data_i,
    output wire out_valid_o,
    output wire [DATA_BITS-1:0] out_data_o
);

    // -------------------------------------------------------------------------
    // Internal wires for submodule connections
    // -------------------------------------------------------------------------

    // conv1 -> relu1
    wire        conv1_out_valid;
    wire [31:0] conv1_out_data;

    // relu1 -> conv2
    wire        relu1_out_valid;
    wire [DATA_BITS-1:0] relu1_out_data;

    // conv2 -> adder
    wire        conv2_out_valid;
    wire [31:0] conv2_out_data;

    // delay_buffer -> adder
    wire        delay_out_valid;
    wire [DATA_BITS-1:0] delay_out_data;

    // adder -> relu2
    wire        adder_valid;
    wire [31:0] adder_data;

    // relu2 -> top output
    wire        relu2_out_valid;
    wire [DATA_BITS-1:0] relu2_out_data;

    // -------------------------------------------------------------------------
    // Submodule instantiations
    // -------------------------------------------------------------------------

    conv3x3 #(
        .WIDTH    (WIDTH),
        .HEIGHT   (HEIGHT),
        .DATA_BITS(DATA_BITS),
        .ACC_BITS (32)
    ) conv1 (
        .clk        (clk),
        .rst        (rst),
        .in_valid_i (in_valid_i),
        .in_data_i  (in_data_i),
        .out_valid_o(conv1_out_valid),
        .out_data_o (conv1_out_data)
    );

    relu #(
        .IN_BITS (32),
        .OUT_BITS(DATA_BITS)
    ) relu1 (
        .clk        (clk),
        .rst        (rst),
        .in_valid_i (conv1_out_valid),
        .in_data_i  (conv1_out_data),
        .out_valid_o(relu1_out_valid),
        .out_data_o (relu1_out_data)
    );

    conv3x3 #(
        .WIDTH    (WIDTH),
        .HEIGHT   (HEIGHT),
        .DATA_BITS(DATA_BITS),
        .ACC_BITS (32)
    ) conv2 (
        .clk        (clk),
        .rst        (rst),
        .in_valid_i (relu1_out_valid),
        .in_data_i  (relu1_out_data),
        .out_valid_o(conv2_out_valid),
        .out_data_o (conv2_out_data)
    );

    // Main path latency = 2×(line_buffer fill + conv pipeline) + relu
    // line_buffer fill = 2*WIDTH + 2, conv pipeline = 2, relu = 1
    localparam MAIN_PATH_DELAY = 4*WIDTH + 9;

    delay_buffer #(
        .DATA_BITS   (DATA_BITS),
        .DELAY_CYCLES(MAIN_PATH_DELAY)
    ) delay_buffer_inst (
        .clk        (clk),
        .rst        (rst),
        .in_valid_i (in_valid_i),
        .in_data_i  (in_data_i),
        .out_valid_o(delay_out_valid),
        .out_data_o (delay_out_data)
    );

    // -------------------------------------------------------------------------
    // Combinational adder: Conv2 output + delayed x (sign-extended)
    // -------------------------------------------------------------------------

    assign adder_valid = conv2_out_valid & delay_out_valid;
    assign adder_data  = conv2_out_data + {{24{delay_out_data[DATA_BITS-1]}}, delay_out_data};

    relu #(
        .IN_BITS (32),
        .OUT_BITS(DATA_BITS)
    ) relu2 (
        .clk        (clk),
        .rst        (rst),
        .in_valid_i (adder_valid),
        .in_data_i  (adder_data),
        .out_valid_o(relu2_out_valid),
        .out_data_o (relu2_out_data)
    );

    // -------------------------------------------------------------------------
    // Top-level output assignments
    // -------------------------------------------------------------------------

    assign out_valid_o = relu2_out_valid;
    assign out_data_o  = relu2_out_data;

endmodule

`resetall
