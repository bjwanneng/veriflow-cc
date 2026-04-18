# Behavior Specification: uart_top

## 1. Domain Knowledge

### 1.1 Background
UART (Universal Asynchronous Receiver-Transmitter) is a widely-used serial communication protocol
that enables data exchange between devices without a shared clock. The transmitter converts parallel
data into a serial bitstream with framing markers (start bit, stop bit); the receiver reassembles the
bits into parallel data using a pre-agreed baud rate. This design implements a full UART transceiver
with a 16x oversampling receiver for robust data recovery.

### 1.2 Key Concepts
- **Baud Rate**: The number of symbol changes per second on the communication line. For 115200 baud,
  each bit period is ~8.68 us.
- **Frame Format (8N1)**: 1 start bit (low), 8 data bits (LSB first), no parity bit, 1 stop bit (high).
  Total: 10 bit periods per frame.
- **16x Oversampling**: The receiver samples the line at 16x the baud rate to locate the center of each
  bit, maximizing noise margin.
- **Metastability & Two-Stage Synchronizer**: External asynchronous inputs (uart_rxd) pass through two
  flip-flops in the clock domain to reduce the probability of metastable states.
- **Frame Error**: If the stop bit is not high when expected, the received data is corrupted and
  rx_frame_err is asserted.

### 1.3 References
- UART protocol: industry-standard asynchronous serial communication, no formal standard number
  (commonly referenced as RS-232 signaling levels, but this design uses digital levels)

### 1.4 Glossary
| Term | Definition |
|------|-----------|
| TXD | Transmit Data serial line |
| RXD | Receive Data serial line |
| LSB | Least Significant Bit — sent first in UART data frame |
| Oversampling | Sampling at a multiple of the baud rate to find the bit center |
| Frame Error | Error detected when stop bit is not the expected value (high) |
| Tick | A single clock-enable pulse at the oversampling rate |

## 2. Module Behavior: uart_top

### 2.1 Cycle-Accurate Behavior

#### Normal Operation
| Cycle | Condition | Action | Output Change | Next State |
|-------|-----------|--------|---------------|------------|
| 0 | Power-on, rst_n=0 | Assert reset to all submodules | uart_txd=1, tx_busy=0, rx_done=0, rx_frame_err=0 | Reset |
| 1 | rst_n rises | Synchronizer stages begin propagating | rst_n_meta=1 | Reset recovery |
| 2 | rst_n_sync rises | Internal reset released, submodules active | Normal operation begins | Idle |
| N | tx_en pulse && !tx_busy | Latch tx_data, start TX FSM | tx_busy=1 | Active |

#### Reset Behavior
| Cycle | Condition | Action | Output Change |
|-------|-----------|--------|---------------|
| -1 | rst_n asserted (low) | Clear synchronizer, all submodules reset | uart_txd=1, tx_busy=0, rx_done=0, rx_frame_err=0 |
| 0 | rst_n de-asserted (high) | Synchronizer begins propagation | rst_n_meta goes high |
| 1 | rst_n_meta high | Second sync stage | rst_n_sync goes high, internal modules start |
| 2 | rst_n_sync high | Normal operation | Modules ready for data |

### 2.2 FSM Specification
No FSM in uart_top — it is a structural wrapper that instantiates submodules and the reset synchronizer.

### 2.3 Register Requirements
| Register | Width (bits) | Reset Value | Purpose |
|----------|-------------|-------------|---------|
| rst_n_meta | 1 | 0 | First stage of reset synchronizer |
| rst_n_sync | 1 | 0 | Second stage of reset synchronizer (used as internal reset) |

### 2.4 Timing Contracts
- **Latency**: 2 cycles (reset synchronizer delay)
- **Throughput**: Determined by submodules
- **Backpressure behavior**: N/A (structural wrapper)
- **Reset recovery**: 2 cycles after rst_n de-assertion

### 2.5 Algorithm Pseudocode
No complex algorithm — structural instantiation of submodules and reset synchronizer.

### 2.6 Protocol Details
Internal wiring only. External UART protocol is handled by uart_tx and uart_rx submodules.

---

## 3. Module Behavior: baud_gen

### 3.1 Cycle-Accurate Behavior

#### Normal Operation
| Cycle | Condition | Action | Output Change | Next State |
|-------|-----------|--------|---------------|------------|
| N | cnt < DIV-1 | Increment counter | tick_16x=0 | Counting |
| N+1 | cnt == DIV-1 | Reset counter, emit tick | tick_16x=1, cnt=0 | Counting |

DIV = CLK_FREQ / (BAUD_RATE * OVERSAMPLE) = 50000000 / (115200 * 16) = 27

