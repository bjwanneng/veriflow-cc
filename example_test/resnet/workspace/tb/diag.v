module diag;
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

    initial begin
        $dumpfile("diag.vcd");
        $dumpvars(0, diag);
        rst = 1; in_valid_i = 0; in_data_i = 0;
        @(posedge clk); @(posedge clk); @(posedge clk);
        rst = 0; @(negedge clk);
        $display("Cycle 0: rst released");

        // Drive 16 pixels
        in_valid_i = 1; in_data_i = 1; @(posedge clk); $display("c1: in=%0d out_v=%b out_d=%0d", in_data_i, out_valid_o, out_data_o);
        in_data_i = 2; @(posedge clk); $display("c2: in=%0d out_v=%b out_d=%0d", in_data_i, out_valid_o, out_data_o);
        in_data_i = 3; @(posedge clk); $display("c3: in=%0d out_v=%b out_d=%0d", in_data_i, out_valid_o, out_data_o);
        in_data_i = 4; @(posedge clk); $display("c4: in=%0d out_v=%b out_d=%0d", in_data_i, out_valid_o, out_data_o);
        in_data_i = 5; @(posedge clk); $display("c5: in=%0d out_v=%b out_d=%0d", in_data_i, out_valid_o, out_data_o);
        in_data_i = 6; @(posedge clk); $display("c6: in=%0d out_v=%b out_d=%0d", in_data_i, out_valid_o, out_data_o);
        in_data_i = 7; @(posedge clk); $display("c7: in=%0d out_v=%b out_d=%0d", in_data_i, out_valid_o, out_data_o);
        in_data_i = 8; @(posedge clk); $display("c8: in=%0d out_v=%b out_d=%0d", in_data_i, out_valid_o, out_data_o);
        in_data_i = 9; @(posedge clk); $display("c9: in=%0d out_v=%b out_d=%0d", in_data_i, out_valid_o, out_data_o);
        in_data_i = 0; @(posedge clk); $display("c10: in=%0d out_v=%b out_d=%0d", in_data_i, out_valid_o, out_data_o);
        in_data_i = 1; @(posedge clk); $display("c11: in=%0d out_v=%b out_d=%0d", in_data_i, out_valid_o, out_data_o);
        in_data_i = 2; @(posedge clk); $display("c12: in=%0d out_v=%b out_d=%0d", in_data_i, out_valid_o, out_data_o);
        in_data_i = 3; @(posedge clk); $display("c13: in=%0d out_v=%b out_d=%0d", in_data_i, out_valid_o, out_data_o);
        in_data_i = 4; @(posedge clk); $display("c14: in=%0d out_v=%b out_d=%0d", in_data_i, out_valid_o, out_data_o);
        in_data_i = 5; @(posedge clk); $display("c15: in=%0d out_v=%b out_d=%0d", in_data_i, out_valid_o, out_data_o);
        in_data_i = 6; @(posedge clk); $display("c16: in=%0d out_v=%b out_d=%0d", in_data_i, out_valid_o, out_data_o);
        in_valid_i = 0; in_data_i = 0;

        // Wait for outputs
        repeat(30) begin
            @(posedge clk);
            $display("c: out_v=%b out_d=%0d", out_valid_o, out_data_o);
        end
        $finish;
    end
endmodule
