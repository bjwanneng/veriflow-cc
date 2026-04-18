// -----------------------------------------------------------------------------
// File   : uart_top.v
// Author : AI Designer
// Date   : 2026-04-15
// -----------------------------------------------------------------------------
// Description:
//   Top-level UART transceiver wrapper. Instantiates baud_gen, uart_tx, and
//   uart_rx submodules with shared clock and synchronized reset. Contains a
//   2-stage reset synchronizer that produces rst_n_sync from the external
//   async active-low rst_n input. All submodules receive rst_n_sync.
// -----------------------------------------------------------------------------
// Change Log:
//   2026-04-15  AI Designer  v1.0  Initial release
// -----------------------------------------------------------------------------

`resetall
`timescale 1ns / 1ps
`default_nettype none

module uart_top
(
    input  wire       clk,
    input  wire       rst_n,
    input  wire [7:0] tx_data,
    input  wire       tx_en,
    output wire       uart_txd,
    output wire       tx_busy,
    input  wire       uart_rxd,
    output wire [7:0] rx_data,
    output wire       rx_done,
    output wire       rx_frame_err
);

    // -------------------------------------------------------------------------
    // Reset synchronizer — 2-stage FF for synchronous reset release
    // -------------------------------------------------------------------------
    reg rst_n_meta = 1'b0;
    reg rst_n_sync = 1'b0;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rst_n_meta <= 1'b0;
            rst_n_sync <= 1'b0;
        end else begin
            rst_n_meta <= 1'b1;
            rst_n_sync <= rst_n_meta;
        end
    end

    // -------------------------------------------------------------------------
    // Internal wires — inter-module connections
    // -------------------------------------------------------------------------
    wire tick_16x;

    // -------------------------------------------------------------------------
    // Baud rate generator instantiation
    // -------------------------------------------------------------------------
    baud_gen baud_gen_inst
    (
        .clk      (clk),
        .rst_n    (rst_n_sync),
        .tick_16x (tick_16x)
    );

    // -------------------------------------------------------------------------
    // UART transmitter instantiation
    // -------------------------------------------------------------------------
    uart_tx uart_tx_inst
    (
        .clk      (clk),
        .rst_n    (rst_n_sync),
        .tick_16x (tick_16x),
        .tx_data  (tx_data),
        .tx_en    (tx_en),
        .uart_txd (uart_txd),
        .tx_busy  (tx_busy)
    );

    // -------------------------------------------------------------------------
    // UART receiver instantiation
    // -------------------------------------------------------------------------
    uart_rx uart_rx_inst
    (
        .clk           (clk),
        .rst_n         (rst_n_sync),
        .tick_16x      (tick_16x),
        .uart_rxd      (uart_rxd),
        .rx_data       (rx_data),
        .rx_done       (rx_done),
        .rx_frame_err  (rx_frame_err)
    );

endmodule

`resetall
