module bad_finalize_next(
    input  wire        clk,
    input  wire        rst,
    input  wire [31:0] data_in,
    output wire [31:0] data_out
);
    reg [31:0] acc_reg = 32'd0, acc_next;
    reg [31:0] result_reg = 32'd0, result_next;
    reg [1:0]  state_reg = 2'd0, state_next;

    assign data_out = result_reg;

    always @* begin
        acc_next = acc_reg;
        result_next = result_reg;
        state_next = state_reg;
        case (state_reg)
            2'd0: begin
                acc_next = data_in;
                state_next = 2'd1;
            end
            2'd1: begin
                result_next = acc_next;  // BUG: reads _next in combinational is OK
                state_next = 2'd2;
            end
            default: ;
        endcase
    end

    always @(posedge clk) begin
        acc_reg <= acc_next;
        result_reg <= result_next;
        state_reg <= state_next;
        // BUG: reading _next in sequential block (finalize pattern)
        if (state_reg == 2'd2)
            result_reg <= acc_next;  // L4 should flag acc_next
        if (rst) begin
            acc_reg <= 32'd0;
            result_reg <= 32'd0;
            state_reg <= 2'd0;
        end
    end
endmodule
