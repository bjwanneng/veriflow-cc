//------------------------------------------------------------------------------
// Module: aes_sbox
// Description: AES S-Box byte substitution — 256-entry combinational lookup
//              per FIPS 197 Table 7.
//------------------------------------------------------------------------------
`resetall
`timescale 1ns / 1ps
`default_nettype none

module aes_sbox(
    input  wire [7:0] byte_in,
    output wire [7:0] byte_out
);

reg [7:0] sbox_out;

assign byte_out = sbox_out;

always @* begin
    case (byte_in)
        // Row 0x0
        8'h00: sbox_out = 8'h63;
        8'h01: sbox_out = 8'h7c;
        8'h02: sbox_out = 8'h77;
        8'h03: sbox_out = 8'h7b;
        8'h04: sbox_out = 8'hf2;
        8'h05: sbox_out = 8'h6b;
        8'h06: sbox_out = 8'h6f;
        8'h07: sbox_out = 8'hc5;
        8'h08: sbox_out = 8'h30;
        8'h09: sbox_out = 8'h01;
        8'h0a: sbox_out = 8'h67;
        8'h0b: sbox_out = 8'h2b;
        8'h0c: sbox_out = 8'hfe;
        8'h0d: sbox_out = 8'hd7;
        8'h0e: sbox_out = 8'hab;
        8'h0f: sbox_out = 8'h76;

        // Row 0x1
        8'h10: sbox_out = 8'hca;
        8'h11: sbox_out = 8'h82;
        8'h12: sbox_out = 8'hc9;
        8'h13: sbox_out = 8'h7d;
        8'h14: sbox_out = 8'hfa;
        8'h15: sbox_out = 8'h59;
        8'h16: sbox_out = 8'h47;
        8'h17: sbox_out = 8'hf0;
        8'h18: sbox_out = 8'had;
        8'h19: sbox_out = 8'hd4;
        8'h1a: sbox_out = 8'ha2;
        8'h1b: sbox_out = 8'haf;
        8'h1c: sbox_out = 8'h9c;
        8'h1d: sbox_out = 8'ha4;
        8'h1e: sbox_out = 8'h72;
        8'h1f: sbox_out = 8'hc0;

        // Row 0x2
        8'h20: sbox_out = 8'hb7;
        8'h21: sbox_out = 8'hfd;
        8'h22: sbox_out = 8'h93;
        8'h23: sbox_out = 8'h26;
        8'h24: sbox_out = 8'h36;
        8'h25: sbox_out = 8'h3f;
        8'h26: sbox_out = 8'hf7;
        8'h27: sbox_out = 8'hcc;
        8'h28: sbox_out = 8'h34;
        8'h29: sbox_out = 8'ha5;
        8'h2a: sbox_out = 8'he5;
        8'h2b: sbox_out = 8'hf1;
        8'h2c: sbox_out = 8'h71;
        8'h2d: sbox_out = 8'hd8;
        8'h2e: sbox_out = 8'h31;
        8'h2f: sbox_out = 8'h15;

        // Row 0x3
        8'h30: sbox_out = 8'h04;
        8'h31: sbox_out = 8'hc7;
        8'h32: sbox_out = 8'h23;
        8'h33: sbox_out = 8'hc3;
        8'h34: sbox_out = 8'h18;
        8'h35: sbox_out = 8'h96;
        8'h36: sbox_out = 8'h05;
        8'h37: sbox_out = 8'h9a;
        8'h38: sbox_out = 8'h07;
        8'h39: sbox_out = 8'h12;
        8'h3a: sbox_out = 8'h80;
        8'h3b: sbox_out = 8'he2;
        8'h3c: sbox_out = 8'heb;
        8'h3d: sbox_out = 8'h27;
        8'h3e: sbox_out = 8'hb2;
        8'h3f: sbox_out = 8'h75;

        // Row 0x4
        8'h40: sbox_out = 8'h09;
        8'h41: sbox_out = 8'h83;
        8'h42: sbox_out = 8'h2c;
        8'h43: sbox_out = 8'h1a;
        8'h44: sbox_out = 8'h1b;
        8'h45: sbox_out = 8'h6e;
        8'h46: sbox_out = 8'h5a;
        8'h47: sbox_out = 8'ha0;
        8'h48: sbox_out = 8'h52;
        8'h49: sbox_out = 8'h3b;
        8'h4a: sbox_out = 8'hd6;
        8'h4b: sbox_out = 8'hb3;
        8'h4c: sbox_out = 8'h29;
        8'h4d: sbox_out = 8'he3;
        8'h4e: sbox_out = 8'h2f;
        8'h4f: sbox_out = 8'h84;

        // Row 0x5
        8'h50: sbox_out = 8'h53;
        8'h51: sbox_out = 8'hd1;
        8'h52: sbox_out = 8'h00;
        8'h53: sbox_out = 8'hed;
        8'h54: sbox_out = 8'h20;
        8'h55: sbox_out = 8'hfc;
        8'h56: sbox_out = 8'hb1;
        8'h57: sbox_out = 8'h5b;
        8'h58: sbox_out = 8'h6a;
        8'h59: sbox_out = 8'hcb;
        8'h5a: sbox_out = 8'hbe;
        8'h5b: sbox_out = 8'h39;
        8'h5c: sbox_out = 8'h4a;
        8'h5d: sbox_out = 8'h4c;
        8'h5e: sbox_out = 8'h58;
        8'h5f: sbox_out = 8'hcf;

        // Row 0x6
        8'h60: sbox_out = 8'hd0;
        8'h61: sbox_out = 8'hef;
        8'h62: sbox_out = 8'haa;
        8'h63: sbox_out = 8'hfb;
        8'h64: sbox_out = 8'h43;
        8'h65: sbox_out = 8'h4d;
        8'h66: sbox_out = 8'h33;
        8'h67: sbox_out = 8'h85;
        8'h68: sbox_out = 8'h45;
        8'h69: sbox_out = 8'hf9;
        8'h6a: sbox_out = 8'h02;
        8'h6b: sbox_out = 8'h7f;
        8'h6c: sbox_out = 8'h50;
        8'h6d: sbox_out = 8'h3c;
        8'h6e: sbox_out = 8'h9f;
        8'h6f: sbox_out = 8'ha8;

        // Row 0x7
        8'h70: sbox_out = 8'h51;
        8'h71: sbox_out = 8'ha3;
        8'h72: sbox_out = 8'h40;
        8'h73: sbox_out = 8'h8f;
        8'h74: sbox_out = 8'h92;
        8'h75: sbox_out = 8'h9d;
        8'h76: sbox_out = 8'h38;
        8'h77: sbox_out = 8'hf5;
        8'h78: sbox_out = 8'hbc;
        8'h79: sbox_out = 8'hb6;
        8'h7a: sbox_out = 8'hda;
        8'h7b: sbox_out = 8'h21;
        8'h7c: sbox_out = 8'h10;
        8'h7d: sbox_out = 8'hff;
        8'h7e: sbox_out = 8'hf3;
        8'h7f: sbox_out = 8'hd2;

        // Row 0x8
        8'h80: sbox_out = 8'hcd;
        8'h81: sbox_out = 8'h0c;
        8'h82: sbox_out = 8'h13;
        8'h83: sbox_out = 8'hec;
        8'h84: sbox_out = 8'h5f;
        8'h85: sbox_out = 8'h97;
        8'h86: sbox_out = 8'h44;
        8'h87: sbox_out = 8'h17;
        8'h88: sbox_out = 8'hc4;
        8'h89: sbox_out = 8'ha7;
        8'h8a: sbox_out = 8'h7e;
        8'h8b: sbox_out = 8'h3d;
        8'h8c: sbox_out = 8'h64;
        8'h8d: sbox_out = 8'h5d;
        8'h8e: sbox_out = 8'h19;
        8'h8f: sbox_out = 8'h73;

        // Row 0x9
        8'h90: sbox_out = 8'h60;
        8'h91: sbox_out = 8'h81;
        8'h92: sbox_out = 8'h4f;
        8'h93: sbox_out = 8'hdc;
        8'h94: sbox_out = 8'h22;
        8'h95: sbox_out = 8'h2a;
        8'h96: sbox_out = 8'h90;
        8'h97: sbox_out = 8'h88;
        8'h98: sbox_out = 8'h46;
        8'h99: sbox_out = 8'hee;
        8'h9a: sbox_out = 8'hb8;
        8'h9b: sbox_out = 8'h14;
        8'h9c: sbox_out = 8'hde;
        8'h9d: sbox_out = 8'h5e;
        8'h9e: sbox_out = 8'h0b;
        8'h9f: sbox_out = 8'hdb;

        // Row 0xa
        8'ha0: sbox_out = 8'he0;
        8'ha1: sbox_out = 8'h32;
        8'ha2: sbox_out = 8'h3a;
        8'ha3: sbox_out = 8'h0a;
        8'ha4: sbox_out = 8'h49;
        8'ha5: sbox_out = 8'h06;
        8'ha6: sbox_out = 8'h24;
        8'ha7: sbox_out = 8'h5c;
        8'ha8: sbox_out = 8'hc2;
        8'ha9: sbox_out = 8'hd3;
        8'haa: sbox_out = 8'hac;
        8'hab: sbox_out = 8'h62;
        8'hac: sbox_out = 8'h91;
        8'had: sbox_out = 8'h95;
        8'hae: sbox_out = 8'he4;
        8'haf: sbox_out = 8'h79;

        // Row 0xb
        8'hb0: sbox_out = 8'he7;
        8'hb1: sbox_out = 8'hc8;
        8'hb2: sbox_out = 8'h37;
        8'hb3: sbox_out = 8'h6d;
        8'hb4: sbox_out = 8'h8d;
        8'hb5: sbox_out = 8'hd5;
        8'hb6: sbox_out = 8'h4e;
        8'hb7: sbox_out = 8'ha9;
        8'hb8: sbox_out = 8'h6c;
        8'hb9: sbox_out = 8'h56;
        8'hba: sbox_out = 8'hf4;
        8'hbb: sbox_out = 8'hea;
        8'hbc: sbox_out = 8'h65;
        8'hbd: sbox_out = 8'h7a;
        8'hbe: sbox_out = 8'hae;
        8'hbf: sbox_out = 8'h08;

        // Row 0xc
        8'hc0: sbox_out = 8'hba;
        8'hc1: sbox_out = 8'h78;
        8'hc2: sbox_out = 8'h25;
        8'hc3: sbox_out = 8'h2e;
        8'hc4: sbox_out = 8'h1c;
        8'hc5: sbox_out = 8'ha6;
        8'hc6: sbox_out = 8'hb4;
        8'hc7: sbox_out = 8'hc6;
        8'hc8: sbox_out = 8'he8;
        8'hc9: sbox_out = 8'hdd;
        8'hca: sbox_out = 8'h74;
        8'hcb: sbox_out = 8'h1f;
        8'hcc: sbox_out = 8'h4b;
        8'hcd: sbox_out = 8'hbd;
        8'hce: sbox_out = 8'h8b;
        8'hcf: sbox_out = 8'h8a;

        // Row 0xd
        8'hd0: sbox_out = 8'h70;
        8'hd1: sbox_out = 8'h3e;
        8'hd2: sbox_out = 8'hb5;
        8'hd3: sbox_out = 8'h66;
        8'hd4: sbox_out = 8'h48;
        8'hd5: sbox_out = 8'h03;
        8'hd6: sbox_out = 8'hf6;
        8'hd7: sbox_out = 8'h0e;
        8'hd8: sbox_out = 8'h61;
        8'hd9: sbox_out = 8'h35;
        8'hda: sbox_out = 8'h57;
        8'hdb: sbox_out = 8'hb9;
        8'hdc: sbox_out = 8'h86;
        8'hdd: sbox_out = 8'hc1;
        8'hde: sbox_out = 8'h1d;
        8'hdf: sbox_out = 8'h9e;

        // Row 0xe
        8'he0: sbox_out = 8'he1;
        8'he1: sbox_out = 8'hf8;
        8'he2: sbox_out = 8'h98;
        8'he3: sbox_out = 8'h11;
        8'he4: sbox_out = 8'h69;
        8'he5: sbox_out = 8'hd9;
        8'he6: sbox_out = 8'h8e;
        8'he7: sbox_out = 8'h94;
        8'he8: sbox_out = 8'h9b;
        8'he9: sbox_out = 8'h1e;
        8'hea: sbox_out = 8'h87;
        8'heb: sbox_out = 8'he9;
        8'hec: sbox_out = 8'hce;
        8'hed: sbox_out = 8'h55;
        8'hee: sbox_out = 8'h28;
        8'hef: sbox_out = 8'hdf;

        // Row 0xf
        8'hf0: sbox_out = 8'h8c;
        8'hf1: sbox_out = 8'ha1;
        8'hf2: sbox_out = 8'h89;
        8'hf3: sbox_out = 8'h0d;
        8'hf4: sbox_out = 8'hbf;
        8'hf5: sbox_out = 8'he6;
        8'hf6: sbox_out = 8'h42;
        8'hf7: sbox_out = 8'h68;
        8'hf8: sbox_out = 8'h41;
        8'hf9: sbox_out = 8'h99;
        8'hfa: sbox_out = 8'h2d;
        8'hfb: sbox_out = 8'h0f;
        8'hfc: sbox_out = 8'hb0;
        8'hfd: sbox_out = 8'h54;
        8'hfe: sbox_out = 8'hbb;
        8'hff: sbox_out = 8'h16;

        default: sbox_out = 8'h00;
    endcase
end

endmodule

`default_nettype wire
