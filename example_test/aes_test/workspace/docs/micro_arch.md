# Microarchitecture Document: aes_128_core

## 1. Module Partitioning

### 1.1 Hierarchy
```
aes_128_core (top, level 0)
├── aes_round_logic (level 1) — combinational round function
│   └── aes_sbox × 16 (level 2) — S-Box lookup instances
├── aes_key_expansion (level 1) — combinational on-the-fly key generation
│   └── aes_sbox × 4 (level 2) — S-Box lookup instances for SubWord
└── Internal FSM + datapath registers (within aes_128_core)
```

### 1.2 Module Responsibilities
| Module | Responsibility | Type |
|--------|---------------|------|
| aes_128_core | Top-level FSM, state register management, round iteration control, I/O | Sequential (FSM) |
| aes_round_logic | Combinational: SubBytes + ShiftRows + MixColumns + AddRoundKey | Combinational |
| aes_key_expansion | Combinational: derive round key from initial key and round number | Combinational |
| aes_sbox | 256-entry byte substitution lookup (FIPS-197 Figure 7) | Combinational |

## 2. Datapath

### 2.1 Data Flow
```
                    ┌─────────────┐
   data_in ───────► │ state_reg   │──┐
   key_in ────────► │ key_reg     │  │
                    └─────────────┘  │
                                     ▼
                          ┌─────────────────────┐
   key_reg ──────────────►│ aes_key_expansion    │
   round_cnt ────────────►│   (combinational)    │──► round_key[127:0]
                          └─────────────────────┘         │
                                                         ▼
                    ┌──────────────────────────────────────────────┐
   state_reg ─────►│              aes_round_logic                  │
   round_key ─────►│  SubBytes → ShiftRows → MixColumns → AddRK   │──► state_next[127:0]
   round_cnt ─────►│              (combinational)                  │
                    └──────────────────────────────────────────────┘
                                     │
                                     ▼
               state_next ──► state_reg (registered on clock edge)
               state_next ──► data_out_reg (when FSM in ROUND_10)
```

### 2.2 Internal Registers
| Register | Width | Reset | Update Condition | Source |
|----------|-------|-------|-----------------|--------|
| state_reg | 128 | 0 | IDLE+start: data_in ^ key_in; ROUND_0/1-9/10: round_logic output | data_in or round_logic |
| key_reg | 128 | 0 | IDLE+start only | key_in |
| round_cnt | 4 | 0 | Increment each round cycle | round_cnt + 1 |
| data_out_reg | 128 | 0 | DONE state | state_reg (final round result) |

### 2.3 Key Data Widths
- State: 128 bits (16 bytes, 4x4 matrix in column-major order)
- Round key: 128 bits
- Round counter: 4 bits (counts 0-10)
- FSM state: 3 bits (5 states)
- S-Box address/data: 8 bits each

## 3. Control Logic

### 3.1 FSM States
| Encoding | State | Description |
|----------|-------|-------------|
| 3'b000 | IDLE | Waiting for start. Latch data_in, key_in on start=1. |
| 3'b001 | ROUND_0 | Initial AddRoundKey: state_reg = data_in ^ key_in |
| 3'b010 | ROUND_1_TO_9 | Iterative rounds 1-9: full round operations |
| 3'b011 | ROUND_10 | Final round: SubBytes+ShiftRows+AddRoundKey (no MixColumns) |
| 3'b100 | DONE | Assert valid=1, output data_out_reg |

### 3.2 FSM Transitions
```
         start=1
IDLE ──────────► ROUND_0 ──────► ROUND_1_TO_9 ◄────┐
                                          │          │
                                          │ round_cnt < 10
                                          ├──────────┘
                                          │ round_cnt = 10
                                          ▼
                                      ROUND_10 ──────► DONE ──────► IDLE
```

### 3.3 Control Signals
| Signal | Condition | Effect |
|--------|-----------|--------|
| state_en | FSM != IDLE | Enable state_reg update |
| cnt_en | FSM in ROUND_0 or ROUND_1_TO_9 | Enable round_cnt increment |
| valid | FSM = DONE | Assert output valid pulse |
| mixcols_en | round_num != 10 | Enable MixColumns in round_logic |

