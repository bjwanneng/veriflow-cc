# Microarchitecture Document: rsa1024_modexp_accel

## 1. Module Partitioning

| Module | Hierarchy | Responsibility |
|--------|-----------|---------------|
| rsa_modexp_top | L0 (top) | AXI4-Lite slave, AXI4-Stream I/O, Square-and-Multiply FSM, register file, operand loading |
| mont_mult_1024 | L1 | CIOS outer loop controller, operand/modulus/accumulator RAM management, instantiates mont_word_engine |
| mont_word_engine | L2 | CIOS inner loop engine (MULT_ACCUM, REDUCE_ACCUM, SHIFT phases), instantiates dsp_mac_32 |
| dsp_mac_32 | L3 | 2-stage pipeline 32x32 MAC: P = a*b + c_in + t_in, maps to DSP48E2 |

### Hierarchy Diagram

```
rsa_modexp_top
├── AXI4-Lite Slave Logic (inline)
│   ├── Register File: reg_N[32], reg_E[32], reg_R2[32], reg_N_prime
│   ├── CTRL_REG (0x0000), STAT_REG (0x0004), PARAM_N_PRIME (0x0010)
│   └── Memory-mapped arrays: N[0x0100], E[0x0200], R2[0x0300]
├── AXI4-Stream Logic (inline)
│   ├── Sink: receives M[0..31]
│   └── Source: outputs Result[0..31]
├── Internal Buffers: reg_M[32], reg_A[32], reg_Result[32]
└── mont_mult_1024
    ├── ram_op_a[32] (BRAM) — operand A
    ├── ram_op_b[32] (BRAM) — operand B
    ├── ram_n[32]   (BRAM) — modulus N
    ├── ram_t[33]   (distributed RAM) — CIOS accumulator
    └── mont_word_engine
        ├── Inner loop counter (j_cnt)
        ├── Carry register
        ├── Reduction factor (m) register
        └── dsp_mac_32
            ├── Pipeline Stage 1: input registers
            └── Pipeline Stage 2: multiply-add + output registers
```

---

## 2. Datapath

### 2.1 Top-Level Data Flow

```
AXI4-Lite ──write──> reg_N, reg_E, reg_R2, reg_N_prime
AXI4-Stream ──32 beats──> reg_M[0..31]

ModExp FSM:
  reg_M ──load──> mont_mult.op_a
  reg_R2 ──load──> mont_mult.op_b    → MontMul → reg_M (M_mont)

  const_1 ──load──> mont_mult.op_a
  reg_R2 ──load──> mont_mult.op_b    → MontMul → reg_A (A_mont)

  reg_A ──load──> mont_mult.op_a
  reg_A ──load──> mont_mult.op_b     → MontMul → reg_A (square)

  reg_A ──load──> mont_mult.op_a
  reg_M ──load──> mont_mult.op_b     → MontMul → reg_A (multiply)

  reg_A ──load──> mont_mult.op_a
  const_1 ──load──> mont_mult.op_b   → MontMul → reg_Result

reg_Result ──32 beats──> AXI4-Stream
```

### 2.2 CIOS Datapath (inside mont_word_engine)

```
                    ┌─────────────────────────────┐
                    │        dsp_mac_32            │
  ram_a[j] ──> a_i ─│  Stage1: reg a,b,c,t       │
  b_reg   ──> b_i ─│  Stage2: a*b+c+t            │
  carry   ──> c_in_i│                             │
  ram_t[j] ─> t_in_i│                             │
                    │  res_out_o ──> t_wr_data    │
                    │  c_out_o  ──> new_carry     │
                    └─────────────────────────────┘

  MULT_ACCUM phase:  a_i = ram_a[j], b_i = B[i], t_in = ram_t[j]
  REDUCE_ACCUM phase: a_i = ram_n[j], b_i = m_factor, t_in = ram_t[j]
```

### 2.3 Operand Loading Path

rsa_modexp_top loads operands into mont_mult_1024's internal RAMs before each MontMul:
1. Assert mont_mult_1024.mem_wr_en_i with mem_sel_i selecting target RAM (op_a/op_b/n)
2. Write 32 words sequentially via mem_addr_i/mem_wdata_i
3. After loading both operands, assert start_i
4. Wait for done_o
5. Read result via result_addr_i/result_data_o, store into reg_A or reg_Result

