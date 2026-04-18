// -----------------------------------------------------------------------------
// File   : uart_rx.v
// Author : AI Designer
// Date   : 2026-04-15
// -----------------------------------------------------------------------------
// Description:
//   UART receiver with 16x oversampling, two-stage input synchronizer, and
//   FSM for start/data/stop detection with frame error indication. Samples
//   each bit at the midpoint (tick 7 of 0-15) for maximum noise margin.
// -----------------------------------------------------------------------------
// Change Log:
//   2026-04-15  AI Designer  v1.0  Initial release
// -----------------------------------------------------------------------------

`resetall
`timescale 1ns / 1ps
`default_nettype none

module uart_rx
(
    input  wire           clk,
    input  wire           rst_n,
    input  wire           tick_16x,
    input  wire           uart_rxd,
    output wire [7:0]     rx_data,
    output wire           rx_done,
    output wire           rx_frame_err
);

    /////////////////////////
    // Parameters & Constants //
    /////////////////////////

    // RX FSM state encoding
    localparam [1:0]
        RX_STATE_IDLE  = 2'd0,
        RX_STATE_START = 2'd1,
        RX_STATE_DATA  = 2'd2,
        RX_STATE_STOP  = 2'd3;

    // Midpoint sample tick (center of bit period in 0..15 range)
    localparam [3:0] TICK_MIDPOINT = 4'd7;

    // End of bit period tick
    localparam [3:0] TICK_BIT_END = 4'd15;

    /////////////////////////
    // Internal Registers    //
    /////////////////////////

    // FSM state
    reg [1:0] state_reg = RX_STATE_IDLE, state_next;

    // Two-stage input synchronizer for uart_rxd
    reg       rxd_meta     = 1'b1;
    reg       rxd_sync_reg = 1'b1;

    // Previous rxd_sync for falling-edge detection
    reg       rxd_sync_d1_reg = 1'b1;

    // Shift register for received data bits
    reg [7:0] shift_reg_reg = 8'd0, shift_reg_next;

    // Data bit counter (0-7)
    reg [2:0] bit_cnt_reg = 3'd0, bit_cnt_next;

    // Oversampling tick counter (0-15)
    reg [3:0] tick_cnt_reg = 4'd0, tick_cnt_next;

    // Frame error flag (level-held)
    reg       rx_frame_err_reg = 1'b0, rx_frame_err_next;

    // Receive done pulse
    reg       rx_done_reg = 1'b0, rx_done_next;

    // Output data register
    reg [7:0] rx_data_reg = 8'd0, rx_data_next;

    /////////////////////////
    // Output Assignments    //
    /////////////////////////

    assign rx_data       = rx_data_reg;
    assign rx_done       = rx_done_reg;
    assign rx_frame_err  = rx_frame_err_reg;

    /////////////////////////////////
    // Input Synchronizer (always runs) //
    /////////////////////////////////

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rxd_meta     <= 1'b1;
            rxd_sync_reg <= 1'b1;
        end else begin
            rxd_meta     <= uart_rxd;
            rxd_sync_reg <= rxd_meta;
        end
    end

    /////////////////////////////////
    // Edge Detection Register       //
    /////////////////////////////////

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rxd_sync_d1_reg <= 1'b1;
        end else begin
            rxd_sync_d1_reg <= rxd_sync_reg;
        end
    end

    /////////////////////////
    // Combinational Logic   //
    /////////////////////////

    // Falling edge detection on synchronized RXD
    wire falling_edge = (rxd_sync_reg == 1'b0) && (rxd_sync_d1_reg == 1'b1);

    always @* begin
        // Default values — prevent latches
        state_next        = state_reg;
        shift_reg_next    = shift_reg_reg;
        bit_cnt_next      = bit_cnt_reg;
        tick_cnt_next     = tick_cnt_reg;
        rx_frame_err_next = rx_frame_err_reg;
        rx_done_next      = 1'b0;
        rx_data_next      = rx_data_reg;

        // Frame error clears when returning to IDLE (new start bit detection)
        if (state_reg == RX_STATE_IDLE) begin
            rx_frame_err_next = 1'b0;
        end

        case (state_reg)
            RX_STATE_IDLE: begin
                if (falling_edge) begin
                    tick_cnt_next = 4'd0;
                    state_next    = RX_STATE_START;
                end
            end

            RX_STATE_START: begin
                if (tick_16x) begin
                    tick_cnt_next = tick_cnt_reg + 4'd1;

                    // Midpoint check — false start detection
                    if (tick_cnt_reg == TICK_MIDPOINT) begin
                        if (rxd_sync_reg != 1'b0) begin
                            // False start — glitch detected
                            state_next = RX_STATE_IDLE;
                        end
                    end

                    // End of start-bit period
                    if (tick_cnt_reg == TICK_BIT_END) begin
                        if (rxd_sync_reg == 1'b0) begin
                            // Valid start bit confirmed
                            tick_cnt_next = 4'd0;
                            bit_cnt_next  = 3'd0;
                            state_next    = RX_STATE_DATA;
                        end else begin
                            // Start bit not valid at end
                            state_next = RX_STATE_IDLE;
                        end
                    end
                end
            end

            RX_STATE_DATA: begin
                if (tick_16x) begin
                    tick_cnt_next = tick_cnt_reg + 4'd1;

                    // Sample at midpoint
                    if (tick_cnt_reg == TICK_MIDPOINT) begin
                        shift_reg_next[bit_cnt_reg] = rxd_sync_reg;
                    end

                    // End of bit period
                    if (tick_cnt_reg == TICK_BIT_END) begin
                        tick_cnt_next = 4'd0;
                        if (bit_cnt_reg == 3'd7) begin
                            state_next = RX_STATE_STOP;
                        end else begin
                            bit_cnt_next = bit_cnt_reg + 3'd1;
                        end
                    end
                end
            end

            RX_STATE_STOP: begin
                if (tick_16x) begin
                    tick_cnt_next = tick_cnt_reg + 4'd1;

                    // Sample stop bit at midpoint
                    if (tick_cnt_reg == TICK_MIDPOINT) begin
                        if (rxd_sync_reg == 1'b1) begin
                            rx_frame_err_next = 1'b0;
                        end else begin
                            rx_frame_err_next = 1'b1;
                        end
                    end

                    // End of stop-bit period
                    if (tick_cnt_reg == TICK_BIT_END) begin
                        rx_data_next = shift_reg_reg;
                        rx_done_next = 1'b1;
                        state_next   = RX_STATE_IDLE;
                    end
                end
            end

            default: begin
                state_next = RX_STATE_IDLE;
            end
        endcase
    end

    /////////////////////////
    // Sequential Logic      //
    /////////////////////////

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_reg        <= RX_STATE_IDLE;
            shift_reg_reg    <= 8'd0;
            bit_cnt_reg      <= 3'd0;
            tick_cnt_reg     <= 4'd0;
            rx_frame_err_reg <= 1'b0;
            rx_done_reg      <= 1'b0;
            rx_data_reg      <= 8'd0;
        end else begin
            state_reg        <= state_next;
            shift_reg_reg    <= shift_reg_next;
            bit_cnt_reg      <= bit_cnt_next;
            tick_cnt_reg     <= tick_cnt_next;
            rx_frame_err_reg <= rx_frame_err_next;
            rx_done_reg      <= rx_done_next;
            rx_data_reg      <= rx_data_next;
        end
    end

endmodule

`resetall