#### Reset Behavior
| Cycle | Condition | Action | Output Change |
|-------|-----------|--------|---------------|
| -1 | rst_n=0 | Clear counter | cnt=0, tick_16x=0 |
| 0 | rst_n=1 (synced) | Begin counting | cnt=0 |

### 3.2 FSM Specification
No FSM — free-running counter.

### 3.3 Register Requirements
| Register | Width (bits) | Reset Value | Purpose |
|----------|-------------|-------------|---------|
| cnt | 5 | 0 | Divider counter, counts 0 to DIV-1 (0 to 26) |

### 3.4 Timing Contracts
- **Latency**: 0 cycles (comparators are combinational)
- **Throughput**: 1 tick per 27 system clock cycles
- **Backpressure behavior**: N/A (free-running)
- **Reset recovery**: 1 cycle

### 3.5 Algorithm Pseudocode
```
DIV = CLK_FREQ / (BAUD_RATE * OVERSAMPLE)  // = 27
cnt = 0

every posedge clk:
    if (!rst_n):
        cnt = 0
        tick_16x = 0
    else:
        if cnt == DIV - 1:
            cnt = 0
            tick_16x = 1
        else:
            cnt = cnt + 1
            tick_16x = 0
```

### 3.6 Protocol Details
Single pulse output. tick_16x is high for exactly 1 system clock cycle every DIV cycles.

---

## 4. Module Behavior: uart_tx

### 4.1 Cycle-Accurate Behavior

#### Normal Operation
| Cycle/Tick | Condition | Action | Output Change | Next State |
|------------|-----------|--------|---------------|------------|
| - | IDLE state, tx_en pulse | Latch tx_data into shift register, set tx_busy=1 | tx_busy=1 | START |
| T0 (tick) | START state, tick_16x=1 | Drive uart_txd=0 (start bit), start bit counter | uart_txd=0 | START (counting) |
| T15 (tick) | START state, tick_cnt==15 | bit_cnt=0, tick_cnt=0 | uart_txd=0 | DATA |
| T0 (tick) | DATA state, tick_16x=1 | Drive uart_txd=shift_reg[0] | uart_txd=data[bit] | DATA (counting) |
| T15 (tick) | DATA state, tick_cnt==15 && bit_cnt<7 | Shift register right, increment bit_cnt | - | DATA |
| T15 (tick) | DATA state, tick_cnt==15 && bit_cnt==7 | All 8 bits sent | - | STOP |
| T0 (tick) | STOP state, tick_16x=1 | Drive uart_txd=1 (stop bit) | uart_txd=1 | STOP (counting) |
| T15 (tick) | STOP state, tick_cnt==15 | Transmission complete, tx_busy=0 | tx_busy=0 | IDLE |

#### Reset Behavior
| Cycle | Condition | Action | Output Change |
|-------|-----------|--------|---------------|
| -1 | rst_n=0 | Clear all registers | uart_txd=1, tx_busy=0 |
| 0 | rst_n=1 (synced) | Enter IDLE | uart_txd=1, tx_busy=0 |

### 4.2 FSM Specification

#### States
| State Name | Description | Outputs |
|-----------|-------------|---------|
| TX_IDLE | Waiting for tx_en | uart_txd=1, tx_busy=0 |
| TX_START | Sending start bit (low) | uart_txd=0, tx_busy=1 |
| TX_DATA | Sending 8 data bits LSB first | uart_txd=data bit, tx_busy=1 |
| TX_STOP | Sending stop bit (high) | uart_txd=1, tx_busy=1 |

#### Transitions
| From | To | Condition |
|------|----|-----------|
| TX_IDLE | TX_START | tx_en==1 (on tick_16x edge) |
| TX_START | TX_DATA | tick_cnt==15 (16 ticks counted) |
| TX_DATA | TX_DATA | tick_cnt==15 && bit_cnt < 7 |
| TX_DATA | TX_STOP | tick_cnt==15 && bit_cnt == 7 |
| TX_STOP | TX_IDLE | tick_cnt==15 |

#### Initial State: TX_IDLE

### 4.3 Register Requirements
| Register | Width (bits) | Reset Value | Purpose |
|----------|-------------|-------------|---------|
| state | 2 | 0 (TX_IDLE) | FSM state |
| shift_reg | 8 | 0 | Data being transmitted |
| bit_cnt | 3 | 0 | Data bit counter (0-7) |
| tick_cnt | 4 | 0 | Oversampling tick counter (0-15) |

### 4.4 Timing Contracts
- **Latency**: 160 tick_16x cycles = 160 * 27 = 4320 system clocks = ~86.4 us (full frame: start + 8 data + stop)
- **Throughput**: 1 frame per 160 tick_16x cycles
- **Backpressure behavior**: tx_busy flag — user must not assert tx_en while busy
- **Reset recovery**: 1 cycle

