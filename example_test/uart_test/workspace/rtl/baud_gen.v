// -----------------------------------------------------------------------------
// File   : baud_gen.v
// Author : Auto-generated
// Date   : 2026-04-15
// -----------------------------------------------------------------------------
// Description:
//   Baud rate tick generator producing 16x oversampling clock ticks.
//   Free-running counter counts from 0 to DIV-1, emitting a 1-cycle-high
//   tick_16x pulse each time the terminal count is reached.
//   DIV = CLK_FREQ / (BAUD_RATE * OVERSAMPLE) = 27 for 50MHz/115200/16x.
// -----------------------------------------------------------------------------
// Change Log:
//   2026-04-15  Auto-generated  v1.0  Initial release
// -----------------------------------------------------------------------------

`resetall
`timescale 1ns / 1ps
`default_nettype none

module baud_gen #
(
    // System clock frequency in Hz
    parameter CLK_FREQ   = 50000000,
    // Target baud rate
    parameter BAUD_RATE  = 115200,
    // Oversampling factor
    parameter OVERSAMPLE = 16
)
(
    input  wire clk,
    input  wire rst_n,
    output wire tick_16x
);

    // -------------------------------------------------------------------------
    // Derived constants
    // -------------------------------------------------------------------------
    // Divider value: number of system clocks per 16x tick
    localparam DIV = CLK_FREQ / (BAUD_RATE * OVERSAMPLE);  // 27 for default params

    // Counter width: ceil(log2(DIV))
    localparam CNT_WIDTH = 5;

    // Terminal count value (DIV - 1)
    localparam DIV_MINUS_1 = DIV - 1;

    // -------------------------------------------------------------------------
    // Internal signals
    // -------------------------------------------------------------------------
    reg [CNT_WIDTH-1:0] cnt_reg   = {CNT_WIDTH{1'b0}}, cnt_next;
    reg                 tick_reg  = 1'b0,               tick_next;

    // -------------------------------------------------------------------------
    // Combinational logic — next-state and output decode
    // -------------------------------------------------------------------------
    always @* begin
        cnt_next  = cnt_reg;
        tick_next = 1'b0;

        if (cnt_reg == DIV_MINUS_1[CNT_WIDTH-1:0]) begin
            cnt_next  = {CNT_WIDTH{1'b0}};
            tick_next = 1'b1;
        end else begin
            cnt_next  = cnt_reg + {{(CNT_WIDTH-1){1'b0}}, 1'b1};
            tick_next = 1'b0;
        end
    end

    // -------------------------------------------------------------------------
    // Sequential logic — register update
    // -------------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cnt_reg  <= {CNT_WIDTH{1'b0}};
            tick_reg <= 1'b0;
        end else begin
            cnt_reg  <= cnt_next;
            tick_reg <= tick_next;
        end
    end

    // -------------------------------------------------------------------------
    // Output assignment
    // -------------------------------------------------------------------------
    assign tick_16x = tick_reg;

endmodule

`resetall
