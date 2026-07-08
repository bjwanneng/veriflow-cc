// Reference: valid/ready handshake output port (Verilog-2005).
// Canonical rule: a valid signal, once asserted, MUST stay asserted and its
// payload MUST stay stable until the corresponding ready is observed.
module handshake_valid_ready (
    input  wire clk,
    input  wire rst,
    input  wire send,          // producer wants to send
    input  wire ready,         // downstream accepts this cycle
    output reg  valid,         // held until ready
    output reg  payload_r      // held stable while valid
);
    always @(posedge clk) begin
        if (rst) begin
            valid     <= 1'b0;
            payload_r <= 1'b0;
        end else if (!valid) begin
            // idle: latch a new transaction when send requested
            if (send) begin
                valid     <= 1'b1;
                payload_r <= 1'b1;   // placeholder payload; replace per design
            end
        end else if (ready) begin
            // accepted: deassert (or re-arm for a streaming source)
            valid     <= 1'b0;
        end
        // while valid && !ready: hold (no else -> registers retain value)
    end
endmodule