### 4.5 Algorithm Pseudocode
```
state = TX_IDLE
shift_reg = 0
bit_cnt = 0
tick_cnt = 0

every posedge clk:
    if (!rst_n):
        state = TX_IDLE
        uart_txd = 1
        tx_busy = 0
    else if (tick_16x):
        tick_cnt = tick_cnt + 1

        switch (state):
            TX_IDLE:
                uart_txd = 1
                tx_busy = 0
                if (tx_en):
                    shift_reg = tx_data
                    tx_busy = 1
                    tick_cnt = 0
                    state = TX_START
                    uart_txd = 0  // start bit

            TX_START:
                uart_txd = 0
                if (tick_cnt == 15):
                    tick_cnt = 0
                    bit_cnt = 0
                    state = TX_DATA

            TX_DATA:
                uart_txd = shift_reg[0]
                if (tick_cnt == 15):
                    tick_cnt = 0
                    shift_reg = shift_reg >> 1
                    if (bit_cnt == 7):
                        state = TX_STOP
                    else:
                        bit_cnt = bit_cnt + 1

            TX_STOP:
                uart_txd = 1
                if (tick_cnt == 15):
                    tx_busy = 0
                    state = TX_IDLE
```

### 4.6 Protocol Details
UART 8N1 frame on uart_txd:
```
IDLE high ___
               \___start___D0___D1___D2___D3___D4___D5___D6___D7___stop___IDLE high
               bit0        bit1  bit2  ...
```
Each bit is 16 tick_16x periods wide.

---

## 5. Module Behavior: uart_rx

### 5.1 Cycle-Accurate Behavior

#### Normal Operation
| Cycle/Tick | Condition | Action | Output Change | Next State |
|------------|-----------|--------|---------------|------------|
| - | IDLE state, falling edge on rxd_sync | Start bit detected, start tick counter | tick_cnt=0 | START_CHK |
| T7 (tick) | START_CHK, tick_cnt==7 | Verify start bit still low at midpoint | - | START_CHK (continue) |
| T15 (tick) | START_CHK, tick_cnt==15, rxd_sync==0 | Start bit confirmed | bit_cnt=0, tick_cnt=0 | DATA |
| T15 (tick) | START_CHK, tick_cnt==15, rxd_sync==1 | False start (glitch) | - | IDLE |
| T7/T8 (tick) | DATA, tick_cnt==7 or 8 | Sample rxd_sync into shift_reg[bit_cnt] | - | DATA (continue) |
| T15 (tick) | DATA, tick_cnt==15 && bit_cnt<7 | Increment bit_cnt | bit_cnt+1 | DATA |
| T15 (tick) | DATA, tick_cnt==15 && bit_cnt==7 | All 8 bits received | - | STOP |
| T7/T8 (tick) | STOP, tick_cnt==7 or 8 | Sample stop bit | - | STOP (continue) |
| T15 (tick) | STOP, tick_cnt==15, rxd_sync==1 | Valid stop bit | rx_data=shift_reg, rx_done=1, rx_frame_err=0 | IDLE |
| T15 (tick) | STOP, tick_cnt==15, rxd_sync==0 | Frame error | rx_data=shift_reg, rx_done=1, rx_frame_err=1 | IDLE |

#### Reset Behavior
| Cycle | Condition | Action | Output Change |
|-------|-----------|--------|---------------|
| -1 | rst_n=0 | Clear all registers | rx_data=0, rx_done=0, rx_frame_err=0 |
| 0 | rst_n=1 (synced) | Enter IDLE | - |

### 5.2 FSM Specification

#### States
| State Name | Description | Outputs |
|-----------|-------------|---------|
| RX_IDLE | Waiting for falling edge on rxd_sync | rx_done=0, rx_frame_err=0 |
| RX_START | Verifying start bit at midpoint | - |
| RX_DATA | Receiving 8 data bits at midpoints | - |
| RX_STOP | Verifying stop bit | - |

#### Transitions
| From | To | Condition |
|------|----|-----------|
| RX_IDLE | RX_START | falling edge detected on rxd_sync (rxd_sync==0 && rxd_sync_d1==1) |
| RX_START | RX_DATA | tick_cnt==15 && rxd_sync==0 (start bit valid) |
| RX_START | RX_IDLE | tick_cnt==15 && rxd_sync==1 (false start) |
| RX_DATA | RX_DATA | tick_cnt==15 && bit_cnt < 7 |
| RX_DATA | RX_STOP | tick_cnt==15 && bit_cnt == 7 |
| RX_STOP | RX_IDLE | tick_cnt==15 |

#### Initial State: RX_IDLE

