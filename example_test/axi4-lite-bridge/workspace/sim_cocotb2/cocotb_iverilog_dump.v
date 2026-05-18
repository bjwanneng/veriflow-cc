module cocotb_iverilog_dump();
initial begin
    string dumpfile_path;    if ($value$plusargs("dumpfile_path=%s", dumpfile_path)) begin
        $dumpfile(dumpfile_path);
    end else begin
        $dumpfile("/Users/wannengzhang/Desktop/work/ai_app_zone/veriflow-cc/example_test/axi4-lite-bridge/workspace/sim_cocotb2/axi4_lite_async_bridge.fst");
    end
    $dumpvars(0, axi4_lite_async_bridge);
end
endmodule
