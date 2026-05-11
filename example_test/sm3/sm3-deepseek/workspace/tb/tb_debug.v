`timescale 1ns/1ps
module tb_debug();
    reg clk;
    reg rst_n;
    reg msg_valid;
    reg [511:0] msg_block;
    reg is_last;
    wire ready;
    wire hash_valid;
    wire [255:0] hash_out;

    sm3_core u_sm3_core (
        .clk(clk), .rst_n(rst_n), .msg_valid(msg_valid),
        .msg_block(msg_block), .is_last(is_last),
        .ready(ready), .hash_valid(hash_valid), .hash_out(hash_out)
    );

    always #5 clk = ~clk;

    initial begin
        $dumpfile("tb_debug.vcd");
        $dumpvars(0, tb_debug);
        clk = 0; rst_n = 0; msg_valid = 0; is_last = 0;
        msg_block = 512'h61626380_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000018;
        #20 rst_n = 1;
        wait(ready == 1'b1);
        @(posedge clk);
        msg_valid = 1; is_last = 1;
        @(posedge clk);
        msg_valid = 0;
        wait(hash_valid == 1'b1);
        $display("hash_out=%h", hash_out);
        #20 $finish;
    end
endmodule
