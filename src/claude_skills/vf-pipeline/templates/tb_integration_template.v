// tb_<design_name>.v — integration test for <design_name>
module tb_<design_name>;
    // Declare wires/regs matching ALL ports of the top module DUT
    reg clk, rst;
    reg [31:0] data_in;
    wire [31:0] data_out;
    wire ready;

    // Cycle counter — used in ALL $display calls for waveform correlation
    integer cycle_count = 0;
    integer fail_count  = 0;

    // Instantiate DUT (top module — submodules are linked via RTL files)
    <design_name> uut (
        .clk(clk), .rst(rst),
        .data_in(data_in), .data_out(data_out), .ready(ready)
    );

    // Clock generation
    initial clk = 0;
    always #5 clk = ~clk;

    // Cycle counter — increment every posedge
    always @(posedge clk) cycle_count = cycle_count + 1;

    // VCD capture — REQUIRED for waveform analysis
    initial begin
        $dumpfile("tb_<design_name>.vcd");
        $dumpvars(0, tb_<design_name>);
    end

    // Test cases (example structure)
    initial begin
        // --- Reset ---
        rst = 1; data_in = 0;
        @(posedge clk); @(posedge clk);
        rst = 0;
        @(negedge clk);  // wait for NBA to settle after rst deassert
        $display("[TRACE] cycle=%0d rst released", cycle_count);

        // --- Test case 1: <description> ---
        data_in = 32'h0000_1234;
        @(posedge clk);   // DUT samples data_in
        @(negedge clk);   // NBA settled — registered outputs now valid
        $display("[TRACE] cycle=%0d data_in=0x%0h data_out=0x%0h", cycle_count, data_in, data_out);
        if (data_out !== 32'hEXPECTED) begin
            $display("[FAIL] cycle=%0d data_out expected=0x%0h got=0x%0h",
                     cycle_count, 32'hEXPECTED, data_out);
            fail_count = fail_count + 1;
        end else
            $display("[PASS] cycle=%0d data_out=0x%0h", cycle_count, data_out);

        // --- Test case 2: multi-cycle operation ---
        // For each cycle where output is expected to change:
        //   @(posedge clk);  // DUT processes
        //   @(negedge clk);  // NBA settled
        //   check outputs

        // --- Summary ---
        if (fail_count == 0) $display("ALL TESTS PASSED");
        else $display("FAILED: %0d assertion(s) failed", fail_count);
        $finish;
    end
endmodule
