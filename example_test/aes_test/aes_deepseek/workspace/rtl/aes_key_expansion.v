`resetall
`timescale 1ns / 1ps
`default_nettype none

//=============================================================================
// aes_key_expansion.v -- On-the-fly AES-128 key expansion (combinational)
//
// Computes the 128-bit round key for any round (0-10) from the initial
// 128-bit cipher key.  Round 0 returns the initial key unchanged.
//
// Algorithm: Generates 44 words w[0:43] using the AES-128 key schedule
// recurrence, then selects the 4-word group for the requested round.
// Pure combinational logic -- no registers, no clock.
//
// Reference: NIST FIPS 197, Section 5.2 "Key Expansion"
//=============================================================================

module aes_key_expansion(
    input  wire [127:0] key_in,    // Initial 128-bit cipher key
    input  wire [3:0]   round,     // Round number (0-10)
    output reg  [127:0] round_key  // Expanded 128-bit round key
);

    //-------------------------------------------------------------------------
    // Internal signals
    //-------------------------------------------------------------------------

    // 44-element word array: w[0..43], each 32 bits wide
    reg [31:0] w [0:43];

    // Temporary variable for key expansion recurrence
    reg [31:0] temp;

    // Loop variable (unrolled by synthesis into combinational network)
    integer i;

    //-------------------------------------------------------------------------
    // S-Box lookup -- AES SubBytes transformation (FIPS 197 Table 7)
    //
    // 256-entry LUT implemented as combinational case statement.
    // Synthesis maps this to distributed LUTs (6-input LUT6 on Xilinx).
    //-------------------------------------------------------------------------

    function [7:0] sbox_lookup;
        input [7:0] byte_in;
        begin
            case (byte_in)
                // Row 0x
                8'h00: sbox_lookup = 8'h63;
                8'h01: sbox_lookup = 8'h7c;
                8'h02: sbox_lookup = 8'h77;
                8'h03: sbox_lookup = 8'h7b;
                8'h04: sbox_lookup = 8'hf2;
                8'h05: sbox_lookup = 8'h6b;
                8'h06: sbox_lookup = 8'h6f;
                8'h07: sbox_lookup = 8'hc5;
                8'h08: sbox_lookup = 8'h30;
                8'h09: sbox_lookup = 8'h01;
                8'h0a: sbox_lookup = 8'h67;
                8'h0b: sbox_lookup = 8'h2b;
                8'h0c: sbox_lookup = 8'hfe;
                8'h0d: sbox_lookup = 8'hd7;
                8'h0e: sbox_lookup = 8'hab;
                8'h0f: sbox_lookup = 8'h76;
                // Row 1x
                8'h10: sbox_lookup = 8'hca;
                8'h11: sbox_lookup = 8'h82;
                8'h12: sbox_lookup = 8'hc9;
                8'h13: sbox_lookup = 8'h7d;
                8'h14: sbox_lookup = 8'hfa;
                8'h15: sbox_lookup = 8'h59;
                8'h16: sbox_lookup = 8'h47;
                8'h17: sbox_lookup = 8'hf0;
                8'h18: sbox_lookup = 8'had;
                8'h19: sbox_lookup = 8'hd4;
                8'h1a: sbox_lookup = 8'ha2;
                8'h1b: sbox_lookup = 8'haf;
                8'h1c: sbox_lookup = 8'h9c;
                8'h1d: sbox_lookup = 8'ha4;
                8'h1e: sbox_lookup = 8'h72;
                8'h1f: sbox_lookup = 8'hc0;
                // Row 2x
                8'h20: sbox_lookup = 8'hb7;
                8'h21: sbox_lookup = 8'hfd;
                8'h22: sbox_lookup = 8'h93;
                8'h23: sbox_lookup = 8'h26;
                8'h24: sbox_lookup = 8'h36;
                8'h25: sbox_lookup = 8'h3f;
                8'h26: sbox_lookup = 8'hf7;
                8'h27: sbox_lookup = 8'hcc;
                8'h28: sbox_lookup = 8'h34;
                8'h29: sbox_lookup = 8'ha5;
                8'h2a: sbox_lookup = 8'he5;
                8'h2b: sbox_lookup = 8'hf1;
                8'h2c: sbox_lookup = 8'h71;
                8'h2d: sbox_lookup = 8'hd8;
                8'h2e: sbox_lookup = 8'h31;
                8'h2f: sbox_lookup = 8'h15;
                // Row 3x
                8'h30: sbox_lookup = 8'h04;
                8'h31: sbox_lookup = 8'hc7;
                8'h32: sbox_lookup = 8'h23;
                8'h33: sbox_lookup = 8'hc3;
                8'h34: sbox_lookup = 8'h18;
                8'h35: sbox_lookup = 8'h96;
                8'h36: sbox_lookup = 8'h05;
                8'h37: sbox_lookup = 8'h9a;
                8'h38: sbox_lookup = 8'h07;
                8'h39: sbox_lookup = 8'h12;
                8'h3a: sbox_lookup = 8'h80;
                8'h3b: sbox_lookup = 8'he2;
                8'h3c: sbox_lookup = 8'heb;
                8'h3d: sbox_lookup = 8'h27;
                8'h3e: sbox_lookup = 8'hb2;
                8'h3f: sbox_lookup = 8'h75;
                // Row 4x
                8'h40: sbox_lookup = 8'h09;
                8'h41: sbox_lookup = 8'h83;
                8'h42: sbox_lookup = 8'h2c;
                8'h43: sbox_lookup = 8'h1a;
                8'h44: sbox_lookup = 8'h1b;
                8'h45: sbox_lookup = 8'h6e;
                8'h46: sbox_lookup = 8'h5a;
                8'h47: sbox_lookup = 8'ha0;
                8'h48: sbox_lookup = 8'h52;
                8'h49: sbox_lookup = 8'h3b;
                8'h4a: sbox_lookup = 8'hd6;
                8'h4b: sbox_lookup = 8'hb3;
                8'h4c: sbox_lookup = 8'h29;
                8'h4d: sbox_lookup = 8'he3;
                8'h4e: sbox_lookup = 8'h2f;
                8'h4f: sbox_lookup = 8'h84;
                // Row 5x
                8'h50: sbox_lookup = 8'h53;
                8'h51: sbox_lookup = 8'hd1;
                8'h52: sbox_lookup = 8'h00;
                8'h53: sbox_lookup = 8'hed;
                8'h54: sbox_lookup = 8'h20;
                8'h55: sbox_lookup = 8'hfc;
                8'h56: sbox_lookup = 8'hb1;
                8'h57: sbox_lookup = 8'h5b;
                8'h58: sbox_lookup = 8'h6a;
                8'h59: sbox_lookup = 8'hcb;
                8'h5a: sbox_lookup = 8'hbe;
                8'h5b: sbox_lookup = 8'h39;
                8'h5c: sbox_lookup = 8'h4a;
                8'h5d: sbox_lookup = 8'h4c;
                8'h5e: sbox_lookup = 8'h58;
                8'h5f: sbox_lookup = 8'hcf;
                // Row 6x
                8'h60: sbox_lookup = 8'hd0;
                8'h61: sbox_lookup = 8'hef;
                8'h62: sbox_lookup = 8'haa;
                8'h63: sbox_lookup = 8'hfb;
                8'h64: sbox_lookup = 8'h43;
                8'h65: sbox_lookup = 8'h4d;
                8'h66: sbox_lookup = 8'h33;
                8'h67: sbox_lookup = 8'h85;
                8'h68: sbox_lookup = 8'h45;
                8'h69: sbox_lookup = 8'hf9;
                8'h6a: sbox_lookup = 8'h02;
                8'h6b: sbox_lookup = 8'h7f;
                8'h6c: sbox_lookup = 8'h50;
                8'h6d: sbox_lookup = 8'h3c;
                8'h6e: sbox_lookup = 8'h9f;
                8'h6f: sbox_lookup = 8'ha8;
                // Row 7x
                8'h70: sbox_lookup = 8'h51;
                8'h71: sbox_lookup = 8'ha3;
                8'h72: sbox_lookup = 8'h40;
                8'h73: sbox_lookup = 8'h8f;
                8'h74: sbox_lookup = 8'h92;
                8'h75: sbox_lookup = 8'h9d;
                8'h76: sbox_lookup = 8'h38;
                8'h77: sbox_lookup = 8'hf5;
                8'h78: sbox_lookup = 8'hbc;
                8'h79: sbox_lookup = 8'hb6;
                8'h7a: sbox_lookup = 8'hda;
                8'h7b: sbox_lookup = 8'h21;
                8'h7c: sbox_lookup = 8'h10;
                8'h7d: sbox_lookup = 8'hff;
                8'h7e: sbox_lookup = 8'hf3;
                8'h7f: sbox_lookup = 8'hd2;
                // Row 8x
                8'h80: sbox_lookup = 8'hcd;
                8'h81: sbox_lookup = 8'h0c;
                8'h82: sbox_lookup = 8'h13;
                8'h83: sbox_lookup = 8'hec;
                8'h84: sbox_lookup = 8'h5f;
                8'h85: sbox_lookup = 8'h97;
                8'h86: sbox_lookup = 8'h44;
                8'h87: sbox_lookup = 8'h17;
                8'h88: sbox_lookup = 8'hc4;
                8'h89: sbox_lookup = 8'ha7;
                8'h8a: sbox_lookup = 8'h7e;
                8'h8b: sbox_lookup = 8'h3d;
                8'h8c: sbox_lookup = 8'h64;
                8'h8d: sbox_lookup = 8'h5d;
                8'h8e: sbox_lookup = 8'h19;
                8'h8f: sbox_lookup = 8'h73;
                // Row 9x
                8'h90: sbox_lookup = 8'h60;
                8'h91: sbox_lookup = 8'h81;
                8'h92: sbox_lookup = 8'h4f;
                8'h93: sbox_lookup = 8'hdc;
                8'h94: sbox_lookup = 8'h22;
                8'h95: sbox_lookup = 8'h2a;
                8'h96: sbox_lookup = 8'h90;
                8'h97: sbox_lookup = 8'h88;
                8'h98: sbox_lookup = 8'h46;
                8'h99: sbox_lookup = 8'hee;
                8'h9a: sbox_lookup = 8'hb8;
                8'h9b: sbox_lookup = 8'h14;
                8'h9c: sbox_lookup = 8'hde;
                8'h9d: sbox_lookup = 8'h5e;
                8'h9e: sbox_lookup = 8'h0b;
                8'h9f: sbox_lookup = 8'hdb;
                // Row Ax
                8'ha0: sbox_lookup = 8'he0;
                8'ha1: sbox_lookup = 8'h32;
                8'ha2: sbox_lookup = 8'h3a;
                8'ha3: sbox_lookup = 8'h0a;
                8'ha4: sbox_lookup = 8'h49;
                8'ha5: sbox_lookup = 8'h06;
                8'ha6: sbox_lookup = 8'h24;
                8'ha7: sbox_lookup = 8'h5c;
                8'ha8: sbox_lookup = 8'hc2;
                8'ha9: sbox_lookup = 8'hd3;
                8'haa: sbox_lookup = 8'hac;
                8'hab: sbox_lookup = 8'h62;
                8'hac: sbox_lookup = 8'h91;
                8'had: sbox_lookup = 8'h95;
                8'hae: sbox_lookup = 8'he4;
                8'haf: sbox_lookup = 8'h79;
                // Row Bx
                8'hb0: sbox_lookup = 8'he7;
                8'hb1: sbox_lookup = 8'hc8;
                8'hb2: sbox_lookup = 8'h37;
                8'hb3: sbox_lookup = 8'h6d;
                8'hb4: sbox_lookup = 8'h8d;
                8'hb5: sbox_lookup = 8'hd5;
                8'hb6: sbox_lookup = 8'h4e;
                8'hb7: sbox_lookup = 8'ha9;
                8'hb8: sbox_lookup = 8'h6c;
                8'hb9: sbox_lookup = 8'h56;
                8'hba: sbox_lookup = 8'hf4;
                8'hbb: sbox_lookup = 8'hea;
                8'hbc: sbox_lookup = 8'h65;
                8'hbd: sbox_lookup = 8'h7a;
                8'hbe: sbox_lookup = 8'hae;
                8'hbf: sbox_lookup = 8'h08;
                // Row Cx
                8'hc0: sbox_lookup = 8'hba;
                8'hc1: sbox_lookup = 8'h78;
                8'hc2: sbox_lookup = 8'h25;
                8'hc3: sbox_lookup = 8'h2e;
                8'hc4: sbox_lookup = 8'h1c;
                8'hc5: sbox_lookup = 8'ha6;
                8'hc6: sbox_lookup = 8'hb4;
                8'hc7: sbox_lookup = 8'hc6;
                8'hc8: sbox_lookup = 8'he8;
                8'hc9: sbox_lookup = 8'hdd;
                8'hca: sbox_lookup = 8'h74;
                8'hcb: sbox_lookup = 8'h1f;
                8'hcc: sbox_lookup = 8'h4b;
                8'hcd: sbox_lookup = 8'hbd;
                8'hce: sbox_lookup = 8'h8b;
                8'hcf: sbox_lookup = 8'h8a;
                // Row Dx
                8'hd0: sbox_lookup = 8'h70;
                8'hd1: sbox_lookup = 8'h3e;
                8'hd2: sbox_lookup = 8'hb5;
                8'hd3: sbox_lookup = 8'h66;
                8'hd4: sbox_lookup = 8'h48;
                8'hd5: sbox_lookup = 8'h03;
                8'hd6: sbox_lookup = 8'hf6;
                8'hd7: sbox_lookup = 8'h0e;
                8'hd8: sbox_lookup = 8'h61;
                8'hd9: sbox_lookup = 8'h35;
                8'hda: sbox_lookup = 8'h57;
                8'hdb: sbox_lookup = 8'hb9;
                8'hdc: sbox_lookup = 8'h86;
                8'hdd: sbox_lookup = 8'hc1;
                8'hde: sbox_lookup = 8'h1d;
                8'hdf: sbox_lookup = 8'h9e;
                // Row Ex
                8'he0: sbox_lookup = 8'he1;
                8'he1: sbox_lookup = 8'hf8;
                8'he2: sbox_lookup = 8'h98;
                8'he3: sbox_lookup = 8'h11;
                8'he4: sbox_lookup = 8'h69;
                8'he5: sbox_lookup = 8'hd9;
                8'he6: sbox_lookup = 8'h8e;
                8'he7: sbox_lookup = 8'h94;
                8'he8: sbox_lookup = 8'h9b;
                8'he9: sbox_lookup = 8'h1e;
                8'hea: sbox_lookup = 8'h87;
                8'heb: sbox_lookup = 8'he9;
                8'hec: sbox_lookup = 8'hce;
                8'hed: sbox_lookup = 8'h55;
                8'hee: sbox_lookup = 8'h28;
                8'hef: sbox_lookup = 8'hdf;
                // Row Fx
                8'hf0: sbox_lookup = 8'h8c;
                8'hf1: sbox_lookup = 8'ha1;
                8'hf2: sbox_lookup = 8'h89;
                8'hf3: sbox_lookup = 8'h0d;
                8'hf4: sbox_lookup = 8'hbf;
                8'hf5: sbox_lookup = 8'he6;
                8'hf6: sbox_lookup = 8'h42;
                8'hf7: sbox_lookup = 8'h68;
                8'hf8: sbox_lookup = 8'h41;
                8'hf9: sbox_lookup = 8'h99;
                8'hfa: sbox_lookup = 8'h2d;
                8'hfb: sbox_lookup = 8'h0f;
                8'hfc: sbox_lookup = 8'hb0;
                8'hfd: sbox_lookup = 8'h54;
                8'hfe: sbox_lookup = 8'hbb;
                8'hff: sbox_lookup = 8'h16;
            endcase
        end
    endfunction

    //-------------------------------------------------------------------------
    // SubWord -- apply S-Box to each of 4 bytes in a 32-bit word
    //
    // MSB-first byte order.  Four independent S-Box lookups in parallel.
    //-------------------------------------------------------------------------

    function [31:0] sub_word;
        input [31:0] word_in;
        begin
            sub_word = {sbox_lookup(word_in[31:24]),
                        sbox_lookup(word_in[23:16]),
                        sbox_lookup(word_in[15: 8]),
                        sbox_lookup(word_in[ 7: 0])};
        end
    endfunction

    //-------------------------------------------------------------------------
    // RotWord -- rotate 32-bit word left by 8 bits
    //
    // [b0, b1, b2, b3] -> [b1, b2, b3, b0].  Pure wiring (no logic gates).
    //-------------------------------------------------------------------------

    function [31:0] rot_word;
        input [31:0] word_in;
        begin
            rot_word = {word_in[23:0], word_in[31:24]};
        end
    endfunction

    //-------------------------------------------------------------------------
    // RCON lookup -- round constant for key expansion g-function
    //
    // Returns the AES RCON byte for key expansion round index 1..10.
    // RCON[1..10] = {0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36}
    //-------------------------------------------------------------------------

    function [7:0] get_rcon;
        input [3:0] rnd;
        begin
            case (rnd)
                4'd1:  get_rcon = 8'h01;
                4'd2:  get_rcon = 8'h02;
                4'd3:  get_rcon = 8'h04;
                4'd4:  get_rcon = 8'h08;
                4'd5:  get_rcon = 8'h10;
                4'd6:  get_rcon = 8'h20;
                4'd7:  get_rcon = 8'h40;
                4'd8:  get_rcon = 8'h80;
                4'd9:  get_rcon = 8'h1b;
                4'd10: get_rcon = 8'h36;
                default: get_rcon = 8'h00;
            endcase
        end
    endfunction

    //-------------------------------------------------------------------------
    // Key Expansion Recurrence -- unrolled combinational network
    //
    // Generates all 44 words w[0:43] from the initial key using the AES-128
    // key schedule recurrence, then selects the 4-word round key for the
    // requested round number.
    //
    // Algorithm (from golden_model.py):
    //   w[0:3] = key_in split into 4 x 32-bit words (MSB first)
    //   For i = 4 to 43:
    //     temp = w[i-1]
    //     if i % 4 == 0:
    //       temp = SubWord(RotWord(temp)) xor (RCON[i/4] << 24)
    //     w[i] = w[i-4] xor temp
    //
    // The synthesis tool unrolls this for-loop into a fully combinational
    // network.  Blocking assignments model the dataflow correctly: each
    // iteration's w[i] feeds the next iteration's w[i-1] dependency.
    //
    // Critical path: ~10 SubWord calls (each ~6 LUT levels) interleaved
    // with ~40 XOR gates through the recurrence chain.
    //-------------------------------------------------------------------------

    always @* begin
        // Initialize w[0:3] from key_in (MSB-first byte order)
        w[0] = key_in[127:96];
        w[1] = key_in[ 95:64];
        w[2] = key_in[ 63:32];
        w[3] = key_in[ 31: 0];

        // Compute w[4] through w[43] using AES-128 key schedule recurrence
        for (i = 4; i < 44; i = i + 1) begin
            temp = w[i-1];

            // Every 4th word (i % 4 == 0): apply g-function
            // g(w) = SubWord(RotWord(w)) xor RCON
            // i[1:0] == 2'b00 is synthesizer-friendly equivalent of i % 4 == 0
            if (i[1:0] == 2'b00) begin
                // i[5:2] = i/4 (ranges 1..10 for i=4..43), avoids 32-bit shift
                temp = sub_word(rot_word(temp)) ^ {get_rcon(i[5:2]), 24'h0};
            end

            w[i] = w[i-4] ^ temp;
        end

        // Select the 4-word group for the requested round
        // round=0 -> identity (w[0:3] = key_in)
        // round=1..10 -> {w[4r], w[4r+1], w[4r+2], w[4r+3]}
        case (round)
            4'd0:  round_key = {w[0],  w[1],  w[2],  w[3]};
            4'd1:  round_key = {w[4],  w[5],  w[6],  w[7]};
            4'd2:  round_key = {w[8],  w[9],  w[10], w[11]};
            4'd3:  round_key = {w[12], w[13], w[14], w[15]};
            4'd4:  round_key = {w[16], w[17], w[18], w[19]};
            4'd5:  round_key = {w[20], w[21], w[22], w[23]};
            4'd6:  round_key = {w[24], w[25], w[26], w[27]};
            4'd7:  round_key = {w[28], w[29], w[30], w[31]};
            4'd8:  round_key = {w[32], w[33], w[34], w[35]};
            4'd9:  round_key = {w[36], w[37], w[38], w[39]};
            4'd10: round_key = {w[40], w[41], w[42], w[43]};
            default: round_key = 128'h0;
        endcase
    end

endmodule

`default_nettype wire
