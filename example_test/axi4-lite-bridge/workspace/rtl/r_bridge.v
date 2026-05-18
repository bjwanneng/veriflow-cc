`resetall
`timescale 1ns / 1ps
`default_nettype none

module r_bridge #(
    parameter FIFO_DEPTH = 4
) (
    // Slave-side (read domain)
    input  wire        s_axi_aclk,
    input  wire        s_axi_aresetn,
    output wire        s_axi_rvalid,
    input  wire        s_axi_rready,
    output wire [31:0] s_axi_rdata,
    output wire [1:0]  s_axi_rresp,

    // Master-side (write domain)
    input  wire        m_axi_aclk,
    input  wire        m_axi_aresetn,
    input  wire        m_axi_rvalid,
    output wire        m_axi_rready,
    input  wire [31:0] m_axi_rdata,
    input  wire [1:0]  m_axi_rresp
);

    // ----------------------------------------------------------------
    // Packed data width: {rdata[31:0], rresp[1:0]} = 34 bits
    // ----------------------------------------------------------------
    localparam PACKED_WIDTH = 34;

    // ----------------------------------------------------------------
    // FIFO interface signals
    // Write side is in m_axi_aclk domain (master pushes R response)
    // Read side is in s_axi_aclk domain (slave pops R response)
    // ----------------------------------------------------------------
    wire                  fifo_wr_en;
    wire [PACKED_WIDTH-1:0] fifo_wr_data;
    wire                  fifo_full;

    wire                  fifo_rd_en;
    wire [PACKED_WIDTH-1:0] fifo_rd_data;
    wire                  fifo_empty;

    // ----------------------------------------------------------------
    // Master side: AXI handshake drives FIFO write
    // m_axi_rready is combinational: ready when FIFO is not full
    // Write on handshake (m_axi_rvalid && m_axi_rready)
    // ----------------------------------------------------------------
    assign m_axi_rready = ~fifo_full;
    assign fifo_wr_en   = m_axi_rvalid & m_axi_rready;
    assign fifo_wr_data = {m_axi_rdata, m_axi_rresp};

    // ----------------------------------------------------------------
    // Slave side: FIFO read drives AXI outputs
    // s_axi_rvalid is registered (from FIFO empty flag, already
    // registered inside async_fifo_gray).
    // s_axi_rdata and s_axi_rresp come from FIFO rd_data.
    // Read on handshake (s_axi_rvalid && s_axi_rready)
    // ----------------------------------------------------------------
    assign fifo_rd_en   = s_axi_rvalid & s_axi_rready;

    // Unpack FIFO read data: upper 32 bits = rdata, lower 2 bits = rresp
    assign s_axi_rdata  = fifo_rd_data[33:2];
    assign s_axi_rresp  = fifo_rd_data[1:0];
    assign s_axi_rvalid = ~fifo_empty;

    // ----------------------------------------------------------------
    // Async FIFO instance (Gray-code pointer crossing, 2-stage sync)
    // Write domain = m_axi_aclk, Read domain = s_axi_aclk
    // ----------------------------------------------------------------
    async_fifo_gray #(
        .DATA_WIDTH (PACKED_WIDTH),
        .FIFO_DEPTH (FIFO_DEPTH)
    ) u_fifo (
        // Write domain (master side)
        .wr_clk   (m_axi_aclk),
        .wr_rst_n (m_axi_aresetn),
        .wr_en    (fifo_wr_en),
        .wr_data  (fifo_wr_data),
        .full     (fifo_full),

        // Read domain (slave side)
        .rd_clk   (s_axi_aclk),
        .rd_rst_n (s_axi_aresetn),
        .rd_en    (fifo_rd_en),
        .rd_data  (fifo_rd_data),
        .empty    (fifo_empty)
    );

endmodule

`resetall
