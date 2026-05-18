`resetall
`timescale 1ns / 1ps
`default_nettype none

module sha256_core (
    input  wire        clk,
    input  wire        reset_n,
    input  wire        init,
    input  wire        next,
    input  wire [511:0] block,
    output wire        ready,
    output wire        digest_valid,
    output wire [255:0] digest
);

    // -------------------------------------------------------------------------
    // FSM state encoding
    // -------------------------------------------------------------------------
    localparam [1:0] S_IDLE     = 2'b00,
                     S_COMPUTE  = 2'b01,
                     S_UPDATE_H = 2'b10,
                     S_DONE     = 2'b11;

    // -------------------------------------------------------------------------
    // SHA-256 initial hash values (H0..H7) per FIPS 180-4 Section 5.3.3
    // -------------------------------------------------------------------------
    localparam [31:0] H0_INIT = 32'h6a09e667,
                      H1_INIT = 32'hbb67ae85,
                      H2_INIT = 32'h3c6ef372,
                      H3_INIT = 32'ha54ff53a,
                      H4_INIT = 32'h510e527f,
                      H5_INIT = 32'h9b05688c,
                      H6_INIT = 32'h1f83d9ab,
                      H7_INIT = 32'h5be0cd19;

    // -------------------------------------------------------------------------
    // Internal registers — FSM, control, and data
    // -------------------------------------------------------------------------
    reg  [1:0]   state_reg;
    reg  [6:0]   t_reg;
    reg  [31:0]  H0_reg, H1_reg, H2_reg, H3_reg, H4_reg, H5_reg, H6_reg, H7_reg;
    reg  [31:0]  a_reg, b_reg, c_reg, d_reg, e_reg, f_reg, g_reg, h_reg;
    reg  [31:0]  W0_reg, W1_reg, W2_reg, W3_reg, W4_reg, W5_reg, W6_reg, W7_reg,
                 W8_reg, W9_reg, W10_reg, W11_reg, W12_reg, W13_reg, W14_reg, W15_reg;
    reg          ready_reg;
    reg          digest_valid_reg;
    reg  [255:0] digest_reg;

    // -------------------------------------------------------------------------
    // Combinational wires — next-state
    // -------------------------------------------------------------------------
    reg  [1:0]   state_next;

    // -------------------------------------------------------------------------
    // Combinational wires — K constant lookup
    // -------------------------------------------------------------------------
    reg [31:0] K_val;

    always @* begin
        case (t_reg[5:0])
            6'd0:  K_val = 32'h428a2f98;
            6'd1:  K_val = 32'h71374491;
            6'd2:  K_val = 32'hb5c0fbcf;
            6'd3:  K_val = 32'he9b5dba5;
            6'd4:  K_val = 32'h3956c25b;
            6'd5:  K_val = 32'h59f111f1;
            6'd6:  K_val = 32'h923f82a4;
            6'd7:  K_val = 32'hab1c5ed5;
            6'd8:  K_val = 32'hd807aa98;
            6'd9:  K_val = 32'h12835b01;
            6'd10: K_val = 32'h243185be;
            6'd11: K_val = 32'h550c7dc3;
            6'd12: K_val = 32'h72be5d74;
            6'd13: K_val = 32'h80deb1fe;
            6'd14: K_val = 32'h9bdc06a7;
            6'd15: K_val = 32'hc19bf174;
            6'd16: K_val = 32'he49b69c1;
            6'd17: K_val = 32'hefbe4786;
            6'd18: K_val = 32'h0fc19dc6;
            6'd19: K_val = 32'h240ca1cc;
            6'd20: K_val = 32'h2de92c6f;
            6'd21: K_val = 32'h4a7484aa;
            6'd22: K_val = 32'h5cb0a9dc;
            6'd23: K_val = 32'h76f988da;
            6'd24: K_val = 32'h983e5152;
            6'd25: K_val = 32'ha831c66d;
            6'd26: K_val = 32'hb00327c8;
            6'd27: K_val = 32'hbf597fc7;
            6'd28: K_val = 32'hc6e00bf3;
            6'd29: K_val = 32'hd5a79147;
            6'd30: K_val = 32'h06ca6351;
            6'd31: K_val = 32'h14292967;
            6'd32: K_val = 32'h27b70a85;
            6'd33: K_val = 32'h2e1b2138;
            6'd34: K_val = 32'h4d2c6dfc;
            6'd35: K_val = 32'h53380d13;
            6'd36: K_val = 32'h650a7354;
            6'd37: K_val = 32'h766a0abb;
            6'd38: K_val = 32'h81c2c92e;
            6'd39: K_val = 32'h92722c85;
            6'd40: K_val = 32'ha2bfe8a1;
            6'd41: K_val = 32'ha81a664b;
            6'd42: K_val = 32'hc24b8b70;
            6'd43: K_val = 32'hc76c51a3;
            6'd44: K_val = 32'hd192e819;
            6'd45: K_val = 32'hd6990624;
            6'd46: K_val = 32'hf40e3585;
            6'd47: K_val = 32'h106aa070;
            6'd48: K_val = 32'h19a4c116;
            6'd49: K_val = 32'h1e376c08;
            6'd50: K_val = 32'h2748774c;
            6'd51: K_val = 32'h34b0bcb5;
            6'd52: K_val = 32'h391c0cb3;
            6'd53: K_val = 32'h4ed8aa4a;
            6'd54: K_val = 32'h5b9cca4f;
            6'd55: K_val = 32'h682e6ff3;
            6'd56: K_val = 32'h748f82ee;
            6'd57: K_val = 32'h78a5636f;
            6'd58: K_val = 32'h84c87814;
            6'd59: K_val = 32'h8cc70208;
            6'd60: K_val = 32'h90befffa;
            6'd61: K_val = 32'ha4506ceb;
            6'd62: K_val = 32'hbef9a3f7;
            6'd63: K_val = 32'hc67178f2;
            default: K_val = 32'd0;
        endcase
    end

    // -------------------------------------------------------------------------
    // Combinational — SHA-256 functions (all rotation amounts are constants)
    // -------------------------------------------------------------------------
    wire [31:0] CH_val;
    wire [31:0] MAJ_val;
    wire [31:0] BSIG0_val;
    wire [31:0] BSIG1_val;
    wire [31:0] SSIG0_val;
    wire [31:0] SSIG1_val;
    wire [31:0] T1;
    wire [31:0] T2;
    wire [31:0] W_new;

    // CH:  (e & f) ^ (~e & g)
    assign CH_val = (e_reg & f_reg) ^ (~e_reg & g_reg);

    // MAJ: (a & b) ^ (a & c) ^ (b & c)
    assign MAJ_val = (a_reg & b_reg) ^ (a_reg & c_reg) ^ (b_reg & c_reg);

    // BSIG0(a) = ROR(a,2) ^ ROR(a,13) ^ ROR(a,22)
    assign BSIG0_val = {a_reg[1:0], a_reg[31:2]}
                     ^ {a_reg[12:0], a_reg[31:13]}
                     ^ {a_reg[21:0], a_reg[31:22]};

    // BSIG1(e) = ROR(e,6) ^ ROR(e,11) ^ ROR(e,25)
    assign BSIG1_val = {e_reg[5:0], e_reg[31:6]}
                     ^ {e_reg[10:0], e_reg[31:11]}
                     ^ {e_reg[24:0], e_reg[31:25]};

    // SSIG0(W[1]) = ROR(W[1],7) ^ ROR(W[1],18) ^ (W[1] >> 3)
    assign SSIG0_val = {W1_reg[6:0], W1_reg[31:7]}
                     ^ {W1_reg[17:0], W1_reg[31:18]}
                     ^ {3'b0, W1_reg[31:3]};

    // SSIG1(W[14]) = ROR(W[14],17) ^ ROR(W[14],19) ^ (W[14] >> 10)
    assign SSIG1_val = {W14_reg[16:0], W14_reg[31:17]}
                     ^ {W14_reg[18:0], W14_reg[31:19]}
                     ^ {10'b0, W14_reg[31:10]};

    // T1 = h + BSIG1(e) + CH(e,f,g) + K[t] + W[0]
    assign T1 = h_reg + BSIG1_val + CH_val + K_val + W0_reg;

    // T2 = BSIG0(a) + MAJ(a,b,c)
    assign T2 = BSIG0_val + MAJ_val;

    // W_new = SSIG1(W[14]) + W[9] + SSIG0(W[1]) + W[0]
    assign W_new = SSIG1_val + W9_reg + SSIG0_val + W0_reg;

    // HINT:
    //   T1, T2, W_new are purely combinational -- they settle in the same cycle
    //   based on current register values.  The round computation is always live,
    //   but the results only get latched when state_reg == S_COMPUTE && t_reg < 64.

    // -------------------------------------------------------------------------
    // FSM next-state logic (combinational block)
    // -------------------------------------------------------------------------
    always @* begin
        state_next = state_reg;
        case (state_reg)
            S_IDLE:     if (next) state_next = S_COMPUTE;
            S_COMPUTE:  if (t_reg == 7'd63) state_next = S_UPDATE_H;
            S_UPDATE_H: state_next = S_DONE;
            S_DONE:     state_next = S_IDLE;
            default:    state_next = S_IDLE;
        endcase
    end

    // -------------------------------------------------------------------------
    // Sequential block — all register updates (async active-low reset)
    // -------------------------------------------------------------------------
    always @(posedge clk or negedge reset_n) begin
        if (!reset_n) begin
            state_reg       <= S_IDLE;
            t_reg           <= 7'd0;
            ready_reg       <= 1'b1;
            digest_valid_reg <= 1'b0;
            digest_reg      <= 256'd0;
            H0_reg <= 32'd0; H1_reg <= 32'd0; H2_reg <= 32'd0; H3_reg <= 32'd0;
            H4_reg <= 32'd0; H5_reg <= 32'd0; H6_reg <= 32'd0; H7_reg <= 32'd0;
            a_reg <= 32'd0; b_reg <= 32'd0; c_reg <= 32'd0; d_reg <= 32'd0;
            e_reg <= 32'd0; f_reg <= 32'd0; g_reg <= 32'd0; h_reg <= 32'd0;
            W0_reg  <= 32'd0; W1_reg  <= 32'd0; W2_reg  <= 32'd0; W3_reg  <= 32'd0;
            W4_reg  <= 32'd0; W5_reg  <= 32'd0; W6_reg  <= 32'd0; W7_reg  <= 32'd0;
            W8_reg  <= 32'd0; W9_reg  <= 32'd0; W10_reg <= 32'd0; W11_reg <= 32'd0;
            W12_reg <= 32'd0; W13_reg <= 32'd0; W14_reg <= 32'd0; W15_reg <= 32'd0;
        end else begin
            // -- Write state register --
            state_reg <= state_next;

            // -- Per-state actions using state_reg (current, pre-transition state) --
            case (state_reg)
                S_IDLE: begin
                    ready_reg       <= 1'b1;
                    digest_valid_reg <= 1'b0;
                    if (init) begin
                        H0_reg <= H0_INIT; H1_reg <= H1_INIT;
                        H2_reg <= H2_INIT; H3_reg <= H3_INIT;
                        H4_reg <= H4_INIT; H5_reg <= H5_INIT;
                        H6_reg <= H6_INIT; H7_reg <= H7_INIT;
                    end
                    if (next) begin
                        ready_reg <= 1'b0;
                        t_reg     <= 7'd0;
                        // Load W[0..15] from block (big-endian: W[0]=block[511:480])
                        W0_reg  <= block[511:480];
                        W1_reg  <= block[479:448];
                        W2_reg  <= block[447:416];
                        W3_reg  <= block[415:384];
                        W4_reg  <= block[383:352];
                        W5_reg  <= block[351:320];
                        W6_reg  <= block[319:288];
                        W7_reg  <= block[287:256];
                        W8_reg  <= block[255:224];
                        W9_reg  <= block[223:192];
                        W10_reg <= block[191:160];
                        W11_reg <= block[159:128];
                        W12_reg <= block[127:96];
                        W13_reg <= block[95:64];
                        W14_reg <= block[63:32];
                        W15_reg <= block[31:0];
                        // Copy hash state to working registers
                        // When init is asserted in the same cycle, use IV directly
                        // (NBA means H_reg hasn't been updated yet this cycle)
                        if (init) begin
                            a_reg <= H0_INIT; b_reg <= H1_INIT;
                            c_reg <= H2_INIT; d_reg <= H3_INIT;
                            e_reg <= H4_INIT; f_reg <= H5_INIT;
                            g_reg <= H6_INIT; h_reg <= H7_INIT;
                        end else begin
                            a_reg <= H0_reg; b_reg <= H1_reg;
                            c_reg <= H2_reg; d_reg <= H3_reg;
                            e_reg <= H4_reg; f_reg <= H5_reg;
                            g_reg <= H6_reg; h_reg <= H7_reg;
                        end
                    end
                end

                S_COMPUTE: begin
                    ready_reg       <= 1'b0;
                    digest_valid_reg <= 1'b0;
                    if (t_reg < 7'd64) begin
                        t_reg <= t_reg + 7'd1;
                        // Update working variables (single-round compression)
                        a_reg <= T1 + T2;
                        b_reg <= a_reg;
                        c_reg <= b_reg;
                        d_reg <= c_reg;
                        e_reg <= d_reg + T1;
                        f_reg <= e_reg;
                        g_reg <= f_reg;
                        h_reg <= g_reg;
                        // Shift W sliding window left, push W_new into W15
                        W0_reg  <= W1_reg;
                        W1_reg  <= W2_reg;
                        W2_reg  <= W3_reg;
                        W3_reg  <= W4_reg;
                        W4_reg  <= W5_reg;
                        W5_reg  <= W6_reg;
                        W6_reg  <= W7_reg;
                        W7_reg  <= W8_reg;
                        W8_reg  <= W9_reg;
                        W9_reg  <= W10_reg;
                        W10_reg <= W11_reg;
                        W11_reg <= W12_reg;
                        W12_reg <= W13_reg;
                        W13_reg <= W14_reg;
                        W14_reg <= W15_reg;
                        W15_reg <= W_new;
                    end
                end

                S_UPDATE_H: begin
                    ready_reg       <= 1'b0;
                    digest_valid_reg <= 1'b0;
                    H0_reg <= H0_reg + a_reg;
                    H1_reg <= H1_reg + b_reg;
                    H2_reg <= H2_reg + c_reg;
                    H3_reg <= H3_reg + d_reg;
                    H4_reg <= H4_reg + e_reg;
                    H5_reg <= H5_reg + f_reg;
                    H6_reg <= H6_reg + g_reg;
                    H7_reg <= H7_reg + h_reg;
                end

                S_DONE: begin
                    ready_reg       <= 1'b0;
                    digest_valid_reg <= 1'b1;
                    digest_reg <= {H0_reg, H1_reg, H2_reg, H3_reg,
                                   H4_reg, H5_reg, H6_reg, H7_reg};
                end

                default: begin
                    ready_reg       <= 1'b0;
                    digest_valid_reg <= 1'b0;
                end
            endcase
        end
    end

    // -------------------------------------------------------------------------
    // Output assignments — registered outputs via wire + _reg + assign
    // -------------------------------------------------------------------------
    assign ready        = ready_reg;
    assign digest_valid = digest_valid_reg;
    assign digest       = digest_reg;

endmodule

`resetall
