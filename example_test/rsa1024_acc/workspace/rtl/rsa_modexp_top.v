// -----------------------------------------------------------------------------
// File   : rsa_modexp_top.v
// Author : AI Coder
// Date   : 2026-04-26
// -----------------------------------------------------------------------------
// Description:
//   Top-level RSA-1024 modular exponentiation accelerator. Contains AXI4-Lite
//   slave interface for register configuration (modulus N, exponent E, R^2 mod
//   N, N'), AXI4-Stream sink for message input and AXI4-Stream source for
//   result output. Implements Square-and-Multiply exponentiation FSM using
//   Montgomery multiplication. Instantiates mont_mult_1024 submodule.
// -----------------------------------------------------------------------------
// Change Log:
//   2026-04-26  AI Coder  v1.0  Initial implementation
// -----------------------------------------------------------------------------

`resetall
`timescale 1ns / 1ps
`default_nettype none

module rsa_modexp_top
(
    input  wire          clk,
    input  wire          rst,
    // AXI4-Lite Slave - Write Address Channel
    input  wire [15:0]   s_axi_awaddr,
    input  wire          s_axi_awvalid,
    output wire          s_axi_awready,
    // AXI4-Lite Slave - Write Data Channel
    input  wire [31:0]   s_axi_wdata,
    input  wire          s_axi_wvalid,
    output wire          s_axi_wready,
    // AXI4-Lite Slave - Write Response Channel
    output wire [1:0]    s_axi_bresp,
    output wire          s_axi_bvalid,
    input  wire          s_axi_bready,
    // AXI4-Lite Slave - Read Address Channel
    input  wire [15:0]   s_axi_araddr,
    input  wire          s_axi_arvalid,
    output wire          s_axi_arready,
    // AXI4-Lite Slave - Read Data Channel
    output wire [31:0]   s_axi_rdata,
    output wire [1:0]    s_axi_rresp,
    output wire          s_axi_rvalid,
    input  wire          s_axi_rready,
    // AXI4-Stream Sink (input message M)
    input  wire [31:0]   s_axis_tdata,
    input  wire          s_axis_tvalid,
    output wire          s_axis_tready,
    input  wire          s_axis_tlast,
    // AXI4-Stream Source (output result)
    output wire [31:0]   m_axis_tdata,
    output wire          m_axis_tvalid,
    input  wire          m_axis_tready,
    output wire          m_axis_tlast
);

    //////////////////////////////////////////////////////////////////
    // AXI4-Lite Write FSM states
    //////////////////////////////////////////////////////////////////

    localparam [1:0]
        WR_STATE_IDLE   = 2'd0,
        WR_STATE_RESP   = 2'd1;

    //////////////////////////////////////////////////////////////////
    // AXI4-Lite Read FSM states
    //////////////////////////////////////////////////////////////////

    localparam [1:0]
        RD_STATE_IDLE = 2'd0,
        RD_STATE_DATA = 2'd1;

    //////////////////////////////////////////////////////////////////
    // Memory select constants
    //////////////////////////////////////////////////////////////////

    localparam [1:0]
        MEM_SEL_OP_A = 2'd0,
        MEM_SEL_OP_B = 2'd1,
        MEM_SEL_N    = 2'd2;

    //////////////////////////////////////////////////////////////////
    // Main FSM state encoding (5-bit)
    //////////////////////////////////////////////////////////////////

    localparam [4:0]
        ST_IDLE             = 5'd0,
        ST_LOAD_M           = 5'd1,
        ST_TO_MONT          = 5'd2,
        ST_WAIT_TO_MONT     = 5'd3,
        ST_READ_MONT_M      = 5'd4,
        ST_EXP_INIT         = 5'd5,
        ST_WAIT_INIT        = 5'd6,
        ST_READ_INIT        = 5'd7,
        ST_EXP_SQUARE       = 5'd8,
        ST_WAIT_SQUARE      = 5'd9,
        ST_READ_SQUARE      = 5'd10,
        ST_EXP_MULT         = 5'd11,
        ST_WAIT_MULT        = 5'd12,
        ST_READ_MULT        = 5'd13,
        ST_FROM_MONT        = 5'd14,
        ST_WAIT_FROM_MONT   = 5'd15,
        ST_READ_FROM_MONT   = 5'd16,
        ST_OUTPUT           = 5'd17;

    //////////////////////////////////////////////////////////////////
    // Register arrays (register file for N, E, R2, M, A, Result)
    //////////////////////////////////////////////////////////////////

    reg [31:0] reg_N [0:31];
    reg [31:0] reg_E [0:31];
    reg [31:0] reg_R2 [0:31];
    reg [31:0] reg_M [0:31];
    reg [31:0] reg_A [0:31];
    reg [31:0] reg_Result [0:31];
    reg [31:0] reg_N_prime = 32'd0;

    //////////////////////////////////////////////////////////////////
    // Main FSM registers
    //////////////////////////////////////////////////////////////////

    reg [4:0]  main_state_reg  = ST_IDLE,  main_state_next;
    reg [10:0] exp_bit_cnt_reg = 11'd0,    exp_bit_cnt_next;
    reg [4:0]  word_cnt_reg    = 5'd0,     word_cnt_next;
    reg [4:0]  load_cnt_reg    = 5'd0,     load_cnt_next;
    reg        load_phase_reg  = 1'b0,     load_phase_next;

    //////////////////////////////////////////////////////////////////
    // AXI4-Lite Write channel registers
    //////////////////////////////////////////////////////////////////

    reg [1:0]  wr_state_reg        = WR_STATE_IDLE, wr_state_next;
    reg        s_axi_awready_reg   = 1'b0,          s_axi_awready_next;
    reg        s_axi_wready_reg    = 1'b0,          s_axi_wready_next;
    reg [1:0]  s_axi_bresp_reg     = 2'b00,         s_axi_bresp_next;
    reg        s_axi_bvalid_reg    = 1'b0,          s_axi_bvalid_next;
    reg        aw_captured_reg     = 1'b0,          aw_captured_next;
    reg [15:0] wr_addr_reg         = 16'd0,         wr_addr_next;
    reg        w_captured_reg      = 1'b0,          w_captured_next;
    reg [15:0] wr_data_addr_reg    = 16'd0,         wr_data_addr_next;
    reg [31:0] wr_data_val_reg     = 32'd0,         wr_data_val_next;

    //////////////////////////////////////////////////////////////////
    // AXI4-Lite Read channel registers
    //////////////////////////////////////////////////////////////////

    reg [1:0]  rd_state_reg        = RD_STATE_IDLE, rd_state_next;
    reg        s_axi_arready_reg   = 1'b0,          s_axi_arready_next;
    reg [31:0] s_axi_rdata_reg     = 32'd0,         s_axi_rdata_next;
    reg [1:0]  s_axi_rresp_reg     = 2'b00,         s_axi_rresp_next;
    reg        s_axi_rvalid_reg    = 1'b0,          s_axi_rvalid_next;

    //////////////////////////////////////////////////////////////////
    // AXI-Stream registers
    //////////////////////////////////////////////////////////////////

    reg        s_axis_tready_reg   = 1'b0,          s_axis_tready_next;
    reg [31:0] m_axis_tdata_reg    = 32'd0,         m_axis_tdata_next;
    reg        m_axis_tvalid_reg   = 1'b0,          m_axis_tvalid_next;
    reg        m_axis_tlast_reg    = 1'b0,          m_axis_tlast_next;

    //////////////////////////////////////////////////////////////////
    // Mont mult interface registers
    //////////////////////////////////////////////////////////////////

    reg        mont_start_reg      = 1'b0,          mont_start_next;
    reg        mem_wr_en_reg       = 1'b0,          mem_wr_en_next;
    reg [1:0]  mem_sel_reg         = 2'd0,          mem_sel_next;
    reg [4:0]  mem_addr_reg        = 5'd0,          mem_addr_next;
    reg [31:0] mem_wdata_reg       = 32'd0,         mem_wdata_next;

    //////////////////////////////////////////////////////////////////
    // Status and control registers
    //////////////////////////////////////////////////////////////////

    reg        busy_reg            = 1'b0,          busy_next;
    reg        done_flag_reg       = 1'b0,          done_flag_next;
    reg        ctrl_start_pulse    = 1'b0;

    //////////////////////////////////////////////////////////////////
    // Wires from mont_mult_1024
    //////////////////////////////////////////////////////////////////

    wire        mont_done;
    wire [31:0] result_data;

    //////////////////////////////////////////////////////////////////
    // Exponent bit extraction
    //////////////////////////////////////////////////////////////////

    // Bit 1023 = MSB, bit 0 = LSB.
    // E[0] is LSW, E[31] is MSW. Bit b is in word (b/32), position (b%32).
    wire [4:0]  exp_word_idx    = exp_bit_cnt_reg[10:5];
    wire [4:0]  exp_bit_in_word = exp_bit_cnt_reg[4:0];
    wire        exp_bit_value   = reg_E[exp_word_idx][exp_bit_in_word];

    //////////////////////////////////////////////////////////////////
    // Output port assignments
    //////////////////////////////////////////////////////////////////

    assign s_axi_awready = s_axi_awready_reg;
    assign s_axi_wready  = s_axi_wready_reg;
    assign s_axi_bresp   = s_axi_bresp_reg;
    assign s_axi_bvalid  = s_axi_bvalid_reg;
    assign s_axi_arready = s_axi_arready_reg;
    assign s_axi_rdata   = s_axi_rdata_reg;
    assign s_axi_rresp   = s_axi_rresp_reg;
    assign s_axi_rvalid  = s_axi_rvalid_reg;
    assign s_axis_tready = s_axis_tready_reg;
    assign m_axis_tdata  = m_axis_tdata_reg;
    assign m_axis_tvalid = m_axis_tvalid_reg;
    assign m_axis_tlast  = m_axis_tlast_reg;

    //////////////////////////////////////////////////////////////////
    // AXI4-Lite Write Channel FSM (combinational)
    //////////////////////////////////////////////////////////////////

    // Two-phase AXI4-Lite write:
    //   WR_STATE_IDLE: Accept AW and W channels independently or together.
    //                  When both captured, transition to WR_STATE_RESP.
    //   WR_STATE_RESP: Assert BVALID with BRESP=OKAY. Wait for BREADY.

    wire aw_capture = s_axi_awvalid && s_axi_awready_reg;
    wire w_capture  = s_axi_wvalid  && s_axi_wready_reg;

    always @* begin
        wr_state_next       = wr_state_reg;
        s_axi_awready_next  = s_axi_awready_reg;
        s_axi_wready_next   = s_axi_wready_reg;
        s_axi_bresp_next    = s_axi_bresp_reg;
        s_axi_bvalid_next   = s_axi_bvalid_reg;
        aw_captured_next    = aw_captured_reg;
        wr_addr_next        = wr_addr_reg;
        w_captured_next     = w_captured_reg;
        wr_data_addr_next   = wr_data_addr_reg;
        wr_data_val_next    = wr_data_val_reg;

        case (wr_state_reg)
            WR_STATE_IDLE: begin
                s_axi_awready_next = 1'b1;
                s_axi_wready_next  = 1'b1;
                s_axi_bvalid_next  = 1'b0;

                // Capture address
                if (aw_capture) begin
                    aw_captured_next   = 1'b1;
                    wr_addr_next       = s_axi_awaddr;
                    s_axi_awready_next = 1'b0;
                end

                // Capture data
                if (w_capture) begin
                    w_captured_next   = 1'b1;
                    wr_data_val_next  = s_axi_wdata;
                    s_axi_wready_next = 1'b0;
                end

                // Determine the effective write address
                // If both arrive same cycle, use current AWADDR
                if (aw_capture && w_capture) begin
                    wr_data_addr_next = s_axi_awaddr;
                end
                // If only data arrives but address was already captured
                else if (w_capture && aw_captured_reg) begin
                    wr_data_addr_next = wr_addr_reg;
                end
                // If only address arrives but data was already captured
                else if (aw_capture && w_captured_reg) begin
                    wr_data_addr_next = s_axi_awaddr;
                end

                // Both captured: transition to response
                if ((aw_capture && w_capture) ||
                    (aw_capture && w_captured_reg) ||
                    (w_capture && aw_captured_reg)) begin
                    wr_state_next      = WR_STATE_RESP;
                    s_axi_bvalid_next  = 1'b1;
                    s_axi_bresp_next   = 2'b00;
                    aw_captured_next   = 1'b0;
                    w_captured_next    = 1'b0;
                end
            end

            WR_STATE_RESP: begin
                s_axi_awready_next = 1'b0;
                s_axi_wready_next  = 1'b0;
                if (s_axi_bready && s_axi_bvalid_reg) begin
                    s_axi_bvalid_next  = 1'b0;
                    wr_state_next      = WR_STATE_IDLE;
                    s_axi_awready_next = 1'b1;
                    s_axi_wready_next  = 1'b1;
                end
            end

            default: wr_state_next = WR_STATE_IDLE;
        endcase
    end

    //////////////////////////////////////////////////////////////////
    // AXI4-Lite Read Channel FSM (combinational)
    //////////////////////////////////////////////////////////////////

    always @* begin
        rd_state_next      = rd_state_reg;
        s_axi_arready_next = s_axi_arready_reg;
        s_axi_rdata_next   = s_axi_rdata_reg;
        s_axi_rresp_next   = 2'b00;
        s_axi_rvalid_next  = s_axi_rvalid_reg;

        case (rd_state_reg)
            RD_STATE_IDLE: begin
                s_axi_arready_next = 1'b1;
                if (s_axi_arvalid && s_axi_arready_reg) begin
                    s_axi_arready_next = 1'b0;
                    s_axi_rvalid_next  = 1'b1;
                    s_axi_rresp_next   = 2'b00;
                    case (s_axi_araddr)
                        16'h0004: begin
                            // STAT_REG: bit[0]=BUSY, bit[1]=DONE
                            s_axi_rdata_next = {30'd0, done_flag_reg, busy_reg};
                        end
                        16'h0010: begin
                            // PARAM_N_PRIME
                            s_axi_rdata_next = reg_N_prime;
                        end
                        default: begin
                            if (s_axi_araddr >= 16'h0100 && s_axi_araddr < 16'h0180) begin
                                s_axi_rdata_next = reg_N[s_axi_araddr[6:2]];
                            end else if (s_axi_araddr >= 16'h0200 && s_axi_araddr < 16'h0280) begin
                                s_axi_rdata_next = reg_E[s_axi_araddr[6:2]];
                            end else if (s_axi_araddr >= 16'h0300 && s_axi_araddr < 16'h0380) begin
                                s_axi_rdata_next = reg_R2[s_axi_araddr[6:2]];
                            end else begin
                                s_axi_rdata_next = 32'd0;
                            end
                        end
                    endcase
                    rd_state_next = RD_STATE_DATA;
                end
            end
            RD_STATE_DATA: begin
                if (s_axi_rready && s_axi_rvalid_reg) begin
                    s_axi_rvalid_next  = 1'b0;
                    rd_state_next      = RD_STATE_IDLE;
                    s_axi_arready_next = 1'b1;
                end
            end
            default: rd_state_next = RD_STATE_IDLE;
        endcase
    end

    //////////////////////////////////////////////////////////////////
    // Main FSM (combinational next-state and output logic)
    //////////////////////////////////////////////////////////////////

    always @* begin
        main_state_next    = main_state_reg;
        exp_bit_cnt_next   = exp_bit_cnt_reg;
        word_cnt_next      = word_cnt_reg;
        mont_start_next    = 1'b0;
        mem_wr_en_next     = 1'b0;
        mem_sel_next       = mem_sel_reg;
        mem_addr_next      = mem_addr_reg;
        mem_wdata_next     = mem_wdata_reg;
        s_axis_tready_next = 1'b0;
        m_axis_tdata_next  = m_axis_tdata_reg;
        m_axis_tvalid_next = 1'b0;
        m_axis_tlast_next  = 1'b0;
        busy_next          = 1'b1;
        done_flag_next     = done_flag_reg;
        load_cnt_next      = load_cnt_reg;
        load_phase_next    = load_phase_reg;

        case (main_state_reg)
            ////////////////////////////////////////
            ST_IDLE: begin
                busy_next = 1'b0;
            end

            ////////////////////////////////////////
            // Receive 32 words of message M via AXI-Stream
            ST_LOAD_M: begin
                s_axis_tready_next = 1'b1;
                if (s_axis_tvalid && s_axis_tready_reg) begin
                    if (s_axis_tlast) begin
                        main_state_next = ST_TO_MONT;
                        load_cnt_next   = 5'd0;
                        load_phase_next = 1'b0;
                    end
                end
            end

            ////////////////////////////////////////
            // Load M -> op_a, R2 -> op_b for MonPro(M, R^2)
            ST_TO_MONT: begin
                if (load_phase_reg == 1'b0) begin
                    // Load M into op_a
                    mem_wr_en_next = 1'b1;
                    mem_sel_next   = MEM_SEL_OP_A;
                    mem_addr_next  = load_cnt_reg;
                    mem_wdata_next = reg_M[load_cnt_reg];
                    if (load_cnt_reg == 5'd31) begin
                        load_phase_next = 1'b1;
                        load_cnt_next   = 5'd0;
                    end else begin
                        load_cnt_next = load_cnt_reg + 5'd1;
                    end
                end else begin
                    // Load R2 into op_b
                    mem_wr_en_next = 1'b1;
                    mem_sel_next   = MEM_SEL_OP_B;
                    mem_addr_next  = load_cnt_reg;
                    mem_wdata_next = reg_R2[load_cnt_reg];
                    if (load_cnt_reg == 5'd31) begin
                        mont_start_next  = 1'b1;
                        main_state_next  = ST_WAIT_TO_MONT;
                        load_cnt_next    = 5'd0;
                    end else begin
                        load_cnt_next = load_cnt_reg + 5'd1;
                    end
                end
            end

            ////////////////////////////////////////
            ST_WAIT_TO_MONT: begin
                if (mont_done) begin
                    main_state_next = ST_READ_MONT_M;
                    load_cnt_next   = 5'd0;
                end
            end

            ////////////////////////////////////////
            // Read MonPro(M, R^2) result into reg_M (M_mont)
            ST_READ_MONT_M: begin
                if (load_cnt_reg == 5'd31) begin
                    main_state_next = ST_EXP_INIT;
                    load_cnt_next   = 5'd0;
                    load_phase_next = 1'b0;
                end else begin
                    load_cnt_next = load_cnt_reg + 5'd1;
                end
            end

            ////////////////////////////////////////
            // Load const_1 -> op_a, R2 -> op_b for MonPro(1, R^2)
            ST_EXP_INIT: begin
                if (load_phase_reg == 1'b0) begin
                    mem_wr_en_next = 1'b1;
                    mem_sel_next   = MEM_SEL_OP_A;
                    mem_addr_next  = load_cnt_reg;
                    if (load_cnt_reg == 5'd0) begin
                        mem_wdata_next = 32'd1;
                    end else begin
                        mem_wdata_next = 32'd0;
                    end
                    if (load_cnt_reg == 5'd31) begin
                        load_phase_next = 1'b1;
                        load_cnt_next   = 5'd0;
                    end else begin
                        load_cnt_next = load_cnt_reg + 5'd1;
                    end
                end else begin
                    mem_wr_en_next = 1'b1;
                    mem_sel_next   = MEM_SEL_OP_B;
                    mem_addr_next  = load_cnt_reg;
                    mem_wdata_next = reg_R2[load_cnt_reg];
                    if (load_cnt_reg == 5'd31) begin
                        mont_start_next  = 1'b1;
                        main_state_next  = ST_WAIT_INIT;
                        load_cnt_next    = 5'd0;
                        exp_bit_cnt_next = 11'd1023;
                    end else begin
                        load_cnt_next = load_cnt_reg + 5'd1;
                    end
                end
            end

            ////////////////////////////////////////
            ST_WAIT_INIT: begin
                if (mont_done) begin
                    main_state_next = ST_READ_INIT;
                    load_cnt_next   = 5'd0;
                end
            end

            ////////////////////////////////////////
            // Read MonPro(1, R^2) result into reg_A (A_mont)
            ST_READ_INIT: begin
                if (load_cnt_reg == 5'd31) begin
                    main_state_next = ST_EXP_SQUARE;
                    load_cnt_next   = 5'd0;
                    load_phase_next = 1'b0;
                end else begin
                    load_cnt_next = load_cnt_reg + 5'd1;
                end
            end

            ////////////////////////////////////////
            // Load reg_A -> op_a and op_b for squaring MonPro(A, A)
            ST_EXP_SQUARE: begin
                if (load_phase_reg == 1'b0) begin
                    mem_wr_en_next = 1'b1;
                    mem_sel_next   = MEM_SEL_OP_A;
                    mem_addr_next  = load_cnt_reg;
                    mem_wdata_next = reg_A[load_cnt_reg];
                    if (load_cnt_reg == 5'd31) begin
                        load_phase_next = 1'b1;
                        load_cnt_next   = 5'd0;
                    end else begin
                        load_cnt_next = load_cnt_reg + 5'd1;
                    end
                end else begin
                    mem_wr_en_next = 1'b1;
                    mem_sel_next   = MEM_SEL_OP_B;
                    mem_addr_next  = load_cnt_reg;
                    mem_wdata_next = reg_A[load_cnt_reg];
                    if (load_cnt_reg == 5'd31) begin
                        mont_start_next = 1'b1;
                        main_state_next = ST_WAIT_SQUARE;
                        load_cnt_next   = 5'd0;
                    end else begin
                        load_cnt_next = load_cnt_reg + 5'd1;
                    end
                end
            end

            ////////////////////////////////////////
            ST_WAIT_SQUARE: begin
                if (mont_done) begin
                    main_state_next = ST_READ_SQUARE;
                    load_cnt_next   = 5'd0;
                end
            end

            ////////////////////////////////////////
            // Read MonPro(A, A) result into reg_A
            ST_READ_SQUARE: begin
                if (load_cnt_reg == 5'd31) begin
                    if (exp_bit_cnt_reg == 11'd0) begin
                        main_state_next = ST_FROM_MONT;
                        load_cnt_next   = 5'd0;
                        load_phase_next = 1'b0;
                    end else if (exp_bit_value) begin
                        main_state_next = ST_EXP_MULT;
                        load_cnt_next   = 5'd0;
                        load_phase_next = 1'b0;
                    end else begin
                        exp_bit_cnt_next = exp_bit_cnt_reg - 11'd1;
                        main_state_next  = ST_EXP_SQUARE;
                        load_cnt_next    = 5'd0;
                        load_phase_next  = 1'b0;
                    end
                end else begin
                    load_cnt_next = load_cnt_reg + 5'd1;
                end
            end

            ////////////////////////////////////////
            // Load reg_A -> op_a, reg_M -> op_b for MonPro(A, M_mont)
            ST_EXP_MULT: begin
                if (load_phase_reg == 1'b0) begin
                    mem_wr_en_next = 1'b1;
                    mem_sel_next   = MEM_SEL_OP_A;
                    mem_addr_next  = load_cnt_reg;
                    mem_wdata_next = reg_A[load_cnt_reg];
                    if (load_cnt_reg == 5'd31) begin
                        load_phase_next = 1'b1;
                        load_cnt_next   = 5'd0;
                    end else begin
                        load_cnt_next = load_cnt_reg + 5'd1;
                    end
                end else begin
                    mem_wr_en_next = 1'b1;
                    mem_sel_next   = MEM_SEL_OP_B;
                    mem_addr_next  = load_cnt_reg;
                    mem_wdata_next = reg_M[load_cnt_reg];
                    if (load_cnt_reg == 5'd31) begin
                        mont_start_next = 1'b1;
                        main_state_next = ST_WAIT_MULT;
                        load_cnt_next   = 5'd0;
                    end else begin
                        load_cnt_next = load_cnt_reg + 5'd1;
                    end
                end
            end

            ////////////////////////////////////////
            ST_WAIT_MULT: begin
                if (mont_done) begin
                    main_state_next = ST_READ_MULT;
                    load_cnt_next   = 5'd0;
                end
            end

            ////////////////////////////////////////
            // Read MonPro(A, M_mont) result into reg_A
            ST_READ_MULT: begin
                if (load_cnt_reg == 5'd31) begin
                    if (exp_bit_cnt_reg == 11'd0) begin
                        main_state_next = ST_FROM_MONT;
                        load_cnt_next   = 5'd0;
                        load_phase_next = 1'b0;
                    end else begin
                        exp_bit_cnt_next = exp_bit_cnt_reg - 11'd1;
                        main_state_next  = ST_EXP_SQUARE;
                        load_cnt_next    = 5'd0;
                        load_phase_next  = 1'b0;
                    end
                end else begin
                    load_cnt_next = load_cnt_reg + 5'd1;
                end
            end

            ////////////////////////////////////////
            // Load reg_A -> op_a, const_1 -> op_b for MonPro(A, 1)
            ST_FROM_MONT: begin
                if (load_phase_reg == 1'b0) begin
                    mem_wr_en_next = 1'b1;
                    mem_sel_next   = MEM_SEL_OP_A;
                    mem_addr_next  = load_cnt_reg;
                    mem_wdata_next = reg_A[load_cnt_reg];
                    if (load_cnt_reg == 5'd31) begin
                        load_phase_next = 1'b1;
                        load_cnt_next   = 5'd0;
                    end else begin
                        load_cnt_next = load_cnt_reg + 5'd1;
                    end
                end else begin
                    mem_wr_en_next = 1'b1;
                    mem_sel_next   = MEM_SEL_OP_B;
                    mem_addr_next  = load_cnt_reg;
                    if (load_cnt_reg == 5'd0) begin
                        mem_wdata_next = 32'd1;
                    end else begin
                        mem_wdata_next = 32'd0;
                    end
                    if (load_cnt_reg == 5'd31) begin
                        mont_start_next  = 1'b1;
                        main_state_next  = ST_WAIT_FROM_MONT;
                        load_cnt_next    = 5'd0;
                    end else begin
                        load_cnt_next = load_cnt_reg + 5'd1;
                    end
                end
            end

            ////////////////////////////////////////
            ST_WAIT_FROM_MONT: begin
                if (mont_done) begin
                    main_state_next = ST_READ_FROM_MONT;
                    load_cnt_next   = 5'd0;
                end
            end

            ////////////////////////////////////////
            // Read MonPro(A, 1) result into reg_Result
            ST_READ_FROM_MONT: begin
                if (load_cnt_reg == 5'd31) begin
                    main_state_next = ST_OUTPUT;
                    word_cnt_next   = 5'd0;
                    done_flag_next  = 1'b1;
                end else begin
                    load_cnt_next = load_cnt_reg + 5'd1;
                end
            end

            ////////////////////////////////////////
            // Output 32 words of result via AXI-Stream
            ST_OUTPUT: begin
                m_axis_tvalid_next = 1'b1;
                m_axis_tdata_next  = reg_Result[word_cnt_reg];
                if (word_cnt_reg == 5'd31) begin
                    m_axis_tlast_next = 1'b1;
                end else begin
                    m_axis_tlast_next = 1'b0;
                end
                if (m_axis_tready && m_axis_tvalid_reg) begin
                    if (word_cnt_reg == 5'd31) begin
                        main_state_next = ST_IDLE;
                        done_flag_next  = 1'b0;
                    end else begin
                        word_cnt_next = word_cnt_reg + 5'd1;
                    end
                end
            end

            ////////////////////////////////////////
            default: main_state_next = ST_IDLE;
        endcase
    end

    //////////////////////////////////////////////////////////////////
    // Sequential: AXI4-Lite write register file update
    //////////////////////////////////////////////////////////////////

    always @(posedge clk) begin
        if (rst) begin
            reg_N_prime       <= 32'd0;
            ctrl_start_pulse  <= 1'b0;
        end else begin
            ctrl_start_pulse <= 1'b0;
            // Detect transition from WR_STATE_IDLE to WR_STATE_RESP
            // which indicates a successful write capture
            if (wr_state_reg == WR_STATE_IDLE && wr_state_next == WR_STATE_RESP) begin
                case (wr_data_addr_next)
                    16'h0000: begin
                        // CTRL_REG: bit[0]=1 starts operation
                        if (wr_data_val_next[0] == 1'b1) begin
                            ctrl_start_pulse <= 1'b1;
                        end
                    end
                    16'h0010: begin
                        reg_N_prime <= wr_data_val_next;
                    end
                    default: begin
                        if (wr_data_addr_next >= 16'h0100 &&
                            wr_data_addr_next < 16'h0180) begin
                            reg_N[wr_data_addr_next[6:2]] <= wr_data_val_next;
                        end else if (wr_data_addr_next >= 16'h0200 &&
                                   wr_data_addr_next < 16'h0280) begin
                            reg_E[wr_data_addr_next[6:2]] <= wr_data_val_next;
                        end else if (wr_data_addr_next >= 16'h0300 &&
                                   wr_data_addr_next < 16'h0380) begin
                            reg_R2[wr_data_addr_next[6:2]] <= wr_data_val_next;
                        end
                    end
                endcase
            end
        end
    end

    //////////////////////////////////////////////////////////////////
    // Sequential: AXI-Stream data capture into reg_M
    //////////////////////////////////////////////////////////////////

    always @(posedge clk) begin
        if (rst) begin
            // reg_M not explicitly reset (data-path)
        end else begin
            if (main_state_reg == ST_LOAD_M && s_axis_tvalid &&
                s_axis_tready_reg) begin
                reg_M[word_cnt_reg] <= s_axis_tdata;
            end
        end
    end

    //////////////////////////////////////////////////////////////////
    // Sequential: result readback from mont_mult_1024
    //////////////////////////////////////////////////////////////////

    // result_addr_i is driven directly from load_cnt_reg (registered signal).
    // mont_mult_1024 has a combinational read port, so result_data is
    // immediately valid for the current load_cnt_reg value.
    // We capture result_data into the target register array on each clock
    // edge, indexed by load_cnt_reg (before it updates).

    always @(posedge clk) begin
        if (rst) begin
            // No reset for data arrays
        end else begin
            case (main_state_reg)
                ST_READ_MONT_M: begin
                    reg_M[load_cnt_reg] <= result_data;
                end
                ST_READ_INIT: begin
                    reg_A[load_cnt_reg] <= result_data;
                end
                ST_READ_SQUARE: begin
                    reg_A[load_cnt_reg] <= result_data;
                end
                ST_READ_MULT: begin
                    reg_A[load_cnt_reg] <= result_data;
                end
                ST_READ_FROM_MONT: begin
                    reg_Result[load_cnt_reg] <= result_data;
                end
                default: ;
            endcase
        end
    end

    //////////////////////////////////////////////////////////////////
    // Sequential: main FSM registers
    //////////////////////////////////////////////////////////////////

    always @(posedge clk) begin
        if (rst) begin
            main_state_reg    <= ST_IDLE;
            exp_bit_cnt_reg   <= 11'd0;
            word_cnt_reg      <= 5'd0;
            mont_start_reg    <= 1'b0;
            mem_wr_en_reg     <= 1'b0;
            mem_sel_reg       <= 2'd0;
            mem_addr_reg      <= 5'd0;
            mem_wdata_reg     <= 32'd0;
            busy_reg          <= 1'b0;
            done_flag_reg     <= 1'b0;
            s_axis_tready_reg <= 1'b0;
            m_axis_tdata_reg  <= 32'd0;
            m_axis_tvalid_reg <= 1'b0;
            m_axis_tlast_reg  <= 1'b0;
            load_cnt_reg      <= 5'd0;
            load_phase_reg    <= 1'b0;
        end else begin
            main_state_reg    <= main_state_next;
            exp_bit_cnt_reg   <= exp_bit_cnt_next;
            word_cnt_reg      <= word_cnt_next;
            mont_start_reg    <= mont_start_next;
            mem_wr_en_reg     <= mem_wr_en_next;
            mem_sel_reg       <= mem_sel_next;
            mem_addr_reg      <= mem_addr_next;
            mem_wdata_reg     <= mem_wdata_next;
            busy_reg          <= busy_next;
            done_flag_reg     <= done_flag_next;
            s_axis_tready_reg <= s_axis_tready_next;
            m_axis_tdata_reg  <= m_axis_tdata_next;
            m_axis_tvalid_reg <= m_axis_tvalid_next;
            m_axis_tlast_reg  <= m_axis_tlast_next;
            load_cnt_reg      <= load_cnt_next;
            load_phase_reg    <= load_phase_next;

            // Handle CTRL_REG start: only in IDLE state
            if (main_state_reg == ST_IDLE && ctrl_start_pulse) begin
                main_state_reg    <= ST_LOAD_M;
                word_cnt_reg      <= 5'd0;
                busy_reg          <= 1'b1;
                done_flag_reg     <= 1'b0;
            end
        end
    end

    //////////////////////////////////////////////////////////////////
    // Sequential: AXI4-Lite write FSM
    //////////////////////////////////////////////////////////////////

    always @(posedge clk) begin
        if (rst) begin
            wr_state_reg       <= WR_STATE_IDLE;
            s_axi_awready_reg  <= 1'b0;
            s_axi_wready_reg   <= 1'b0;
            s_axi_bresp_reg    <= 2'b00;
            s_axi_bvalid_reg   <= 1'b0;
            aw_captured_reg    <= 1'b0;
            wr_addr_reg        <= 16'd0;
            w_captured_reg     <= 1'b0;
            wr_data_addr_reg   <= 16'd0;
            wr_data_val_reg    <= 32'd0;
        end else begin
            wr_state_reg       <= wr_state_next;
            s_axi_awready_reg  <= s_axi_awready_next;
            s_axi_wready_reg   <= s_axi_wready_next;
            s_axi_bresp_reg    <= s_axi_bresp_next;
            s_axi_bvalid_reg   <= s_axi_bvalid_next;
            aw_captured_reg    <= aw_captured_next;
            wr_addr_reg        <= wr_addr_next;
            w_captured_reg     <= w_captured_next;
            wr_data_addr_reg   <= wr_data_addr_next;
            wr_data_val_reg    <= wr_data_val_next;
        end
    end

    //////////////////////////////////////////////////////////////////
    // Sequential: AXI4-Lite read FSM
    //////////////////////////////////////////////////////////////////

    always @(posedge clk) begin
        if (rst) begin
            rd_state_reg       <= RD_STATE_IDLE;
            s_axi_arready_reg  <= 1'b0;
            s_axi_rdata_reg    <= 32'd0;
            s_axi_rresp_reg    <= 2'b00;
            s_axi_rvalid_reg   <= 1'b0;
        end else begin
            rd_state_reg       <= rd_state_next;
            s_axi_arready_reg  <= s_axi_arready_next;
            s_axi_rdata_reg    <= s_axi_rdata_next;
            s_axi_rresp_reg    <= s_axi_rresp_next;
            s_axi_rvalid_reg   <= s_axi_rvalid_next;
        end
    end

    //////////////////////////////////////////////////////////////////
    // mont_mult_1024 instantiation
    //////////////////////////////////////////////////////////////////

    mont_mult_1024 #
    (
        .WORD_WIDTH (32),
        .NUM_WORDS  (32)
    )
    mont_mult_1024_inst
    (
        .clk            (clk),
        .rst            (rst),
        .start_i        (mont_start_reg),
        .done_o         (mont_done),
        .mem_wr_en_i    (mem_wr_en_reg),
        .mem_sel_i      (mem_sel_reg),
        .mem_addr_i     (mem_addr_reg),
        .mem_wdata_i    (mem_wdata_reg),
        .n_prime_i      (reg_N_prime),
        .result_addr_i  (load_cnt_reg),
        .result_data_o  (result_data)
    );

endmodule

`resetall
