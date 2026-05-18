`resetall
`timescale 1ns / 1ps
`default_nettype none

module b_bridge #(
    parameter FIFO_DEPTH = 4
) (
    // Slave-side clock domain (read side of FIFO)
    input  wire        s_axi_aclk,
    input  wire        s_axi_aresetn,
    // Master-side clock domain (write side of FIFO)
    input  wire        m_axi_aclk,
    input  wire        m_axi_aresetn,
    // Master-side AXI B inputs (source — writes into FIFO)
    input  wire        m_axi_bvalid,
    output wire        m_axi_bready,
    input  wire  [1:0] m_axi_bresp,
    // Slave-side AXI B outputs (sink — reads from FIFO)
    output wire        s_axi_bvalid,
    input  wire        s_axi_bready,
    output wire  [1:0] s_axi_bresp
);

    // ----------------------------------------------------------------
    // Internal wires to/from async FIFO
    // ----------------------------------------------------------------
    // Write side (m_domain)
    wire        fifo_wr_en;
    wire [1:0]  fifo_wr_data;
    wire        fifo_full;

    // Read side (s_domain)
    wire        fifo_rd_en;
    wire [1:0]  fifo_rd_data;
    wire        fifo_empty;

    // ----------------------------------------------------------------
    // Master side (write side — m_axi_aclk domain)
    // m_axi_bready must be combinational and NOT depend on m_axi_bvalid
    // to prevent deadlock per AXI spec.
    // ----------------------------------------------------------------
    assign m_axi_bready = ~fifo_full;

    // Write enable: handshake occurs when both valid and ready are high
    assign fifo_wr_en   = m_axi_bvalid & m_axi_bready;
    assign fifo_wr_data = m_axi_bresp;

    // ----------------------------------------------------------------
    // Slave side (read side — s_axi_aclk domain)
    // s_axi_bvalid must NOT depend on s_axi_bready (AXI rule).
    // ----------------------------------------------------------------
    assign s_axi_bvalid = ~fifo_empty;
    assign s_axi_bresp  = fifo_rd_data;

    // Read enable: pop from FIFO on handshake
    assign fifo_rd_en   = s_axi_bvalid & s_axi_bready;

    // ----------------------------------------------------------------
    // Async FIFO instantiation
    // B channel: data flows M_domain -> S_domain (reverse direction)
    //   wr_clk  = m_axi_aclk  (master domain writes BRESP)
    //   rd_clk  = s_axi_aclk  (slave domain reads BRESP)
    // ----------------------------------------------------------------
    async_fifo_gray #(
        .DATA_WIDTH (2),
        .FIFO_DEPTH (FIFO_DEPTH)
    ) u_async_fifo (
        // Write side (m_domain)
        .wr_clk    (m_axi_aclk),
        .wr_rst_n  (m_axi_aresetn),
        .wr_en     (fifo_wr_en),
        .wr_data   (fifo_wr_data),
        .full      (fifo_full),
        // Read side (s_domain)
        .rd_clk    (s_axi_aclk),
        .rd_rst_n  (s_axi_aresetn),
        .rd_en     (fifo_rd_en),
        .rd_data   (fifo_rd_data),
        .empty     (fifo_empty)
    );

endmodule

`resetall
