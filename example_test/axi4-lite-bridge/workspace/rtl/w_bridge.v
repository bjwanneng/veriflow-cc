`resetall
`timescale 1ns / 1ps
`default_nettype none

module w_bridge #(
    parameter FIFO_DEPTH = 4
) (
    // Slave-side clock domain
    input  wire        s_axi_aclk,
    input  wire        s_axi_aresetn,
    // Master-side clock domain
    input  wire        m_axi_aclk,
    input  wire        m_axi_aresetn,
    // Slave-side AXI W interface (inputs)
    input  wire        s_axi_wvalid,
    input  wire [31:0] s_axi_wdata,
    input  wire [3:0]  s_axi_wstrb,
    // Slave-side AXI W interface (output)
    output wire        s_axi_wready,
    // Master-side AXI W interface (outputs)
    output wire        m_axi_wvalid,
    output wire [31:0] m_axi_wdata,
    output wire [3:0]  m_axi_wstrb,
    // Master-side AXI W interface (input)
    input  wire        m_axi_wready
);

    // ---------------------------------------------------------------
    // Internal wires to/from async FIFO
    // ---------------------------------------------------------------
    // Packed data: {wdata[31:0], wstrb[3:0]} = 36 bits
    wire [35:0] fifo_wr_data;
    wire        fifo_wr_en;
    wire        fifo_full;

    wire [35:0] fifo_rd_data;
    wire        fifo_rd_en;
    wire        fifo_empty;

    assign fifo_wr_data = {s_axi_wdata, s_axi_wstrb};

    // ---------------------------------------------------------------
    // Slave-side: s_axi_wready = !fifo_full (combinational, must not
    // depend on wvalid to prevent AXI deadlock)
    // ---------------------------------------------------------------
    assign s_axi_wready = ~fifo_full;

    // Write enable: handshake occurs when valid && ready
    assign fifo_wr_en = s_axi_wvalid & s_axi_wready;

    // ---------------------------------------------------------------
    // Master-side: m_axi_wvalid = !fifo_empty (combinational, must not
    // depend on wready to prevent AXI deadlock)
    // ---------------------------------------------------------------
    assign m_axi_wvalid = ~fifo_empty;

    // Unpack FIFO read data into separate wdata and wstrb
    assign m_axi_wdata = fifo_rd_data[35:4];
    assign m_axi_wstrb = fifo_rd_data[3:0];

    // Read enable: handshake occurs when valid && ready
    assign fifo_rd_en = m_axi_wvalid & m_axi_wready;

    // ---------------------------------------------------------------
    // Instantiate async FIFO (Gray-code pointer crossing)
    // Write side in s_domain, read side in m_domain
    // ---------------------------------------------------------------
    async_fifo_gray #(
        .DATA_WIDTH (36),
        .FIFO_DEPTH (FIFO_DEPTH)
    ) u_async_fifo (
        // Write domain (slave side)
        .wr_clk    (s_axi_aclk),
        .wr_rst_n  (s_axi_aresetn),
        .wr_en     (fifo_wr_en),
        .wr_data   (fifo_wr_data),
        .full      (fifo_full),

        // Read domain (master side)
        .rd_clk    (m_axi_aclk),
        .rd_rst_n  (m_axi_aresetn),
        .rd_en     (fifo_rd_en),
        .rd_data   (fifo_rd_data),
        .empty     (fifo_empty)
    );

endmodule

`resetall
