# Behavior Specification: chacha20

## 1. Domain Knowledge

### 1.1 Background
ChaCha20 is a stream cipher designed by Daniel J. Bernstein, standardized in RFC 8439 (formerly RFC 7539). It generates a pseudorandom keystream from a 256-bit key and 96-bit nonce, which is XORed with plaintext for encryption or ciphertext for decryption. It is widely used in TLS 1.3, SSH, WireGuard, and other security protocols as an alternative to AES.

### 1.2 Key Concepts
- **Stream Cipher**: Encryption method that generates a keystream XORed with data. Encrypt and decrypt are identical operations.
- **Quarter Round (QR)**: The fundamental building block of ChaCha20. Operates on four 32-bit state words using modular addition, XOR, and bit rotation.
- **State Matrix**: A 4x4 matrix of 16 x 32-bit words. Initialized with constants, key, counter, and nonce. Modified through 20 rounds (10 double-rounds).
- **Double Round**: One column round + one diagonal round. ChaCha20 performs 10 double-rounds per block.
- **Modular Addition**: All additions are modulo 2^32 (32-bit unsigned wrap-around).
- **Circular Left Rotation**: Bit rotation that wraps MSB bits to LSB positions (not shift — no bits lost).

### 1.3 References
- RFC 8439: "ChaCha20 and Poly1305 for IETF Protocols", January 2018
  - Section 2.1: The ChaCha Quarter Round
  - Section 2.2: A ChaCha State
  - Section 2.3: The ChaCha20 Block Function
  - Section 2.4: The ChaCha20 Encryption Algorithm
  - Section 2.4.2: Example and Test Vector for ChaCha20
  - Section 2.6.2: Example and Test Vector for AEAD

### 1.4 Glossary
| Term | Definition |
|------|-----------|
| QR | Quarter Round — the fundamental 4-word operation |
| Nonce | Number used once — 96-bit value that must be unique per key |
| Block | 64-byte (512-bit) keystream output from one ChaCha20 evaluation |
| Double-round | One column round + one diagonal round |
| State matrix | 4x4 array of 32-bit words forming the algorithm's working state |

## 2. Module Behavior: chacha20_top

### 2.1 Cycle-Accurate Behavior

#### Normal Operation
| Cycle | Condition | Action | Output Change | Next State |
|-------|-----------|--------|---------------|------------|
| 0 | rst_n de-asserted, start_i HIGH | Sample key_i, nonce_i, counter_i. Pass to core. Start core. Begin FSM. | ready_o = LOW | COMPUTE |
| 1-22 | core busy | Wait for core to complete 20 rounds + add | (no output change) | COMPUTE |
| 22 | core.done_o pulse | Store 512-bit keystream in output register. Begin output phase. | block_done_o = pulse HIGH | OUTPUT |
| 23-38 | Output phase | Stream 16 words of (keystream XOR din_data_i) to dout_data_o, one per cycle when dout_ready_i HIGH | dout_valid_o = HIGH, dout_data_o = keystream[i] ^ din_data_i | OUTPUT |
| 38 | 16th word transferred | Increment block counter. Return to IDLE or re-start for next block. | ready_o = HIGH | IDLE |

#### Reset Behavior
| Cycle | Condition | Action | Output Change |
|-------|-----------|--------|---------------|
| -1 | rst_n_i asserted | Clear all registers, reset FSM to IDLE, clear counter | ready_o = LOW, dout_valid_o = LOW |
| 0 | rst_n_i de-asserted | FSM enters IDLE state, 2-stage sync reset settles | ready_o = HIGH after 2 cycles |

### 2.2 FSM Specification

#### States
| State Name | Description | Outputs |
|-----------|-------------|---------|
| IDLE | Waiting for start_i | ready_o = HIGH, dout_valid_o = LOW, block_done_o = LOW |
| COMPUTE | Core is performing 10 double-rounds | ready_o = LOW, din_ready_o = LOW |
| OUTPUT | Streaming 16 keystream words XORed with input data | dout_valid_o = HIGH (when data available) |

#### Transitions
| From | To | Condition |
|------|----|-----------|
| IDLE | COMPUTE | start_i = HIGH |
| COMPUTE | OUTPUT | core_done = HIGH |
| OUTPUT | IDLE | All 16 words transferred |
| OUTPUT | COMPUTE | All 16 words transferred AND auto-continue (counter increment, start next block) |

