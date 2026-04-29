// -----------------------------------------------------------------------------
// File   : sha256_core.v
// Author : VeriFlow-CC
// Date   : 2026-04-27
// -----------------------------------------------------------------------------
// Description:
//   SHA-256 cryptographic hash core per FIPS 180-4. Iterative architecture
//   processes one compression round per clock cycle (64 rounds per 512-bit
//   message block). Accepts init/next command protocol; outputs 256-bit digest
//   with single-cycle digest_valid pulse. Uses 16-entry sliding window shift
//   register for the message schedule (W) and eight 32-bit working variables
//   (a-h) plus eight 32-bit hash state registers (H0-H7).
// -----------------------------------------------------------------------------
// Change Log:
//   2026-04-27  VeriFlow-CC  v1.0  Initial release
// -----------------------------------------------------------------------------

`resetall
`timescale 1ns / 1ps
`default_nettype none

module sha256_core
(
    input  wire           clk,
    input  wire           rst,
    input  wire           init,
    input  wire           next,
    input  wire [511:0]   block,
    output wire           ready,
    output wire           digest_valid,
    output wire [255:0]   digest
);

    /////////////////////////////////////////////////////////////////////////////
    // FSM State Encoding                                                     //
    /////////////////////////////////////////////////////////////////////////////

    localparam [1:0]
        STATE_IDLE     = 2'd0,
        STATE_COMPUTE  = 2'd1,
        STATE_UPDATE_H = 2'd2,
        STATE_DONE     = 2'd3;

    /////////////////////////////////////////////////////////////////////////////
    // SHA-256 Initial Hash Values (IV) — FIPS 180-4 Section 5.3.3           //
    /////////////////////////////////////////////////////////////////////////////

    localparam [31:0] H0_INIT = 32'h6a09e667;
    localparam [31:0] H1_INIT = 32'hbb67ae85;
    localparam [31:0] H2_INIT = 32'h3c6ef372;
    localparam [31:0] H3_INIT = 32'ha54ff53a;
    localparam [31:0] H4_INIT = 32'h510e527f;
    localparam [31:0] H5_INIT = 32'h9b05688c;
    localparam [31:0] H6_INIT = 32'h1f83d9ab;
    localparam [31:0] H7_INIT = 32'h5be0cd19;

    /////////////////////////////////////////////////////////////////////////////
    // SHA-256 Combinational Functions — FIPS 180-4 Section 4.1.2            //
    /////////////////////////////////////////////////////////////////////////////

    // Ch(x, y, z) = (x & y) ^ (~x & z)
    function [31:0] Ch;
        input [31:0] x;
        input [31:0] y;
        input [31:0] z;
        begin
            Ch = (x & y) ^ (~x & z);
        end
    endfunction

    // Maj(x, y, z) = (x & y) ^ (x & z) ^ (y & z)
    function [31:0] Maj;
        input [31:0] x;
        input [31:0] y;
        input [31:0] z;
        begin
            Maj = (x & y) ^ (x & z) ^ (y & z);
        end
    endfunction

    // Sigma0(x) = ROTR(x,2) ^ ROTR(x,13) ^ ROTR(x,22)
    function [31:0] Sigma0;
        input [31:0] x;
        begin
            Sigma0 = {x[ 1: 0], x[31: 2]}
                   ^ {x[12: 0], x[31:13]}
                   ^ {x[21: 0], x[31:22]};
        end
    endfunction

    // Sigma1(x) = ROTR(x,6) ^ ROTR(x,11) ^ ROTR(x,25)
    function [31:0] Sigma1;
        input [31:0] x;
        begin
            Sigma1 = {x[ 5: 0], x[31: 6]}
                   ^ {x[10: 0], x[31:11]}
                   ^ {x[24: 0], x[31:25]};
        end
    endfunction

    // sigma0(x) = ROTR(x,7) ^ ROTR(x,18) ^ SHR(x,3)
    function [31:0] sigma0;
        input [31:0] x;
        begin
            sigma0 = {x[ 6: 0], x[31: 7]}
                   ^ {x[17: 0], x[31:18]}
                   ^ (x >> 3);
        end
    endfunction

    // sigma1(x) = ROTR(x,17) ^ ROTR(x,19) ^ SHR(x,10)
    function [31:0] sigma1;
        input [31:0] x;
        begin
            sigma1 = {x[16: 0], x[31:17]}
                   ^ {x[18: 0], x[31:19]}
                   ^ (x >> 10);
        end
    endfunction

    // K_ROM — round constants (FIPS 180-4 Section 4.2.2)
    function [31:0] K_ROM;
        input [5:0] addr;
        begin
            case (addr)
                6'd0:  K_ROM = 32'h428a2f98;
                6'd1:  K_ROM = 32'h71374491;
                6'd2:  K_ROM = 32'hb5c0fbcf;
                6'd3:  K_ROM = 32'he9b5dba5;
                6'd4:  K_ROM = 32'h3956c25b;
                6'd5:  K_ROM = 32'h59f111f1;
                6'd6:  K_ROM = 32'h923f82a4;
                6'd7:  K_ROM = 32'hab1c5ed5;
                6'd8:  K_ROM = 32'hd807aa98;
                6'd9:  K_ROM = 32'h12835b01;
                6'd10: K_ROM = 32'h243185be;
                6'd11: K_ROM = 32'h550c7dc3;
                6'd12: K_ROM = 32'h72be5d74;
                6'd13: K_ROM = 32'h80deb1fe;
                6'd14: K_ROM = 32'h9bdc06a7;
                6'd15: K_ROM = 32'hc19bf174;
                6'd16: K_ROM = 32'he49b69c1;
                6'd17: K_ROM = 32'hefbe4786;
                6'd18: K_ROM = 32'h0fc19dc6;
                6'd19: K_ROM = 32'h240ca1cc;
                6'd20: K_ROM = 32'h2de92c6f;
                6'd21: K_ROM = 32'h4a7484aa;
                6'd22: K_ROM = 32'h5cb0a9dc;
                6'd23: K_ROM = 32'h76f988da;
                6'd24: K_ROM = 32'h983e5152;
                6'd25: K_ROM = 32'ha831c66d;
                6'd26: K_ROM = 32'hb00327c8;
                6'd27: K_ROM = 32'hbf597fc7;
                6'd28: K_ROM = 32'hc6e00bf3;
                6'd29: K_ROM = 32'hd5a79147;
                6'd30: K_ROM = 32'h06ca6351;
                6'd31: K_ROM = 32'h14292967;
                6'd32: K_ROM = 32'h27b70a85;
                6'd33: K_ROM = 32'h2e1b2138;
                6'd34: K_ROM = 32'h4d2c6dfc;
                6'd35: K_ROM = 32'h53380d13;
                6'd36: K_ROM = 32'h650a7354;
                6'd37: K_ROM = 32'h766a0abb;
                6'd38: K_ROM = 32'h81c2c92e;
                6'd39: K_ROM = 32'h92722c85;
                6'd40: K_ROM = 32'ha2bfe8a1;
                6'd41: K_ROM = 32'ha81a664b;
                6'd42: K_ROM = 32'hc24b8b70;
                6'd43: K_ROM = 32'hc76c51a3;
                6'd44: K_ROM = 32'hd192e819;
                6'd45: K_ROM = 32'hd6990624;
                6'd46: K_ROM = 32'hf40e3585;
                6'd47: K_ROM = 32'h106aa070;
                6'd48: K_ROM = 32'h19a4c116;
                6'd49: K_ROM = 32'h1e376c08;
                6'd50: K_ROM = 32'h2748774c;
                6'd51: K_ROM = 32'h34b0bcb5;
                6'd52: K_ROM = 32'h391c0cb3;
                6'd53: K_ROM = 32'h4ed8aa4a;
                6'd54: K_ROM = 32'h5b9cca4f;
                6'd55: K_ROM = 32'h682e6ff3;
                6'd56: K_ROM = 32'h748f82ee;
                6'd57: K_ROM = 32'h78a5636f;
                6'd58: K_ROM = 32'h84c87814;
                6'd59: K_ROM = 32'h8cc70208;
                6'd60: K_ROM = 32'h90befffa;
                6'd61: K_ROM = 32'ha4506ceb;
                6'd62: K_ROM = 32'hbef9a3f7;
                6'd63: K_ROM = 32'hc67178f2;
                default: K_ROM = 32'd0;
            endcase
        end
    endfunction

    /////////////////////////////////////////////////////////////////////////////
    // FSM and Control Registers                                              //
    /////////////////////////////////////////////////////////////////////////////

    reg [1:0] state_reg = STATE_IDLE, state_next;

    // Round counter (0 to 63)
    reg [5:0] t_reg = 6'd0, t_next;

    /////////////////////////////////////////////////////////////////////////////
    // Output Register Group                                                   //
    /////////////////////////////////////////////////////////////////////////////

    reg         ready_reg        = 1'b1,  ready_next;
    reg         digest_valid_reg = 1'b0,  digest_valid_next;
    reg [255:0] digest_reg       = 256'd0, digest_next;

    /////////////////////////////////////////////////////////////////////////////
    // Hash State Registers (H0-H7)                                           //
    /////////////////////////////////////////////////////////////////////////////

    reg [31:0] H0_reg = 32'd0, H0_next;
    reg [31:0] H1_reg = 32'd0, H1_next;
    reg [31:0] H2_reg = 32'd0, H2_next;
    reg [31:0] H3_reg = 32'd0, H3_next;
    reg [31:0] H4_reg = 32'd0, H4_next;
    reg [31:0] H5_reg = 32'd0, H5_next;
    reg [31:0] H6_reg = 32'd0, H6_next;
    reg [31:0] H7_reg = 32'd0, H7_next;

    /////////////////////////////////////////////////////////////////////////////
    // Working Variable Registers (a-h)                                       //
    /////////////////////////////////////////////////////////////////////////////

    reg [31:0] a_reg = 32'd0, a_next;
    reg [31:0] b_reg = 32'd0, b_next;
    reg [31:0] c_reg = 32'd0, c_next;
    reg [31:0] d_reg = 32'd0, d_next;
    reg [31:0] e_reg = 32'd0, e_next;
    reg [31:0] f_reg = 32'd0, f_next;
    reg [31:0] g_reg = 32'd0, g_next;
    reg [31:0] h_reg = 32'd0, h_next;

    /////////////////////////////////////////////////////////////////////////////
    // Message Schedule — 16x32 Shift Register                                //
    /////////////////////////////////////////////////////////////////////////////

    reg [31:0] W_reg [0:15];

    // Temporary register for new W value computed before shift
    reg [31:0] w_new_val = 32'd0;

    /////////////////////////////////////////////////////////////////////////////
    // Combinational Datapath: T1 and T2                                      //
    /////////////////////////////////////////////////////////////////////////////

    // W_t: the current round word is always at shift-register position 0.
    // The shift register is pre-loaded with block words W[0:15] and
    // subsequently fed with w_new_val = sigma1(W[14])+W[9]+sigma0(W[1])+W[0]
    // every COMPUTE cycle, so W_reg[0] always holds the correct W_t.
    wire [31:0] W_t;
    assign W_t = W_reg[0];

    // T1 = h + Sigma1(e) + Ch(e, f, g) + K[t] + W_t
    wire [31:0] T1;
    assign T1 = h_reg + Sigma1(e_reg) + Ch(e_reg, f_reg, g_reg)
              + K_ROM(t_reg) + W_t;

    // T2 = Sigma0(a) + Maj(a, b, c)
    wire [31:0] T2;
    assign T2 = Sigma0(a_reg) + Maj(a_reg, b_reg, c_reg);

    /////////////////////////////////////////////////////////////////////////////
    // Combinational Next-State Logic (always @*)                             //
    /////////////////////////////////////////////////////////////////////////////

    always @* begin
        // Default values — hold current state
        state_next        = state_reg;
        t_next            = t_reg;
        ready_next        = 1'b0;
        digest_valid_next = 1'b0;
        digest_next       = digest_reg;

        H0_next = H0_reg; H1_next = H1_reg; H2_next = H2_reg; H3_next = H3_reg;
        H4_next = H4_reg; H5_next = H5_reg; H6_next = H6_reg; H7_next = H7_reg;

        a_next = a_reg; b_next = b_reg; c_next = c_reg; d_next = d_reg;
        e_next = e_reg; f_next = f_reg; g_next = g_reg; h_next = h_reg;

        case (state_reg)

            // ----------------------------------------------------------------
            STATE_IDLE: begin
                ready_next = 1'b1;
                if (next) begin
                    // next takes priority: start block processing
                    state_next = STATE_COMPUTE;
                    t_next     = 6'd0;
                    ready_next = 1'b0;
                    // Initialize working variables from hash state
                    a_next = H0_reg;
                    b_next = H1_reg;
                    c_next = H2_reg;
                    d_next = H3_reg;
                    e_next = H4_reg;
                    f_next = H5_reg;
                    g_next = H6_reg;
                    h_next = H7_reg;
                end else if (init) begin
                    // Load IV into hash state; stay in IDLE
                    H0_next = H0_INIT;
                    H1_next = H1_INIT;
                    H2_next = H2_INIT;
                    H3_next = H3_INIT;
                    H4_next = H4_INIT;
                    H5_next = H5_INIT;
                    H6_next = H6_INIT;
                    H7_next = H7_INIT;
                end
            end

            // ----------------------------------------------------------------
            STATE_COMPUTE: begin
                ready_next = 1'b0;
                if (t_reg == 6'd63) begin
                    state_next = STATE_UPDATE_H;
                    t_next     = 6'd0;
                end else begin
                    state_next = STATE_COMPUTE;
                    t_next     = t_reg + 6'd1;
                end
                // Compression round: update working variables a-h
                //   h <= g;  g <= f;  f <= e;  e <= d + T1;
                //   d <= c;  c <= b;  b <= a;  a <= T1 + T2;
                a_next = T1 + T2;
                b_next = a_reg;
                c_next = b_reg;
                d_next = c_reg;
                e_next = d_reg + T1;
                f_next = e_reg;
                g_next = f_reg;
                h_next = g_reg;
            end

            // ----------------------------------------------------------------
            STATE_UPDATE_H: begin
                ready_next = 1'b0;
                state_next = STATE_DONE;
                // Accumulate working variables into hash state
                H0_next = H0_reg + a_reg;
                H1_next = H1_reg + b_reg;
                H2_next = H2_reg + c_reg;
                H3_next = H3_reg + d_reg;
                H4_next = H4_reg + e_reg;
                H5_next = H5_reg + f_reg;
                H6_next = H6_reg + g_reg;
                H7_next = H7_reg + h_reg;
            end

            // ----------------------------------------------------------------
            STATE_DONE: begin
                ready_next        = 1'b1;
                digest_valid_next = 1'b1;
                digest_next       = {H0_reg, H1_reg, H2_reg, H3_reg,
                                     H4_reg, H5_reg, H6_reg, H7_reg};
                state_next        = STATE_IDLE;
            end

            // ----------------------------------------------------------------
            default: begin
                state_next = STATE_IDLE;
                ready_next = 1'b1;
            end

        endcase
    end

    /////////////////////////////////////////////////////////////////////////////
    // Sequential Register Update (always @(posedge clk))                     //
    /////////////////////////////////////////////////////////////////////////////

    always @(posedge clk) begin

        // --- Register updates (non-blocking) ---
        state_reg        <= state_next;
        t_reg            <= t_next;
        ready_reg        <= ready_next;
        digest_valid_reg <= digest_valid_next;
        digest_reg       <= digest_next;

        H0_reg <= H0_next; H1_reg <= H1_next; H2_reg <= H2_next; H3_reg <= H3_next;
        H4_reg <= H4_next; H5_reg <= H5_next; H6_reg <= H6_next; H7_reg <= H7_next;

        a_reg <= a_next; b_reg <= b_next; c_reg <= c_next; d_reg <= d_next;
        e_reg <= e_next; f_reg <= f_next; g_reg <= g_next; h_reg <= h_next;

        // --- W array writes (blocking: iverilog index race) ---
        // Guarded by !rst so no spurious shifts occur during reset.
        if (!rst) begin
            if (state_reg == STATE_IDLE && next) begin
                // Load 512-bit block into W[0:15] (big-endian mapping)
                W_reg[0]  = block[511:480];  // blocking: iverilog index race
                W_reg[1]  = block[479:448];  // blocking: iverilog index race
                W_reg[2]  = block[447:416];  // blocking: iverilog index race
                W_reg[3]  = block[415:384];  // blocking: iverilog index race
                W_reg[4]  = block[383:352];  // blocking: iverilog index race
                W_reg[5]  = block[351:320];  // blocking: iverilog index race
                W_reg[6]  = block[319:288];  // blocking: iverilog index race
                W_reg[7]  = block[287:256];  // blocking: iverilog index race
                W_reg[8]  = block[255:224];  // blocking: iverilog index race
                W_reg[9]  = block[223:192];  // blocking: iverilog index race
                W_reg[10] = block[191:160];  // blocking: iverilog index race
                W_reg[11] = block[159:128];  // blocking: iverilog index race
                W_reg[12] = block[127:96];   // blocking: iverilog index race
                W_reg[13] = block[95:64];    // blocking: iverilog index race
                W_reg[14] = block[63:32];    // blocking: iverilog index race
                W_reg[15] = block[31:0];     // blocking: iverilog index race
            end else if (state_reg == STATE_COMPUTE) begin
                // Compute new W value before shift (uses pre-shift W_reg values)
                w_new_val = sigma1(W_reg[14]) + W_reg[9]
                          + sigma0(W_reg[1])  + W_reg[0];
                // Shift W array left: W[i] <= W[i+1], W[15] <= w_new_val
                W_reg[0]  = W_reg[1];   // blocking: iverilog index race
                W_reg[1]  = W_reg[2];   // blocking: iverilog index race
                W_reg[2]  = W_reg[3];   // blocking: iverilog index race
                W_reg[3]  = W_reg[4];   // blocking: iverilog index race
                W_reg[4]  = W_reg[5];   // blocking: iverilog index race
                W_reg[5]  = W_reg[6];   // blocking: iverilog index race
                W_reg[6]  = W_reg[7];   // blocking: iverilog index race
                W_reg[7]  = W_reg[8];   // blocking: iverilog index race
                W_reg[8]  = W_reg[9];   // blocking: iverilog index race
                W_reg[9]  = W_reg[10];  // blocking: iverilog index race
                W_reg[10] = W_reg[11];  // blocking: iverilog index race
                W_reg[11] = W_reg[12];  // blocking: iverilog index race
                W_reg[12] = W_reg[13];  // blocking: iverilog index race
                W_reg[13] = W_reg[14];  // blocking: iverilog index race
                W_reg[14] = W_reg[15];  // blocking: iverilog index race
                W_reg[15] = w_new_val;  // blocking: iverilog index race
            end
        end

        // --- Synchronous active-high reset (last-assignment-wins) ---
        if (rst) begin
            state_reg        <= STATE_IDLE;
            t_reg            <= 6'd0;
            ready_reg        <= 1'b1;
            digest_valid_reg <= 1'b0;
            digest_reg       <= 256'd0;

            H0_reg <= 32'd0; H1_reg <= 32'd0; H2_reg <= 32'd0; H3_reg <= 32'd0;
            H4_reg <= 32'd0; H5_reg <= 32'd0; H6_reg <= 32'd0; H7_reg <= 32'd0;

            a_reg <= 32'd0; b_reg <= 32'd0; c_reg <= 32'd0; d_reg <= 32'd0;
            e_reg <= 32'd0; f_reg <= 32'd0; g_reg <= 32'd0; h_reg <= 32'd0;
        end
    end

    /////////////////////////////////////////////////////////////////////////////
    // Output Port Assignments                                                //
    /////////////////////////////////////////////////////////////////////////////

    assign ready        = ready_reg;
    assign digest_valid = digest_valid_reg;
    assign digest       = digest_reg;

endmodule

`resetall
