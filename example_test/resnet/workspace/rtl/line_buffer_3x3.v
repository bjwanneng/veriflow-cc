`resetall
`timescale 1ns / 1ps
`default_nettype none

// line_buffer_3x3 — streaming 3×3 window extractor with zero-padding on all sides.
//
// For a WIDTH×HEIGHT input image, produces WIDTH×HEIGHT output windows.
// Padding mode: pad=1 on all four edges (output size = input size).
//
// Timing: first output appears 1 cycle after START_ROW_THRESH rows are
// fully received.  Total output latency = START_ROW_THRESH*WIDTH + 1 +
// (HEIGHT-START_ROW_THRESH)*WIDTH + 1  cycles from first input pixel.
//
// Architecture: 4 rotating line buffers (minimum for conflict-free
// full-padding convolution).

module line_buffer_3x3 #(
    parameter WIDTH     = 16,
    parameter HEIGHT    = 16,
    parameter DATA_BITS = 8
) (
    input  wire                  clk,
    input  wire                  rst,
    input  wire                  in_valid_i,
    input  wire [DATA_BITS-1:0]  in_data_i,
    output wire                  out_valid_o,
    output wire [DATA_BITS*9-1:0] out_window_o
);

    // -------------------------------------------------------------------------
    // Constants
    // -------------------------------------------------------------------------
    localparam PIXEL_COUNT    = WIDTH * HEIGHT;
    localparam PC_BITS        = $clog2(PIXEL_COUNT + 1);
    localparam START_ROW_THRESH = (HEIGHT >= 2) ? 2'd2 : 2'd1;

    // -------------------------------------------------------------------------
    // Four rotating line buffers (minimum for conflict-free full padding)
    // -------------------------------------------------------------------------
    reg [DATA_BITS-1:0] line_buf [0:3][0:WIDTH-1];

    // -------------------------------------------------------------------------
    // Input tracking
    // -------------------------------------------------------------------------
    reg [1:0]               wr_buf_idx;   // 0..3 rotates every row
    reg [$clog2(WIDTH)-1:0] wr_col;
    reg [$clog2(HEIGHT):0]  wr_row;       // rows received so far

    // -------------------------------------------------------------------------
    // Output tracking
    // -------------------------------------------------------------------------
    reg                    out_running;
    reg [PC_BITS-1:0]      out_cnt;
    reg [$clog2(HEIGHT)-1:0] out_row;
    reg [$clog2(WIDTH)-1:0]  out_col;

    reg                  out_valid_reg;
    reg [DATA_BITS-1:0]  out_window_reg [0:8];

    // -------------------------------------------------------------------------
    // Combinational window formation for current (out_row, out_col)
    // -------------------------------------------------------------------------
    wire [$clog2(HEIGHT)-1:0] out_row_m1 = out_row - 1;
    wire [$clog2(HEIGHT)-1:0] out_row_p1 = out_row + 1;

    wire [1:0] buf_top = (out_row > 0)              ? out_row_m1[1:0] : 2'd0;
    wire [1:0] buf_mid = out_row[1:0];
    wire [1:0] buf_bot = (out_row < HEIGHT - 1)     ? out_row_p1[1:0] : 2'd0;

    wire [$clog2(WIDTH)-1:0] col_left  = (out_col > 0)        ? (out_col - 1) : {$clog2(WIDTH){1'b0}};
    wire [$clog2(WIDTH)-1:0] col_mid   = out_col;
    wire [$clog2(WIDTH)-1:0] col_right = (out_col < WIDTH - 1) ? (out_col + 1) : {$clog2(WIDTH){1'b0}};

    wire [DATA_BITS-1:0] w00 = (out_row > 0        && out_col > 0)        ? line_buf[buf_top][col_left]  : {DATA_BITS{1'b0}};
    wire [DATA_BITS-1:0] w01 = (out_row > 0)                              ? line_buf[buf_top][col_mid]   : {DATA_BITS{1'b0}};
    wire [DATA_BITS-1:0] w02 = (out_row > 0        && out_col < WIDTH-1)  ? line_buf[buf_top][col_right] : {DATA_BITS{1'b0}};

    wire [DATA_BITS-1:0] w10 = (out_col > 0)                              ? line_buf[buf_mid][col_left]  : {DATA_BITS{1'b0}};
    wire [DATA_BITS-1:0] w11 =                                          line_buf[buf_mid][col_mid];
    wire [DATA_BITS-1:0] w12 = (out_col < WIDTH-1)                        ? line_buf[buf_mid][col_right] : {DATA_BITS{1'b0}};

    wire [DATA_BITS-1:0] w20 = (out_row < HEIGHT-1 && out_col > 0)        ? line_buf[buf_bot][col_left]  : {DATA_BITS{1'b0}};
    wire [DATA_BITS-1:0] w21 = (out_row < HEIGHT-1)                       ? line_buf[buf_bot][col_mid]   : {DATA_BITS{1'b0}};
    wire [DATA_BITS-1:0] w22 = (out_row < HEIGHT-1 && out_col < WIDTH-1)  ? line_buf[buf_bot][col_right] : {DATA_BITS{1'b0}};

    integer j;

    // -------------------------------------------------------------------------
    // Sequential logic
    // -------------------------------------------------------------------------
    always @(posedge clk) begin
        if (rst) begin
            wr_buf_idx    <= 2'd0;
            wr_col        <= {$clog2(WIDTH){1'b0}};
            wr_row        <= {$clog2(HEIGHT)+1{1'b0}};
            out_running   <= 1'b0;
            out_cnt       <= {PC_BITS{1'b0}};
            out_row       <= {$clog2(HEIGHT){1'b0}};
            out_col       <= {$clog2(WIDTH){1'b0}};
            out_valid_reg <= 1'b0;
            for (j = 0; j < 9; j = j + 1)
                out_window_reg[j] <= {DATA_BITS{1'b0}};
        end else begin
            // ---- Write incoming pixel -------------------------------------
            if (in_valid_i) begin
                line_buf[wr_buf_idx][wr_col] <= in_data_i;
                wr_col <= wr_col + {{$clog2(WIDTH)-1{1'b0}}, 1'b1};
                if (wr_col == WIDTH[$clog2(WIDTH)-1:0] - {{$clog2(WIDTH)-1{1'b0}}, 1'b1}) begin
                    wr_buf_idx <= wr_buf_idx + 2'd1;
                    wr_row     <= wr_row + 1;
                end
            end

            // ---- Start outputting when enough rows are buffered -----------
            if (!out_running && wr_row >= START_ROW_THRESH) begin
                out_running <= 1'b1;
            end

            // ---- Produce one window per cycle -----------------------------
            if (out_running) begin
                out_valid_reg <= 1'b1;

                out_window_reg[0] <= w00;  // top-left
                out_window_reg[1] <= w01;  // top-center
                out_window_reg[2] <= w02;  // top-right
                out_window_reg[3] <= w10;  // mid-left
                out_window_reg[4] <= w11;  // mid-center
                out_window_reg[5] <= w12;  // mid-right
                out_window_reg[6] <= w20;  // bot-left
                out_window_reg[7] <= w21;  // bot-center
                out_window_reg[8] <= w22;  // bot-right

                out_col <= out_col + {{$clog2(WIDTH)-1{1'b0}}, 1'b1};
                if (out_col == WIDTH[$clog2(WIDTH)-1:0] - {{$clog2(WIDTH)-1{1'b0}}, 1'b1}) begin
                    out_row <= out_row + 1;
                end

                out_cnt <= out_cnt + 1;
                if (out_cnt == PIXEL_COUNT[PC_BITS-1:0] - 1) begin
                    out_running <= 1'b0;
                end
            end else begin
                out_valid_reg <= 1'b0;
            end
        end
    end

    // -------------------------------------------------------------------------
    // Output assignments
    // -------------------------------------------------------------------------
    assign out_valid_o = out_valid_reg;
    assign out_window_o = {
        out_window_reg[0], out_window_reg[1], out_window_reg[2],
        out_window_reg[3], out_window_reg[4], out_window_reg[5],
        out_window_reg[6], out_window_reg[7], out_window_reg[8]
    };

endmodule
`resetall