#### Initial State: IDLE

### 2.3 Register Requirements
| Register | Width (bits) | Reset Value | Purpose |
|----------|-------------|-------------|---------|
| counter_reg | 32 | 0x0 | Current block counter, auto-incremented |
| keystream_reg | 512 | 0x0 | Stores computed keystream block (16 x 32-bit) |
| word_cnt | 4 | 0x0 | Counts output words (0-15) |
| fsm_state | 2 | 0 (IDLE) | FSM state register |

### 2.4 Timing Contracts
- **Latency**: 22 cycles from start_i to block_done_o (1 init + 20 rounds + 1 finalize)
- **Throughput**: 1 block (512 bits) per 38 cycles (22 compute + 16 output)
- **Backpressure behavior**: Stall — if dout_ready_i is LOW during OUTPUT phase, output word counter and keystream pointer freeze
- **Reset recovery**: 2 cycles after rst_n de-assertion (reset synchronizer)

### 2.5 Algorithm Pseudocode
```
INPUT: key[255:0], nonce[95:0], counter[31:0], din_data[31:0], start, din_valid
OUTPUT: dout_data[31:0], dout_valid, dout_ready, block_done, ready

On start:
  chacha20_core.start(key, nonce, counter)
  Wait for core.done
  keystream[511:0] = core.state_out
  For i = 0 to 15:
    dout_data = keystream[i*32 +: 32] XOR din_data
    Assert dout_valid, wait for dout_ready
  counter = counter + 1
  Assert block_done pulse
```

### 2.6 Protocol Details
**Data Streaming Interface (valid/ready handshake):**
```
Cycle:  0   1   2   3   4   5
dout_valid: ___/‾‾‾‾‾‾‾‾‾‾‾‾‾\___
dout_data:  ====[D0][D1][D2][D3]====
dout_ready: ‾‾‾‾‾‾‾‾‾‾\________/‾‾‾  (backpressure example)
Transfer:       T0      T1  T2  T3    (data transferred when valid AND ready)
```
- Data is transferred on cycles where both valid and ready are HIGH
- When downstream de-asserts ready, the output holds the current word

## 3. Module Behavior: chacha20_core

### 3.1 Cycle-Accurate Behavior

#### Normal Operation
| Cycle | Condition | Action | Output Change | Next State |
|-------|-----------|--------|---------------|------------|
| 0 | start_i HIGH | Initialize state[0..15] from constants, key, counter, nonce. Copy to init_state. Set round_cnt=0. | busy_o = HIGH | ROUND |
| 1 | round_cnt even (column round) | Apply QR to columns: QR(0,4,8,12), QR(1,5,9,13), QR(2,6,10,14), QR(3,7,11,15). Increment round_cnt. | state updated | ROUND |
| 2 | round_cnt odd (diagonal round) | Apply QR to diagonals: QR(0,5,10,15), QR(1,6,11,12), QR(2,7,8,13), QR(3,4,9,14). Increment round_cnt. | state updated | ROUND |
| 3-20 | round_cnt < 20 | Alternate column/diagonal rounds | state updated | ROUND |
| 21 | round_cnt = 20 | Add init_state to working state: state[i] = state[i] + init_state[i] for all i. Output 512-bit result. | state_o valid, done_o = pulse HIGH | IDLE |

#### Reset Behavior
| Cycle | Condition | Action | Output Change |
|-------|-----------|--------|---------------|
| -1 | rst_n_i asserted | Clear state matrix, round counter | done_o = LOW, busy_o = LOW |
| 0 | rst_n_i de-asserted | Enter IDLE | busy_o = LOW |

### 3.2 FSM Specification

#### States
| State Name | Description | Outputs |
|-----------|-------------|---------|
| IDLE | Waiting for start_i | busy_o = LOW, done_o = LOW |
| ROUND | Performing round operations | busy_o = HIGH |
| FINALIZE | Adding initial state to working state | busy_o = HIGH, done_o = pulse |

#### Transitions
| From | To | Condition |
|------|----|-----------|
| IDLE | ROUND | start_i = HIGH |
| ROUND | ROUND | round_cnt < 20 |
| ROUND | FINALIZE | round_cnt = 20 |
| FINALIZE | IDLE | (auto, 1 cycle) |

#### Initial State: IDLE

