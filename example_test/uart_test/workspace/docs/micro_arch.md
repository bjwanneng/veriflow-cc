# Microarchitecture Document: uart_top

## 1. Module Partitioning

| Module | Responsibility | Hierarchy | Clock Domain |
|--------|---------------|-----------|-------------|
| uart_top | Structural wrapper — instantiates all submodules, reset synchronizer | 0 (top) | clk_sys (50 MHz) |
| baud_gen | Free-running counter producing 16x baud rate tick pulses | 1 | clk_sys |
| uart_tx | FSM-driven parallel-to-serial transmitter (8N1) | 1 | clk_sys |
| uart_rx | FSM-driven serial-to-parallel receiver with 16x oversampling, input synchronizer | 1 | clk_sys |

All modules operate in a single clock domain (clk_sys, 50 MHz). No clock domain crossings except
for the external uart_rxd input, handled by a 2-stage synchronizer inside uart_rx.

## 2. Datapath

### 2.1 TX Datapath
```
tx_data[7:0] --> [Shift Register] --> uart_txd (serial out)
                       ^
                  tx_en latches tx_data into shift_reg
                  Shift right on each bit boundary (every 16 tick_16x)
```

- tx_en pulse captures tx_data[7:0] into an 8-bit shift register
- FSM drives uart_txd: start bit (0), shift_reg[0] for each data bit (LSB first), stop bit (1)
- Shift register shifts right after each data bit period completes

### 2.2 RX Datapath
```
uart_rxd --> [2-stage sync] --> rxd_sync --> [FSM + tick counter] --> shift_reg[7:0] --> rx_data[7:0]
                                                                           |
                                                                     rx_frame_err
```

- uart_rxd passes through 2 flip-flop synchronizer → rxd_sync
- FSM detects falling edge (start bit), verifies at midpoint (tick 7), then samples each data bit at midpoint
- shift_reg accumulates bits LSB first; after 8 bits + stop bit check, outputs rx_data and rx_done pulse

### 2.3 Baud Rate Generator
```
clk (50 MHz) --> [Counter 0..26] --> tick_16x pulse (every 27 clocks)
```

- DIV = CLK_FREQ / (BAUD_RATE * OVERSAMPLE) = 27
- tick_16x pulses high for 1 system clock cycle every 27 system clocks
- Shared by both TX and RX

## 3. Control Logic

### 3.1 TX FSM

```
         tx_en
TX_IDLE ────────> TX_START ────────> TX_DATA ────────> TX_STOP ────> TX_IDLE
(uart_txd=1)     (uart_txd=0)       (uart_txd=shift[0])  (uart_txd=1)
(tx_busy=0)      (tx_busy=1)        (tx_busy=1)           (tx_busy=1 → 0)
                  tick_cnt==15       tick_cnt==15          tick_cnt==15
                                  && bit_cnt==7
```

State encoding (2 bits): TX_IDLE=0, TX_START=1, TX_DATA=2, TX_STOP=3

### 3.2 RX FSM

```
                    falling edge           start valid           8 bits done
RX_IDLE ──────────> RX_START ──────────> RX_DATA ──────────> RX_STOP ────> RX_IDLE
                    (tick_cnt=0)           (bit_cnt=0)          (check stop)
                            |
                            v  start invalid (tick_cnt==7, rxd_sync==1)
                         RX_IDLE
```

State encoding (2 bits): RX_IDLE=0, RX_START=1, RX_DATA=2, RX_STOP=3

Special behavior:
- RX_START checks rxd_sync at tick_cnt==7 (midpoint). If high, it's a false start → back to RX_IDLE.
- RX_DATA samples rxd_sync into shift_reg[bit_cnt] at tick_cnt==7 (midpoint).
- RX_STOP checks rxd_sync at tick_cnt==7. If low → rx_frame_err=1. Either way, asserts rx_done.

### 3.3 Reset Synchronizer (in uart_top)

```verilog
reg rst_n_meta, rst_n_sync;
always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        rst_n_meta <= 1'b0;
        rst_n_sync <= 1'b0;
    end else begin
        rst_n_meta <= 1'b1;
        rst_n_sync <= rst_n_meta;
    end
end
```

