// Anchor: SM3 compression round (j < 16, XOR mode)
// Style: single sequential block with combinational intermediates
// All 8 registers (A-H) update simultaneously in one cycle.

`resetall
`timescale 1ns / 1ps
`default_nettype none

module hash_round_one_cycle
(
    input  wire         clk,
    input  wire         rst,
    output wire [31:0]  a_reg,
    output wire [31:0]  b_reg,
    output wire [31:0]  c_reg,
    output wire [31:0]  d_reg,
    output wire [31:0]  e_reg,
    output wire [31:0]  f_reg,
    output wire [31:0]  g_reg,
    output wire [31:0]  h_reg,
    input  wire [31:0]  w_j,
    input  wire [31:0]  w_prime_j,
    input  wire         calc_en
);

// State registers (A-H)
reg [31:0] a_reg_reg = 32'd0;
reg [31:0] b_reg_reg = 32'd0;
reg [31:0] c_reg_reg = 32'd0;
reg [31:0] d_reg_reg = 32'd0;
reg [31:0] e_reg_reg = 32'd0;
reg [31:0] f_reg_reg = 32'd0;
reg [31:0] g_reg_reg = 32'd0;
reg [31:0] h_reg_reg = 32'd0;

// SM3 round constant for j < 16
localparam T0 = 32'h79CC4519;

// Combinational intermediates
wire [31:0] rol_a_12;
wire [33:0] ss1_sum;   // ROL(A,12) + E + T0  (34-bit to hold overflow)
wire [33:0] ss1;       // ROL(ss1_sum, 7)
wire [31:0] ss2;
wire [31:0] tt1;
wire [31:0] tt2;
wire [31:0] p0_tt2;

assign rol_a_12 = {a_reg_reg[19:0], a_reg_reg[31:20]};

// Sum before rotation — explicit wire to avoid part-select on expression
assign ss1_sum = rol_a_12 + e_reg_reg + T0;

// ROL(ss1_sum, 7): {ss1_sum[34-1-7:0], ss1_sum[34-1:34-7]}
// = {ss1_sum[26:0], ss1_sum[33:27]}
assign ss1 = {ss1_sum[26:0], ss1_sum[33:27]};

assign ss2    = ss1[31:0] ^ rol_a_12;
assign tt1    = (a_reg_reg ^ b_reg_reg ^ c_reg_reg) + d_reg_reg + ss2 + w_prime_j;
assign tt2    = (e_reg_reg ^ f_reg_reg ^ g_reg_reg) + h_reg_reg + ss1[31:0] + w_j;
assign p0_tt2 = tt2 ^ {tt2[22:0], tt2[31:23]} ^ {tt2[14:0], tt2[31:15]};

// Sequential update (all 8 registers simultaneously)
always @(posedge clk) begin
    if (rst) begin
        a_reg_reg <= 32'd0;
        b_reg_reg <= 32'd0;
        c_reg_reg <= 32'd0;
        d_reg_reg <= 32'd0;
        e_reg_reg <= 32'd0;
        f_reg_reg <= 32'd0;
        g_reg_reg <= 32'd0;
        h_reg_reg <= 32'd0;
    end else begin
        a_reg_reg <= calc_en ? tt1 : a_reg_reg;
        b_reg_reg <= calc_en ? a_reg_reg : b_reg_reg;
        c_reg_reg <= calc_en ? {b_reg_reg[22:0], b_reg_reg[31:23]} : c_reg_reg;
        d_reg_reg <= calc_en ? c_reg_reg : d_reg_reg;
        e_reg_reg <= calc_en ? p0_tt2 : e_reg_reg;
        f_reg_reg <= calc_en ? e_reg_reg : f_reg_reg;
        g_reg_reg <= calc_en ? {f_reg_reg[12:0], f_reg_reg[31:13]} : g_reg_reg;
        h_reg_reg <= calc_en ? g_reg_reg : h_reg_reg;
    end
end

// Output assignments
assign a_reg = a_reg_reg;
assign b_reg = b_reg_reg;
assign c_reg = c_reg_reg;
assign d_reg = d_reg_reg;
assign e_reg = e_reg_reg;
assign f_reg = f_reg_reg;
assign g_reg = g_reg_reg;
assign h_reg = h_reg_reg;

endmodule

`resetall