## 4. Algorithm Pseudocode

### 4.1 aes_sbox
```
INPUT: addr[7:0]
OUTPUT: dout[7:0]
// 256-entry case statement with FIPS-197 Figure 7 values
// Example: addr=8'h00 → dout=8'h63, addr=8'h01 → dout=8'h7C, etc.
```

### 4.2 aes_key_expansion (on-the-fly)
```
INPUT: key_in[127:0], round_num[3:0]
OUTPUT: round_key[127:0]

// Split key into 4 words (each 32-bit)
W[0] = key_in[127:96]  // Most significant word
W[1] = key_in[95:64]
W[2] = key_in[63:32]
W[3] = key_in[31:0]    // Least significant word

if round_num == 0:
    return {W[0], W[1], W[2], W[3]}

// Iteratively compute round keys
for i = 4 to (4*round_num + 3):
    temp = W[i-1]
    if (i % 4) == 0:
        temp = RotWord(temp)            // {temp[23:0], temp[31:24]}
        temp = SubWord(temp)            // 4x S-Box lookups
        temp[31:24] = temp[31:24] ^ RCON(i/4)  // XOR round constant
    W[i] = W[i-4] ^ temp

return {W[4*round_num], W[4*round_num+1], W[4*round_num+2], W[4*round_num+3]}

// Rcon table: RCON(1)=01, RCON(2)=02, RCON(3)=04, RCON(4)=08,
// RCON(5)=10, RCON(6)=20, RCON(7)=40, RCON(8)=80, RCON(9)=1B, RCON(10)=36
```

### 4.3 aes_round_logic
```
INPUT: state_in[127:0], round_key[127:0], round_num[3:0]
OUTPUT: state_out[127:0]

// Step 1: SubBytes — 16 parallel S-Box lookups
for i = 0 to 15:
    sub[i] = SBOX(state_in[8*i +: 8])

// Step 2: ShiftRows — cyclic left shift per row (column-major indexing)
// Byte indices: byte[row + 4*col], row=0..3, col=0..3
// Row 0: no shift → [0,4,8,12]
// Row 1: shift left 1 → [1,5,9,13] → [5,9,13,1]
// Row 2: shift left 2 → [2,6,10,14] → [10,14,2,6]
// Row 3: shift left 3 → [3,7,11,15] → [15,3,7,11]
shift[0]  = sub[0];   shift[4]  = sub[4];   shift[8]  = sub[8];   shift[12] = sub[12];
shift[1]  = sub[5];   shift[5]  = sub[9];   shift[9]  = sub[13];  shift[13] = sub[1];
shift[2]  = sub[10];  shift[6]  = sub[14];  shift[10] = sub[2];   shift[14] = sub[6];
shift[3]  = sub[15];  shift[7]  = sub[3];   shift[11] = sub[7];   shift[15] = sub[11];

// Step 3: MixColumns (skip for round 10)
if round_num != 10:
    for col = 0 to 3:
        s0=shift[4*col+0]; s1=shift[4*col+1]; s2=shift[4*col+2]; s3=shift[4*col+3]
        mix[4*col+0] = xtime(s0) ^ (xtime(s1) ^ s1) ^ s2 ^ s3    // 2*s0 + 3*s1 + s2 + s3
        mix[4*col+1] = s0 ^ xtime(s1) ^ (xtime(s2) ^ s2) ^ s3    // s0 + 2*s1 + 3*s2 + s3
        mix[4*col+2] = s0 ^ s1 ^ xtime(s2) ^ (xtime(s3) ^ s3)    // s0 + s1 + 2*s2 + 3*s3
        mix[4*col+3] = (xtime(s0) ^ s0) ^ s1 ^ s2 ^ xtime(s3)    // 3*s0 + s1 + s2 + 2*s3
else:
    mix = shift

// Step 4: AddRoundKey
state_out = mix ^ round_key

// xtime(a) = {a[6:0], 1'b0} ^ (a[7] ? 8'h1B : 8'h00)
```

