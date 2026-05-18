`resetall
`timescale 1ns / 1ps
`default_nettype none

module conv2d_engine #(
    parameter IMG_WIDTH  = 128,
    parameter IMG_HEIGHT = 128
)(
    input  wire        clk,
    input  wire        rst,
    input  wire        cfg_valid,
    input  wire  [7:0] cfg_data,
    output wire        cfg_ready,
    input  wire        in_valid,
    output wire        in_ready,
    input  wire  [7:0] in_pixel,
    output wire        out_valid,
    input  wire        out_ready,
    output wire [23:0] out_result
);

    // ---------------------------------------------------------------
    // FSM states
    // ---------------------------------------------------------------
    localparam [2:0] STATE_CONFIG  = 3'd0,
                     STATE_FILL    = 3'd1,
                     STATE_COMPUTE = 3'd2,
                     STATE_DONE    = 3'd3;

    // ---------------------------------------------------------------
    // Internal registers
    // ---------------------------------------------------------------
    reg [2:0]  state_reg       = STATE_CONFIG;
    reg [2:0]  state_next;

    // Config
    reg [7:0]  kernel_reg [0:8];
    reg        stride_reg      = 1'b0;  // 0=stride1, 1=stride2
    reg        padding_reg     = 1'b0;  // 0=valid, 1=same
    reg [3:0]  cfg_count_reg   = 4'd0;

    // Counters
    // pipeline_cnt tracks the pipeline position (always increments)
    // pixel_cnt tracks how many real pixels have been consumed
    reg [$clog2(IMG_WIDTH+2)-1:0]  col_cnt_reg  = {$clog2(IMG_WIDTH+2){1'b0}};
    reg [$clog2(IMG_HEIGHT+2)-1:0] row_cnt_reg  = {$clog2(IMG_HEIGHT+2){1'b0}};
    reg [31:0] pixel_cnt_reg       = 32'd0;

    // Line buffers
    reg [7:0]  line_buf_0 [0:IMG_WIDTH-1];
    reg [7:0]  line_buf_1 [0:IMG_WIDTH-1];

    // Sliding window
    reg [7:0]  window_reg [0:2][0:2];

    // Pipeline / output registers
    reg        out_valid_reg  = 1'b0;
    reg [23:0] out_result_reg = {24{1'b0}};
    reg        cfg_ready_reg  = 1'b1;

    // ---------------------------------------------------------------
    // Derived constants and wires
    // ---------------------------------------------------------------
    wire [31:0] total_real_pixels = IMG_WIDTH * IMG_HEIGHT;

    // Total pipeline cycles per frame
    wire [31:0] total_pipe_cycles = padding_reg
        ? ((IMG_WIDTH + 1) * (IMG_HEIGHT + 1))
        : (IMG_WIDTH * IMG_HEIGHT);

    // Counter wrap limits
    // During FILL: always use standard limits (W-1, H-1) since only real pixels advance
    // During COMPUTE with same padding: use extended limits (W, H)
    wire in_compute = (state_reg == STATE_COMPUTE);
    wire [$clog2(IMG_WIDTH+2)-1:0]  col_limit =
        (padding_reg && in_compute) ? IMG_WIDTH : (IMG_WIDTH - 1);
    wire [$clog2(IMG_HEIGHT+2)-1:0] row_limit =
        (padding_reg && in_compute) ? IMG_HEIGHT : (IMG_HEIGHT - 1);

    // Pipeline advance control:
    // Valid padding: advance only when consuming a real pixel (no virtual zeros)
    // Same padding:  advance every cycle during COMPUTE (virtual zeros fill gaps)
    wire output_stalled = out_valid_reg & ~out_ready;

    // Is the current column position within the real image bounds?
    wire col_in_img = (col_cnt_reg < IMG_WIDTH);

    // Only accept real pixels when pipeline position is within image bounds.
    // For same padding, col can go to IMG_WIDTH (virtual) -- don't accept real
    // pixels there. Similarly row can go to IMG_HEIGHT.
    wire pos_in_image = col_in_img && (row_cnt_reg < IMG_HEIGHT);

    wire can_accept_real = (state_reg == STATE_FILL || state_reg == STATE_COMPUTE)
                           & ~output_stalled
                           & (pixel_cnt_reg < total_real_pixels)
                           & pos_in_image;

    wire accepting = can_accept_real & in_valid;

    // Advance control:
    // Valid padding: advance only when consuming a real pixel.
    // Same padding: during FILL, advance when consuming a real pixel.
    //   During COMPUTE: at real positions (col < W, row < H), advance when accepting.
    //   At virtual columns (col == W) or virtual rows (row == H): advance unconditionally.
    wire in_virtual_row = padding_reg && in_compute && (row_cnt_reg >= IMG_HEIGHT);
    wire advance = padding_reg
        ? (state_reg == STATE_COMPUTE
           ? (~output_stalled & (in_virtual_row ? 1'b1 : (col_in_img ? accepting : 1'b1)))
           : accepting)
        : accepting;

    // Window shift: must shift at every advance for correct MAC computation.
    // At virtual positions, window loads zeros (via lb0_col/current_pixel guards).
    wire window_advance = advance;

    // in_ready: combinational
    assign in_ready = can_accept_real;

    // Pixel source: real pixel if accepting, else virtual zero
    wire use_real_pixel = accepting;
    wire [7:0] current_pixel = use_real_pixel ? in_pixel : 8'd0;

    // cfg_ready: registered output
    assign cfg_ready = cfg_ready_reg;

    // Output ports
    assign out_valid  = out_valid_reg;
    assign out_result = out_result_reg;

    // ---------------------------------------------------------------
    // Next counter values (combinational)
    // ---------------------------------------------------------------
    wire [$clog2(IMG_WIDTH+2)-1:0]  col_cnt_next;
    wire [$clog2(IMG_HEIGHT+2)-1:0] row_cnt_next;
    wire [31:0]                     pixel_cnt_next;

    assign col_cnt_next = advance
        ? ((col_cnt_reg == col_limit)
           ? {$clog2(IMG_WIDTH+2){1'b0}}
           : (col_cnt_reg + {{$clog2(IMG_WIDTH+2)-1{1'b0}}, 1'b1}))
        : col_cnt_reg;

    assign row_cnt_next = advance
        ? ((col_cnt_reg == col_limit)
           ? ((row_cnt_reg == row_limit)
              ? {$clog2(IMG_HEIGHT+2){1'b0}}
              : (row_cnt_reg + {{$clog2(IMG_HEIGHT+2)-1{1'b0}}, 1'b1}))
           : row_cnt_reg)
        : row_cnt_reg;

    assign pixel_cnt_next = use_real_pixel
        ? (pixel_cnt_reg + 32'd1)
        : pixel_cnt_reg;

    // Pipeline cycle counter (for FSM done condition)
    wire [31:0] pipe_cnt_next = advance ? (col_cnt_reg == col_limit && row_cnt_reg == row_limit)
                                          ? 32'd0  // wraps
                                          : {30'd0, 1'b0, 1'b0}  // placeholder
                                        : 32'd0;
    // Actually, use a simpler approach: track total pipeline advances
    reg [31:0] pipe_cycle_reg = 32'd0;
    wire [31:0] pipe_cycle_next = advance ? (pipe_cycle_reg + 32'd1) : pipe_cycle_reg;

    // ---------------------------------------------------------------
    // Line buffer read for window load
    // ---------------------------------------------------------------
    wire [7:0] lb0_col = col_in_img ? line_buf_0[col_cnt_reg] : 8'd0;
    wire [7:0] lb1_col = col_in_img ? line_buf_1[col_cnt_reg] : 8'd0;

    // ---------------------------------------------------------------
    // Zero-substitution for same-padding
    // ---------------------------------------------------------------
    // New window at position (row_cnt_reg, col_cnt_reg):
    //   window_new[ky][kx] = image[row-2+ky][col-2+kx]
    //   Zero when out of bounds (< 0 or >= IMG_HEIGHT/WIDTH)

    wire signed [$clog2(IMG_HEIGHT+2):0] img_y_r0 = $signed({1'b0, row_cnt_reg}) - 2;
    wire signed [$clog2(IMG_HEIGHT+2):0] img_y_r1 = $signed({1'b0, row_cnt_reg}) - 1;
    wire signed [$clog2(IMG_HEIGHT+2):0] img_y_r2 = $signed({1'b0, row_cnt_reg});

    wire row0_in = (img_y_r0 >= 0) && (img_y_r0 < IMG_HEIGHT);
    wire row1_in = (img_y_r1 >= 0) && (img_y_r1 < IMG_HEIGHT);
    wire row2_in = (img_y_r2 >= 0) && (img_y_r2 < IMG_HEIGHT);

    wire signed [$clog2(IMG_WIDTH+2):0] img_x_c0 = $signed({1'b0, col_cnt_reg}) - 2;
    wire signed [$clog2(IMG_WIDTH+2):0] img_x_c1 = $signed({1'b0, col_cnt_reg}) - 1;
    wire signed [$clog2(IMG_WIDTH+2):0] img_x_c2 = $signed({1'b0, col_cnt_reg});

    wire col0_in = (img_x_c0 >= 0) && (img_x_c0 < IMG_WIDTH);
    wire col1_in = (img_x_c1 >= 0) && (img_x_c1 < IMG_WIDTH);
    wire col2_in = (img_x_c2 >= 0) && (img_x_c2 < IMG_WIDTH);

    // Effective window values with zero-substitution
    // The MAC reads from the next window state (after shift+load).
    // window_new[ky][0] = old window_reg[ky][1]
    // window_new[ky][1] = old window_reg[ky][2]
    // window_new[ky][2] = new column (lb0, lb1, or current_pixel)
    // At virtual columns (window frozen), window_reg still holds the data
    // from the last real column position, and lb0_col/lb1_col are zero
    // (guarded by col_in_img). This produces the correct MAC values because:
    //   - eff[ky][0] = window_reg[ky][1] = data from col-2 (correct)
    //   - eff[ky][1] = window_reg[ky][2] = data from col-1 (correct)
    //   - eff[ky][2] = lb_col or current_pixel = 0 (correct, out of bounds)
    wire [7:0] eff_win_0_0 = (row0_in && col0_in) ? window_reg[0][1] : 8'd0;
    wire [7:0] eff_win_0_1 = (row0_in && col1_in) ? window_reg[0][2] : 8'd0;
    wire [7:0] eff_win_0_2 = (row0_in && col2_in) ? lb0_col          : 8'd0;

    wire [7:0] eff_win_1_0 = (row1_in && col0_in) ? window_reg[1][1] : 8'd0;
    wire [7:0] eff_win_1_1 = (row1_in && col1_in) ? window_reg[1][2] : 8'd0;
    wire [7:0] eff_win_1_2 = (row1_in && col2_in) ? lb1_col          : 8'd0;

    wire [7:0] eff_win_2_0 = (row2_in && col0_in) ? window_reg[2][1] : 8'd0;
    wire [7:0] eff_win_2_1 = (row2_in && col1_in) ? window_reg[2][2] : 8'd0;
    wire [7:0] eff_win_2_2 = (row2_in && col2_in) ? current_pixel    : 8'd0;

    // ---------------------------------------------------------------
    // MAC: 9 parallel signed multipliers + adder tree
    // ---------------------------------------------------------------
    wire signed [16:0] prod_0 = $signed({1'b0, eff_win_0_0}) * $signed(kernel_reg[0]);
    wire signed [16:0] prod_1 = $signed({1'b0, eff_win_0_1}) * $signed(kernel_reg[1]);
    wire signed [16:0] prod_2 = $signed({1'b0, eff_win_0_2}) * $signed(kernel_reg[2]);
    wire signed [16:0] prod_3 = $signed({1'b0, eff_win_1_0}) * $signed(kernel_reg[3]);
    wire signed [16:0] prod_4 = $signed({1'b0, eff_win_1_1}) * $signed(kernel_reg[4]);
    wire signed [16:0] prod_5 = $signed({1'b0, eff_win_1_2}) * $signed(kernel_reg[5]);
    wire signed [16:0] prod_6 = $signed({1'b0, eff_win_2_0}) * $signed(kernel_reg[6]);
    wire signed [16:0] prod_7 = $signed({1'b0, eff_win_2_1}) * $signed(kernel_reg[7]);
    wire signed [16:0] prod_8 = $signed({1'b0, eff_win_2_2}) * $signed(kernel_reg[8]);

    wire signed [17:0] sum_r0 = prod_0 + prod_1 + prod_2;
    wire signed [17:0] sum_r1 = prod_3 + prod_4 + prod_5;
    wire signed [17:0] sum_r2 = prod_6 + prod_7 + prod_8;
    wire signed [18:0] sum_s0 = sum_r0 + sum_r1;
    wire signed [19:0] mac_result = sum_s0 + sum_r2;

    // ---------------------------------------------------------------
    // Output valid logic (combinational)
    // ---------------------------------------------------------------
    reg mac_valid_w;
    wire [23:0] mac_result_w = {{4{mac_result[19]}}, mac_result[19:0]};

    wire signed [$clog2(IMG_HEIGHT+2):0] out_y_valid = $signed({1'b0, row_cnt_reg}) - 2;
    wire signed [$clog2(IMG_WIDTH+2):0]  out_x_valid = $signed({1'b0, col_cnt_reg}) - 2;
    wire signed [$clog2(IMG_HEIGHT+2):0] out_y_same  = $signed({1'b0, row_cnt_reg}) - 1;
    wire signed [$clog2(IMG_WIDTH+2):0]  out_x_same  = $signed({1'b0, col_cnt_reg}) - 1;

    wire [31:0] out_h = padding_reg
        ? ((IMG_HEIGHT + (stride_reg ? 1 : 0)) / (stride_reg ? 2 : 1))
        : ((IMG_HEIGHT - 3) / (stride_reg ? 2 : 1) + 1);
    wire [31:0] out_w = padding_reg
        ? ((IMG_WIDTH + (stride_reg ? 1 : 0)) / (stride_reg ? 2 : 1))
        : ((IMG_WIDTH - 3) / (stride_reg ? 2 : 1) + 1);

    wire [1:0] stride_val = stride_reg ? 2'd2 : 2'd1;

    always @* begin
        mac_valid_w = 1'b0;

        if (advance) begin
            if (padding_reg == 1'b0) begin
                // Valid padding: need row >= 2, col >= 2
                if (row_cnt_reg >= 2 && col_cnt_reg >= 2) begin
                    if ((out_y_valid % stride_val) == 0 &&
                        (out_x_valid % stride_val) == 0) begin
                        // Compare in grid coordinates (divide by stride)
                        if ((out_y_valid / stride_val) < out_h &&
                            (out_x_valid / stride_val) < out_w) begin
                            mac_valid_w = 1'b1;
                        end
                    end
                end
            end else begin
                // Same padding: need row >= 1, col >= 1
                if (row_cnt_reg >= 1 && col_cnt_reg >= 1) begin
                    if ((out_y_same % stride_val) == 0 &&
                        (out_x_same % stride_val) == 0) begin
                        if (out_y_same >= 0 && out_x_same >= 0 &&
                            (out_y_same / stride_val) < out_h &&
                            (out_x_same / stride_val) < out_w) begin
                            mac_valid_w = 1'b1;
                        end
                    end
                end
            end
        end
    end

    // ---------------------------------------------------------------
    // FSM next-state logic (combinational)
    // ---------------------------------------------------------------
    always @* begin
        state_next = state_reg;

        case (state_reg)
            STATE_CONFIG: begin
                if (cfg_count_reg == 4'd10 && cfg_valid == 1'b1) begin
                    state_next = STATE_FILL;
                end
            end

            STATE_FILL: begin
                if (padding_reg == 1'b0) begin
                    // Valid padding: transition after (2,1) is processed
                    if (row_cnt_reg == 2 && col_cnt_reg == 1) begin
                        state_next = STATE_COMPUTE;
                    end
                end else begin
                    // Same padding: transition after (1,0) is processed
                    if (row_cnt_reg == 1 && col_cnt_reg == 0) begin
                        state_next = STATE_COMPUTE;
                    end
                end
            end

            STATE_COMPUTE: begin
                // Done when counters wrap past the last position
                // For same padding: after (row_limit, col_limit) = (H, W)
                // For valid padding: after all pixels consumed
                if (padding_reg) begin
                    // Check if this advance will complete the last position
                    if (advance && col_cnt_reg == col_limit && row_cnt_reg == row_limit) begin
                        state_next = STATE_DONE;
                    end
                end else begin
                    if (pixel_cnt_next >= total_pipe_cycles) begin
                        state_next = STATE_DONE;
                    end
                end
            end

            STATE_DONE: begin
                state_next = STATE_CONFIG;
            end

            default: begin
                state_next = STATE_CONFIG;
            end
        endcase
    end

    // ---------------------------------------------------------------
    // Sequential logic: ALL register updates in one always block
    // ---------------------------------------------------------------
    integer i;

    always @(posedge clk) begin
        if (rst) begin
            state_reg       <= STATE_CONFIG;
            cfg_count_reg   <= 4'd0;
            stride_reg      <= 1'b0;
            padding_reg     <= 1'b0;
            col_cnt_reg     <= {$clog2(IMG_WIDTH+2){1'b0}};
            row_cnt_reg     <= {$clog2(IMG_HEIGHT+2){1'b0}};
            pixel_cnt_reg   <= 32'd0;
            pipe_cycle_reg  <= 32'd0;
            out_valid_reg   <= 1'b0;
            out_result_reg  <= {24{1'b0}};
            cfg_ready_reg   <= 1'b1;

            for (i = 0; i < 9; i = i + 1) begin
                kernel_reg[i] <= 8'd0;
            end
            for (i = 0; i < IMG_WIDTH; i = i + 1) begin
                line_buf_0[i] <= 8'd0;
                line_buf_1[i] <= 8'd0;
            end
            for (i = 0; i < 3; i = i + 1) begin
                window_reg[i][0] <= 8'd0;
                window_reg[i][1] <= 8'd0;
                window_reg[i][2] <= 8'd0;
            end
        end else begin
            state_reg <= state_next;

            // ---- Config state: latch kernel + config ----
            if (state_reg == STATE_CONFIG && cfg_valid == 1'b1) begin
                if (cfg_count_reg <= 4'd8) begin
                    kernel_reg[cfg_count_reg] <= cfg_data;
                end else if (cfg_count_reg == 4'd9) begin
                    // cfg_data: 1=stride1, 2=stride2
                    stride_reg <= (cfg_data[1]) ? 1'b1 : 1'b0;
                end else if (cfg_count_reg == 4'd10) begin
                    padding_reg <= cfg_data[0];
                end
                cfg_count_reg <= cfg_count_reg + 4'd1;
            end

            // Reset config counter when DONE
            if (state_reg == STATE_DONE) begin
                cfg_count_reg <= 4'd0;
            end

            // cfg_ready: HIGH in CONFIG and DONE
            cfg_ready_reg <= (state_next == STATE_CONFIG) ||
                             (state_next == STATE_DONE);

            // ---- Output register update ----
            if (output_stalled) begin
                // Hold during backpressure
            end else begin
                if (state_reg == STATE_COMPUTE && mac_valid_w) begin
                    out_valid_reg  <= 1'b1;
                    out_result_reg <= mac_result_w;
                end else begin
                    out_valid_reg  <= 1'b0;
                    out_result_reg <= {24{1'b0}};
                end
            end

            // ---- Pipeline advance ----
            if (advance) begin
                col_cnt_reg    <= col_cnt_next;
                row_cnt_reg    <= row_cnt_next;
                pixel_cnt_reg  <= pixel_cnt_next;
                pipe_cycle_reg <= pipe_cycle_next;
            end

            // ---- Window shift: only at real image columns ----
            // At virtual columns (same padding), window is frozen to prevent
            // zeros from corrupting the state needed for the next real row.
            if (window_advance) begin
                window_reg[0][0] <= window_reg[0][1];
                window_reg[0][1] <= window_reg[0][2];
                window_reg[0][2] <= lb0_col;

                window_reg[1][0] <= window_reg[1][1];
                window_reg[1][1] <= window_reg[1][2];
                window_reg[1][2] <= lb1_col;

                window_reg[2][0] <= window_reg[2][1];
                window_reg[2][1] <= window_reg[2][2];
                window_reg[2][2] <= current_pixel;
            end

            // Update line buffers only at real image columns (guard against
            // out-of-bounds array access at virtual column col==IMG_WIDTH)
            if (window_advance && col_in_img) begin
                line_buf_0[col_cnt_reg] <= line_buf_1[col_cnt_reg];
                line_buf_1[col_cnt_reg] <= current_pixel;
            end

            // ---- Reset counters when transitioning to FILL ----
            if (state_reg == STATE_CONFIG && state_next == STATE_FILL) begin
                col_cnt_reg    <= {$clog2(IMG_WIDTH+2){1'b0}};
                row_cnt_reg    <= {$clog2(IMG_HEIGHT+2){1'b0}};
                pixel_cnt_reg  <= 32'd0;
                pipe_cycle_reg <= 32'd0;
            end
        end
    end

endmodule

`resetall
