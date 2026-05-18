module diag2;
    reg clk, rst;
    reg in_valid_i;
    reg [7:0] in_data_i;
    wire out_valid_o;
    wire [7:0] out_data_o;

    resnet_basic_block #(.WIDTH(4),.HEIGHT(4),.CHANNELS(1)) uut (
        .clk(clk), .rst(rst),
        .in_valid_i(in_valid_i), .in_data_i(in_data_i),
        .out_valid_o(out_valid_o), .out_data_o(out_data_o)
    );

    initial clk = 0;
    always #2.5 clk = ~clk;

    integer c;
    initial begin
        $dumpfile("diag2.vcd");
        $dumpvars(0, diag2);
        rst = 1; in_valid_i = 0; in_data_i = 0;
        @(posedge clk); @(posedge clk); @(posedge clk);
        rst = 0; @(negedge clk);

        for (c = 1; c <= 40; c = c + 1) begin
            if (c <= 16) begin
                in_valid_i = 1;
                case (c)
                    1: in_data_i = 1;  2: in_data_i = 2;  3: in_data_i = 3;  4: in_data_i = 4;
                    5: in_data_i = 5;  6: in_data_i = 6;  7: in_data_i = 7;  8: in_data_i = 8;
                    9: in_data_i = 9; 10: in_data_i = 0; 11: in_data_i = 1; 12: in_data_i = 2;
                   13: in_data_i = 3; 14: in_data_i = 4; 15: in_data_i = 5; 16: in_data_i = 6;
                endcase
            end else begin
                in_valid_i = 0;
                in_data_i = 0;
            end
            @(posedge clk);
            #0.1;
            $display("c%0d: iv=%b id=%0d lb_v=%b c1_v=%b c2_v=%b d_v=%b add_v=%b ov=%b od=%0d",
                c, in_valid_i, in_data_i,
                uut.conv1.lb_valid,
                uut.conv1.prod_valid_reg,
                uut.conv2.sum_valid_reg,
                uut.delay_out_valid,
                uut.adder_valid,
                out_valid_o, out_data_o);
        end
        $finish;
    end
endmodule