External rst_n drives the synchronizer only. All submodules receive rst_n_sync.

## 4. Interface Protocol

### 4.1 Inter-Module Signals

| Source | Dest | Signal | Width | Protocol | Description |
|--------|------|--------|-------|----------|-------------|
| uart_top | baud_gen | clk | 1 | clock | System clock |
| uart_top | baud_gen | rst_n | 1 | reset | Synchronized reset (rst_n_sync) |
| baud_gen | uart_tx | tick_16x | 1 | pulse | 1-cycle-high pulse every 27 sys clocks |
| baud_gen | uart_rx | tick_16x | 1 | pulse | Same as above |
| uart_top | uart_tx | tx_data[7:0] | 8 | data | Byte to transmit, latched on tx_en |
| uart_top | uart_tx | tx_en | 1 | pulse | Start transmission (must be high when !tx_busy) |
| uart_tx | uart_top | uart_txd | 1 | serial | UART transmit line (idle high) |
| uart_tx | uart_top | tx_busy | 1 | level | High during active transmission |
| uart_top | uart_rx | uart_rxd | 1 | serial | UART receive line (external, async) |
| uart_rx | uart_top | rx_data[7:0] | 8 | data | Received byte, valid when rx_done=1 |
| uart_rx | uart_top | rx_done | 1 | pulse | 1-cycle-high pulse when frame received |
| uart_rx | uart_top | rx_frame_err | 1 | level | High if stop bit was invalid, clears on next start bit |

### 4.2 Timing
- tx_en must not be asserted while tx_busy is high
- rx_done pulse lasts 1 system clock cycle
- rx_frame_err is level-held: asserted on frame error, deasserted when next start bit is detected

## 5. Timing Closure Plan

### 5.1 Critical Path
The longest combinational path is in uart_rx:
- tick_16x → tick_cnt increment → comparison (tick_cnt==7) → FSM state logic → rxd_sync mux → shift_reg write

At 50 MHz (20 ns period), this path is trivially fast. No timing closure concerns.

### 5.2 Clock Frequency
Target: 50 MHz (20 ns period). Estimated worst-case logic depth: ~5 LUT levels (~5 ns).
Timing margin: > 70%.

## 6. Resource Plan

| Module | Estimated LUTs | Estimated FFs | Notes |
|--------|---------------|---------------|-------|
| baud_gen | 5 | 5 | 5-bit counter + comparator |
| uart_tx | 20 | 17 | 2-bit FSM + 8-bit shift + 4-bit tick_cnt + 3-bit bit_cnt |
| uart_rx | 30 | 20 | 2-bit FSM + 8-bit shift + 4-bit tick_cnt + 3-bit bit_cnt + 2-bit sync + 1-bit err |
| uart_top | 2 | 2 | Reset synchronizer |
| **Total** | **~57** | **~44** | Well within any FPGA limits |

No BRAMs or DSPs needed.

## 7. Key Design Decisions

1. **16x Oversampling**: Chosen over simple clock division for robust bit-center sampling.
   This adds ~20 FFs (counters) but significantly improves noise immunity.

2. **No Parity**: Per requirement, the PARITY state in the TX FSM is skipped. Data transitions
   directly from TX_DATA to TX_STOP after 8 bits.

3. **Fixed Baud Rate (115200)**: Parameterized via module parameters (CLK_FREQ, BAUD_RATE, OVERSAMPLE)
   but default values are hardcoded. DIV=27 gives 0.47% error — well within tolerance.

4. **Separate TX and RX FSMs**: Independent state machines allow full-duplex operation. TX and RX
   can operate simultaneously without interference.

5. **Input Synchronizer in RX**: uart_rxd is asynchronous to clk_sys. A 2-stage synchronizer
   reduces metastability probability to negligible levels.

6. **Reset Synchronizer in Top**: External rst_n passes through a 2-stage synchronizer to produce
   rst_n_sync. All submodules use rst_n_sync as their reset. This ensures synchronous reset release.

7. **Midpoint Sampling (tick 7)**: RX samples data at tick 7 out of 0-15, placing the sample point
   at approximately the center of each bit period for maximum noise margin.
