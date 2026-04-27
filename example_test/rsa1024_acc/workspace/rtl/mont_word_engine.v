// -----------------------------------------------------------------------------
// File   : mont_word_engine.v
// Author : VeriFlow-CC
// Date   : 2026-04-26
// -----------------------------------------------------------------------------
// Description:
//   CIOS algorithm inner loop engine. Handles multiply-accumulate (MULT_ACCUM)
//   and reduce-accumulate (REDUCE_ACCUM) phases for 32 words per outer loop
//   iteration. Computes reduction factor m = t[0] * N' mod 2^32 internally.
//   Instantiates dsp_mac_32 for the 32x32 multiply-accumulate operations.
//   The dsp_mac_32 has a 2-stage pipeline with 2-cycle latency. The engine
//   issues reads and feeds the DSP pipeline every 3 cycles per word to
//   account for 1-cycle RAM read latency + 2-cycle DSP pipeline.
// -----------------------------------------------------------------------------
// Change Log:
//   2026-04-26  VeriFlow-CC  v1.0  Initial release
// -----------------------------------------------------------------------------

`resetall
`timescale 1ns / 1ps
`default_nettype none

module mont_word_engine #
(
    // Bit width of each word
    parameter WORD_WIDTH = 32,
    // Number of words per operand
    parameter NUM_WORDS  = 32
)
(
    input  wire                   clk,
    input  wire                   rst,
    input  wire                   start_i,
    output wire                   done_o,
    input  wire [WORD_WIDTH-1:0]  b_i,
    input  wire [WORD_WIDTH-1:0]  n_prime_i,
    output wire [4:0]             addr_rd_o,
    input  wire [WORD_WIDTH-1:0]  a_j_i,
    input  wire [WORD_WIDTH-1:0]  n_j_i,
    output wire [5:0]             t_rd_addr_o,
    input  wire [WORD_WIDTH-1:0]  t_rd_data_i,
    output wire [5:0]             t_wr_addr_o,
    output wire [WORD_WIDTH-1:0]  t_wr_data_o,
    output wire                   t_wr_en_o
);

    // -------------------------------------------------------------------------
    // FSM state encoding (3 bits, 7 states)
    // -------------------------------------------------------------------------
    localparam [2:0]
        ENGINE_STATE_IDLE         = 3'd0,
        ENGINE_STATE_MULT_ACCUM   = 3'd1,
        ENGINE_STATE_CARRY1       = 3'd2,
        ENGINE_STATE_COMPUTE_M    = 3'd3,
        ENGINE_STATE_REDUCE_ACCUM = 3'd4,
        ENGINE_STATE_CARRY2       = 3'd5,
        ENGINE_STATE_SHIFT        = 3'd6;

    // -------------------------------------------------------------------------
    // Internal registers
    // -------------------------------------------------------------------------

    // FSM state
    reg [2:0]  state_reg = ENGINE_STATE_IDLE, state_next;

    // Inner loop word counter (0 to NUM_WORDS-1)
    reg [4:0]  j_cnt_reg = 5'd0, j_cnt_next;

    // Pipeline sub-phase counter:
    //   0 = issue RAM reads, feed DSP stage 1
    //   1 = RAM data arrives, feed DSP stage 2 (actually DSP inputs are same,
    //       just waiting for RAM data to be available at t_rd_data_i)
    //   2 = DSP output valid, capture result, advance j
    reg [1:0]  pipe_reg = 2'd0, pipe_next;

    // Carry propagation register
    reg [WORD_WIDTH-1:0] carry_reg = {WORD_WIDTH{1'b0}}, carry_next;

    // Latched B[i] value
    reg [WORD_WIDTH-1:0] b_reg = {WORD_WIDTH{1'b0}}, b_next;

    // Computed reduction factor m = t[0] * N' mod 2^32
    reg [WORD_WIDTH-1:0] m_factor_reg = {WORD_WIDTH{1'b0}}, m_factor_next;

    // Shift phase counter (0 to NUM_WORDS, i.e. 0 to 32)
    reg [5:0]  shift_cnt_reg = 6'd0, shift_cnt_next;

    // Shift sub-phase: 0 = issue read, 1 = write data
    reg        shift_phase_reg = 1'b0, shift_phase_next;

    // Carry1 / Carry2 sub-phase: 0 = issue read of t[32], 1 = write t[32]+carry
    reg        carry_phase_reg = 1'b0, carry_phase_next;

    // Stored carry for carry propagation phases
    reg [WORD_WIDTH-1:0] saved_carry_reg = {WORD_WIDTH{1'b0}}, saved_carry_next;

    // Stored t[32] value read during carry propagation
    reg [WORD_WIDTH-1:0] t32_val_reg = {WORD_WIDTH{1'b0}}, t32_val_next;

    // Done output register (pulse for 1 cycle)
    reg        done_reg = 1'b0, done_next;

    // -------------------------------------------------------------------------
    // dsp_mac_32 interface signals
    // -------------------------------------------------------------------------
    reg [WORD_WIDTH-1:0] mac_a;
    reg [WORD_WIDTH-1:0] mac_b;

    wire [WORD_WIDTH-1:0] mac_res_out;
    wire [WORD_WIDTH-1:0] mac_c_out;

    // -------------------------------------------------------------------------
    // T RAM address/data mux: select between MAC result, carry-add, or shift
    // -------------------------------------------------------------------------
    reg [5:0]            t_rd_addr_mux;
    reg [WORD_WIDTH-1:0] t_wr_data_mux;
    reg [5:0]            t_wr_addr_mux;
    reg                  t_wr_en_mux;

    // -------------------------------------------------------------------------
    // dsp_mac_32 instantiation
    // -------------------------------------------------------------------------
    dsp_mac_32 dsp_mac_32_inst (
        .clk       (clk),
        .rst       (rst),
        .a_i       (mac_a),
        .b_i       (mac_b),
        .c_in_i    (carry_reg),
        .t_in_i    (t_rd_data_i),
        .res_out_o (mac_res_out),
        .c_out_o   (mac_c_out)
    );

    // -------------------------------------------------------------------------
    // Output port assignments
    // -------------------------------------------------------------------------
    assign done_o       = done_reg;
    assign addr_rd_o    = j_cnt_reg;
    assign t_rd_addr_o  = t_rd_addr_mux;
    assign t_wr_addr_o  = t_wr_addr_mux;
    assign t_wr_data_o  = t_wr_data_mux;
    assign t_wr_en_o    = t_wr_en_mux;

    // -------------------------------------------------------------------------
    // Combinational logic: next-state and output decode
    // -------------------------------------------------------------------------
    always @* begin
        // Default: hold state, no changes
        state_next        = state_reg;
        j_cnt_next        = j_cnt_reg;
        pipe_next         = pipe_reg;
        carry_next        = carry_reg;
        b_next            = b_reg;
        m_factor_next     = m_factor_reg;
        shift_cnt_next    = shift_cnt_reg;
        shift_phase_next  = shift_phase_reg;
        carry_phase_next  = carry_phase_reg;
        saved_carry_next  = saved_carry_reg;
        t32_val_next      = t32_val_reg;
        done_next         = 1'b0;

        // Default dsp_mac_32 inputs
        mac_a = {WORD_WIDTH{1'b0}};
        mac_b = {WORD_WIDTH{1'b0}};

        // Default T RAM read/write controls
        t_rd_addr_mux = {1'b0, j_cnt_reg};
        t_wr_data_mux = {WORD_WIDTH{1'b0}};
        t_wr_addr_mux = 6'd0;
        t_wr_en_mux   = 1'b0;

        case (state_reg)
            ///////////////////////////////////////////////////////////////////
            // IDLE: Wait for start_i
            ///////////////////////////////////////////////////////////////////
            ENGINE_STATE_IDLE: begin
                if (start_i) begin
                    state_next   = ENGINE_STATE_MULT_ACCUM;
                    j_cnt_next   = 5'd0;
                    pipe_next    = 2'd0;
                    carry_next   = {WORD_WIDTH{1'b0}};
                    b_next       = b_i;
                end
            end

            ///////////////////////////////////////////////////////////////////
            // MULT_ACCUM: t[j] += A[j] * B[i] + C, for j = 0..31
            // Pipeline: 3 cycles per word
            //   pipe=0: issue RAM reads, feed DSP inputs
            //   pipe=1: RAM data arrives, re-feed DSP (1 cycle wait)
            //   pipe=2: DSP output valid, write t[j], update carry
            ///////////////////////////////////////////////////////////////////
            ENGINE_STATE_MULT_ACCUM: begin
                case (pipe_reg)
                    2'd0: begin
                        // Issue RAM reads for A[j], t[j]
                        t_rd_addr_mux = {1'b0, j_cnt_reg};
                        mac_a = a_j_i;
                        mac_b = b_reg;
                        pipe_next = 2'd1;
                    end
                    2'd1: begin
                        // RAM read data now available
                        t_rd_addr_mux = {1'b0, j_cnt_reg};
                        mac_a = a_j_i;
                        mac_b = b_reg;
                        pipe_next = 2'd2;
                    end
                    2'd2: begin
                        // DSP output is valid
                        t_wr_data_mux = mac_res_out;
                        t_wr_addr_mux = {1'b0, j_cnt_reg};
                        t_wr_en_mux   = 1'b1;
                        carry_next    = mac_c_out;

                        if (j_cnt_reg == (NUM_WORDS - 1)) begin
                            // Last word done, go to carry propagation
                            state_next      = ENGINE_STATE_CARRY1;
                            carry_phase_next = 1'b0;
                            saved_carry_next = mac_c_out;
                            pipe_next       = 2'd0;
                        end else begin
                            // Advance to next word
                            j_cnt_next = j_cnt_reg + 5'd1;
                            pipe_next  = 2'd0;
                        end
                    end
                    default: begin
                        pipe_next = 2'd0;
                    end
                endcase
            end

            ///////////////////////////////////////////////////////////////////
            // CARRY1: t[32] = t[32] + carry (from MULT_ACCUM)
            // Two sub-phases:
            //   carry_phase=0: read t[32]
            //   carry_phase=1: write t[32] + saved_carry
            ///////////////////////////////////////////////////////////////////
            ENGINE_STATE_CARRY1: begin
                if (!carry_phase_reg) begin
                    // Issue read of t[32]
                    t_rd_addr_mux   = 6'd32;
                    carry_phase_next = 1'b1;
                end else begin
                    // t_rd_data_i has t[32], write t[32] + saved_carry
                    t_wr_data_mux = t_rd_data_i + saved_carry_reg;
                    t_wr_addr_mux = 6'd32;
                    t_wr_en_mux   = 1'b1;
                    // Issue read of t[0] for COMPUTE_M (data available next cycle)
                    t_rd_addr_mux = 6'd0;
                    state_next    = ENGINE_STATE_COMPUTE_M;
                end
            end

            ///////////////////////////////////////////////////////////////////
            // COMPUTE_M: m = (t[0] * N') mod 2^32
            // Two sub-phases:
            //   carry_phase=1 (continues from CARRY1): read t[0]
            //   then: compute m and go to REDUCE_ACCUM
            ///////////////////////////////////////////////////////////////////
            ENGINE_STATE_COMPUTE_M: begin
                // Read t[0] -- data will be available next cycle
                t_rd_addr_mux = 6'd0;

                // Compute m = t[0] * N' mod 2^32
                // t_rd_data_i has t[0] (read issued in previous state)
                m_factor_next = (t_rd_data_i * n_prime_i);

                state_next = ENGINE_STATE_REDUCE_ACCUM;
                j_cnt_next = 5'd0;
                pipe_next  = 2'd0;
                carry_next = {WORD_WIDTH{1'b0}};
            end

            ///////////////////////////////////////////////////////////////////
            // REDUCE_ACCUM: t[j] += N[j] * m + C, for j = 0..31
            // Same 3-cycle pipeline as MULT_ACCUM
            ///////////////////////////////////////////////////////////////////
            ENGINE_STATE_REDUCE_ACCUM: begin
                case (pipe_reg)
                    2'd0: begin
                        // Issue RAM reads for N[j], t[j]
                        t_rd_addr_mux = {1'b0, j_cnt_reg};
                        mac_a = n_j_i;
                        mac_b = m_factor_reg;
                        pipe_next = 2'd1;
                    end
                    2'd1: begin
                        // RAM data now valid
                        t_rd_addr_mux = {1'b0, j_cnt_reg};
                        mac_a = n_j_i;
                        mac_b = m_factor_reg;
                        pipe_next = 2'd2;
                    end
                    2'd2: begin
                        // DSP output valid
                        t_wr_data_mux = mac_res_out;
                        t_wr_addr_mux = {1'b0, j_cnt_reg};
                        t_wr_en_mux   = 1'b1;
                        carry_next    = mac_c_out;

                        if (j_cnt_reg == (NUM_WORDS - 1)) begin
                            state_next      = ENGINE_STATE_CARRY2;
                            carry_phase_next = 1'b0;
                            saved_carry_next = mac_c_out;
                            pipe_next       = 2'd0;
                        end else begin
                            j_cnt_next = j_cnt_reg + 5'd1;
                            pipe_next  = 2'd0;
                        end
                    end
                    default: begin
                        pipe_next = 2'd0;
                    end
                endcase
            end

            ///////////////////////////////////////////////////////////////////
            // CARRY2: t[32] = t[32] + carry (from REDUCE_ACCUM)
            ///////////////////////////////////////////////////////////////////
            ENGINE_STATE_CARRY2: begin
                if (!carry_phase_reg) begin
                    // Issue read of t[32]
                    t_rd_addr_mux   = 6'd32;
                    carry_phase_next = 1'b1;
                end else begin
                    // Write t[32] + saved_carry
                    t_wr_data_mux = t_rd_data_i + saved_carry_reg;
                    t_wr_addr_mux = 6'd32;
                    t_wr_en_mux   = 1'b1;
                    state_next    = ENGINE_STATE_SHIFT;
                    shift_cnt_next   = 6'd0;
                    shift_phase_next = 1'b0;
                end
            end

            ///////////////////////////////////////////////////////////////////
            // SHIFT: t[j] = t[j+1], for j = 0..31
            // Two sub-phases per word:
            //   shift_phase=0: issue read of t[shift_cnt+1]
            //   shift_phase=1: write t[shift_cnt] = t_rd_data_i
            ///////////////////////////////////////////////////////////////////
            ENGINE_STATE_SHIFT: begin
                if (!shift_phase_reg) begin
                    // Issue read of t[shift_cnt+1]
                    t_rd_addr_mux   = shift_cnt_reg + 6'd1;
                    shift_phase_next = 1'b1;
                end else begin
                    // Write t[shift_cnt] = t_rd_data_i (read data from prev cycle)
                    t_wr_data_mux = t_rd_data_i;
                    t_wr_addr_mux = shift_cnt_reg;
                    t_wr_en_mux   = 1'b1;
                    shift_phase_next = 1'b0;

                    if (shift_cnt_reg == 6'd31) begin
                        // All 32 words shifted (j = 0..31)
                        state_next = ENGINE_STATE_IDLE;
                        done_next  = 1'b1;
                    end else begin
                        shift_cnt_next = shift_cnt_reg + 6'd1;
                    end
                end
            end

            default: begin
                state_next = ENGINE_STATE_IDLE;
            end
        endcase
    end

    // -------------------------------------------------------------------------
    // Sequential logic: register updates
    // -------------------------------------------------------------------------
    always @(posedge clk) begin
        if (rst) begin
            state_reg        <= ENGINE_STATE_IDLE;
            j_cnt_reg        <= 5'd0;
            pipe_reg         <= 2'd0;
            carry_reg        <= {WORD_WIDTH{1'b0}};
            b_reg            <= {WORD_WIDTH{1'b0}};
            m_factor_reg     <= {WORD_WIDTH{1'b0}};
            shift_cnt_reg    <= 6'd0;
            shift_phase_reg  <= 1'b0;
            carry_phase_reg  <= 1'b0;
            saved_carry_reg  <= {WORD_WIDTH{1'b0}};
            t32_val_reg      <= {WORD_WIDTH{1'b0}};
            done_reg         <= 1'b0;
        end else begin
            state_reg        <= state_next;
            j_cnt_reg        <= j_cnt_next;
            pipe_reg         <= pipe_next;
            carry_reg        <= carry_next;
            b_reg            <= b_next;
            m_factor_reg     <= m_factor_next;
            shift_cnt_reg    <= shift_cnt_next;
            shift_phase_reg  <= shift_phase_next;
            carry_phase_reg  <= carry_phase_next;
            saved_carry_reg  <= saved_carry_next;
            t32_val_reg      <= t32_val_next;
            done_reg         <= done_next;
        end
    end

endmodule

`resetall
