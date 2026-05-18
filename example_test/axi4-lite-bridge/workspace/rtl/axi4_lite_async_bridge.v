`resetall
`timescale 1ns / 1ps
`default_nettype none

module axi4_lite_async_bridge #(
    parameter ADDR_WIDTH = 32,
    parameter DATA_WIDTH = 32,
    parameter RESP_WIDTH = 2,
    parameter FIFO_DEPTH = 4
) (
    // Clocks and resets
    input  wire              s_axi_aclk,
    input  wire              s_axi_aresetn,
    input  wire              m_axi_aclk,
    input  wire              m_axi_aresetn,

    // Slave-side AXI (AW channel)
    input  wire              s_axi_awvalid,
    output wire              s_axi_awready,
    input  wire [ADDR_WIDTH-1:0] s_axi_awaddr,
    input  wire [2:0]        s_axi_awprot,

    // Slave-side AXI (W channel)
    input  wire              s_axi_wvalid,
    output wire              s_axi_wready,
    input  wire [DATA_WIDTH-1:0] s_axi_wdata,
    input  wire [3:0]        s_axi_wstrb,

    // Slave-side AXI (B channel)
    output wire              s_axi_bvalid,
    input  wire              s_axi_bready,
    output wire [RESP_WIDTH-1:0] s_axi_bresp,

    // Slave-side AXI (AR channel)
    input  wire              s_axi_arvalid,
    output wire              s_axi_arready,
    input  wire [ADDR_WIDTH-1:0] s_axi_araddr,
    input  wire [2:0]        s_axi_arprot,

    // Slave-side AXI (R channel)
    output wire              s_axi_rvalid,
    input  wire              s_axi_rready,
    output wire [DATA_WIDTH-1:0] s_axi_rdata,
    output wire [RESP_WIDTH-1:0] s_axi_rresp,

    // Master-side AXI (AW channel)
    output wire              m_axi_awvalid,
    input  wire              m_axi_awready,
    output wire [ADDR_WIDTH-1:0] m_axi_awaddr,
    output wire [2:0]        m_axi_awprot,

    // Master-side AXI (W channel)
    output wire              m_axi_wvalid,
    input  wire              m_axi_wready,
    output wire [DATA_WIDTH-1:0] m_axi_wdata,
    output wire [3:0]        m_axi_wstrb,

    // Master-side AXI (B channel)
    input  wire              m_axi_bvalid,
    output wire              m_axi_bready,
    input  wire [RESP_WIDTH-1:0] m_axi_bresp,

    // Master-side AXI (AR channel)
    output wire              m_axi_arvalid,
    input  wire              m_axi_arready,
    output wire [ADDR_WIDTH-1:0] m_axi_araddr,
    output wire [2:0]        m_axi_arprot,

    // Master-side AXI (R channel)
    input  wire              m_axi_rvalid,
    output wire              m_axi_rready,
    input  wire [DATA_WIDTH-1:0] m_axi_rdata,
    input  wire [RESP_WIDTH-1:0] m_axi_rresp
);

    // ---------------------------------------------------------------
    // AW channel bridge (S_domain -> M_domain)
    // ---------------------------------------------------------------
    aw_bridge #(
        .FIFO_DEPTH(FIFO_DEPTH)
    ) u_aw_bridge (
        .s_axi_aclk    (s_axi_aclk),
        .s_axi_aresetn (s_axi_aresetn),
        .m_axi_aclk    (m_axi_aclk),
        .m_axi_aresetn (m_axi_aresetn),
        .s_axi_awvalid (s_axi_awvalid),
        .s_axi_awready (s_axi_awready),
        .s_axi_awaddr  (s_axi_awaddr),
        .s_axi_awprot  (s_axi_awprot),
        .m_axi_awvalid (m_axi_awvalid),
        .m_axi_awready (m_axi_awready),
        .m_axi_awaddr  (m_axi_awaddr),
        .m_axi_awprot  (m_axi_awprot)
    );

    // ---------------------------------------------------------------
    // W channel bridge (S_domain -> M_domain)
    // ---------------------------------------------------------------
    w_bridge #(
        .FIFO_DEPTH(FIFO_DEPTH)
    ) u_w_bridge (
        .s_axi_aclk    (s_axi_aclk),
        .s_axi_aresetn (s_axi_aresetn),
        .m_axi_aclk    (m_axi_aclk),
        .m_axi_aresetn (m_axi_aresetn),
        .s_axi_wvalid  (s_axi_wvalid),
        .s_axi_wready  (s_axi_wready),
        .s_axi_wdata   (s_axi_wdata),
        .s_axi_wstrb   (s_axi_wstrb),
        .m_axi_wvalid  (m_axi_wvalid),
        .m_axi_wready  (m_axi_wready),
        .m_axi_wdata   (m_axi_wdata),
        .m_axi_wstrb   (m_axi_wstrb)
    );

    // ---------------------------------------------------------------
    // B channel bridge (M_domain -> S_domain)
    // ---------------------------------------------------------------
    b_bridge #(
        .FIFO_DEPTH(FIFO_DEPTH)
    ) u_b_bridge (
        .s_axi_aclk    (s_axi_aclk),
        .s_axi_aresetn (s_axi_aresetn),
        .m_axi_aclk    (m_axi_aclk),
        .m_axi_aresetn (m_axi_aresetn),
        .m_axi_bvalid  (m_axi_bvalid),
        .m_axi_bready  (m_axi_bready),
        .m_axi_bresp   (m_axi_bresp),
        .s_axi_bvalid  (s_axi_bvalid),
        .s_axi_bready  (s_axi_bready),
        .s_axi_bresp   (s_axi_bresp)
    );

    // ---------------------------------------------------------------
    // AR channel bridge (S_domain -> M_domain)
    // ---------------------------------------------------------------
    ar_bridge #(
        .FIFO_DEPTH(FIFO_DEPTH)
    ) u_ar_bridge (
        .s_axi_aclk    (s_axi_aclk),
        .s_axi_aresetn (s_axi_aresetn),
        .m_axi_aclk    (m_axi_aclk),
        .m_axi_aresetn (m_axi_aresetn),
        .s_axi_arvalid (s_axi_arvalid),
        .s_axi_arready (s_axi_arready),
        .s_axi_araddr  (s_axi_araddr),
        .s_axi_arprot  (s_axi_arprot),
        .m_axi_arvalid (m_axi_arvalid),
        .m_axi_arready (m_axi_arready),
        .m_axi_araddr  (m_axi_araddr),
        .m_axi_arprot  (m_axi_arprot)
    );

    // ---------------------------------------------------------------
    // R channel bridge (M_domain -> S_domain)
    // ---------------------------------------------------------------
    r_bridge #(
        .FIFO_DEPTH(FIFO_DEPTH)
    ) u_r_bridge (
        .s_axi_aclk    (s_axi_aclk),
        .s_axi_aresetn (s_axi_aresetn),
        .m_axi_aclk    (m_axi_aclk),
        .m_axi_aresetn (m_axi_aresetn),
        .m_axi_rvalid  (m_axi_rvalid),
        .m_axi_rready  (m_axi_rready),
        .m_axi_rdata   (m_axi_rdata),
        .m_axi_rresp   (m_axi_rresp),
        .s_axi_rvalid  (s_axi_rvalid),
        .s_axi_rready  (s_axi_rready),
        .s_axi_rdata   (s_axi_rdata),
        .s_axi_rresp   (s_axi_rresp)
    );

endmodule

`resetall
