// -----------------------------------------------------------------------------
// File   : uart_tx.v
// Author : AI Designer
// Date   : 2026-04-15
// -----------------------------------------------------------------------------
// Description:
//   UART transmitter — parallel-to-serial converter with FSM for 8N1 frame
//   format. Drives start bit (low), 8 data bits LSB-first, and stop bit (high).
//   Operates on 16x oversampling ticks from the baud rate generator. Each bit
//   period spans 16 tick_16x cycles. No parity bit per design specification.
// -----------------------------------------------------------------------------
// Change Log:
//   2026-04-15  AI Designer  v1.0  Initial release
// -----------------------------------------------------------------------------

`resetall
`timescale 1ns / 1ps
`default_nettype none

module uart_tx
(
    input  wire       clk,
    input  wire       rst_n,
    input  wire       tick_16x,
    input  wire [7:0] tx_data,
    input  wire       tx_en,
    output wire       uart_txd,
    output wire       tx_busy
);

    // -------------------------------------------------------------------------
    // FSM state encoding (2 bits)
    // -------------------------------------------------------------------------
    localparam [1:0]
        TX_IDLE  = 2'd0,
        TX_START = 2'd1,
        TX_DATA  = 2'd2,
        TX_STOP  = 2'd3;

    // -------------------------------------------------------------------------
    // Internal registers
    // -------------------------------------------------------------------------
    reg [1:0] state_reg    = TX_IDLE,    state_next;
    reg [7:0] shift_reg    = 8'd0,       shift_next;
    reg [2:0] bit_cnt_reg  = 3'd0,       bit_cnt_next;
    reg [3:0] tick_cnt_reg = 4'd0,       tick_cnt_next;
    reg       uart_txd_reg = 1'b1,       uart_txd_next;
    reg       tx_busy_reg  = 1'b0,       tx_busy_next;

    // -------------------------------------------------------------------------
    // Output port assignments
    // -------------------------------------------------------------------------
    assign uart_txd = uart_txd_reg;
    assign tx_busy  = tx_busy_reg;

    // -------------------------------------------------------------------------
    // Combinational logic — next-state and output decode
    // -------------------------------------------------------------------------
    always @* begin
        // Default values — hold state, preserve registers
        state_next    = state_reg;
        shift_next    = shift_reg;
        bit_cnt_next  = bit_cnt_reg;
        tick_cnt_next = tick_cnt_reg;
        uart_txd_next = uart_txd_reg;
        tx_busy_next  = tx_busy_reg;

        // Tick counter increments on every tick_16x pulse
        if (tick_16x) begin
            tick_cnt_next = tick_cnt_reg + 4'd1;
        end

        case (state_reg)
            TX_IDLE: begin
                uart_txd_next = 1'b1;
                tx_busy_next  = 1'b0;
                if (tx_en) begin
                    shift_next    = tx_data;
                    tx_busy_next  = 1'b1;
                    tick_cnt_next = 4'd0;
                    state_next    = TX_START;
                    uart_txd_next = 1'b0;
                end
            end

            TX_START: begin
                uart_txd_next = 1'b0;
                if (tick_16x && tick_cnt_reg == 4'd15) begin
                    tick_cnt_next = 4'd0;
                    bit_cnt_next  = 3'd0;
                    state_next    = TX_DATA;
                end
            end

            TX_DATA: begin
                uart_txd_next = shift_reg[0];
                if (tick_16x && tick_cnt_reg == 4'd15) begin
                    tick_cnt_next = 4'd0;
                    shift_next    = {1'b0, shift_reg[7:1]};
                    if (bit_cnt_reg == 3'd7) begin
                        state_next = TX_STOP;
                    end else begin
                        bit_cnt_next = bit_cnt_reg + 3'd1;
                    end
                end
            end

            TX_STOP: begin
                uart_txd_next = 1'b1;
                if (tick_16x && tick_cnt_reg == 4'd15) begin
                    tx_busy_next = 1'b0;
                    state_next   = TX_IDLE;
                end
            end

            default: begin
                state_next = TX_IDLE;
            end
        endcase
    end

    // -------------------------------------------------------------------------
    // Sequential logic — register update with async reset
    // -------------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_reg    <= TX_IDLE;
            shift_reg    <= 8'd0;
            bit_cnt_reg  <= 3'd0;
            tick_cnt_reg <= 4'd0;
            uart_txd_reg <= 1'b1;
            tx_busy_reg  <= 1'b0;
        end else begin
            state_reg    <= state_next;
            shift_reg    <= shift_next;
            bit_cnt_reg  <= bit_cnt_next;
            tick_cnt_reg <= tick_cnt_next;
            uart_txd_reg <= uart_txd_next;
            tx_busy_reg  <= tx_busy_next;
        end
    end

endmodule

`resetall
