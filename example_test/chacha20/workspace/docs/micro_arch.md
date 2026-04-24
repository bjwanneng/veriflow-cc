# Microarchitecture Document: ChaCha20 Stream Cipher Core

## 1. Module Partitioning

### 1.1 Module Hierarchy

```
chacha20_top (Level 0 — top)
├── chacha20_core (Level 1 — processing)
│   ├── chacha20_qr × 4 (Level 2 — combinational quarter-round)
```

### 1.2 Module Responsibilities

| Module | Responsibility | Type |
|--------|---------------|------|
| `chacha20_top` | Reset synchronization, key/nonce/counter management, block-level FSM, data streaming with XOR, output word counter | top + control |
| `chacha20_core` | State matrix initialization, 20-round iterative computation using 4 parallel QR units, initial state addition, round counter | processing |
| `chacha20_qr` | Combinational quarter-round: 4 additions, 4 XORs, 4 rotations on four 32-bit words | combinational processing |

## 2. Datapath

### 2.1 Top-Level Datapath

```
                    ┌─────────────────────┐
  key_i[255:0] ────►│                     │
  nonce_i[95:0] ───►│                     │
  counter_i[31:0]─►│   chacha20_core     │
  start_i ────────►│                     │──► state_o[511:0]
                    │                     │──► done_o
                    │                     │──► busy_o
                    └─────────────────────┘
                              │
                              ▼ state_o → keystream_reg[511:0]
                              │
din_data_i[31:0] ──────────►(XOR)──► dout_data_o[31:0]
                              ▲
                    keystream_reg[word_sel*32 +: 32]
```

### 2.2 Core Datapath

```
                    State Matrix (16 x 32-bit registers)
                    ┌───┬───┬───┬───┐
                    │ 0 │ 1 │ 2 │ 3 │  ← constants
                    ├───┼───┼───┼───┤
                    │ 4 │ 5 │ 6 │ 7 │  ← key[0:7]
                    ├───┼───┼───┼───┤
                    │ 8 │ 9 │10 │11 │  ← key[8:15] (conceptual)
                    ├───┼───┼───┼───┤
                    │12 │13 │14 │15 │  ← counter, nonce[0:2]
                    └─┬─┴─┬─┴─┬─┴─┬─┘
                      │   │   │   │
            ┌─────────▼───▼───▼───▼─────────┐
            │  4x chacha20_qr (combinational) │
            │  Column mode: QR(0,4,8,12)      │
            │                QR(1,5,9,13)      │
            │                QR(2,6,10,14)     │
            │                QR(3,7,11,15)     │
            │  Diagonal mode: QR(0,5,10,15)   │
            │                 QR(1,6,11,12)   │
            │                 QR(2,7,8,13)    │
            │                 QR(3,4,9,14)    │
            └─────────┬───┬───┬───┬─────────┘
                      │   │   │   │
                      ▼   ▼   ▼   ▼
                    State Matrix (updated)
                      + init_state (after 20 rounds)
```

### 2.3 QR Datapath

```
a_i ──┬──►[+]──►[XOR]──►[<<<16]──►┬──►[+]──►[XOR]──►[<<<8]───►┬──► a_o
      │     ▲      ▲               │     ▲      ▲               │
b_i ──┤─────┘      │               └─────┘      │               │
      │            │                            │               │
      │        ┌───┘                        ┌───┘               │
c_i ──┤────────┼────────────────────────────┼──────────────────►├──► c_o
      │        │                            │                   │
d_i ──┘        ▼                            ▼                   │
              [<<<16] result           [<<<8] result            │
                                                               │
b_i ──►[XOR]──►[<<<12]──►┬──►(partial b)──►[XOR]──►[<<<7]────►└──► b_o
         ▲                │                    ▲
c_i partial───────────────┘                    │
                                          c+d result
d_i ─────────────────────────────────────────────────────────────► d_o
  (after XOR and rotation stages)
```

Simplified QR signal flow (32-bit operations):
```
a' = (a+b); d ^= a'; d = rot16(d);
c' = (c+d); b ^= c'; b = rot12(b);
a'' = (a'+b); d ^= a''; d = rot8(d);
c'' = (c'+d); b ^= c''; b = rot7(b);
Output: (a'', b, c'', d)
```

