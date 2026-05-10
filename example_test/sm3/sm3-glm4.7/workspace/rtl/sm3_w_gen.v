//----------------------------------------------------------------------------
// Module: sm3_w_gen
// Description: SM3 message expansion unit
//              Generates W_j and W'_j for the compression function
//
//              Algorithm:
//              - For j < 16: W_j = msg_block_word[j]
//              - For j >= 16: W_j = P1(W_j-16 ⊕ W_j-9 ⊕ ROL(W_j-3, 15))
//                             ⊕ ROL(W_j-13, 7) ⊕ W_j-6
//              - W'_j = W_j ⊕ W_j+4
//
//              Where P1(X) = X ⊕ ROL(X, 15) ⊕ ROL(X, 23)
//----------------------------------------------------------------------------

module sm3_w_gen (
    input  wire         clk,
    input  wire         rst,
    input  wire         load_en,
    input  wire         calc_en,
    input  wire [511:0] msg_block,
    input  wire [5:0]   round_cnt,
    output reg  [31:0]  w,
    output reg  [31:0]  w_prime
);

    //------------------------------------------------------------------------
    // 16-word shift register for area optimization
    // Stores W_{j} to W_{j+15} where j is the current round
    //------------------------------------------------------------------------
    reg [31:0] w_sr [0:15];

    //------------------------------------------------------------------------
    // Helper function: Rotate Left
    //------------------------------------------------------------------------
    function [31:0] rol;
        input [31:0] x;
        input [4:0]  n;
        begin
            rol = (x << n) | (x >> (32 - n));
        end
    endfunction

    //------------------------------------------------------------------------
    // Helper function: P1 permutation
    // P1(X) = X ⊕ ROL(X, 15) ⊕ ROL(X, 23)
    //------------------------------------------------------------------------
    function [31:0] p1;
        input [31:0] x;
        begin
            p1 = x ^ rol(x, 15) ^ rol(x, 23);
        end
    endfunction

    //------------------------------------------------------------------------
    // Combinational output generation
    //------------------------------------------------------------------------
    always @(*) begin
        if (round_cnt < 16) begin
            // For rounds 0-15, W comes from the shift register (loaded from msg_block)
            w = w_sr[round_cnt];
        end else begin
            // For rounds 16-63, W has been computed in the previous cycle
            w = w_sr[0];
        end

        // W'_j = W_j ⊕ W_j+4
        if (round_cnt < 60) begin
            w_prime = w ^ w_sr[4];
        end else begin
            // For rounds 60-63, W_j+4 doesn't exist
            // Use 0 (unused in these rounds)
            w_prime = w ^ 32'h0;
        end
    end

    //------------------------------------------------------------------------
    // Sequential logic: Load and compute W values
    //------------------------------------------------------------------------
    integer i;
    reg [31:0] w_tmp;
    reg [31:0] w_next;

    always @(posedge clk) begin
        if (rst) begin
            // Reset: clear all shift register entries
            for (i = 0; i < 16; i = i + 1) begin
                w_sr[i] <= 32'h0;
            end
        end else if (load_en) begin
            // Load initial 16 words from msg_block (big-endian format)
            // msg_block[511:480] = W_0, msg_block[479:448] = W_1, ...
            for (i = 0; i < 16; i = i + 1) begin
                w_sr[i] <= msg_block[511 - i*32 -: 32];
            end
        end else if (calc_en && round_cnt < 63) begin
            // Compute and shift W values for next round
            if (round_cnt < 16) begin
                // Initial rounds: just shift, no computation needed
                // W values are already loaded
                for (i = 0; i < 15; i = i + 1) begin
                    w_sr[i] <= w_sr[i + 1];
                end
                w_sr[15] <= 32'h0; // Will be computed next cycle
            end else begin
                // Compute W_{round_cnt+1} = P1(W_{j-16} ⊕ W_{j-9} ⊕ ROL(W_{j-3}, 15))
                //                      ⊕ ROL(W_{j-13}, 7) ⊕ W_{j-6}
                // where j = round_cnt + 1
                w_tmp = w_sr[0] ^ w_sr[7] ^ rol(w_sr[13], 15);
                w_next = p1(w_tmp) ^ rol(w_sr[3], 7) ^ w_sr[10];

                // Shift register: insert new W_next, shift out oldest
                for (i = 0; i < 15; i = i + 1) begin
                    w_sr[i] <= w_sr[i + 1];
                end
                w_sr[15] <= w_next;
            end
        end
    end

endmodule