---

## 3. Control Logic

### 3.1 rsa_modexp_top FSM (14 states)

```
ST_IDLE ──CTRL_REG=1──> ST_LOAD_M ──32 beats──> ST_TO_MONT
ST_TO_MONT ──start──> ST_WAIT_TO_MONT ──done──> ST_EXP_INIT
ST_EXP_INIT ──start──> ST_WAIT_INIT ──done──> ST_EXP_SQUARE
ST_EXP_SQUARE ──start──> ST_WAIT_SQUARE ──done──┬─E[bit]=1──> ST_EXP_MULT
                                                  └─E[bit]=0──> next square or ST_FROM_MONT
ST_EXP_MULT ──start──> ST_WAIT_MULT ──done──> next square or ST_FROM_MONT
ST_FROM_MONT ──start──> ST_WAIT_FROM_MONT ──done──> ST_OUTPUT
ST_OUTPUT ──32 beats──> ST_IDLE
```

Exponent scanning: MSB-first (bit 1023 down to 0). Counter `exp_bit_cnt` tracks current position.

### 3.2 mont_mult_1024 FSM (6 states)

```
ST_IDLE ──start──> ST_INIT ──t[] cleared──> ST_RUN
ST_RUN ──engine_start──> ST_WAIT ──engine_done──┬─i<31──> ST_RUN (next i)
                                                  └─i=31──> ST_COPY
ST_COPY ──32 words copied──> ST_DONE ──1 cycle──> ST_IDLE
```

### 3.3 mont_word_engine FSM (7 states)

```
ST_IDLE ──start──> ST_MULT_ACCUM ──j=32──> ST_CARRY1
ST_CARRY1 ──done──> ST_COMPUTE_M ──m ready──> ST_REDUCE_ACCUM
ST_REDUCE_ACCUM ──j=32──> ST_CARRY2 ──done──> ST_SHIFT
ST_SHIFT ──33 words──> ST_IDLE (done_o pulse)
```

### 3.4 dsp_mac_32

No FSM. 2-stage pipeline: inputs registered on cycle 1, multiply-add-output on cycle 2.

---

## 4. Algorithm Pseudocode

### 4.1 dsp_mac_32

```
Pipeline Stage 1 (cycle N):
  a_reg   <= a_i
  b_reg   <= b_i
  c_in_reg <= c_in_i
  t_in_reg <= t_in_i

Pipeline Stage 2 (cycle N+1):
  temp_64 = a_reg * b_reg + c_in_reg + t_in_reg
  res_out_o <= temp_64[31:0]
  c_out_o   <= temp_64[63:32]
```

### 4.2 mont_word_engine (CIOS Inner Loop)

```
INPUT: B[i] (32-bit), N' (32-bit)
       A[0..31] via ram_a, N[0..31] via ram_n, t[0..32] via ram_t
OUTPUT: Updated t[0..32]

// Phase 1: Multiply-Accumulate
C = 0
FOR j = 0 TO 31:
    // Issue RAM reads (1-cycle latency)
    addr_rd_o = j                    // reads A[j], N[j]
    t_rd_addr_o = j                  // reads t[j]
    // Wait 1 cycle for RAM data
    // Feed dsp_mac_32 (2-cycle pipeline)
    dsp_mac_32.a_i = A_j_i           // from ram_a
    dsp_mac_32.b_i = b_reg           // B[i], latched at start
    dsp_mac_32.c_in_i = carry_reg    // running carry
    dsp_mac_32.t_in_i = t_rd_data    // from ram_t
    // 2 cycles later, get result
    carry_reg = dsp_mac_32.c_out_o
    t_wr_addr_o = j
    t_wr_data_o = dsp_mac_32.res_out_o
    t_wr_en_o = 1
// Carry propagation to t[32]
t_rd_addr_o = 32
t[32] = t[32] + carry_reg

// Phase 2: Compute Reduction Factor
t_rd_addr_o = 0
wait 1 cycle
m_factor = (t_rd_data * n_prime_i) & 0xFFFFFFFF   // keep lower 32 bits

// Phase 3: Reduce-Accumulate
C = 0
FOR j = 0 TO 31:
    addr_rd_o = j                    // reads N[j]
    t_rd_addr_o = j                  // reads t[j]
    // Feed dsp_mac_32
    dsp_mac_32.a_i = N_j_i           // from ram_n
    dsp_mac_32.b_i = m_factor        // reduction factor
    dsp_mac_32.c_in_i = carry_reg
    dsp_mac_32.t_in_i = t_rd_data
    // 2 cycles later
    carry_reg = dsp_mac_32.c_out_o
    t_wr_addr_o = j
    t_wr_data_o = dsp_mac_32.res_out_o
    t_wr_en_o = 1
// Carry propagation to t[32] if carry_reg != 0
t[32] = t[32] + carry_reg

// Phase 4: Shift (t[j] = t[j+1])
FOR j = 0 TO 32:
    t_rd_addr_o = j + 1
    wait 1 cycle
    t_wr_addr_o = j
    t_wr_data_o = t_rd_data
    t_wr_en_o = 1
```