## 3. Control Logic

### 3.1 chacha20_top FSM

```
         start_i
  IDLE ──────────► COMPUTE
   ▲                  │
   │                  │ core_done
   │                  ▼
   │              OUTPUT
   │                  │
   └──────────────────┘
          16 words sent
```

| Signal | IDLE | COMPUTE | OUTPUT |
|--------|------|---------|--------|
| ready_o | 1 | 0 | 0 |
| din_ready_o | 0 | 0 | 1 (when dout_ready_i) |
| dout_valid_o | 0 | 0 | 1 (when data available) |
| block_done_o | 0 | 0 | pulse on last word |
| core.start_i | pulse on transition | 0 | 0 |

### 3.2 chacha20_core FSM

```
            start_i
  IDLE ──────────► ROUND ◄────┐
   ▲                  │        │
   │                  │ round_cnt < 20
   │                  │        │
   │                  ▼        │
   │              (loop back)──┘
   │                  │
   │                  │ round_cnt = 20
   │                  ▼
   └──────── FINALIZE (1 cycle, then auto → IDLE)
```

| Signal | IDLE | ROUND | FINALIZE |
|--------|------|-------|----------|
| busy_o | 0 | 1 | 1 |
| done_o | 0 | 0 | pulse (1 cycle) |
| state_o | X | X | valid |

**Round select logic**: `round_cnt[0]` determines column (0) vs diagonal (1) operation.

### 3.3 QR Input Mux (in chacha20_core)

The 4 QR instances receive different state words depending on column vs diagonal mode:

| QR Instance | Column Round (round_cnt[0]=0) | Diagonal Round (round_cnt[0]=1) |
|-------------|-------------------------------|--------------------------------|
| QR0 | state[0], state[4], state[8], state[12] | state[0], state[5], state[10], state[15] |
| QR1 | state[1], state[5], state[9], state[13] | state[1], state[6], state[11], state[12] |
| QR2 | state[2], state[6], state[10], state[14] | state[2], state[7], state[8], state[13] |
| QR3 | state[3], state[7], state[11], state[15] | state[3], state[4], state[9], state[14] |

**Implementation**: Use 4-wide mux (2:1) per QR input, selected by `round_cnt[0]`. Output mux routes QR outputs back to the correct state registers.

### 3.4 Output Word Select (in chacha20_top)

Keystream register `keystream_reg[511:0]` is read as 16 x 32-bit words. A 4-bit `word_cnt` selects which word to output:
```
dout_data_o = keystream_reg[word_cnt*32 +: 32] ^ din_data_i
```

## 4. Algorithm Pseudocode

### 4.1 Quarter Round (chacha20_qr) — Combinational

```
INPUT:  a[31:0], b[31:0], c[31:0], d[31:0]
OUTPUT: a'[31:0], b'[31:0], c'[31:0], d'[31:0]

  // Step 1
  a = (a + b) mod 2^32
  d = d XOR a
  d = (d <<< 16)

  // Step 2
  c = (c + d) mod 2^32
  b = b XOR c
  b = (b <<< 12)

  // Step 3
  a = (a + b) mod 2^32
  d = d XOR a
  d = (d <<< 8)

  // Step 4
  c = (c + d) mod 2^32
  b = b XOR c
  b = (b <<< 7)

Return (a, b, c, d)
```

### 4.2 Block Function (chacha20_core) — Sequential, 22 cycles

```
INPUT:  key[255:0], nonce[95:0], counter[31:0], start
OUTPUT: state[511:0], done

Cycle 0 (INIT):
  state[0]  = 0x61707865
  state[1]  = 0x3320646e
  state[2]  = 0x79622d32
  state[3]  = 0x6b206574
  state[7:4]  = key[255:128]  // key words 0-3
  state[11:8] = key[127:0]    // key words 4-7
  state[12] = counter
  state[15:13] = nonce[95:0]  // nonce words 0-2
  init_state[0:15] = state[0:15]
  round_cnt = 0

Cycles 1-20 (ROUNDS):
  For round_cnt = 0 to 19:
    If round_cnt[0] == 0:  // even = column round
      Apply QR to columns (4 parallel QR instances)
    Else:                   // odd = diagonal round
      Apply QR to diagonals (4 parallel QR instances)
    state[0:15] = QR outputs
    round_cnt = round_cnt + 1

Cycle 21 (FINALIZE):
  For i = 0 to 15:
    state[i] = (state[i] + init_state[i]) mod 2^32
  state_o[511:0] = {state[15], state[14], ..., state[0]}
  done_o = 1 (pulse)
```

