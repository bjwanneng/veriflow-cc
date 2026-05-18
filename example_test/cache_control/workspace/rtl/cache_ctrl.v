// =============================================================================
// Module:     cache_ctrl
// Descriptor: 4-way set-associative write-back cache controller
//             64 sets, 128-bit cache lines, 22-bit tags
//             LRU replacement, write-allocate policy
// =============================================================================
`resetall
`timescale 1ns / 1ps
`default_nettype none

module cache_ctrl (
    input  wire         clk,
    input  wire         rst,
    input  wire [31:0]  addr,
    input  wire [31:0]  wdata,
    input  wire [3:0]   byte_en,
    input  wire         mem_read,
    input  wire         mem_write,
    output wire [31:0]  rdata,
    output wire         ready,
    output wire [31:0]  m_addr,
    output wire [127:0] m_wdata,
    output wire         m_rd_en,
    output wire         m_wr_en,
    input  wire [127:0] m_rdata
);

    // =========================================================================
    // FSM States
    // =========================================================================
    localparam [2:0] IDLE        = 3'd0;
    localparam [2:0] COMPARE_TAG = 3'd1;
    localparam [2:0] WRITE_BACK  = 3'd2;
    localparam [2:0] MEM_READ    = 3'd3;
    localparam [2:0] REFILL      = 3'd4;

    // =========================================================================
    // Storage Arrays
    // =========================================================================
    reg [127:0] data_array  [0:63][0:3];  // 64 sets x 4 ways x 128-bit lines
    reg [21:0]  tag_array   [0:63][0:3];  // 22-bit tags
    reg         valid_array [0:63][0:3];  // valid bits
    reg         dirty_array [0:63][0:3];  // dirty bits

    // LRU: 64 sets x 4 ways x 2-bit counters
    reg [1:0]   lru_cnt [0:63][0:3];

    // =========================================================================
    // Internal Registers (sequential)
    // =========================================================================
    reg [2:0]   state_reg;
    reg         ready_reg;
    reg [31:0]  rdata_reg;

    // Latched request
    reg [31:0]  req_addr_reg;
    reg [31:0]  req_wdata_reg;
    reg [3:0]   req_byte_en_reg;
    reg         req_is_read_reg;
    reg         req_is_write_reg;

    // Victim tracking
    reg [1:0]   victim_way_reg;

    // Counters for multi-cycle states
    reg         wb_cnt_reg;
    reg         rd_cnt_reg;

    // Pending cache line from memory
    reg [127:0] pending_line_reg;

    // Memory interface registers
    reg [31:0]  m_addr_reg;
    reg [127:0] m_wdata_reg;
    reg         m_rd_en_reg;
    reg         m_wr_en_reg;

    // =========================================================================
    // Combinational Signals
    // =========================================================================
    wire [5:0]   req_index    = req_addr_reg[9:4];
    wire [21:0]  req_tag      = req_addr_reg[31:10];
    wire [1:0]   word_idx     = req_addr_reg[3:2];

    // Hit detection
    reg         hit;
    reg [1:0]   hit_way;

    // Victim selection (LRU)
    reg [1:0]   victim_way_next;

    // Write-back address composition
    wire [5:0]   wb_index     = req_index;
    wire [21:0]  wb_tag       = tag_array[req_index][victim_way_reg];
    wire [31:0]  wb_addr      = {wb_tag, wb_index, 4'b0000};

    // Word extraction helpers (combinational)
    wire [127:0] word_merge_mask;
    wire [127:0] word_shifted;
    wire [31:0]  extracted_word;

    // Combinational word select: MSB-first
    // word_idx 0 -> [127:96], 1 -> [95:64], 2 -> [63:32], 3 -> [31:0]
    assign extracted_word = (word_idx == 2'd0) ? pending_line_reg[127:96] :
                            (word_idx == 2'd1) ? pending_line_reg[95:64]  :
                            (word_idx == 2'd2) ? pending_line_reg[63:32]  :
                                                 pending_line_reg[31:0];

    // Merge mask for write into 128-bit line
    assign word_merge_mask = (word_idx == 2'd0) ? 128'hFFFFFFFF_00000000_00000000_00000000 :
                             (word_idx == 2'd1) ? 128'h00000000_FFFFFFFF_00000000_00000000 :
                             (word_idx == 2'd2) ? 128'h00000000_00000000_FFFFFFFF_00000000 :
                                                  128'h00000000_00000000_00000000_FFFFFFFF;

    assign word_shifted    = (word_idx == 2'd0) ? {req_wdata_reg, 96'd0} :
                             (word_idx == 2'd1) ? {32'd0, req_wdata_reg, 64'd0} :
                             (word_idx == 2'd2) ? {64'd0, req_wdata_reg, 32'd0} :
                                                  {96'd0, req_wdata_reg};

    // =========================================================================
    // Combinational: Hit Detection & Victim Selection
    // =========================================================================
    always @(*) begin
        hit     = 1'b0;
        hit_way = 2'd0;
        victim_way_next = 2'd0;

        // Check all 4 ways for a tag match (valid + tag compare)
        if (valid_array[req_index][0] && (tag_array[req_index][0] == req_tag)) begin
            hit     = 1'b1;
            hit_way = 2'd0;
        end else if (valid_array[req_index][1] && (tag_array[req_index][1] == req_tag)) begin
            hit     = 1'b1;
            hit_way = 2'd1;
        end else if (valid_array[req_index][2] && (tag_array[req_index][2] == req_tag)) begin
            hit     = 1'b1;
            hit_way = 2'd2;
        end else if (valid_array[req_index][3] && (tag_array[req_index][3] == req_tag)) begin
            hit     = 1'b1;
            hit_way = 2'd3;
        end

        // LRU victim: first way with counter == 0
        if (lru_cnt[req_index][0] == 2'd0)
            victim_way_next = 2'd0;
        else if (lru_cnt[req_index][1] == 2'd0)
            victim_way_next = 2'd1;
        else if (lru_cnt[req_index][2] == 2'd0)
            victim_way_next = 2'd2;
        else
            victim_way_next = 2'd3;
    end

    // =========================================================================
    // Sequential Logic (single always block)
    // =========================================================================
    always @(posedge clk) begin
        if (rst) begin
            // FSM state
            state_reg       <= IDLE;
            ready_reg       <= 1'b1;
            rdata_reg       <= 32'd0;

            // Latched request
            req_addr_reg    <= 32'd0;
            req_wdata_reg   <= 32'd0;
            req_byte_en_reg <= 4'd0;
            req_is_read_reg <= 1'b0;
            req_is_write_reg<= 1'b0;

            // Victim tracking
            victim_way_reg  <= 2'd0;

            // Counters
            wb_cnt_reg      <= 1'b0;
            rd_cnt_reg      <= 1'b0;

            // Pending line
            pending_line_reg<= 128'd0;

            // Memory interface
            m_addr_reg      <= 32'd0;
            m_wdata_reg     <= 128'd0;
            m_rd_en_reg     <= 1'b0;
            m_wr_en_reg     <= 1'b0;

            // Clear valid and dirty arrays
            valid_array[0][0]  <= 1'b0; valid_array[0][1]  <= 1'b0;
            valid_array[0][2]  <= 1'b0; valid_array[0][3]  <= 1'b0;
            valid_array[1][0]  <= 1'b0; valid_array[1][1]  <= 1'b0;
            valid_array[1][2]  <= 1'b0; valid_array[1][3]  <= 1'b0;
            valid_array[2][0]  <= 1'b0; valid_array[2][1]  <= 1'b0;
            valid_array[2][2]  <= 1'b0; valid_array[2][3]  <= 1'b0;
            valid_array[3][0]  <= 1'b0; valid_array[3][1]  <= 1'b0;
            valid_array[3][2]  <= 1'b0; valid_array[3][3]  <= 1'b0;
            valid_array[4][0]  <= 1'b0; valid_array[4][1]  <= 1'b0;
            valid_array[4][2]  <= 1'b0; valid_array[4][3]  <= 1'b0;
            valid_array[5][0]  <= 1'b0; valid_array[5][1]  <= 1'b0;
            valid_array[5][2]  <= 1'b0; valid_array[5][3]  <= 1'b0;
            valid_array[6][0]  <= 1'b0; valid_array[6][1]  <= 1'b0;
            valid_array[6][2]  <= 1'b0; valid_array[6][3]  <= 1'b0;
            valid_array[7][0]  <= 1'b0; valid_array[7][1]  <= 1'b0;
            valid_array[7][2]  <= 1'b0; valid_array[7][3]  <= 1'b0;
            valid_array[8][0]  <= 1'b0; valid_array[8][1]  <= 1'b0;
            valid_array[8][2]  <= 1'b0; valid_array[8][3]  <= 1'b0;
            valid_array[9][0]  <= 1'b0; valid_array[9][1]  <= 1'b0;
            valid_array[9][2]  <= 1'b0; valid_array[9][3]  <= 1'b0;
            valid_array[10][0] <= 1'b0; valid_array[10][1] <= 1'b0;
            valid_array[10][2] <= 1'b0; valid_array[10][3] <= 1'b0;
            valid_array[11][0] <= 1'b0; valid_array[11][1] <= 1'b0;
            valid_array[11][2] <= 1'b0; valid_array[11][3] <= 1'b0;
            valid_array[12][0] <= 1'b0; valid_array[12][1] <= 1'b0;
            valid_array[12][2] <= 1'b0; valid_array[12][3] <= 1'b0;
            valid_array[13][0] <= 1'b0; valid_array[13][1] <= 1'b0;
            valid_array[13][2] <= 1'b0; valid_array[13][3] <= 1'b0;
            valid_array[14][0] <= 1'b0; valid_array[14][1] <= 1'b0;
            valid_array[14][2] <= 1'b0; valid_array[14][3] <= 1'b0;
            valid_array[15][0] <= 1'b0; valid_array[15][1] <= 1'b0;
            valid_array[15][2] <= 1'b0; valid_array[15][3] <= 1'b0;
            valid_array[16][0] <= 1'b0; valid_array[16][1] <= 1'b0;
            valid_array[16][2] <= 1'b0; valid_array[16][3] <= 1'b0;
            valid_array[17][0] <= 1'b0; valid_array[17][1] <= 1'b0;
            valid_array[17][2] <= 1'b0; valid_array[17][3] <= 1'b0;
            valid_array[18][0] <= 1'b0; valid_array[18][1] <= 1'b0;
            valid_array[18][2] <= 1'b0; valid_array[18][3] <= 1'b0;
            valid_array[19][0] <= 1'b0; valid_array[19][1] <= 1'b0;
            valid_array[19][2] <= 1'b0; valid_array[19][3] <= 1'b0;
            valid_array[20][0] <= 1'b0; valid_array[20][1] <= 1'b0;
            valid_array[20][2] <= 1'b0; valid_array[20][3] <= 1'b0;
            valid_array[21][0] <= 1'b0; valid_array[21][1] <= 1'b0;
            valid_array[21][2] <= 1'b0; valid_array[21][3] <= 1'b0;
            valid_array[22][0] <= 1'b0; valid_array[22][1] <= 1'b0;
            valid_array[22][2] <= 1'b0; valid_array[22][3] <= 1'b0;
            valid_array[23][0] <= 1'b0; valid_array[23][1] <= 1'b0;
            valid_array[23][2] <= 1'b0; valid_array[23][3] <= 1'b0;
            valid_array[24][0] <= 1'b0; valid_array[24][1] <= 1'b0;
            valid_array[24][2] <= 1'b0; valid_array[24][3] <= 1'b0;
            valid_array[25][0] <= 1'b0; valid_array[25][1] <= 1'b0;
            valid_array[25][2] <= 1'b0; valid_array[25][3] <= 1'b0;
            valid_array[26][0] <= 1'b0; valid_array[26][1] <= 1'b0;
            valid_array[26][2] <= 1'b0; valid_array[26][3] <= 1'b0;
            valid_array[27][0] <= 1'b0; valid_array[27][1] <= 1'b0;
            valid_array[27][2] <= 1'b0; valid_array[27][3] <= 1'b0;
            valid_array[28][0] <= 1'b0; valid_array[28][1] <= 1'b0;
            valid_array[28][2] <= 1'b0; valid_array[28][3] <= 1'b0;
            valid_array[29][0] <= 1'b0; valid_array[29][1] <= 1'b0;
            valid_array[29][2] <= 1'b0; valid_array[29][3] <= 1'b0;
            valid_array[30][0] <= 1'b0; valid_array[30][1] <= 1'b0;
            valid_array[30][2] <= 1'b0; valid_array[30][3] <= 1'b0;
            valid_array[31][0] <= 1'b0; valid_array[31][1] <= 1'b0;
            valid_array[31][2] <= 1'b0; valid_array[31][3] <= 1'b0;
            valid_array[32][0] <= 1'b0; valid_array[32][1] <= 1'b0;
            valid_array[32][2] <= 1'b0; valid_array[32][3] <= 1'b0;
            valid_array[33][0] <= 1'b0; valid_array[33][1] <= 1'b0;
            valid_array[33][2] <= 1'b0; valid_array[33][3] <= 1'b0;
            valid_array[34][0] <= 1'b0; valid_array[34][1] <= 1'b0;
            valid_array[34][2] <= 1'b0; valid_array[34][3] <= 1'b0;
            valid_array[35][0] <= 1'b0; valid_array[35][1] <= 1'b0;
            valid_array[35][2] <= 1'b0; valid_array[35][3] <= 1'b0;
            valid_array[36][0] <= 1'b0; valid_array[36][1] <= 1'b0;
            valid_array[36][2] <= 1'b0; valid_array[36][3] <= 1'b0;
            valid_array[37][0] <= 1'b0; valid_array[37][1] <= 1'b0;
            valid_array[37][2] <= 1'b0; valid_array[37][3] <= 1'b0;
            valid_array[38][0] <= 1'b0; valid_array[38][1] <= 1'b0;
            valid_array[38][2] <= 1'b0; valid_array[38][3] <= 1'b0;
            valid_array[39][0] <= 1'b0; valid_array[39][1] <= 1'b0;
            valid_array[39][2] <= 1'b0; valid_array[39][3] <= 1'b0;
            valid_array[40][0] <= 1'b0; valid_array[40][1] <= 1'b0;
            valid_array[40][2] <= 1'b0; valid_array[40][3] <= 1'b0;
            valid_array[41][0] <= 1'b0; valid_array[41][1] <= 1'b0;
            valid_array[41][2] <= 1'b0; valid_array[41][3] <= 1'b0;
            valid_array[42][0] <= 1'b0; valid_array[42][1] <= 1'b0;
            valid_array[42][2] <= 1'b0; valid_array[42][3] <= 1'b0;
            valid_array[43][0] <= 1'b0; valid_array[43][1] <= 1'b0;
            valid_array[43][2] <= 1'b0; valid_array[43][3] <= 1'b0;
            valid_array[44][0] <= 1'b0; valid_array[44][1] <= 1'b0;
            valid_array[44][2] <= 1'b0; valid_array[44][3] <= 1'b0;
            valid_array[45][0] <= 1'b0; valid_array[45][1] <= 1'b0;
            valid_array[45][2] <= 1'b0; valid_array[45][3] <= 1'b0;
            valid_array[46][0] <= 1'b0; valid_array[46][1] <= 1'b0;
            valid_array[46][2] <= 1'b0; valid_array[46][3] <= 1'b0;
            valid_array[47][0] <= 1'b0; valid_array[47][1] <= 1'b0;
            valid_array[47][2] <= 1'b0; valid_array[47][3] <= 1'b0;
            valid_array[48][0] <= 1'b0; valid_array[48][1] <= 1'b0;
            valid_array[48][2] <= 1'b0; valid_array[48][3] <= 1'b0;
            valid_array[49][0] <= 1'b0; valid_array[49][1] <= 1'b0;
            valid_array[49][2] <= 1'b0; valid_array[49][3] <= 1'b0;
            valid_array[50][0] <= 1'b0; valid_array[50][1] <= 1'b0;
            valid_array[50][2] <= 1'b0; valid_array[50][3] <= 1'b0;
            valid_array[51][0] <= 1'b0; valid_array[51][1] <= 1'b0;
            valid_array[51][2] <= 1'b0; valid_array[51][3] <= 1'b0;
            valid_array[52][0] <= 1'b0; valid_array[52][1] <= 1'b0;
            valid_array[52][2] <= 1'b0; valid_array[52][3] <= 1'b0;
            valid_array[53][0] <= 1'b0; valid_array[53][1] <= 1'b0;
            valid_array[53][2] <= 1'b0; valid_array[53][3] <= 1'b0;
            valid_array[54][0] <= 1'b0; valid_array[54][1] <= 1'b0;
            valid_array[54][2] <= 1'b0; valid_array[54][3] <= 1'b0;
            valid_array[55][0] <= 1'b0; valid_array[55][1] <= 1'b0;
            valid_array[55][2] <= 1'b0; valid_array[55][3] <= 1'b0;
            valid_array[56][0] <= 1'b0; valid_array[56][1] <= 1'b0;
            valid_array[56][2] <= 1'b0; valid_array[56][3] <= 1'b0;
            valid_array[57][0] <= 1'b0; valid_array[57][1] <= 1'b0;
            valid_array[57][2] <= 1'b0; valid_array[57][3] <= 1'b0;
            valid_array[58][0] <= 1'b0; valid_array[58][1] <= 1'b0;
            valid_array[58][2] <= 1'b0; valid_array[58][3] <= 1'b0;
            valid_array[59][0] <= 1'b0; valid_array[59][1] <= 1'b0;
            valid_array[59][2] <= 1'b0; valid_array[59][3] <= 1'b0;
            valid_array[60][0] <= 1'b0; valid_array[60][1] <= 1'b0;
            valid_array[60][2] <= 1'b0; valid_array[60][3] <= 1'b0;
            valid_array[61][0] <= 1'b0; valid_array[61][1] <= 1'b0;
            valid_array[61][2] <= 1'b0; valid_array[61][3] <= 1'b0;
            valid_array[62][0] <= 1'b0; valid_array[62][1] <= 1'b0;
            valid_array[62][2] <= 1'b0; valid_array[62][3] <= 1'b0;
            valid_array[63][0] <= 1'b0; valid_array[63][1] <= 1'b0;
            valid_array[63][2] <= 1'b0; valid_array[63][3] <= 1'b0;

            dirty_array[0][0]  <= 1'b0; dirty_array[0][1]  <= 1'b0;
            dirty_array[0][2]  <= 1'b0; dirty_array[0][3]  <= 1'b0;
            dirty_array[1][0]  <= 1'b0; dirty_array[1][1]  <= 1'b0;
            dirty_array[1][2]  <= 1'b0; dirty_array[1][3]  <= 1'b0;
            dirty_array[2][0]  <= 1'b0; dirty_array[2][1]  <= 1'b0;
            dirty_array[2][2]  <= 1'b0; dirty_array[2][3]  <= 1'b0;
            dirty_array[3][0]  <= 1'b0; dirty_array[3][1]  <= 1'b0;
            dirty_array[3][2]  <= 1'b0; dirty_array[3][3]  <= 1'b0;
            dirty_array[4][0]  <= 1'b0; dirty_array[4][1]  <= 1'b0;
            dirty_array[4][2]  <= 1'b0; dirty_array[4][3]  <= 1'b0;
            dirty_array[5][0]  <= 1'b0; dirty_array[5][1]  <= 1'b0;
            dirty_array[5][2]  <= 1'b0; dirty_array[5][3]  <= 1'b0;
            dirty_array[6][0]  <= 1'b0; dirty_array[6][1]  <= 1'b0;
            dirty_array[6][2]  <= 1'b0; dirty_array[6][3]  <= 1'b0;
            dirty_array[7][0]  <= 1'b0; dirty_array[7][1]  <= 1'b0;
            dirty_array[7][2]  <= 1'b0; dirty_array[7][3]  <= 1'b0;
            dirty_array[8][0]  <= 1'b0; dirty_array[8][1]  <= 1'b0;
            dirty_array[8][2]  <= 1'b0; dirty_array[8][3]  <= 1'b0;
            dirty_array[9][0]  <= 1'b0; dirty_array[9][1]  <= 1'b0;
            dirty_array[9][2]  <= 1'b0; dirty_array[9][3]  <= 1'b0;
            dirty_array[10][0] <= 1'b0; dirty_array[10][1] <= 1'b0;
            dirty_array[10][2] <= 1'b0; dirty_array[10][3] <= 1'b0;
            dirty_array[11][0] <= 1'b0; dirty_array[11][1] <= 1'b0;
            dirty_array[11][2] <= 1'b0; dirty_array[11][3] <= 1'b0;
            dirty_array[12][0] <= 1'b0; dirty_array[12][1] <= 1'b0;
            dirty_array[12][2] <= 1'b0; dirty_array[12][3] <= 1'b0;
            dirty_array[13][0] <= 1'b0; dirty_array[13][1] <= 1'b0;
            dirty_array[13][2] <= 1'b0; dirty_array[13][3] <= 1'b0;
            dirty_array[14][0] <= 1'b0; dirty_array[14][1] <= 1'b0;
            dirty_array[14][2] <= 1'b0; dirty_array[14][3] <= 1'b0;
            dirty_array[15][0] <= 1'b0; dirty_array[15][1] <= 1'b0;
            dirty_array[15][2] <= 1'b0; dirty_array[15][3] <= 1'b0;
            dirty_array[16][0] <= 1'b0; dirty_array[16][1] <= 1'b0;
            dirty_array[16][2] <= 1'b0; dirty_array[16][3] <= 1'b0;
            dirty_array[17][0] <= 1'b0; dirty_array[17][1] <= 1'b0;
            dirty_array[17][2] <= 1'b0; dirty_array[17][3] <= 1'b0;
            dirty_array[18][0] <= 1'b0; dirty_array[18][1] <= 1'b0;
            dirty_array[18][2] <= 1'b0; dirty_array[18][3] <= 1'b0;
            dirty_array[19][0] <= 1'b0; dirty_array[19][1] <= 1'b0;
            dirty_array[19][2] <= 1'b0; dirty_array[19][3] <= 1'b0;
            dirty_array[20][0] <= 1'b0; dirty_array[20][1] <= 1'b0;
            dirty_array[20][2] <= 1'b0; dirty_array[20][3] <= 1'b0;
            dirty_array[21][0] <= 1'b0; dirty_array[21][1] <= 1'b0;
            dirty_array[21][2] <= 1'b0; dirty_array[21][3] <= 1'b0;
            dirty_array[22][0] <= 1'b0; dirty_array[22][1] <= 1'b0;
            dirty_array[22][2] <= 1'b0; dirty_array[22][3] <= 1'b0;
            dirty_array[23][0] <= 1'b0; dirty_array[23][1] <= 1'b0;
            dirty_array[23][2] <= 1'b0; dirty_array[23][3] <= 1'b0;
            dirty_array[24][0] <= 1'b0; dirty_array[24][1] <= 1'b0;
            dirty_array[24][2] <= 1'b0; dirty_array[24][3] <= 1'b0;
            dirty_array[25][0] <= 1'b0; dirty_array[25][1] <= 1'b0;
            dirty_array[25][2] <= 1'b0; dirty_array[25][3] <= 1'b0;
            dirty_array[26][0] <= 1'b0; dirty_array[26][1] <= 1'b0;
            dirty_array[26][2] <= 1'b0; dirty_array[26][3] <= 1'b0;
            dirty_array[27][0] <= 1'b0; dirty_array[27][1] <= 1'b0;
            dirty_array[27][2] <= 1'b0; dirty_array[27][3] <= 1'b0;
            dirty_array[28][0] <= 1'b0; dirty_array[28][1] <= 1'b0;
            dirty_array[28][2] <= 1'b0; dirty_array[28][3] <= 1'b0;
            dirty_array[29][0] <= 1'b0; dirty_array[29][1] <= 1'b0;
            dirty_array[29][2] <= 1'b0; dirty_array[29][3] <= 1'b0;
            dirty_array[30][0] <= 1'b0; dirty_array[30][1] <= 1'b0;
            dirty_array[30][2] <= 1'b0; dirty_array[30][3] <= 1'b0;
            dirty_array[31][0] <= 1'b0; dirty_array[31][1] <= 1'b0;
            dirty_array[31][2] <= 1'b0; dirty_array[31][3] <= 1'b0;
            dirty_array[32][0] <= 1'b0; dirty_array[32][1] <= 1'b0;
            dirty_array[32][2] <= 1'b0; dirty_array[32][3] <= 1'b0;
            dirty_array[33][0] <= 1'b0; dirty_array[33][1] <= 1'b0;
            dirty_array[33][2] <= 1'b0; dirty_array[33][3] <= 1'b0;
            dirty_array[34][0] <= 1'b0; dirty_array[34][1] <= 1'b0;
            dirty_array[34][2] <= 1'b0; dirty_array[34][3] <= 1'b0;
            dirty_array[35][0] <= 1'b0; dirty_array[35][1] <= 1'b0;
            dirty_array[35][2] <= 1'b0; dirty_array[35][3] <= 1'b0;
            dirty_array[36][0] <= 1'b0; dirty_array[36][1] <= 1'b0;
            dirty_array[36][2] <= 1'b0; dirty_array[36][3] <= 1'b0;
            dirty_array[37][0] <= 1'b0; dirty_array[37][1] <= 1'b0;
            dirty_array[37][2] <= 1'b0; dirty_array[37][3] <= 1'b0;
            dirty_array[38][0] <= 1'b0; dirty_array[38][1] <= 1'b0;
            dirty_array[38][2] <= 1'b0; dirty_array[38][3] <= 1'b0;
            dirty_array[39][0] <= 1'b0; dirty_array[39][1] <= 1'b0;
            dirty_array[39][2] <= 1'b0; dirty_array[39][3] <= 1'b0;
            dirty_array[40][0] <= 1'b0; dirty_array[40][1] <= 1'b0;
            dirty_array[40][2] <= 1'b0; dirty_array[40][3] <= 1'b0;
            dirty_array[41][0] <= 1'b0; dirty_array[41][1] <= 1'b0;
            dirty_array[41][2] <= 1'b0; dirty_array[41][3] <= 1'b0;
            dirty_array[42][0] <= 1'b0; dirty_array[42][1] <= 1'b0;
            dirty_array[42][2] <= 1'b0; dirty_array[42][3] <= 1'b0;
            dirty_array[43][0] <= 1'b0; dirty_array[43][1] <= 1'b0;
            dirty_array[43][2] <= 1'b0; dirty_array[43][3] <= 1'b0;
            dirty_array[44][0] <= 1'b0; dirty_array[44][1] <= 1'b0;
            dirty_array[44][2] <= 1'b0; dirty_array[44][3] <= 1'b0;
            dirty_array[45][0] <= 1'b0; dirty_array[45][1] <= 1'b0;
            dirty_array[45][2] <= 1'b0; dirty_array[45][3] <= 1'b0;
            dirty_array[46][0] <= 1'b0; dirty_array[46][1] <= 1'b0;
            dirty_array[46][2] <= 1'b0; dirty_array[46][3] <= 1'b0;
            dirty_array[47][0] <= 1'b0; dirty_array[47][1] <= 1'b0;
            dirty_array[47][2] <= 1'b0; dirty_array[47][3] <= 1'b0;
            dirty_array[48][0] <= 1'b0; dirty_array[48][1] <= 1'b0;
            dirty_array[48][2] <= 1'b0; dirty_array[48][3] <= 1'b0;
            dirty_array[49][0] <= 1'b0; dirty_array[49][1] <= 1'b0;
            dirty_array[49][2] <= 1'b0; dirty_array[49][3] <= 1'b0;
            dirty_array[50][0] <= 1'b0; dirty_array[50][1] <= 1'b0;
            dirty_array[50][2] <= 1'b0; dirty_array[50][3] <= 1'b0;
            dirty_array[51][0] <= 1'b0; dirty_array[51][1] <= 1'b0;
            dirty_array[51][2] <= 1'b0; dirty_array[51][3] <= 1'b0;
            dirty_array[52][0] <= 1'b0; dirty_array[52][1] <= 1'b0;
            dirty_array[52][2] <= 1'b0; dirty_array[52][3] <= 1'b0;
            dirty_array[53][0] <= 1'b0; dirty_array[53][1] <= 1'b0;
            dirty_array[53][2] <= 1'b0; dirty_array[53][3] <= 1'b0;
            dirty_array[54][0] <= 1'b0; dirty_array[54][1] <= 1'b0;
            dirty_array[54][2] <= 1'b0; dirty_array[54][3] <= 1'b0;
            dirty_array[55][0] <= 1'b0; dirty_array[55][1] <= 1'b0;
            dirty_array[55][2] <= 1'b0; dirty_array[55][3] <= 1'b0;
            dirty_array[56][0] <= 1'b0; dirty_array[56][1] <= 1'b0;
            dirty_array[56][2] <= 1'b0; dirty_array[56][3] <= 1'b0;
            dirty_array[57][0] <= 1'b0; dirty_array[57][1] <= 1'b0;
            dirty_array[57][2] <= 1'b0; dirty_array[57][3] <= 1'b0;
            dirty_array[58][0] <= 1'b0; dirty_array[58][1] <= 1'b0;
            dirty_array[58][2] <= 1'b0; dirty_array[58][3] <= 1'b0;
            dirty_array[59][0] <= 1'b0; dirty_array[59][1] <= 1'b0;
            dirty_array[59][2] <= 1'b0; dirty_array[59][3] <= 1'b0;
            dirty_array[60][0] <= 1'b0; dirty_array[60][1] <= 1'b0;
            dirty_array[60][2] <= 1'b0; dirty_array[60][3] <= 1'b0;
            dirty_array[61][0] <= 1'b0; dirty_array[61][1] <= 1'b0;
            dirty_array[61][2] <= 1'b0; dirty_array[61][3] <= 1'b0;
            dirty_array[62][0] <= 1'b0; dirty_array[62][1] <= 1'b0;
            dirty_array[62][2] <= 1'b0; dirty_array[62][3] <= 1'b0;
            dirty_array[63][0] <= 1'b0; dirty_array[63][1] <= 1'b0;
            dirty_array[63][2] <= 1'b0; dirty_array[63][3] <= 1'b0;

            // Initialize LRU counters to 0-1-2-3 so victim order starts at way 0
            lru_cnt[0][0]  <= 2'd0; lru_cnt[0][1]  <= 2'd1;
            lru_cnt[0][2]  <= 2'd2; lru_cnt[0][3]  <= 2'd3;
            lru_cnt[1][0]  <= 2'd0; lru_cnt[1][1]  <= 2'd1;
            lru_cnt[1][2]  <= 2'd2; lru_cnt[1][3]  <= 2'd3;
            lru_cnt[2][0]  <= 2'd0; lru_cnt[2][1]  <= 2'd1;
            lru_cnt[2][2]  <= 2'd2; lru_cnt[2][3]  <= 2'd3;
            lru_cnt[3][0]  <= 2'd0; lru_cnt[3][1]  <= 2'd1;
            lru_cnt[3][2]  <= 2'd2; lru_cnt[3][3]  <= 2'd3;
            lru_cnt[4][0]  <= 2'd0; lru_cnt[4][1]  <= 2'd1;
            lru_cnt[4][2]  <= 2'd2; lru_cnt[4][3]  <= 2'd3;
            lru_cnt[5][0]  <= 2'd0; lru_cnt[5][1]  <= 2'd1;
            lru_cnt[5][2]  <= 2'd2; lru_cnt[5][3]  <= 2'd3;
            lru_cnt[6][0]  <= 2'd0; lru_cnt[6][1]  <= 2'd1;
            lru_cnt[6][2]  <= 2'd2; lru_cnt[6][3]  <= 2'd3;
            lru_cnt[7][0]  <= 2'd0; lru_cnt[7][1]  <= 2'd1;
            lru_cnt[7][2]  <= 2'd2; lru_cnt[7][3]  <= 2'd3;
            lru_cnt[8][0]  <= 2'd0; lru_cnt[8][1]  <= 2'd1;
            lru_cnt[8][2]  <= 2'd2; lru_cnt[8][3]  <= 2'd3;
            lru_cnt[9][0]  <= 2'd0; lru_cnt[9][1]  <= 2'd1;
            lru_cnt[9][2]  <= 2'd2; lru_cnt[9][3]  <= 2'd3;
            lru_cnt[10][0] <= 2'd0; lru_cnt[10][1] <= 2'd1;
            lru_cnt[10][2] <= 2'd2; lru_cnt[10][3] <= 2'd3;
            lru_cnt[11][0] <= 2'd0; lru_cnt[11][1] <= 2'd1;
            lru_cnt[11][2] <= 2'd2; lru_cnt[11][3] <= 2'd3;
            lru_cnt[12][0] <= 2'd0; lru_cnt[12][1] <= 2'd1;
            lru_cnt[12][2] <= 2'd2; lru_cnt[12][3] <= 2'd3;
            lru_cnt[13][0] <= 2'd0; lru_cnt[13][1] <= 2'd1;
            lru_cnt[13][2] <= 2'd2; lru_cnt[13][3] <= 2'd3;
            lru_cnt[14][0] <= 2'd0; lru_cnt[14][1] <= 2'd1;
            lru_cnt[14][2] <= 2'd2; lru_cnt[14][3] <= 2'd3;
            lru_cnt[15][0] <= 2'd0; lru_cnt[15][1] <= 2'd1;
            lru_cnt[15][2] <= 2'd2; lru_cnt[15][3] <= 2'd3;
            lru_cnt[16][0] <= 2'd0; lru_cnt[16][1] <= 2'd1;
            lru_cnt[16][2] <= 2'd2; lru_cnt[16][3] <= 2'd3;
            lru_cnt[17][0] <= 2'd0; lru_cnt[17][1] <= 2'd1;
            lru_cnt[17][2] <= 2'd2; lru_cnt[17][3] <= 2'd3;
            lru_cnt[18][0] <= 2'd0; lru_cnt[18][1] <= 2'd1;
            lru_cnt[18][2] <= 2'd2; lru_cnt[18][3] <= 2'd3;
            lru_cnt[19][0] <= 2'd0; lru_cnt[19][1] <= 2'd1;
            lru_cnt[19][2] <= 2'd2; lru_cnt[19][3] <= 2'd3;
            lru_cnt[20][0] <= 2'd0; lru_cnt[20][1] <= 2'd1;
            lru_cnt[20][2] <= 2'd2; lru_cnt[20][3] <= 2'd3;
            lru_cnt[21][0] <= 2'd0; lru_cnt[21][1] <= 2'd1;
            lru_cnt[21][2] <= 2'd2; lru_cnt[21][3] <= 2'd3;
            lru_cnt[22][0] <= 2'd0; lru_cnt[22][1] <= 2'd1;
            lru_cnt[22][2] <= 2'd2; lru_cnt[22][3] <= 2'd3;
            lru_cnt[23][0] <= 2'd0; lru_cnt[23][1] <= 2'd1;
            lru_cnt[23][2] <= 2'd2; lru_cnt[23][3] <= 2'd3;
            lru_cnt[24][0] <= 2'd0; lru_cnt[24][1] <= 2'd1;
            lru_cnt[24][2] <= 2'd2; lru_cnt[24][3] <= 2'd3;
            lru_cnt[25][0] <= 2'd0; lru_cnt[25][1] <= 2'd1;
            lru_cnt[25][2] <= 2'd2; lru_cnt[25][3] <= 2'd3;
            lru_cnt[26][0] <= 2'd0; lru_cnt[26][1] <= 2'd1;
            lru_cnt[26][2] <= 2'd2; lru_cnt[26][3] <= 2'd3;
            lru_cnt[27][0] <= 2'd0; lru_cnt[27][1] <= 2'd1;
            lru_cnt[27][2] <= 2'd2; lru_cnt[27][3] <= 2'd3;
            lru_cnt[28][0] <= 2'd0; lru_cnt[28][1] <= 2'd1;
            lru_cnt[28][2] <= 2'd2; lru_cnt[28][3] <= 2'd3;
            lru_cnt[29][0] <= 2'd0; lru_cnt[29][1] <= 2'd1;
            lru_cnt[29][2] <= 2'd2; lru_cnt[29][3] <= 2'd3;
            lru_cnt[30][0] <= 2'd0; lru_cnt[30][1] <= 2'd1;
            lru_cnt[30][2] <= 2'd2; lru_cnt[30][3] <= 2'd3;
            lru_cnt[31][0] <= 2'd0; lru_cnt[31][1] <= 2'd1;
            lru_cnt[31][2] <= 2'd2; lru_cnt[31][3] <= 2'd3;
            lru_cnt[32][0] <= 2'd0; lru_cnt[32][1] <= 2'd1;
            lru_cnt[32][2] <= 2'd2; lru_cnt[32][3] <= 2'd3;
            lru_cnt[33][0] <= 2'd0; lru_cnt[33][1] <= 2'd1;
            lru_cnt[33][2] <= 2'd2; lru_cnt[33][3] <= 2'd3;
            lru_cnt[34][0] <= 2'd0; lru_cnt[34][1] <= 2'd1;
            lru_cnt[34][2] <= 2'd2; lru_cnt[34][3] <= 2'd3;
            lru_cnt[35][0] <= 2'd0; lru_cnt[35][1] <= 2'd1;
            lru_cnt[35][2] <= 2'd2; lru_cnt[35][3] <= 2'd3;
            lru_cnt[36][0] <= 2'd0; lru_cnt[36][1] <= 2'd1;
            lru_cnt[36][2] <= 2'd2; lru_cnt[36][3] <= 2'd3;
            lru_cnt[37][0] <= 2'd0; lru_cnt[37][1] <= 2'd1;
            lru_cnt[37][2] <= 2'd2; lru_cnt[37][3] <= 2'd3;
            lru_cnt[38][0] <= 2'd0; lru_cnt[38][1] <= 2'd1;
            lru_cnt[38][2] <= 2'd2; lru_cnt[38][3] <= 2'd3;
            lru_cnt[39][0] <= 2'd0; lru_cnt[39][1] <= 2'd1;
            lru_cnt[39][2] <= 2'd2; lru_cnt[39][3] <= 2'd3;
            lru_cnt[40][0] <= 2'd0; lru_cnt[40][1] <= 2'd1;
            lru_cnt[40][2] <= 2'd2; lru_cnt[40][3] <= 2'd3;
            lru_cnt[41][0] <= 2'd0; lru_cnt[41][1] <= 2'd1;
            lru_cnt[41][2] <= 2'd2; lru_cnt[41][3] <= 2'd3;
            lru_cnt[42][0] <= 2'd0; lru_cnt[42][1] <= 2'd1;
            lru_cnt[42][2] <= 2'd2; lru_cnt[42][3] <= 2'd3;
            lru_cnt[43][0] <= 2'd0; lru_cnt[43][1] <= 2'd1;
            lru_cnt[43][2] <= 2'd2; lru_cnt[43][3] <= 2'd3;
            lru_cnt[44][0] <= 2'd0; lru_cnt[44][1] <= 2'd1;
            lru_cnt[44][2] <= 2'd2; lru_cnt[44][3] <= 2'd3;
            lru_cnt[45][0] <= 2'd0; lru_cnt[45][1] <= 2'd1;
            lru_cnt[45][2] <= 2'd2; lru_cnt[45][3] <= 2'd3;
            lru_cnt[46][0] <= 2'd0; lru_cnt[46][1] <= 2'd1;
            lru_cnt[46][2] <= 2'd2; lru_cnt[46][3] <= 2'd3;
            lru_cnt[47][0] <= 2'd0; lru_cnt[47][1] <= 2'd1;
            lru_cnt[47][2] <= 2'd2; lru_cnt[47][3] <= 2'd3;
            lru_cnt[48][0] <= 2'd0; lru_cnt[48][1] <= 2'd1;
            lru_cnt[48][2] <= 2'd2; lru_cnt[48][3] <= 2'd3;
            lru_cnt[49][0] <= 2'd0; lru_cnt[49][1] <= 2'd1;
            lru_cnt[49][2] <= 2'd2; lru_cnt[49][3] <= 2'd3;
            lru_cnt[50][0] <= 2'd0; lru_cnt[50][1] <= 2'd1;
            lru_cnt[50][2] <= 2'd2; lru_cnt[50][3] <= 2'd3;
            lru_cnt[51][0] <= 2'd0; lru_cnt[51][1] <= 2'd1;
            lru_cnt[51][2] <= 2'd2; lru_cnt[51][3] <= 2'd3;
            lru_cnt[52][0] <= 2'd0; lru_cnt[52][1] <= 2'd1;
            lru_cnt[52][2] <= 2'd2; lru_cnt[52][3] <= 2'd3;
            lru_cnt[53][0] <= 2'd0; lru_cnt[53][1] <= 2'd1;
            lru_cnt[53][2] <= 2'd2; lru_cnt[53][3] <= 2'd3;
            lru_cnt[54][0] <= 2'd0; lru_cnt[54][1] <= 2'd1;
            lru_cnt[54][2] <= 2'd2; lru_cnt[54][3] <= 2'd3;
            lru_cnt[55][0] <= 2'd0; lru_cnt[55][1] <= 2'd1;
            lru_cnt[55][2] <= 2'd2; lru_cnt[55][3] <= 2'd3;
            lru_cnt[56][0] <= 2'd0; lru_cnt[56][1] <= 2'd1;
            lru_cnt[56][2] <= 2'd2; lru_cnt[56][3] <= 2'd3;
            lru_cnt[57][0] <= 2'd0; lru_cnt[57][1] <= 2'd1;
            lru_cnt[57][2] <= 2'd2; lru_cnt[57][3] <= 2'd3;
            lru_cnt[58][0] <= 2'd0; lru_cnt[58][1] <= 2'd1;
            lru_cnt[58][2] <= 2'd2; lru_cnt[58][3] <= 2'd3;
            lru_cnt[59][0] <= 2'd0; lru_cnt[59][1] <= 2'd1;
            lru_cnt[59][2] <= 2'd2; lru_cnt[59][3] <= 2'd3;
            lru_cnt[60][0] <= 2'd0; lru_cnt[60][1] <= 2'd1;
            lru_cnt[60][2] <= 2'd2; lru_cnt[60][3] <= 2'd3;
            lru_cnt[61][0] <= 2'd0; lru_cnt[61][1] <= 2'd1;
            lru_cnt[61][2] <= 2'd2; lru_cnt[61][3] <= 2'd3;
            lru_cnt[62][0] <= 2'd0; lru_cnt[62][1] <= 2'd1;
            lru_cnt[62][2] <= 2'd2; lru_cnt[62][3] <= 2'd3;
            lru_cnt[63][0] <= 2'd0; lru_cnt[63][1] <= 2'd1;
            lru_cnt[63][2] <= 2'd2; lru_cnt[63][3] <= 2'd3;

        end else begin
            // Default: deassert memory interface each cycle
            m_rd_en_reg <= 1'b0;
            m_wr_en_reg <= 1'b0;

            case (state_reg)
                // ==============================================================
                // IDLE: Wait for request, latch inputs on mem_read|mem_write
                // ==============================================================
                IDLE: begin
                    ready_reg <= 1'b1;
                    if (mem_read | mem_write) begin
                        req_addr_reg    <= addr;
                        req_wdata_reg   <= wdata;
                        req_byte_en_reg <= byte_en;
                        req_is_read_reg <= mem_read;
                        req_is_write_reg<= mem_write;
                        ready_reg       <= 1'b0;
                        state_reg       <= COMPARE_TAG;
                    end
                end

                // ==============================================================
                // COMPARE_TAG: Tag lookup, hit/miss resolution
                // ==============================================================
                COMPARE_TAG: begin
                    if (hit) begin
                        // ----- HIT path -----
                        // LRU update: read old_val first, then update
                        begin : hit_lru_update
                            reg [1:0] old_val;
                            old_val = lru_cnt[req_index][hit_way];

                            lru_cnt[req_index][hit_way] <= 2'd3;

                            if ((hit_way != 2'd0) && (lru_cnt[req_index][2'd0] > old_val))
                                lru_cnt[req_index][2'd0] <= lru_cnt[req_index][2'd0] - 2'd1;
                            if ((hit_way != 2'd1) && (lru_cnt[req_index][2'd1] > old_val))
                                lru_cnt[req_index][2'd1] <= lru_cnt[req_index][2'd1] - 2'd1;
                            if ((hit_way != 2'd2) && (lru_cnt[req_index][2'd2] > old_val))
                                lru_cnt[req_index][2'd2] <= lru_cnt[req_index][2'd2] - 2'd1;
                            if ((hit_way != 2'd3) && (lru_cnt[req_index][2'd3] > old_val))
                                lru_cnt[req_index][2'd3] <= lru_cnt[req_index][2'd3] - 2'd1;
                        end

                        if (req_is_read_reg) begin
                            // Read hit: extract word
                            case (word_idx)
                                2'd0: rdata_reg <= data_array[req_index][hit_way][127:96];
                                2'd1: rdata_reg <= data_array[req_index][hit_way][95:64];
                                2'd2: rdata_reg <= data_array[req_index][hit_way][63:32];
                                2'd3: rdata_reg <= data_array[req_index][hit_way][31:0];
                                default: rdata_reg <= 32'd0;
                            endcase
                        end else begin
                            // Write hit: merge word, set dirty
                            rdata_reg <= 32'd0;
                            case (word_idx)
                                2'd0: data_array[req_index][hit_way][127:96] <= req_wdata_reg;
                                2'd1: data_array[req_index][hit_way][95:64]  <= req_wdata_reg;
                                2'd2: data_array[req_index][hit_way][63:32]  <= req_wdata_reg;
                                2'd3: data_array[req_index][hit_way][31:0]   <= req_wdata_reg;
                                default: ;
                            endcase
                            dirty_array[req_index][hit_way] <= 1'b1;
                        end

                        ready_reg <= 1'b1;
                        state_reg <= IDLE;
                    end else begin
                        // ----- MISS path -----
                        victim_way_reg <= victim_way_next;

                        if (valid_array[req_index][victim_way_next] &&
                            dirty_array[req_index][victim_way_next]) begin
                            // Dirty victim: need write-back first
                            state_reg <= WRITE_BACK;
                            wb_cnt_reg <= 1'b0;
                        end else begin
                            // Clean or invalid victim: go straight to memory read
                            state_reg <= MEM_READ;
                            rd_cnt_reg <= 1'b0;
                        end
                    end
                end

                // ==============================================================
                // WRITE_BACK: Evict dirty victim line to memory
                // ==============================================================
                WRITE_BACK: begin
                    case (wb_cnt_reg)
                        1'b0: begin
                            // Cycle 0: drive write-back address and data
                            m_addr_reg  <= {tag_array[req_index][victim_way_reg],
                                            req_index, 4'b0000};
                            m_wdata_reg <= data_array[req_index][victim_way_reg];
                            m_wr_en_reg <= 1'b1;
                            wb_cnt_reg  <= 1'b1;
                        end
                        1'b1: begin
                            // Cycle 1: clear interface, transition to MEM_READ
                            m_wr_en_reg <= 1'b0;
                            state_reg   <= MEM_READ;
                            rd_cnt_reg  <= 1'b0;
                        end
                        default: ;
                    endcase
                end

                // ==============================================================
                // MEM_READ: Fetch cache line from memory
                // ==============================================================
                MEM_READ: begin
                    case (rd_cnt_reg)
                        1'b0: begin
                            // Cycle 0: drive read address
                            m_addr_reg  <= {req_tag, req_index, 4'b0000};
                            m_rd_en_reg <= 1'b1;
                            rd_cnt_reg  <= 1'b1;
                        end
                        1'b1: begin
                            // Cycle 1: capture memory data, clear interface
                            pending_line_reg <= m_rdata;
                            m_rd_en_reg      <= 1'b0;
                            state_reg        <= REFILL;
                        end
                        default: ;
                    endcase
                end

                // ==============================================================
                // REFILL: Write fetched line into cache, complete the request
                // ==============================================================
                REFILL: begin
                    // Write the fetched line into the victim way
                    if (req_is_read_reg) begin
                        // Read miss refill: write line, extract word for rdata
                        data_array[req_index][victim_way_reg]  <= pending_line_reg;
                        tag_array[req_index][victim_way_reg]   <= req_tag;
                        valid_array[req_index][victim_way_reg] <= 1'b1;
                        dirty_array[req_index][victim_way_reg] <= 1'b0;

                        case (word_idx)
                            2'd0: rdata_reg <= pending_line_reg[127:96];
                            2'd1: rdata_reg <= pending_line_reg[95:64];
                            2'd2: rdata_reg <= pending_line_reg[63:32];
                            2'd3: rdata_reg <= pending_line_reg[31:0];
                            default: rdata_reg <= 32'd0;
                        endcase
                    end else begin
                        // Write miss refill: merge wdata into line, write back, dirty=1
                        rdata_reg <= 32'd0;
                        case (word_idx)
                            2'd0: data_array[req_index][victim_way_reg] <=
                                {req_wdata_reg, pending_line_reg[95:0]};
                            2'd1: data_array[req_index][victim_way_reg] <=
                                {pending_line_reg[127:96], req_wdata_reg, pending_line_reg[63:0]};
                            2'd2: data_array[req_index][victim_way_reg] <=
                                {pending_line_reg[127:64], req_wdata_reg, pending_line_reg[31:0]};
                            2'd3: data_array[req_index][victim_way_reg] <=
                                {pending_line_reg[127:32], req_wdata_reg};
                            default: data_array[req_index][victim_way_reg] <= pending_line_reg;
                        endcase
                        tag_array[req_index][victim_way_reg]   <= req_tag;
                        valid_array[req_index][victim_way_reg] <= 1'b1;
                        dirty_array[req_index][victim_way_reg] <= 1'b1;
                    end

                    // LRU update for the refilled way
                    begin : refill_lru_update
                        reg [1:0] old_val;
                        old_val = lru_cnt[req_index][victim_way_reg];

                        lru_cnt[req_index][victim_way_reg] <= 2'd3;

                        if ((victim_way_reg != 2'd0) && (lru_cnt[req_index][2'd0] > old_val))
                            lru_cnt[req_index][2'd0] <= lru_cnt[req_index][2'd0] - 2'd1;
                        if ((victim_way_reg != 2'd1) && (lru_cnt[req_index][2'd1] > old_val))
                            lru_cnt[req_index][2'd1] <= lru_cnt[req_index][2'd1] - 2'd1;
                        if ((victim_way_reg != 2'd2) && (lru_cnt[req_index][2'd2] > old_val))
                            lru_cnt[req_index][2'd2] <= lru_cnt[req_index][2'd2] - 2'd1;
                        if ((victim_way_reg != 2'd3) && (lru_cnt[req_index][2'd3] > old_val))
                            lru_cnt[req_index][2'd3] <= lru_cnt[req_index][2'd3] - 2'd1;
                    end

                    ready_reg <= 1'b1;
                    state_reg <= IDLE;
                end

                default: begin
                    state_reg <= IDLE;
                end
            endcase
        end
    end

    // =========================================================================
    // Output Assignments (registered outputs via wire)
    // =========================================================================
    assign rdata   = rdata_reg;
    assign ready   = ready_reg;
    assign m_addr  = m_addr_reg;
    assign m_wdata = m_wdata_reg;
    assign m_rd_en = m_rd_en_reg;
    assign m_wr_en = m_wr_en_reg;

endmodule
`default_nettype wire
