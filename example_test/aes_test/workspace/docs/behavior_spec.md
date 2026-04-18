# Behavior Specification: aes_128_core

## 1. Domain Knowledge

### 1.1 Background
AES (Advanced Encryption Standard) is a symmetric block cipher standardized by NIST as FIPS-197. It operates on 128-bit data blocks using keys of 128, 192, or 256 bits. This design implements AES-128, which uses a 128-bit key and performs 10 rounds of transformation. The AES algorithm is widely used in secure communication, storage encryption, and authentication protocols. In hardware, AES cores are essential building blocks for cryptographic subsystems in FPGAs and ASICs.

### 1.2 Key Concepts
- **AES State**: The 128-bit intermediate data organized as a 4x4 matrix of bytes. Each byte is indexed as state[row][col] where row is 0-3 and col is 0-3. In the 128-bit vector, byte 0 is state[0][0], byte 1 is state[1][0], byte 2 is state[2][0], byte 3 is state[3][0], etc. (column-major order).
- **SubBytes**: Non-linear byte substitution using a fixed 256-entry lookup table (S-Box). Each of the 16 bytes is independently replaced.
- **ShiftRows**: Cyclic left shift of each row in the state matrix. Row 0 is not shifted, row 1 shifts by 1, row 2 by 2, row 3 by 3 bytes.
- **MixColumns**: Column-wise linear transformation in GF(2^8) using the irreducible polynomial x^8 + x^4 + x^3 + x + 1 (0x11B). Each column is multiplied by a fixed 4x4 matrix [[2,3,1,1],[1,2,3,1],[1,1,2,3],[3,1,1,2]].
- **AddRoundKey**: XOR of the 128-bit state with a 128-bit round key derived from the key schedule.
- **Key Expansion**: Algorithm to derive 11 round keys (round 0 through round 10) from the original 128-bit key. Uses RotWord, SubWord, and Rcon operations.
- **GF(2^8) multiplication**: Multiplication in the Galois Field GF(2^8). The xtime operation (multiply by 0x02) is the fundamental building block: left-shift by 1, XOR with 0x1B if the MSB was set.

### 1.3 References
- **FIPS-197**: Federal Information Processing Standards Publication 197, "Advanced Encryption Standard (AES)", November 26, 2001. Sections 4 (Mathematical Preliminaries), 5 (Algorithm Description), and Appendix B (Test Vectors).

### 1.4 Glossary
| Term | Definition |
|------|-----------|
| S-Box | Substitution Box; a fixed 256-byte lookup table for non-linear byte mapping |
| State | 128-bit intermediate data during AES processing, viewed as 4x4 byte matrix |
| Round Key | 128-bit key derived from key expansion for each round |
| Rcon | Round constant used in key expansion; each round has a specific value |
| xtime | Multiply by 0x02 in GF(2^8); fundamental GF multiplication building block |
| GF(2^8) | Galois Field with 256 elements, defined by irreducible polynomial 0x11B |
| RotWord | Cyclic rotation of a 32-bit word: [a0,a1,a2,a3] -> [a1,a2,a3,a0] |
| SubWord | Apply S-Box substitution to each byte of a 32-bit word |

## 2. Module Behavior: aes_128_core

### 2.1 Cycle-Accurate Behavior

#### Normal Operation
| Cycle | Condition | Action | Output Change | Next State |
|-------|-----------|--------|---------------|------------|
| 0 | IDLE, start=1 | Latch data_in into state_reg, key_in into key_reg. Compute AddRoundKey (state XOR key). Set round_cnt=0. | valid=0, data_out unchanged | ROUND_0 |
| 1 | ROUND_0 | Register initial AddRoundKey result into state_reg. round_cnt=1. | valid=0, data_out unchanged | ROUND_1_TO_9 |
| 2 | ROUND_1_TO_9, round_cnt=1 | Apply full round (SubBytes+ShiftRows+MixColumns+AddRoundKey). Store result in state_reg. round_cnt=2. | valid=0 | ROUND_1_TO_9 |
| 3-10 | ROUND_1_TO_9, round_cnt=2..9 | Same as cycle 2. Each cycle computes one full round. round_cnt increments. | valid=0 | ROUND_1_TO_9 |
| 11 | ROUND_1_TO_9, round_cnt=10 | Transition to ROUND_10 state. | valid=0 | ROUND_10 |
| 12 | ROUND_10 | Apply final round (SubBytes+ShiftRows+AddRoundKey, NO MixColumns). Store result in data_out register. | valid=1, data_out=encrypted result | DONE |
| 13 | DONE | Deassert valid. | valid=0 | IDLE |

**Note on FSM timing**: The exact cycle mapping depends on whether the state register update happens at the end of the current cycle or the next. The critical path goes through round_logic combinational logic.

