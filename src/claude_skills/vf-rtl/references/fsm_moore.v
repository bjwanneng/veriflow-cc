// Reference: Moore FSM (Verilog-2005). State register + next-state + outputs.
// Demonstrates the project's reset-polarity and onehot-friendly explicit states.
module fsm_moore (
    input  wire clk,
    input  wire rst,
    input  wire start,
    output reg  done
);
    localparam IDLE = 2'd0;
    localparam RUN  = 2'd1;
    localparam DONE = 2'd2;

    reg [1:0] state_r;
    always @(posedge clk) begin
        if (rst) begin
            state_r <= IDLE;
            done    <= 1'b0;
        end else begin
            case (state_r)
                IDLE: state_r <= start ? RUN  : IDLE;
                RUN:  state_r <= DONE;
                DONE: begin
                    done    <= 1'b1;
                    state_r <= IDLE;
                end
                default: state_r <= IDLE;
            endcase
        end
    end
endmodule
