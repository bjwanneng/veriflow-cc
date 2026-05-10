`timescale 1ns / 1ps

module tb_debug();
    reg clk;
    reg rst_n;
    reg msg_valid;
    reg [511:0] msg_block;
    reg is_last;

    wire ready;
    wire hash_valid;
    wire [255:0] hash_out;
    wire load_en;
    wire calc_en;
    wire update_v_en;
    wire [5:0] round_cnt;

    sm3_core u_sm3_core (
        .clk        (clk),
        .rst_n      (rst_n),
        .msg_valid  (msg_valid),
        .msg_block  (msg_block),
        .is_last    (is_last),
        .ready      (ready),
        .hash_valid (hash_valid),
        .hash_out   (hash_out)
    );

    assign load_en     = u_sm3_core.u_fsm.load_en;
    assign calc_en     = u_sm3_core.u_fsm.calc_en;
    assign update_v_en = u_sm3_core.u_fsm.update_v_en;
    assign round_cnt   = u_sm3_core.u_fsm.round_cnt;

    always #5 clk = ~clk;

    integer cycle;
    always @(posedge clk) begin
        cycle <= cycle + 1;
        if (calc_en || update_v_en || load_en) begin
            $display("[%0d] load_en=%b calc_en=%b update_v_en=%b round=%0d A=%08h B=%08h V0=%08h hash=%064h",
                cycle, load_en, calc_en, update_v_en, round_cnt,
                u_sm3_core.u_compress.a_reg,
                u_sm3_core.u_compress.b_reg,
                u_sm3_core.u_compress.v0_reg,
                hash_out);
        end
        if (hash_valid) begin
            $display("[%0d] HASH_VALID hash_out=%064h", cycle, hash_out);
        end
    end

    initial begin
        clk = 0;
        cycle = 0;
        rst_n = 0;
        msg_valid = 0;
        is_last = 0;
        msg_block = 512'h61626380_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000018;

        #35 rst_n = 1;
        $display("[%0d] rst_n released", $time);

        wait(ready == 1'b1);
        $display("[%0d] ready=1", $time);
        @(posedge clk);
        msg_valid = 1;
        is_last = 1;
        $display("[%0d] driving msg_valid=1", $time);

        @(posedge clk);
        msg_valid = 0;
        $display("[%0d] msg_valid=0", $time);

        wait(hash_valid == 1'b1);
        $display("[%0d] hash_valid=1 hash_out=%064h", $time, hash_out);
        if (hash_out == 256'h66c7f0f4_62eeedd9_d1f2d46b_dc10e4e2_4167c487_5cf2f7a2_297da02b_8f4ba8e0) begin
            $display("PASS");
        end else begin
            $display("FAIL: expected 66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0");
        end

        #20 $finish;
    end
endmodule