### 3.3 Register Requirements
| Register | Width (bits) | Reset Value | Purpose |
|----------|-------------|-------------|---------|
| state[0:15] | 512 (16x32) | 0x0 | Working state matrix |
| init_state[0:15] | 512 (16x32) | 0x0 | Saved initial state for final addition |
| round_cnt | 5 | 0 | Round counter (0-20) |
| core_fsm | 2 | 0 (IDLE) | Core FSM state |

### 3.4 Timing Contracts
- **Latency**: 22 cycles (1 init + 20 rounds + 1 finalize)
- **Throughput**: 1 block per 22 cycles
- **Backpressure behavior**: N/A (internal module, always ready)
- **Reset recovery**: 1 cycle after rst_n de-assertion

### 3.5 Algorithm Pseudocode
```
ChaCha20 Block Function:
INPUT: key[255:0], nonce[95:0], counter[31:0]
OUTPUT: state[511:0] (keystream block)

Step 1: Initialize state matrix:
  state[0]  = 0x61707865  (constant "expa")
  state[1]  = 0x3320646e  (constant "nd 3")
  state[2]  = 0x79622d32  (constant "2-by")
  state[3]  = 0x6b206574  (constant "te k")
  state[4:11] = key[255:0] split into 8 x 32-bit words (little-endian)
  state[12] = counter
  state[13:15] = nonce[95:0] split into 3 x 32-bit words (little-endian)
  init_state = state  (save copy)

Step 2: Perform 20 rounds (10 double-rounds):
  For round = 0 to 19:
    If round is even (column round):
      QR(state[0], state[4], state[8],  state[12])
      QR(state[1], state[5], state[9],  state[13])
      QR(state[2], state[6], state[10], state[14])
      QR(state[3], state[7], state[11], state[15])
    If round is odd (diagonal round):
      QR(state[0], state[5], state[10], state[15])
      QR(state[1], state[6], state[11], state[12])
      QR(state[2], state[7], state[8],  state[13])
      QR(state[3], state[4], state[9],  state[14])

Step 3: Add initial state:
  For i = 0 to 15:
    state[i] = (state[i] + init_state[i]) mod 2^32

Step 4: Output state[0:15] as keystream block (512 bits)
```

## 4. Module Behavior: chacha20_qr

### 4.1 Cycle-Accurate Behavior
This module is combinational. Output changes immediately based on input. No cycle behavior applicable.

### 4.2 Algorithm Pseudocode
```
Quarter Round QR(a, b, c, d):
INPUT: a[31:0], b[31:0], c[31:0], d[31:0]
OUTPUT: a'[31:0], b'[31:0], c'[31:0], d'[31:0]

  a = (a + b) mod 2^32
  d = d XOR a
  d = (d <<< 16)    // rotate left 16 bits
  c = (c + d) mod 2^32
  b = b XOR c
  b = (b <<< 12)    // rotate left 12 bits
  a = (a + b) mod 2^32
  d = d XOR a
  d = (d <<< 8)     // rotate left 8 bits
  c = (c + d) mod 2^32
  b = b XOR c
  b = (b <<< 7)     // rotate left 7 bits

Return (a, b, c, d)
```

## 5. Cross-Module Timing

### 5.1 Pipeline Stage Assignment
| Pipeline Stage | Module | Duration (cycles) |
|---------------|--------|-------------------|
| 1 | chacha20_qr (combinational) | 0 (same cycle) |
| 2 | chacha20_core (iterative rounds) | 22 |
| 3 | chacha20_top (data streaming) | 16 |

### 5.2 Module-to-Module Timing
| Source | Destination | Signal | Latency (cycles) |
|--------|------------|--------|------------------|
| chacha20_top.start_i | chacha20_core.start_i | start pulse | 0 (combinational) |
| chacha20_core.state_o | chacha20_top.keystream_reg | done → register store | 1 |
| chacha20_core.round computation | chacha20_qr.* | state → QR → state | 0 (combinational within clock edge) |

### 5.3 Critical Path Description
The critical path is within a single quarter-round operation: three 32-bit additions chained with XOR and rotation operations. The path runs: add(a+b) → XOR(d^a) → rot(d) → add(c+d) → XOR(b^c) → rot(b) → add(a+b) → XOR(d^a) → rot(d) → add(c+d) → XOR(b^c) → rot(b). At 100 MHz (10ns), this is well within timing for any modern FPGA.