### 4.3 Encryption/Decryption (chacha20_top)

```
INPUT:  key, nonce, counter, din_data[31:0], start
OUTPUT: dout_data[31:0], dout_valid, block_done

On start_i:
  counter_reg = counter_i
  Start chacha20_core with key, nonce, counter_reg

On core.done_o:
  keystream_reg = core.state_o
  word_cnt = 0
  Enter OUTPUT state

In OUTPUT state (each cycle when dout_ready_i):
  dout_data_o = keystream_reg[word_cnt*32 +: 32] XOR din_data_i
  dout_valid_o = 1
  If dout_ready_i:
    word_cnt = word_cnt + 1
    If word_cnt == 15:
      counter_reg = counter_reg + 1
      block_done_o = pulse
      Return to IDLE (or auto-start next block)
```

## 5. Interface Protocol

### 5.1 Inter-Module: valid/ready handshake

Used between chacha20_top and external systems for data streaming.

```
Initiator (chacha20_top):
  dout_valid_o = HIGH when keystream word is available
  dout_data_o  = valid data when dout_valid_o is HIGH
  Wait for dout_ready_i = HIGH to advance to next word

Response (external):
  din_valid_i  = HIGH when input data word is available
  din_data_i   = valid data when din_valid_i is HIGH
  din_ready_o  = HIGH when ready to consume input
```

### 5.2 Internal: Pulse-based control

- `start_i` → `core.start_i`: Single-cycle pulse to begin computation
- `core.done_o` → `block_done_o`: Single-cycle pulse indicating completion
- No valid/ready needed between top and core (core is always ready in IDLE)

## 6. Timing Closure Plan

### 6.1 Critical Path
**Path**: QR combinational logic — 3 chained add-XOR-rotate groups
- Worst case: 3 × (32-bit add + XOR + rotate) ≈ 6-8 ns on generic FPGA
- Target: 10 ns (100 MHz) — comfortable margin

### 6.2 Mitigation Strategies
- If timing fails at higher frequencies, pipeline the QR into 2 stages (split after step 2)
- Rotations are free in FPGA (routing-only), adds are the limiting factor
- No BRAM access on critical path (all register-based)

### 6.3 Clock Domain
- Single clock domain `clk_core` at 100 MHz
- Reset synchronizer (2-stage) at top level, synchronized reset distributed to all modules

## 7. Resource Plan

### 7.1 Per-Module Estimates

| Module | LUTs | FFs | BRAMs | Notes |
|--------|------|-----|-------|-------|
| chacha20_qr × 4 | ~480 (120 each) | 0 | 0 | Combinational: 3 adders + 3 XOR + 3 rot per QR |
| chacha20_core | ~100 | ~550 | 0 | 16×32 state + 16×32 init_state + 5-bit counter + FSM |
| chacha20_top | ~50 | ~560 | 0 | 512-bit keystream reg + 32-bit counter + 4-bit word_cnt + FSM + reset sync |
| **Total** | **~630** | **~1110** | **0** | Well within 4000 LUT / 3000 FF budget |

### 7.2 Key Design Decisions

1. **Iterative (folded) architecture**: 4 parallel QR units reused across 20 rounds. Trades throughput for area. 22 cycles/block vs 1 cycle/block for full pipeline. Chosen for: compact area (~630 LUTs), sufficient throughput for 100 MHz target.
2. **Combinational QR**: All 8 operations (4 add + 4 XOR/rotate) in one cycle. Avoids pipeline registers in QR. Works at 100 MHz with margin.
3. **Register-based state**: No BRAM used. 512-bit state + 512-bit init_state = 1024 FFs. Single-cycle access, no BRAM latency.
4. **Wide parallel interface**: Key/nonce/counter loaded as wide buses (256/96/32 bits). Avoids serial load FSM complexity.
5. **Auto-increment counter**: Block counter incremented automatically for multi-block streaming. No external management needed.