#### Reset Behavior
| Cycle | Condition | Action | Output Change |
|-------|-----------|--------|---------------|
| -1 | rst_n=0 (asserted) | Clear state_reg, key_reg, round_cnt. Force FSM to IDLE. | valid=0, data_out=0 |
| 0 | rst_n=1 (de-asserted, after synchronizer) | FSM in IDLE, ready for start pulse. | valid=0, data_out=0 |

### 2.2 FSM Specification

#### States
| State Name | Description | Outputs |
|-----------|-------------|---------|
| IDLE | Waiting for start pulse. data_in/key_in sampled on start. | valid=0 |
| ROUND_0 | Compute initial AddRoundKey (data_in XOR key_in). 1 cycle. | valid=0 |
| ROUND_1_TO_9 | Iterative rounds 1-9. Each cycle: SubBytes+ShiftRows+MixColumns+AddRoundKey. | valid=0 |
| ROUND_10 | Final round: SubBytes+ShiftRows+AddRoundKey (no MixColumns). | valid=0 |
| DONE | Output result. Assert valid for 1 cycle. | valid=1 |

#### Transitions
| From | To | Condition |
|------|----|-----------|
| IDLE | ROUND_0 | start=1 |
| ROUND_0 | ROUND_1_TO_9 | Unconditional (1 cycle) |
| ROUND_1_TO_9 | ROUND_1_TO_9 | round_cnt < 10 |
| ROUND_1_TO_9 | ROUND_10 | round_cnt = 10 |
| ROUND_10 | DONE | Unconditional (1 cycle) |
| DONE | IDLE | Unconditional (1 cycle) |

#### Initial State: IDLE

### 2.3 Register Requirements
| Register | Width (bits) | Reset Value | Purpose |
|----------|-------------|-------------|---------|
| state_reg | 128 | 0x0 | Holds current AES state between rounds |
| key_reg | 128 | 0x0 | Latched copy of initial key_in |
| round_cnt | 4 | 0x0 | Current round counter (0-10) |
| data_out_reg | 128 | 0x0 | Output register holding final ciphertext |
| fsm_state | 3 | IDLE (0) | Current FSM state |

### 2.4 Timing Contracts
- **Latency**: 12 clock cycles (from start assertion to valid assertion)
- **Throughput**: 1 result per 12+ cycles (cannot accept new start until current encryption completes)
- **Backpressure behavior**: None (no backpressure support; start must not be asserted during encryption)
- **Reset recovery**: 2 cycles after rst_n de-assertion (synchronizer latency)

### 2.5 Algorithm Pseudocode

INPUT: data_in[127:0], key_in[127:0], start
OUTPUT: data_out[127:0], valid

```
// Cycle 0: Start
State = data_in
RoundKey = key_in
State = State ^ RoundKey   // Initial AddRoundKey

// Cycles 1 to 9
for round = 1 to 9:
    State = SubBytes(State)
    State = ShiftRows(State)
    State = MixColumns(State)
    RoundKey = KeyExpansion(key_in, round)
    State = State ^ RoundKey

// Cycle 10
State = SubBytes(State)
State = ShiftRows(State)
// Note: no MixColumns in final round
RoundKey = KeyExpansion(key_in, 10)
data_out = State ^ RoundKey
valid = 1
```

### 2.6 Protocol Details
**Start-Valid Handshake Protocol:**
- Master asserts `start` for exactly 1 clock cycle with valid `data_in` and `key_in`
- AES core captures inputs on the rising edge where `start=1`
- Master must NOT assert `start` again until `valid` has been observed
- AES core asserts `valid` for exactly 1 clock cycle when `data_out` is ready
- `data_out` holds the ciphertext value while `valid=1`

Signal sequence:
```
Cycle:    0   1   2   3  ...  11  12  13  14
start:   _/‾\___________________________________
data_in: [==VALID==]___________________________
key_in:  [==VALID==]___________________________
valid:   ___________________________/‾\________
data_out:________________________[==RESULT===]__
```

---

## 2b. Module Behavior: aes_round_logic

This module is combinational. Output changes immediately based on inputs. No cycle behavior applicable.

### 2b.5 Algorithm Pseudocode

INPUT: state_in[127:0], round_key[127:0], round_num[3:0]
OUTPUT: state_out[127:0]

