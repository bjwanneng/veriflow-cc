`resetall
`timescale 1ns / 1ps
`default_nettype none

module aw_bridge #(
    parameter FIFO_DEPTH = 4
) (
    // Slave-side clock domain
    input  wire        s_axi_aclk,
    input  wire        s_axi_aresetn,
    // Master-side clock domain
    input  wire        m_axi_aclk,
    input  wire        m_axi_aresetn,
    // Slave-side AW channel (inputs)
    input  wire        s_axi_awvalid,
    output wire        s_axi_awready,
    input  wire [31:0] s_axi_awaddr,
    input  wire [2:0]  s_axi_awprot,
    // Master-side AW channel (outputs)
    output wire        m_axi_awvalid,
    input  wire        m_axi_awready,
    output wire [31:0] m_axi_awaddr,
    output wire [2:0]  m_axi_awprot
);

    // ---------------------------------------------------------------
    // Internal wires to/from async FIFO
    // ---------------------------------------------------------------
    // Packed data: {awaddr[31:0], awprot[2:0]} = 35 bits
    localparam FIFO_DATA_W = 35;

    wire                    fifo_full;
    wire                    fifo_empty;
    wire                    fifo_wr_en;
    wire [FIFO_DATA_W-1:0] fifo_wr_data;
    wire                    fifo_rd_en;
    wire [FIFO_DATA_W-1:0] fifo_rd_data;

    // ---------------------------------------------------------------
    // Slave side (s_domain): write into FIFO
    // ---------------------------------------------------------------
    // awready is combinational: ready when FIFO is not full
    // (must NOT depend on awvalid per AXI spec)
    assign s_axi_awready = ~fifo_full;

    // Write enable: handshake occurs when valid && ready
    assign fifo_wr_en = s_axi_awvalid & s_axi_awready;

    // Pack address and protection into FIFO write data
    assign fifo_wr_data = {s_axi_awaddr, s_axi_awprot};

    // ---------------------------------------------------------------
    // Master side (m_domain): read from FIFO
    // ---------------------------------------------------------------
    // Registered outputs for master-side
    reg        m_axi_awvalid_reg;
    reg [31:0] m_axi_awaddr_reg;
    reg [2:0]  m_axi_awprot_reg;

    // Read enable: handshake occurs when valid && ready
    assign fifo_rd_en = m_axi_awvalid_reg & m_axi_awready;

    // Registered output assignments
    assign m_axi_awvalid = m_axi_awvalid_reg;
    assign m_axi_awaddr  = m_axi_awaddr_reg;
    assign m_axi_awprot  = m_axi_awprot_reg;

    // Master-side sequential logic in m_domain
    always @(posedge m_axi_aclk or negedge m_axi_aresetn) begin
        if (!m_axi_aresetn) begin
            m_axi_awvalid_reg <= 1'b0;
            m_axi_awaddr_reg  <= 32'd0;
            m_axi_awprot_reg  <= 3'd0;
        end else begin
            if (fifo_rd_en) begin
                // Handshake completed: pop consumed the entry
                // Check if FIFO has more data after this pop
                m_axi_awvalid_reg <= 1'b0;
                m_axi_awaddr_reg  <= 32'd0;
                m_axi_awprot_reg  <= 3'd0;
            end else if (!fifo_empty && !m_axi_awvalid_reg) begin
                // FIFO has data and we are not already driving valid
                m_axi_awvalid_reg <= 1'b1;
                m_axi_awaddr_reg  <= fifo_rd_data[34:3];
                m_axi_awprot_reg  <= fifo_rd_data[2:0];
            end
            // else: hold current values (valid stays high until handshake)
        end
    end

    // ---------------------------------------------------------------
    // Async FIFO instance (Gray-code pointer crossing)
    // ---------------------------------------------------------------
    async_fifo_gray #(
        .DATA_WIDTH (FIFO_DATA_W),
        .FIFO_DEPTH (FIFO_DEPTH)
    ) u_async_fifo (
        // Write domain (s_domain)
        .wr_clk   (s_axi_aclk),
        .wr_rst_n (s_axi_aresetn),
        .wr_en    (fifo_wr_en),
        .wr_data  (fifo_wr_data),
        .full     (fifo_full),
        // Read domain (m_domain)
        .rd_clk   (m_axi_aclk),
        .rd_rst_n (m_axi_aresetn),
        .rd_en    (fifo_rd_en),
        .rd_data  (fifo_rd_data),
        .empty    (fifo_empty)
    );

endmodule

`resetall
