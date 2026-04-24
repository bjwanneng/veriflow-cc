// -----------------------------------------------------------------------------
// File   : chacha20_top.v
// Author : AI Coder
// Date   : 2026-04-24
// -----------------------------------------------------------------------------
// Description:
//   Top-level ChaCha20 stream cipher wrapper. Handles reset synchronization,
//   key/nonce/counter loading via parallel inputs, FSM for block generation,
//   and data streaming interface with XOR against keystream.
// -----------------------------------------------------------------------------
// Change Log:
//   2026-04-24  AI Coder  v1.0  Initial release
// -----------------------------------------------------------------------------

`resetall
`timescale 1ns / 1ps
`default_nettype none

module chacha20_top
(
    input  wire          clk_i,
    input  wire          rst_n_i,
    input  wire [255:0]  key_i,
    input  wire [95:0]   nonce_i,
    input  wire [31:0]   counter_i,
    input  wire          start_i,
    input  wire          din_valid_i,
    input  wire [31:0]   din_data_i,
    output wire          din_ready_o,
    output wire          dout_valid_o,
    output wire [31:0]   dout_data_o,
    input  wire          dout_ready_i,
    output wire          ready_o,
    output wire          block_done_o
);

    //////////////////////////
    // Reset Synchronizer   //
    //////////////////////////

    reg rst_n_meta = 1'b0;
    reg rst_n_sync = 1'b0;

    always @(posedge clk_i or negedge rst_n_i) begin
        if (!rst_n_i) begin
            rst_n_meta <= 1'b0;
            rst_n_sync <= 1'b0;
        end else begin
            rst_n_meta <= 1'b1;
            rst_n_sync <= rst_n_meta;
        end
    end

    ////////////////////////////
    // FSM State Encoding     //
    ////////////////////////////

    localparam [1:0]
        TOP_STATE_IDLE   = 2'd0,
        TOP_STATE_COMPUTE = 2'd1,
        TOP_STATE_OUTPUT = 2'd2;

    reg [1:0] top_state_reg = TOP_STATE_IDLE, top_state_next;

    ////////////////////////////
    // Internal Registers     //
    ////////////////////////////

    reg [31:0]  counter_reg    = {32{1'b0}}, counter_next;
    reg [511:0] keystream_reg  = {512{1'b0}}, keystream_next;
    reg [3:0]   word_cnt_reg   = 4'd0, word_cnt_next;
    reg         start_pulse_reg = 1'b0, start_pulse_next;
    reg         block_done_reg  = 1'b0, block_done_next;

    ////////////////////////////
    // Internal Wires         //
    ////////////////////////////

    wire [511:0] core_state_o;
    wire         core_done_o;
    wire         core_busy_o;

    ////////////////////////////
    // Output Registers       //
    ////////////////////////////

    reg        ready_o_reg      = 1'b0, ready_o_next;
    reg        din_ready_o_reg  = 1'b0, din_ready_o_next;
    reg        dout_valid_o_reg = 1'b0, dout_valid_o_next;

    ////////////////////////////
    // Output Assignments     //
    ////////////////////////////

    assign ready_o      = ready_o_reg;
    assign din_ready_o  = din_ready_o_reg;
    assign dout_valid_o = dout_valid_o_reg;
    assign block_done_o = block_done_reg;

    ////////////////////////////
    // Keystream Word Select  //
    ////////////////////////////

    reg [31:0] keystream_word;

    always @* begin
        case (word_cnt_reg)
            4'd0:  keystream_word = keystream_reg[31:0];
            4'd1:  keystream_word = keystream_reg[63:32];
            4'd2:  keystream_word = keystream_reg[95:64];
            4'd3:  keystream_word = keystream_reg[127:96];
            4'd4:  keystream_word = keystream_reg[159:128];
            4'd5:  keystream_word = keystream_reg[191:160];
            4'd6:  keystream_word = keystream_reg[223:192];
            4'd7:  keystream_word = keystream_reg[255:224];
            4'd8:  keystream_word = keystream_reg[287:256];
            4'd9:  keystream_word = keystream_reg[319:288];
            4'd10: keystream_word = keystream_reg[351:320];
            4'd11: keystream_word = keystream_reg[383:352];
            4'd12: keystream_word = keystream_reg[415:384];
            4'd13: keystream_word = keystream_reg[447:416];
            4'd14: keystream_word = keystream_reg[479:448];
            4'd15: keystream_word = keystream_reg[511:480];
            default: keystream_word = {32{1'b0}};
        endcase
    end

    // Data output is combinational (gated by dout_valid_o)
    assign dout_data_o  = (top_state_reg == TOP_STATE_OUTPUT) ? (keystream_word ^ din_data_i) : {32{1'b0}};

    ////////////////////////////
    // Combinational Logic    //
    ////////////////////////////

    always @* begin
        // Default values to prevent latches
        top_state_next    = top_state_reg;
        counter_next      = counter_reg;
        keystream_next    = keystream_reg;
        word_cnt_next     = word_cnt_reg;
        start_pulse_next  = 1'b0;
        block_done_next   = 1'b0;
        ready_o_next      = 1'b0;
        din_ready_o_next  = 1'b0;
        dout_valid_o_next = 1'b0;

        case (top_state_reg)
            TOP_STATE_IDLE: begin
                ready_o_next = 1'b1;
                if (start_i) begin
                    counter_next     = counter_i;
                    start_pulse_next = 1'b1;
                    top_state_next   = TOP_STATE_COMPUTE;
                end
            end

            TOP_STATE_COMPUTE: begin
                if (core_done_o) begin
                    keystream_next   = core_state_o;
                    word_cnt_next    = 4'd0;
                    top_state_next   = TOP_STATE_OUTPUT;
                end
            end

            TOP_STATE_OUTPUT: begin
                dout_valid_o_next = 1'b1;
                din_ready_o_next  = dout_ready_i;
                if (dout_ready_i) begin
                    if (word_cnt_reg == 4'd15) begin
                        counter_next    = counter_reg + 32'd1;
                        block_done_next = 1'b1;
                        top_state_next  = TOP_STATE_IDLE;
                    end else begin
                        word_cnt_next = word_cnt_reg + 4'd1;
                    end
                end
            end

            default: begin
                top_state_next = TOP_STATE_IDLE;
            end
        endcase
    end

    ////////////////////////////
    // Sequential Logic       //
    ////////////////////////////

    always @(posedge clk_i or negedge rst_n_sync) begin
        if (!rst_n_sync) begin
            top_state_reg    <= TOP_STATE_IDLE;
            counter_reg      <= {32{1'b0}};
            keystream_reg    <= {512{1'b0}};
            word_cnt_reg     <= 4'd0;
            start_pulse_reg  <= 1'b0;
            block_done_reg   <= 1'b0;
            ready_o_reg      <= 1'b0;
            din_ready_o_reg  <= 1'b0;
            dout_valid_o_reg <= 1'b0;
        end else begin
            top_state_reg    <= top_state_next;
            counter_reg      <= counter_next;
            keystream_reg    <= keystream_next;
            word_cnt_reg     <= word_cnt_next;
            start_pulse_reg  <= start_pulse_next;
            block_done_reg   <= block_done_next;
            ready_o_reg      <= ready_o_next;
            din_ready_o_reg  <= din_ready_o_next;
            dout_valid_o_reg <= dout_valid_o_next;
        end
    end

    ///////////////////////////
    // Submodule Instantiation //
    ///////////////////////////

    chacha20_core chacha20_core_inst
    (
        .clk_i      (clk_i),
        .rst_n_i    (rst_n_sync),
        .key_i      (key_i),
        .nonce_i    (nonce_i),
        .counter_i  (counter_reg),
        .start_i    (start_pulse_reg),
        .state_o    (core_state_o),
        .done_o     (core_done_o),
        .busy_o     (core_busy_o)
    );

endmodule

`resetall
