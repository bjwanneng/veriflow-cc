// Anchor: 4-state FSM (IDLE / LOAD / PROCESS / DONE)
// Style: two-segment (combinational next-state + sequential state update)
// Encoding: localparam, 2-bit binary

`resetall
`timescale 1ns / 1ps
`default_nettype none

module fsm_4state
(
    input  wire         clk,
    input  wire         rst,
    input  wire         start,
    input  wire         done_signal,
    output wire [1:0]   state_reg,
    output wire         load_en,
    output wire         process_en,
    output wire         done_out
);

localparam IDLE    = 2'b00;
localparam LOAD    = 2'b01;
localparam PROCESS = 2'b10;
localparam DONE    = 2'b11;

reg [1:0] state_reg_reg = IDLE;
reg [1:0] next_state;

// Combinational next-state logic
always @(*) begin
    case (state_reg_reg)
        IDLE:    next_state = start ? LOAD : IDLE;
        LOAD:    next_state = start ? PROCESS : LOAD;
        PROCESS: next_state = done_signal ? DONE : PROCESS;
        DONE:    next_state = DONE;
        default: next_state = IDLE;
    endcase
end

// Sequential state update
always @(posedge clk) begin
    if (rst) begin
        state_reg_reg <= IDLE;
    end else begin
        state_reg_reg <= next_state;
    end
end

// Output decode (Moore machine)
assign load_en    = (state_reg_reg == LOAD);
assign process_en = (state_reg_reg == PROCESS);
assign done_out   = (state_reg_reg == DONE);
assign state_reg  = state_reg_reg;

endmodule

`resetall
