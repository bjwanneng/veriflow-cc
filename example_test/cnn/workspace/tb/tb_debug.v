`timescale 1ns / 1ps

module tb_debug;

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

    // Trace key signals
    always @(posedge clk) begin
        if (uut.state_reg != 3'd0 || in_valid) begin
            $display("cyc=%0d st=%0d col=%0d row=%0d pix=%0d adv=%b mac_v=%b ov=%b or=%0d iv=%b ir=%b ip=%0d | adv=%b pad=%b r2=%b c2=%b oy=%0d ox=%0d sv=%0d omod_y=%0d omod_x=%0d oh=%0d ow=%0d",
                     cycle, uut.state_reg, uut.col_cnt_reg, uut.row_cnt_reg,
                     uut.pixel_cnt_reg, (uut.accepting | uut.virtual_pixel),
                     uut.mac_valid_w, uut.out_valid_reg,
                     $signed(uut.out_result_reg),
                     in_valid, in_ready, in_pixel,
                     (uut.accepting | uut.virtual_pixel),
                     uut.padding_reg,
                     (uut.row_cnt_reg >= 2), (uut.col_cnt_reg >= 2),
                     uut.out_y_valid, uut.out_x_valid,
                     uut.stride_val,
                     (uut.out_y_valid % uut.stride_val),
                     (uut.out_x_valid % uut.stride_val),
                     uut.out_h, uut.out_w
                     );
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

        // Config: 11 words (kernel all 1s, stride=1, padding=0)
        begin : cfg
            integer i;
            reg [7:0] cfg [0:10];
            cfg[0]=1; cfg[1]=1; cfg[2]=1; cfg[3]=1; cfg[4]=1;
            cfg[5]=1; cfg[6]=1; cfg[7]=1; cfg[8]=1;
            cfg[9]=1; cfg[10]=0;  // stride=1, padding=0
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

        // Stream pixels 1..25 back-to-back (in_valid held high continuously)
        begin : stream
            integer p;
            for (p = 1; p <= 25; p = p + 1) begin
                @(posedge clk);
                in_pixel <= p;
                in_valid <= 1;
            end
            @(posedge clk);
            in_valid <= 0;
            in_pixel <= 0;
        end

        // Drain
        repeat(30) @(posedge clk);

        $display("\n=== DONE ===");
        $finish;
    end

    initial begin
        #200000;
        $display("TIMEOUT");
        $finish;
    end

endmodule