### 4.4 aes_128_core (top-level FSM)
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

## 5. Interface Protocol

### 5.1 Inter-Module Interfaces
All internal interfaces are direct combinational connections (no handshake between submodules).

| Source | Destination | Signal | Width | Protocol |
|--------|------------|--------|-------|----------|
| aes_128_core.state_reg | aes_round_logic.state_in | state | 128 | Direct |
| aes_128_core.key_reg | aes_key_expansion.key_in | key | 128 | Direct |
| aes_128_core.round_cnt | aes_key_expansion.round_num | round | 4 | Direct |
| aes_128_core.round_cnt | aes_round_logic.round_num | round | 4 | Direct |
| aes_key_expansion.round_key | aes_round_logic.round_key | key | 128 | Direct |
| aes_round_logic.state_out | aes_128_core.state_next | next state | 128 | Direct |

### 5.2 Top-Level I/O Protocol
- **Start-Valid pulse protocol**: start asserted for 1 cycle → encryption begins → valid asserted for 1 cycle when done
- **data_in/key_in**: Must be stable when start is asserted. Sampled into internal registers on start.
- **data_out**: Valid when valid=1. Holds value for 1 cycle.
- **start must not be re-asserted** until valid pulse is observed.

## 6. Timing Closure Plan

### 6.1 Critical Path
```
state_reg → aes_key_expansion (iterative key XOR chain for high rounds)
          → aes_round_logic: 16x S-Box case lookups
                             → ShiftRows wiring
                             → MixColumns GF(2^8) xtime+XOR
                             → AddRoundKey XOR
          → state_next → register D input
```

### 6.2 Mitigation Strategies
- **S-Box**: Implemented as combinational case statement — synthesizes to LUTs, no BRAM latency
- **Key expansion**: Iterative XOR chain is the longest path. For round 10, requires ~40 32-bit XOR operations in chain. At 100 MHz (10ns) on Artix-7, this is feasible but will be the timing bottleneck.
- **MixColumns**: xtime is a single shift + conditional XOR; 4 columns computed in parallel
- **No pipelining needed**: 10ns budget is sufficient for the combinational depth

### 6.3 Clock Domain
- Single clock domain (clk_core at 100 MHz)
- Reset synchronizer: 2-stage for rst_n before use

## 7. Resource Plan

### 7.1 Estimated Resources (Artix-7 XC7A35T)
| Module | LUTs | FFs | BRAMs | Notes |
|--------|------|-----|-------|-------|
| aes_sbox × 20 | ~1200 | 0 | 0 | 16 in round_logic + 4 in key_expansion; ~60 LUTs each |
| aes_key_expansion | ~800 | 0 | 0 | XOR chain + 4 S-Box + Rcon logic |
| aes_round_logic (wiring + MixColumns) | ~600 | 0 | 0 | ShiftRows wiring + GF(2^8) multiply |
| aes_128_core (FSM + regs) | ~50 | ~270 | 0 | 128+128+128+4+3 = ~391 FFs (state, key, output, cnt, fsm) |
| **Total** | **~2650** | **~270** | **0** | Fits comfortably in XC7A35T |

## 8. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| FSM + iterative (not pipelined) | Area-efficient for non-continuous encryption. 12-cycle latency is acceptable per requirement. |
| On-the-fly key expansion | Eliminates need to store 11 × 128-bit round keys (saves ~1400 FFs). Combinational logic computes the required key in the same cycle. |
| S-Box as case statement | No BRAM needed; pure LUT implementation. 256-entry case synthesizes efficiently. |
| No BRAM usage | S-Box in distributed logic; no block RAM required, leaving BRAM available for other functions. |
| Single clock domain | Simplifies design; no CDC complexity needed for a standalone encryption core. |
| Separate aes_round_logic module | Isolates combinational datapath from FSM for clarity and reuse. MixColumns bypass controlled by round_num. |
