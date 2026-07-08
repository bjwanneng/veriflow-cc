// Reference: round-robin arbiter for N requestors (Verilog-2005).
// The granted requestor loses eligibility until every other pending requestor
// has been served, then eligibility refills — strict round-robin fairness.
module arbiter_round_robin #(parameter N = 4) (
    input  wire         clk,
    input  wire         rst,
    input  wire [N-1:0] req,
    output reg  [N-1:0] grant
);
    reg  [N-1:0] mask_r;            // 1 = eligible this rotation
    wire [N-1:0] req_masked = req & mask_r;
    reg  [N-1:0] g;
    integer i;

    // Priority encode: prefer lowest-index eligible requester; if none eligible,
    // fall back to lowest-index requester overall (mask refill point).
    always @(*) begin
        g = {N{1'b0}};
        for (i = 0; i < N; i = i + 1)
            if (g == {N{1'b0}} && req_masked[i])
                g = (1 << i);
        for (i = 0; i < N; i = i + 1)
            if (g == {N{1'b0}} && req[i])
                g = (1 << i);
    end

    always @(posedge clk) begin
        if (rst) begin
            grant  <= {N{1'b0}};
            mask_r <= {N{1'b1}};
        end else begin
            grant <= g;
            if (g != {N{1'b0}}) begin
                if ((mask_r & ~g) != {N{1'b0}})
                    mask_r <= mask_r & ~g;   // exclude granted until others served
                else
                    mask_r <= {N{1'b1}};     // everyone served -> refill
            end
        end
    end
endmodule
