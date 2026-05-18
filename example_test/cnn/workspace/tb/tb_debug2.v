`timescale 1ns / 1ps

module tb_debug2;

    parameter IMG_W = 5;
    parameter IMG_H = 5;
    parameter CLK_PERIOD = 10;

    reg        clk;
    reg        rst;
    reg        cfg_valid;
    reg  [7:0] cfg_data;
    wire       cfg_ready;
    reg        in_valid;
    wire       in_ready;
    reg  [7:0] in_pixel;
    wire       out_valid;
    reg        out_ready;
    wire [23:0] out_result;

    conv2d_engine #(
        .IMG_WIDTH (IMG_W),
        .IMG_HEIGHT(IMG_H)
    ) uut (
        .clk       (clk),
        .rst       (rst),
        .cfg_valid (cfg_valid),
        .cfg_data  (cfg_data),
        .cfg_ready (cfg_ready),
        .in_valid  (in_valid),
        .in_ready  (in_ready),
        .in_pixel  (in_pixel),
        .out_valid (out_valid),
        .out_ready (out_ready),
        .out_result(out_result)
    );

    initial clk = 0;
    always #(CLK_PERIOD/2) clk = ~clk;

    integer cycle = 0;
    always @(posedge clk) cycle <= cycle + 1;

    integer out_count = 0;

    always @(posedge clk) begin
        if (uut.state_reg == 3'd1 && uut.advance) begin
            $display("FILL cyc=%0d col=%0d row=%0d w=[%0d,%0d,%0d;%0d,%0d,%0d;%0d,%0d,%0d] pix=%0d lb0=%0d lb1=%0d",
                     cycle, uut.col_cnt_reg, uut.row_cnt_reg,
                     uut.window_reg[0][0], uut.window_reg[0][1], uut.window_reg[0][2],
                     uut.window_reg[1][0], uut.window_reg[1][1], uut.window_reg[1][2],
                     uut.window_reg[2][0], uut.window_reg[2][1], uut.window_reg[2][2],
                     in_pixel, uut.lb0_col, uut.lb1_col);
        end
        if (uut.state_reg == 3'd2 && uut.advance) begin
            $display("COMP cyc=%0d col=%0d row=%0d w=[%0d,%0d,%0d;%0d,%0d,%0d;%0d,%0d,%0d] pix=%0d lb0=%0d lb1=%0d mac=%b omod=%0d",
                     cycle, uut.col_cnt_reg, uut.row_cnt_reg,
                     uut.window_reg[0][0], uut.window_reg[0][1], uut.window_reg[0][2],
                     uut.window_reg[1][0], uut.window_reg[1][1], uut.window_reg[1][2],
                     uut.window_reg[2][0], uut.window_reg[2][1], uut.window_reg[2][2],
                     in_pixel, uut.lb0_col, uut.lb1_col,
                     uut.mac_valid_w, $signed(uut.mac_result_w));
        end
        if (out_valid === 1'b1 && out_ready === 1'b1) begin
            $display("[OUT] cyc=%0d result=%0d", cycle, $signed(out_result));
            out_count = out_count + 1;
        end
    end

    initial begin
        cfg_valid = 0; cfg_data = 0;
        in_valid = 0; in_pixel = 0;
        out_ready = 1;

        // Reset
        rst = 1;
        repeat(5) @(posedge clk);
        rst = 0;
        @(posedge clk);

        // Config: kernel all 1s, stride=1, padding=1 (SAME padding)
        begin : cfg
            integer i;
            reg [7:0] cfg [0:10];
            cfg[0]=1; cfg[1]=1; cfg[2]=1; cfg[3]=1; cfg[4]=1;
            cfg[5]=1; cfg[6]=1; cfg[7]=1; cfg[8]=1;
            cfg[9]=1; cfg[10]=1;  // stride=1, padding=1 (same)
            for (i = 0; i < 11; i = i + 1) begin
                @(posedge clk);
                cfg_data <= cfg[i];
                cfg_valid <= 1;
                @(posedge clk);
                cfg_valid <= 0;
                cfg_data <= 0;
                @(posedge clk);
            end
        end

        $display("Config done, streaming 5x5 image with SAME padding...");

        // Stream pixels 1..25, respecting in_ready
        begin : stream
            integer p;
            p = 1;
            while (p <= 25) begin
                @(posedge clk);
                if (in_ready) begin
                    in_pixel <= p;
                    in_valid <= 1;
                    p = p + 1;
                end else begin
                    in_valid <= 0;
                end
            end
            @(posedge clk);
            in_valid <= 0;
            in_pixel <= 0;
        end

        // Drain: allow virtual zero flushing
        repeat(50) @(posedge clk);

        $display("\nTotal outputs: %0d (expected 25)", out_count);
        $display("Expected: 16 27 33 39 28 39 63 72 81 57 69 108 117 126 87 99 153 162 171 117 76 117 123 129 88");
        $finish;
    end

    initial begin
        #500000;
        $display("TIMEOUT");
        $finish;
    end

endmodule