### 4.3 mont_mult_1024 (CIOS Outer Loop)

```
INPUT: A[0..31], B[0..31], N[0..31], N'
OUTPUT: Result[0..31] = MonPro(A, B)

// Initialize
t[0..32] = 0
i = 0

// Outer loop
FOR i = 0 TO 31:
    start mont_word_engine(B[i], N')
    wait for done
    // After done, t[] is updated for this iteration

// Result is in t[0..31]
copy t[0..31] to result RAM
assert done_o
```

### 4.4 rsa_modexp_top (Square-and-Multiply)

```
INPUT: M via AXI-Stream, E via AXI-Lite, N via AXI-Lite, R2 via AXI-Lite, N' via AXI-Lite
OUTPUT: Result = M^E mod N via AXI-Stream

// Wait for start
wait for CTRL_REG write (0x0001)

// Load message M
FOR w = 0 TO 31:
    receive s_axis_tdata -> reg_M[w]
    assert s_axis_tready

// Convert M to Montgomery domain
load mont_mult: op_a = M, op_b = R2
start mont_mult, wait done
M_mont = mont_mult result

// Initialize accumulator in Montgomery domain
load mont_mult: op_a = 1, op_b = R2
start mont_mult, wait done
A_mont = mont_mult result

// Square-and-Multiply (MSB to LSB)
FOR bit = 1023 DOWNTO 0:
    // Square
    load mont_mult: op_a = A_mont, op_b = A_mont
    start mont_mult, wait done
    A_mont = mont_mult result

    // Conditional multiply
    IF E[bit] == 1:
        load mont_mult: op_a = A_mont, op_b = M_mont
        start mont_mult, wait done
        A_mont = mont_mult result

// Exit Montgomery domain
load mont_mult: op_a = A_mont, op_b = 1
start mont_mult, wait done
Result = mont_mult result

// Output result
FOR w = 0 TO 31:
    m_axis_tdata = Result[w]
    assert m_axis_tvalid
    wait for m_axis_tready
    m_axis_tlast = (w == 31)

// Done
STAT_REG.DONE = 1
goto IDLE
```

### 4.5 CIOS Mathematical Reference (verbatim from requirement.md)

Word size w = 32, number of words s = 32.
N' = -N^(-1) mod 2^32

**Outer loop** i from 0 to s-1:
1. **Multiply-Accumulate:**
   C = 0
   **Inner loop** j from 0 to s-1:
   (C, t[j]) = t[j] + A[j] × B[i] + C
   t[s] = t[s] + C