```
// Step 1: SubBytes - apply S-Box to each of 16 bytes
for i = 0 to 15:
    sub_bytes[i] = SBOX(state_in[8*i +: 8])

// Step 2: ShiftRows - reorder bytes (column-major state matrix)
// State matrix: row = byte_index % 4, col = byte_index / 4
// After ShiftRows:
//   Row 0: no shift
//   Row 1: left shift by 1 column
//   Row 2: left shift by 2 columns
//   Row 3: left shift by 3 columns
shift_rows = ShiftRows_reorder(sub_bytes)

// Step 3: MixColumns (only for rounds 1-9)
if round_num != 10:
    for col = 0 to 3:
        s0 = shift_rows[4*col + 0]
        s1 = shift_rows[4*col + 1]
        s2 = shift_rows[4*col + 2]
        s3 = shift_rows[4*col + 3]
        mix_col[4*col + 0] = xtime(s0) ^ xtime(s1) ^ s1 ^ s2 ^ s3
        mix_col[4*col + 1] = s0 ^ xtime(s1) ^ xtime(s2) ^ s2 ^ s3
        mix_col[4*col + 2] = s0 ^ s1 ^ xtime(s2) ^ xtime(s3) ^ s3
        mix_col[4*col + 3] = xtime(s0) ^ s0 ^ s1 ^ s2 ^ xtime(s3)
else:
    mix_col = shift_rows

// Step 4: AddRoundKey
state_out = mix_col ^ round_key
```

---

## 2c. Module Behavior: aes_key_expansion

This module is combinational. Output changes immediately based on inputs. No cycle behavior applicable.

### 2c.5 Algorithm Pseudocode

INPUT: key_in[127:0], round_num[3:0]
OUTPUT: round_key[127:0]

```
// Key words: W[0], W[1], W[2], W[3] = key_in split into 4 x 32-bit words
// W[i] = key_in[32*i +: 32]

if round_num == 0:
    round_key = key_in
else:
    // Iteratively compute W[4]..W[4*round_num+3]
    W[0] = key_in[127:96]
    W[1] = key_in[95:64]
    W[2] = key_in[63:32]
    W[3] = key_in[31:0]

    for i = 4 to (4*round_num + 3):
        temp = W[i-1]
        if (i % 4) == 0:
            // RotWord
            temp = {temp[23:0], temp[31:24]}
            // SubWord
            temp = {SBOX(temp[31:24]), SBOX(temp[23:16]), SBOX(temp[15:8]), SBOX(temp[7:0])}
            // XOR with Rcon
            temp = temp ^ {RCON(i/4), 24'h0}
        W[i] = W[i-4] ^ temp

    round_key = {W[4*round_num], W[4*round_num+1], W[4*round_num+2], W[4*round_num+3]}

// Rcon values:
// RCON(1) = 8'h01, RCON(2) = 8'h02, RCON(3) = 8'h04, RCON(4) = 8'h08
// RCON(5) = 8'h10, RCON(6) = 8'h20, RCON(7) = 8'h40, RCON(8) = 8'h80
// RCON(9) = 8'h1B, RCON(10) = 8'h36
```

---

## 2d. Module Behavior: aes_sbox

This module is combinational. Output changes immediately based on inputs. No cycle behavior applicable.

### 2d.5 Algorithm Pseudocode

INPUT: addr[7:0]
OUTPUT: dout[7:0]

```
// 256-entry lookup table (FIPS-197 Section 5.1.1, Figure 7)
// Uses case statement with all 256 precomputed values
dout = SBOX_TABLE[addr]
```

---

## 3. Cross-Module Timing

### 3.1 Pipeline Stage Assignment
| Pipeline Stage | Module | Duration (cycles) |
|---------------|--------|-------------------|
| FSM Control | aes_128_core | 12 cycles per encryption |
| Combinational datapath | aes_round_logic | 0 cycles (combinational) |
| Combinational keygen | aes_key_expansion | 0 cycles (combinational) |
| Combinational lookup | aes_sbox | 0 cycles (combinational) |

### 3.2 Module-to-Module Timing
| Source | Destination | Signal | Latency (cycles) |
|--------|------------|--------|------------------|
| aes_128_core.state_reg | aes_round_logic.state_in | state data | 0 (same cycle, combinational path) |
| aes_128_core.key_reg | aes_key_expansion.key_in | key data | 0 (combinational) |
| aes_128_core.round_cnt | aes_key_expansion.round_num | round counter | 0 (combinational) |
| aes_key_expansion.round_key | aes_round_logic.round_key | round key | 0 (combinational chain) |
| aes_round_logic.state_out | aes_128_core.state_next | next state | 0 (combinational, registered at clock edge) |

### 3.3 Critical Path Description
The longest combinational path is: state_reg -> aes_key_expansion (key computation for requested round) -> aes_round_logic (16 S-Box lookups + ShiftRows wiring + MixColumns GF(2^8) operations + AddRoundKey XOR) -> state_next -> register input.

The key_expansion for higher rounds requires iterative XOR chains (up to 40 word-level XOR operations for round 10), combined with S-Box lookups. This combined with the 16 parallel S-Box lookups in SubBytes and the GF(2^8) multiplications in MixColumns forms the critical path. At 100 MHz (10ns), this should be achievable on Artix-7.