### 5.3 Register Requirements
| Register | Width (bits) | Reset Value | Purpose |
|----------|-------------|-------------|---------|
| state | 2 | 0 (RX_IDLE) | FSM state |
| rxd_meta | 1 | 1 | First synchronizer stage for uart_rxd |
| rxd_sync | 1 | 1 | Second synchronizer stage for uart_rxd |
| rxd_sync_d1 | 1 | 1 | Previous rxd_sync for edge detection |
| shift_reg | 8 | 0 | Assembled received data |
| bit_cnt | 3 | 0 | Data bit counter (0-7) |
| tick_cnt | 4 | 0 | Oversampling tick counter (0-15) |
| rx_frame_err_r | 1 | 0 | Frame error register |

### 5.4 Timing Contracts
- **Latency**: ~160 tick_16x cycles from start bit detection to rx_done (same as TX frame time)
- **Throughput**: 1 frame per 160 tick_16x cycles
- **Backpressure behavior**: None — received data is overwritten if not read before next frame
- **Reset recovery**: 1 cycle

### 5.5 Algorithm Pseudocode
```
state = RX_IDLE
shift_reg = 0
rxd_meta = 1, rxd_sync = 1, rxd_sync_d1 = 1
bit_cnt = 0, tick_cnt = 0
rx_frame_err_r = 0

every posedge clk:
    if (!rst_n):
        // reset all
    else:
        // Synchronizer (always runs)
        rxd_meta = uart_rxd
        rxd_sync = rxd_meta
        rxd_sync_d1 = rxd_sync  // for edge detection

        // Frame error clears on new start bit
        if (state == RX_IDLE):
            rx_frame_err_r = 0

        if (tick_16x):
            tick_cnt = tick_cnt + 1

            switch (state):
                RX_IDLE:
                    rx_done = 0
                    if (rxd_sync == 0 && rxd_sync_d1 == 1):  // falling edge
                        tick_cnt = 0
                        state = RX_START

                RX_START:
                    if (tick_cnt == 7):  // midpoint check
                        if (rxd_sync != 0):  // false start
                            state = RX_IDLE
                    if (tick_cnt == 15):
                        if (rxd_sync == 0):  // valid start
                            tick_cnt = 0
                            bit_cnt = 0
                            state = RX_DATA
                        else:
                            state = RX_IDLE

                RX_DATA:
                    if (tick_cnt == 7):  // sample at midpoint
                        shift_reg[bit_cnt] = rxd_sync
                    if (tick_cnt == 15):
                        tick_cnt = 0
                        if (bit_cnt == 7):
                            state = RX_STOP
                        else:
                            bit_cnt = bit_cnt + 1

                RX_STOP:
                    if (tick_cnt == 7):
                        if (rxd_sync == 1):
                            rx_frame_err_r = 0
                        else:
                            rx_frame_err_r = 1
                    if (tick_cnt == 15):
                        rx_data = shift_reg
                        rx_done = 1
                        state = RX_IDLE
```

### 5.6 Protocol Details
RX samples at the center of each bit (tick_cnt == 7 out of 0-15). The two-stage synchronizer
adds 2 system-clock cycles of latency to uart_rxd, which is negligible relative to the 27-clock
tick period.

Frame error timing:
- rx_frame_err is asserted when stop bit is sampled as 0
- rx_frame_err stays high until the next start bit is detected (returns to IDLE)

---

## 6. Cross-Module Timing

### 6.1 Pipeline Stage Assignment
| Stage | Module | Duration (tick_16x cycles) |
|-------|--------|---------------------------|
| Clock generation | baud_gen | Continuous (1 tick per 27 sys clocks) |
| Transmit | uart_tx | 160 tick_16x cycles per frame |
| Receive | uart_rx | ~160 tick_16x cycles per frame |

### 6.2 Module-to-Module Timing
| Source | Destination | Signal | Latency |
|--------|------------|--------|---------|
| baud_gen.tick_16x | uart_tx.tick_16x | Direct | 0 cycles |
| baud_gen.tick_16x | uart_rx.tick_16x | Direct | 0 cycles |
| uart_top.rst_n | uart_top.rst_n_sync | Reset synchronizer | 2 sys clock cycles |
| uart_top.uart_rxd | uart_rx.rxd_sync | Input synchronizer | 2 sys clock cycles |
| uart_rx.rx_data | uart_top.rx_data | Direct | 0 cycles |

### 6.3 Critical Path Description
The longest combinational path is likely in uart_rx, from the tick_16x input through the tick counter
comparison, FSM state decode, shift register data selection, and output mux. At 50 MHz (20 ns period),
this path is not critical. The baud_gen counter comparison (5-bit) and uart_tx shift logic are very short paths.