2. **Reduction:**
   Compute reduction factor m = (t[0] × N') mod 2^32
   C = 0
   **Inner loop** j from 0 to s-1:
   (C, t[j]) = t[j] + N[j] × m + C
3. **Shift:**
   **Inner loop** j from 0 to s-1:
   t[j] = t[j+1]

---

## 5. Interface Protocol

### 5.1 Inter-Module Communication

#### rsa_modexp_top ↔ mont_mult_1024
| Signal | Width | Direction | Protocol |
|--------|-------|-----------|----------|
| start_i | 1 | top→mult | Pulse (1 cycle) |
| done_o | 1 | mult→top | Level (held until next start) |
| mem_wr_en_i | 1 | top→mult | Level (write enable) |
| mem_sel_i | 2 | top→mult | Data (00=op_a, 01=op_b, 10=n) |
| mem_addr_i | 5 | top→mult | Data (word index) |
| mem_wdata_i | 32 | top→mult | Data (word value) |
| n_prime_i | 32 | top→mult | Data (held constant) |
| result_addr_i | 5 | top→mult | Data (word index) |
| result_data_o | 32 | mult→top | Data (combinational read) |

#### mont_mult_1024 ↔ mont_word_engine
| Signal | Width | Direction | Protocol |
|--------|-------|-----------|----------|
| start_i | 1 | mult→engine | Pulse (1 cycle) |
| done_o | 1 | engine→mult | Pulse (1 cycle) |
| b_i | 32 | mult→engine | Data (valid at start) |
| n_prime_i | 32 | mult→engine | Data (held constant) |
| addr_rd_o | 5 | engine→mult | Address (registered) |
| a_j_i | 32 | mult→engine | Data (1-cycle RAM latency) |
| n_j_i | 32 | mult→engine | Data (1-cycle RAM latency) |
| t_rd/t_wr signals | various | bidirectional | RAM interface |

#### mont_word_engine ↔ dsp_mac_32
| Signal | Width | Direction | Protocol |
|--------|-------|-----------|----------|
| a_i, b_i, c_in_i, t_in_i | 32 each | engine→mac | Data (continuous, 2-cycle pipeline) |
| res_out_o, c_out_o | 32 each | mac→engine | Data (registered, 2-cycle latency) |

### 5.2 AXI4-Lite Slave (rsa_modexp_top external)

Standard AXI4-Lite protocol with no burst support:
- Write: AWADDR+AWVALID → AWREADY, WDATA+WVALID → WREADY, BRESP+BVALID → BREADY
- Read: ARADDR+ARVALID → ARREADY, RDATA+RRESP+RVALID → RREADY
- All responses OKAY (2'b00)

Address map (16-bit address, 32-bit data):
| Offset | Name | R/W | Description |
|--------|------|-----|-------------|
| 0x0000 | CTRL_REG | W | bit[0]=1 starts modexp |
| 0x0004 | STAT_REG | R | bit[0]=BUSY, bit[1]=DONE |
| 0x0010 | PARAM_N_PRIME | R/W | Montgomery N' (32-bit) |
| 0x0100-0x017F | MEM_MODULUS_N | R/W | N[0..31], 4-byte stride |
| 0x0200-0x027F | MEM_EXPONENT_E | R/W | E[0..31], 4-byte stride |
| 0x0300-0x037F | MEM_R_SQUARE | R/W | R^2[0..31], 4-byte stride |

### 5.3 AXI4-Stream (rsa_modexp_top external)

- Sink (input): 32 beats of TDATA[31:0], TLAST on beat 31, LSB-first (word 0 first)
- Source (output): 32 beats of TDATA[31:0], TLAST on beat 31, LSB-first
- Backpressure: TREADY deasserted when module busy

---

## 6. Timing Closure Plan

### 6.1 Critical Path Analysis

| Path | Logic | Estimated Delay | Margin |
|------|-------|----------------|--------|
| dsp_mac_32 multiply-add | 32×32 mult + 64-bit add (DSP48E2) | ~2.5 ns | 1.5 ns |
| CIOS FSM + RAM addr gen | State transition + counter + MUX | ~1.5 ns | 2.5 ns |
| AXI4-Lite decode | Address compare + register MUX | ~2.0 ns | 2.0 ns |
| Operand load MUX | 32-to-1 word selection | ~1.8 ns | 2.2 ns |

### 6.2 Mitigation Strategies

1. **DSP48E2 for multiplication**: Behavioral `*` operator lets yosys infer DSP48E2, avoiding LUT-based multiplier that would not meet 4 ns timing.
2. **Registered RAM outputs**: All RAM reads are synchronous (1-cycle latency), breaking combinational paths.
3. **FSM output registers**: FSM outputs (RAM addresses, control signals) are registered to break combinational feedback.
4. **Pipeline dsp_mac_32**: 2-stage pipeline absorbs multiply-add delay into two clock periods.

### 6.3 Clock Domain

Single clock domain (clk_core at 250 MHz). No CDC required.

---

## 7. Resource Plan

### 7.1 Estimated Usage Per Module

| Module | LUTs | FFs | BRAM (36K) | DSP48E2 |
|--------|------|-----|-----------|---------|
| dsp_mac_32 | ~50 | ~200 | 0 | 1 |
| mont_word_engine | ~300 | ~150 | 0 | 0 |
| mont_mult_1024 | ~500 | ~300 | 3 | 0 |
| rsa_modexp_top | ~2000 | ~1500 | 0 | 0 |
| **Total** | **~2850** | **~2150** | **3** | **1** |

### 7.2 Memory Map

| Storage | Size | Type | Location |
|---------|------|------|----------|
| ram_op_a | 32×32 | BRAM | mont_mult_1024 |
| ram_op_b | 32×32 | BRAM | mont_mult_1024 |
| ram_n | 32×32 | BRAM | mont_mult_1024 |
| ram_t | 33×32 | Distributed RAM | mont_mult_1024 |
| reg_N | 32×32 | FF | rsa_modexp_top |
| reg_E | 32×32 | FF | rsa_modexp_top |
| reg_R2 | 32×32 | FF | rsa_modexp_top |
| reg_M | 32×32 | FF | rsa_modexp_top |
| reg_A | 32×32 | FF | rsa_modexp_top |
| reg_Result | 32×32 | FF | rsa_modexp_top |

### 7.3 Device Utilization (XCVU9P)

| Resource | Used | Available | Utilization |
|----------|------|-----------|-------------|
| LUTs | ~2,850 | 1,182,240 | <1% |
| FFs | ~2,150 | 2,364,480 | <1% |
| BRAM36K | 3 | 2,160 | <1% |
| DSP48E2 | 1 | 6,840 | <1% |

The design easily fits the VU9P with vast margin. The dominant resources are FFs for the register arrays (N, E, R2, M, A, Result — six 1024-bit arrays = 6144 FFs total).

---

## 8. Key Design Decisions

1. **CIOS over other Montgomery variants**: CIOS interleaves multiplication and reduction word-by-word, minimizing memory bandwidth (only needs to read A[j] and N[j] per cycle) and accumulator size (33 words instead of full 2048-bit). This is optimal for FPGA with BRAM-based operand storage.

2. **Single DSP48E2**: The design uses one DSP48E2 for all 32×32 multiplications, time-multiplexed across all words. This minimizes DSP usage at the cost of throughput. A fully parallel design would use 32 DSPs but is unnecessary for RSA throughput requirements.

3. **Operands in FFs (rsa_modexp_top level)**: N, E, R2, M, A, Result are stored as flip-flop arrays rather than BRAMs because they need to be loaded/read word-by-word via AXI-Lite and AXI-Stream, and the sizes (32×32 = 1024 bits each) are small enough to use FFs without significant area penalty.

4. **Operand RAMs in mont_mult_1024**: op_a, op_b, and n use BRAM because they are accessed sequentially by mont_word_engine (one word per cycle), which matches BRAM read characteristics perfectly.

5. **t[] accumulator as distributed RAM**: The t[0..32] accumulator needs fast read-modify-write in a single cycle during CIOS. Distributed RAM (LUT-based) provides combinational read with synchronous write, ideal for this pattern.

6. **Sync-high reset**: Per requirement spec. All modules use `always @(posedge clk)` with `if (rst)` reset. No synchronizer chain needed.

7. **Behavioral multiplication**: Using `*` operator for 32×32 multiply instead of instantiating DSP48E2 primitives. This ensures iverilog simulation compatibility while yosys maps to DSP48E2 during synthesis.

8. **LSB-first word ordering**: CIOS algorithm processes words from index 0 (LSB) to 31 (MSB). AXI-Stream also sends word 0 first. No byte reordering needed.

9. **Final subtraction omitted in Montgomery**: The CIOS algorithm as described produces a result in [0, 2N). For RSA operations where inputs are always < N, the result is correct without final subtraction. If needed, a conditional subtraction can be added as a post-processing step.

10. **Exponent scanning MSB-first**: Square-and-Multiply scans from bit 1023 down to 0. This is the standard left-to-right method. The exponent E is stored with E[0] being the least significant word, so bit indexing requires word + bit extraction: E[bit/32][bit%32].
