# Behavior Specification: rsa1024_modexp_accel

## 1. Domain Knowledge

### 1.1 Background

RSA is an asymmetric cryptographic algorithm where security relies on the computational difficulty of factoring large integers. RSA-2048 uses 2048-bit keys, but the Chinese Remainder Theorem (CRT) optimization splits RSA-2048 into two parallel RSA-1024 operations, halving the hardware datapath width. The core operation is modular exponentiation (M^E mod N), which is computed using repeated modular multiplications. Montgomery multiplication eliminates costly trial divisions by transforming numbers into Montgomery domain where modular reduction becomes inexpensive word-by-word operations.

### 1.2 Key Concepts

- **Modular Exponentiation**: Computing M^E mod N using Square-and-Multiply algorithm. Each squaring or multiplication is a full 1024-bit modular multiply.
- **Montgomery Multiplication (MonPro)**: Algorithm for computing A × B × R^(-1) mod N without explicit division. Uses precomputed N' = -N^(-1) mod 2^w.
- **CIOS (Coarsely Integrated Operand Scanning)**: A word-level Montgomery multiplication algorithm that interleaves multiplication and reduction in a word-serial fashion, minimizing memory bandwidth and area.
- **Montgomery Domain**: Numbers are transformed by multiplying by R = 2^1024. Operations in this domain use MonPro instead of regular modular multiply. Conversion: M_mont = MontMul(M, R^2 mod N). Inverse: Result = MontMul(A_mont, 1).
- **CRT (Chinese Remainder Theorem)**: Optimization that splits RSA-2048 into two RSA-1024 operations (one mod p, one mod q), performed in software. Hardware only handles 1024-bit width.
- **Square-and-Multiply**: Exponentiation algorithm that scans exponent bits from MSB to LSB. For each bit: square accumulator; if bit=1, also multiply by base.
- **DSP48E2**: Xilinx UltraScale+ DSP block that performs 27x18 or 32x32 (cascaded) multiplication efficiently. Behavioral `*` operator is mapped to DSP48E2 by synthesis tools.

### 1.3 References

- PKCS#1 v2.2: RSA Cryptography Standard (IETF RFC 8017)
- "High-Speed RSA Implementation" by Cetin Kaya Koc, RSA Laboratories
- Montgomery, P. L. "Modular Multiplication Without Trial Division", Mathematics of Computation, 1985
- CIOS Algorithm: Koc, Acar, Kaliski "Analyzing and Comparing Montgomery Multiplication Algorithms", IEEE Micro, 1996

### 1.4 Glossary

| Term | Definition |
|------|-----------|
| MonPro | Montgomery Product: A × B × R^(-1) mod N |
| CIOS | Coarsely Integrated Operand Scanning Montgomery algorithm |
| CRT | Chinese Remainder Theorem for RSA optimization |
| N' | Montgomery parameter: -N^(-1) mod 2^32 |
| R | Montgomery radix: 2^1024 for 1024-bit operands |
| R^2 mod N | Precomputed Montgomery domain conversion factor |
| w | Word width: 32 bits |
| s | Number of words: 32 (for 1024-bit operands) |
| t[] | CIOS accumulator array: 33 words (0 to 32) |

---

## 2. Module Behavior: dsp_mac_32

### 2.1 Cycle-Accurate Behavior

#### Normal Operation
| Cycle | Condition | Action | Output Change | Next State |
|-------|-----------|--------|---------------|------------|
| 0 | Inputs valid | Register a, b, c_in, t_in into pipeline stage 1 | No change | Pipeline stage 1 loaded |
| 1 | Pipeline stage 1 loaded | Compute temp_64 = a * b + c_in + t_in | No change | Computation in progress |
| 2 | Computation complete | Register result: res_out = temp_64[31:0], c_out = temp_64[63:32] | res_out, c_out updated | Outputs valid |

#### Reset Behavior
| Cycle | Condition | Action | Output Change |
|-------|-----------|--------|---------------|
| -1 | rst asserted | Clear all pipeline registers | res_out = 0, c_out = 0 |
| 0 | rst de-asserted | Ready to accept new inputs | Outputs hold reset values |

### 2.2 FSM Specification

This module has no FSM. It is a pure 2-stage pipeline that processes data every cycle after filling the pipeline.

### 2.3 Register Requirements
| Register | Width (bits) | Reset Value | Purpose |
|----------|-------------|-------------|---------|
| a_reg | 32 | 0 | Pipeline stage 1: registered multiplicand |
| b_reg | 32 | 0 | Pipeline stage 1: registered multiplier |
| c_in_reg | 32 | 0 | Pipeline stage 1: registered carry-in |
| t_in_reg | 32 | 0 | Pipeline stage 1: registered accumulated value |
| res_out | 32 | 0 | Pipeline stage 2: result word |
| c_out | 32 | 0 | Pipeline stage 2: carry-out |

### 2.4 Timing Contracts
- **Latency**: 2 cycles (from input change to output update)
- **Throughput**: 1 result per cycle (fully pipelined after initial fill)
- **Backpressure behavior**: N/A (no handshake; inputs are continuously sampled)
- **Reset recovery**: 0 cycles after rst de-assertion (ready immediately)

### 2.5 Algorithm Pseudocode

```
INPUT: a[31:0], b[31:0], c_in[31:0], t_in[31:0]
OUTPUT: res_out[31:0], c_out[31:0]

Step 1: Register inputs (pipeline stage 1)
  a_reg <= a; b_reg <= b; c_in_reg <= c_in; t_in_reg <= t_in

Step 2: Compute (pipeline stage 2)
  temp_64 = a_reg * b_reg + c_in_reg + t_in_reg  // 64-bit result
  res_out <= temp_64[31:0]
  c_out   <= temp_64[63:32]
```

### 2.6 Protocol Details

No complex protocol — synchronous pipeline with registered inputs and outputs. No valid/ready handshake.

---

## 2. Module Behavior: mont_word_engine

### 2.1 Cycle-Accurate Behavior

#### Normal Operation (simplified per-phase view)
| Cycle | Condition | Action | Output Change | Next State |
|-------|-----------|--------|---------------|------------|
| 0 | start_i asserted | Latch b_i, begin MULT_ACCUM | addr_rd_o = 0, t_rd_addr_o = 0 | MULT_ACCUM |
| 1-2 | MULT_ACCUM j=0 | Issue RAM reads for A[0], N[0], t[0]; feed dsp_mac_32 | addr_rd_o increments | Waiting for MAC |
| 3 | MAC result ready (j=0) | Write result to t[0], start j=1 | t_wr_en=1, t_wr_data=MAC result | Next j |
| ... | ... | Repeat for j=1..31 | ... | ... |
| N | j=31 complete | Carry propagation to t[32] | t_wr for t[32] | COMPUTE_M |
| N+1 | COMPUTE_M | Read t[0], compute m = t[0] * n_prime | m_factor computed | REDUCE_ACCUM |
| N+2 | REDUCE_ACCUM j=0 | Issue reads for N[0], t[0]; feed dsp_mac_32 | addr_rd_o = 0 | Waiting for MAC |
| ... | ... | Repeat for j=0..31 | ... | ... |
| M | REDUCE done | Carry propagation | t_wr for t[32] | SHIFT |
| M+1 | SHIFT | t[j] = t[j+1] for j=0..31 | Sequential reads/writes | SHIFT |
| M+32 | Shift complete | Assert done_o | done_o = 1 | IDLE |

#### Reset Behavior
| Cycle | Condition | Action | Output Change |
|-------|-----------|--------|---------------|
| -1 | rst asserted | Clear all counters and state | done_o = 0, all outputs = 0 |
| 0 | rst de-asserted | Enter IDLE state | Ready for start_i |

### 2.2 FSM Specification

#### States
| State Name | Description | Outputs |
|-----------|-------------|---------|
| ST_IDLE | Waiting for start_i | done_o = 0, all outputs inactive |
| ST_MULT_ACCUM | Multiply-accumulate phase: j=0..31, compute t[j] += A[j]*B[i] + C | addr_rd_o = j, t_wr_en active |
| ST_CARRY1 | Carry propagation: t[32] += C from MULT_ACCUM | t_wr_addr = 32 |
| ST_COMPUTE_M | Compute reduction factor m = t[0] * N' mod 2^32 | Internal computation |
| ST_REDUCE_ACCUM | Reduce-accumulate phase: j=0..31, compute t[j] += N[j]*m + C | addr_rd_o = j, t_wr_en active |
| ST_CARRY2 | Carry propagation: handle final carry from REDUCE_ACCUM | t_wr_addr = 32 |
| ST_SHIFT | Shift t array: t[j] = t[j+1] for j=0..31 | Sequential t_rd/t_wr |

#### Transitions
| From | To | Condition |
|------|----|-----------|
| ST_IDLE | ST_MULT_ACCUM | start_i asserted |
| ST_MULT_ACCUM | ST_CARRY1 | j counter reaches NUM_WORDS (32) |
| ST_CARRY1 | ST_COMPUTE_M | Carry write complete |
| ST_COMPUTE_M | ST_REDUCE_ACCUM | m_factor computed (1 cycle) |
| ST_REDUCE_ACCUM | ST_CARRY2 | j counter reaches NUM_WORDS (32) |
| ST_CARRY2 | ST_SHIFT | Carry write complete |
| ST_SHIFT | ST_IDLE | All 33 words shifted (counter = 33) |

#### Initial State: ST_IDLE

### 2.3 Register Requirements
| Register | Width (bits) | Reset Value | Purpose |
|----------|-------------|-------------|---------|
| state | 3 | 0 (IDLE) | FSM state register |
| j_cnt | 5 | 0 | Inner loop word counter (0-31) |
| carry | 32 | 0 | Carry propagation register |
| b_reg | 32 | 0 | Latched B[i] value |
| m_factor | 32 | 0 | Computed reduction factor |
| shift_cnt | 6 | 0 | Shift phase counter (0-32) |

### 2.4 Timing Contracts
- **Latency**: ~130-140 cycles per invocation (32 MULT + 32 REDUCE + 33 SHIFT + overhead, accounting for 2-cycle DSP pipeline)
- **Throughput**: 1 inner loop iteration per ~130-140 cycles
- **Backpressure behavior**: Stall (waits for start_i, no backpressure on RAM)
- **Reset recovery**: 0 cycles after rst de-assertion

### 2.5 Algorithm Pseudocode (CIOS Inner Loop)

```
INPUT: B[i] (fixed outer loop multiplier), N' (Montgomery parameter)
       A[0..31] via RAM, N[0..31] via RAM, t[0..32] via RAM
OUTPUT: Updated t[0..32] array (one outer iteration of CIOS)

// Phase 1: Multiply-Accumulate
C = 0
FOR j = 0 TO s-1:
    (C, t[j]) = t[j] + A[j] * B[i] + C    // via dsp_mac_32 (2-cycle latency)
t[32] = t[32] + C                           // carry propagation

// Phase 2: Compute Reduction Factor
m = (t[0] * N') mod 2^32                    // simple 32x32 multiply, keep lower 32 bits

// Phase 3: Reduce-Accumulate
C = 0
FOR j = 0 TO s-1:
    (C, t[j]) = t[j] + N[j] * m + C        // via dsp_mac_32 (2-cycle latency)
// carry propagation to t[32] if needed

// Phase 4: Shift
FOR j = 0 TO s:
    t[j] = t[j+1]                            // shift array left by one word
```

Note: The 2-cycle latency of dsp_mac_32 must be accounted for in the FSM. The pipeline can be kept busy by issuing the next RAM read while the previous MAC is computing.

### 2.6 Protocol Details

RAM read timing: addr_rd_o is asserted, data (a_j_i, n_j_i) is available on the next clock cycle. This is standard synchronous RAM timing.

---

## 2. Module Behavior: mont_mult_1024

### 2.1 Cycle-Accurate Behavior

#### Normal Operation
| Cycle | Condition | Action | Output Change | Next State |
|-------|-----------|--------|---------------|------------|
| 0 | start_i asserted | Initialize i=0, clear t[0..32] | done_o = 0 | RUN_OUTER |
| 1 | i=0 | Load B[0], start mont_word_engine | engine_start = 1, b_i = B[0] | WAIT_ENGINE |
| ... | engine running | Wait for mont_word_engine done | ... | WAIT_ENGINE |
| N | engine done, i<31 | Increment i, load B[i+1], restart engine | engine_start = 1 | WAIT_ENGINE |
| ... | engine done, i=31 | All iterations complete | Copy result from t[] to op_a RAM | COMPLETE |
| M | Result copied | Assert done_o | done_o = 1 | IDLE |

#### Reset Behavior
| Cycle | Condition | Action | Output Change |
|-------|-----------|--------|---------------|
| -1 | rst asserted | Clear all RAMs and registers | done_o = 0 |
| 0 | rst de-asserted | Enter IDLE | Ready for start_i |

### 2.2 FSM Specification

#### States
| State Name | Description | Outputs |
|-----------|-------------|---------|
| ST_IDLE | Waiting for start_i | done_o = 0 |
| ST_INIT | Clear t[0..32], set i=0 | Initialize t RAM |
| ST_RUN | Start mont_word_engine for iteration i | engine_start = 1, b_i = B[i] |
| ST_WAIT | Wait for mont_word_engine to complete | Monitor engine done_o |
| ST_COPY | Copy result from t[] to op_a result storage | Read t[], write to result RAM |
| ST_DONE | Assert done_o for one cycle | done_o = 1 |

#### Transitions
| From | To | Condition |
|------|----|-----------|
| ST_IDLE | ST_INIT | start_i asserted |
| ST_INIT | ST_RUN | t[] initialized (33 cycles) |
| ST_RUN | ST_WAIT | engine_start pulse sent |
| ST_WAIT | ST_RUN | engine done AND i < 31 |
| ST_WAIT | ST_COPY | engine done AND i = 31 |
| ST_COPY | ST_DONE | All 32 result words copied |
| ST_DONE | ST_IDLE | done_o pulsed (1 cycle) |

#### Initial State: ST_IDLE

### 2.3 Register Requirements
| Register | Width (bits) | Reset Value | Purpose |
|----------|-------------|-------------|---------|
| state | 3 | 0 (IDLE) | FSM state |
| i_cnt | 5 | 0 | Outer loop counter (0-31) |
| copy_cnt | 5 | 0 | Result copy counter |

Internal RAMs:
| RAM | Depth x Width | Type | Purpose |
|-----|--------------|------|---------|
| ram_op_a | 32 x 32 | BRAM | Operand A |
| ram_op_b | 32 x 32 | BRAM | Operand B |
| ram_n | 32 x 32 | BRAM | Modulus N |
| ram_t | 33 x 32 | Distributed | CIOS accumulator |

### 2.4 Timing Contracts
- **Latency**: ~4200-4500 cycles (32 outer iterations × ~130-140 cycles per inner iteration + overhead)
- **Throughput**: 1 Montgomery multiplication per ~4200-4500 cycles
- **Backpressure behavior**: N/A (start/done handshake)
- **Reset recovery**: 0 cycles after rst de-assertion

### 2.5 Algorithm Pseudocode (CIOS Outer Loop)

```
INPUT: A[0..31], B[0..31], N[0..31], N'
OUTPUT: Result[0..31] = MonPro(A, B) = A * B * R^(-1) mod N

// Initialize accumulator
t[0..32] = 0

// Outer loop: 32 iterations
FOR i = 0 TO 31:
    // Inner loop via mont_word_engine
    C = 0
    FOR j = 0 TO 31:
        (C, t[j]) = t[j] + A[j] * B[i] + C
    t[32] = t[32] + C

    m = (t[0] * N') mod 2^32
    C = 0
    FOR j = 0 TO 31:
        (C, t[j]) = t[j] + N[j] * m + C
    // carry propagation

    FOR j = 0 TO 32:
        t[j] = t[j+1]

// Final subtraction (if result >= N)
// Note: For correct Montgomery multiplication, final subtraction
// may be needed if t >= N. This is handled conditionally.
Result = t[0..31]
```

### 2.6 Protocol Details

Operand loading: Before starting, parent writes operands via mem_wr_en_i/mem_sel_i/mem_addr_i/mem_wdata_i interface. This is a simple synchronous write port with 1-cycle latency (write on posedge clk when mem_wr_en_i = 1).

Result reading: After done_o is asserted, parent reads result via result_addr_i/result_data_o. This is a combinational read from the internal result RAM.

---

## 2. Module Behavior: rsa_modexp_top

### 2.1 Cycle-Accurate Behavior

#### Normal Operation (Square-and-Multiply)
| Cycle | Condition | Action | Output Change | Next State |
|-------|-----------|--------|---------------|------------|
| 0 | AXI write to CTRL_REG (0x0000 = 1) | Load parameters complete, start FSM | hw_start_pulse = 1 | ST_LOAD_M |
| 1-32 | ST_LOAD_M | Receive 32 words via AXI-Stream into M buffer | s_axis_tready = 1 | ST_TO_MONT |
| 33 | ST_TO_MONT | Load M as op_a, R2 as op_b; start mont_mult | mont_mult start | ST_WAIT_MONT |
| ... | mont_mult running | Wait for mont_mult done | ... | ST_WAIT_MONT |
| N | mont_mult done | Store M_mont = MontMul(M, R^2) | M_mont stored | ST_EXP_INIT |
| N+1 | ST_EXP_INIT | Load 1 as op_a, R2 as op_b; start mont_mult | mont_mult start | ST_WAIT_INIT |
| ... | mont_mult running | Wait for result | ... | ST_WAIT_INIT |
| M | init done | Store A_mont = MontMul(1, R^2) | A_mont stored | ST_EXP_SQUARE |
| M+1 | ST_EXP_SQUARE | Load A as both ops; start mont_mult (square) | mont_mult start | ST_WAIT_SQ |
| ... | mont_mult running | Wait for result | ... | ST_WAIT_SQ |
| K | square done | Update A_mont = MontMul(A, A) | A_mont updated | ST_EXP_MULT / next bit |
| K+1 | E[bit]=1, ST_EXP_MULT | Load A and M_mont; start mont_mult (multiply) | mont_mult start | ST_WAIT_MUL |
| ... | mont_mult running | Wait for result | ... | ST_WAIT_MUL |
| L | multiply done | Update A_mont = MontMul(A, M_mont) | A_mont updated | ST_EXP_SQUARE / next bit |
| ... | All bits processed | Exponentiation complete | ... | ST_FROM_MONT |
| P | ST_FROM_MONT | Load A as op_a, 1 as op_b; start mont_mult | mont_mult start | ST_WAIT_FROM |
| Q | from_mont done | Result = MontMul(A, 1) | Result stored | ST_OUTPUT |
| Q+1 to Q+32 | ST_OUTPUT | Send 32 words via AXI-Stream | m_axis_tvalid = 1 | ST_IDLE (after last beat) |

#### Reset Behavior
| Cycle | Condition | Action | Output Change |
|-------|-----------|--------|---------------|
| -1 | rst asserted | Clear all registers, FSM to IDLE | All AXI outputs at reset values |
| 0 | rst de-asserted | Enter ST_IDLE, AXI-Lite slave ready | Can accept register writes |

### 2.2 FSM Specification

#### States
| State Name | Description | Outputs |
|-----------|-------------|---------|
| ST_IDLE | Waiting for CTRL_REG start command | BUSY=0, DONE=0 |
| ST_LOAD_M | Receiving message M via AXI-Stream (32 beats) | s_axis_tready=1 |
| ST_TO_MONT | Convert M to Montgomery domain: MontMul(M, R^2) | mont_mult start |
| ST_WAIT_TO_MONT | Wait for MontMul(M, R^2) to complete | BUSY=1 |
| ST_EXP_INIT | Initialize accumulator: MontMul(1, R^2) | mont_mult start |
| ST_WAIT_INIT | Wait for MontMul(1, R^2) | BUSY=1 |
| ST_EXP_SQUARE | Square step: MontMul(A, A) | mont_mult start |
| ST_WAIT_SQUARE | Wait for square result | BUSY=1 |
| ST_EXP_MULT | Multiply step (if E[bit]=1): MontMul(A, M_mont) | mont_mult start |
| ST_WAIT_MULT | Wait for multiply result | BUSY=1 |
| ST_FROM_MONT | Convert from Montgomery domain: MontMul(A, 1) | mont_mult start |
| ST_WAIT_FROM_MONT | Wait for final MontMul | BUSY=1 |
| ST_OUTPUT | Output result via AXI-Stream (32 beats) | m_axis_tvalid=1, DONE=1 |

#### Transitions
| From | To | Condition |
|------|----|-----------|
| ST_IDLE | ST_LOAD_M | CTRL_REG written with bit[0]=1 |
| ST_LOAD_M | ST_TO_MONT | 32nd AXI-Stream beat received (s_axis_tlast) |
| ST_TO_MONT | ST_WAIT_TO_MONT | mont_mult started |
| ST_WAIT_TO_MONT | ST_EXP_INIT | mont_mult done |
| ST_EXP_INIT | ST_WAIT_INIT | mont_mult started |
| ST_WAIT_INIT | ST_EXP_SQUARE | mont_mult done |
| ST_EXP_SQUARE | ST_WAIT_SQUARE | mont_mult started |
| ST_WAIT_SQUARE | ST_EXP_MULT | mont_mult done AND E[bit]=1 AND bits remaining |
| ST_WAIT_SQUARE | ST_EXP_SQUARE | mont_mult done AND E[bit]=0 AND bits remaining |
| ST_WAIT_SQUARE | ST_FROM_MONT | mont_mult done AND all exponent bits processed |
| ST_EXP_MULT | ST_WAIT_MULT | mont_mult started |
| ST_WAIT_MULT | ST_EXP_SQUARE | mont_mult done AND bits remaining |
| ST_WAIT_MULT | ST_FROM_MONT | mont_mult done AND all exponent bits processed |
| ST_FROM_MONT | ST_WAIT_FROM_MONT | mont_mult started |
| ST_WAIT_FROM_MONT | ST_OUTPUT | mont_mult done |
| ST_OUTPUT | ST_IDLE | 32nd AXI-Stream beat sent (m_axis_tlast) |

#### Initial State: ST_IDLE

### 2.3 Register Requirements
| Register | Width (bits) | Reset Value | Purpose |
|----------|-------------|-------------|---------|
| state | 4 | 0 (IDLE) | FSM state |
| exp_bit_cnt | 11 | 0 | Exponent bit counter (0-1023) |
| word_cnt | 5 | 0 | AXI-Stream word counter (0-31) |
| reg_N[0:31] | 32 each | 0 | Modulus N (1024-bit, 32 words) |
| reg_E[0:31] | 32 each | 0 | Exponent E (1024-bit, 32 words) |
| reg_R2[0:31] | 32 each | 0 | R^2 mod N (1024-bit, 32 words) |
| reg_N_prime | 32 | 0 | Montgomery parameter N' |
| reg_M[0:31] | 32 each | 0 | Message M buffer |
| reg_A[0:31] | 32 each | 0 | Accumulator A buffer |
| reg_Result[0:31] | 32 each | 0 | Result buffer |

### 2.4 Timing Contracts
- **Latency**: ~16M-20M cycles worst case (1024 bits × ~8400 cycles per MontMul × 2 ops per bit when E[bit]=1)
  - Average: ~12M cycles (assuming ~50% of exponent bits are 1)
- **Throughput**: 1 RSA-1024 modexp per operation (~12M cycles average)
- **Backpressure behavior**: AXI-Stream input stalls when busy; AXI-Stream output stalls when downstream not ready
- **Reset recovery**: 0 cycles after rst de-assertion

### 2.5 Algorithm Pseudocode (Square-and-Multiply)

```
INPUT: M (message), E (exponent), N (modulus), R^2 mod N, N'
OUTPUT: Result = M^E mod N

// Step 1: Enter Montgomery domain
M_mont = MontMul(M, R^2 mod N)     // M * R mod N

// Step 2: Initialize accumulator
A_mont = MontMul(1, R^2 mod N)      // 1 * R mod N = R mod N

// Step 3: Square-and-Multiply loop (MSB to LSB)
FOR bit = 1023 DOWNTO 0:
    A_mont = MontMul(A_mont, A_mont)  // Square
    IF E[bit] == 1:
        A_mont = MontMul(A_mont, M_mont)  // Multiply

// Step 4: Exit Montgomery domain
Result = MontMul(A_mont, 1)          // Remove R factor
```

### 2.6 Protocol Details

#### AXI4-Lite Slave Protocol
- **Write transaction**: AW channel (awaddr + awvalid/awready) → W channel (wdata + wvalid/wready) → B channel (bresp + bvalid/bready)
- **Read transaction**: AR channel (araddr + arvalid/arready) → R channel (rdata + rresp + rvalid/rready)
- All responses use OKAY (bresp/rresp = 2'b00)
- No burst support (single beat per transaction)
- Address map:

| Offset | Register | Access | Description |
|--------|----------|--------|-------------|
| 0x0000 | CTRL_REG | W | bit[0]=1 starts operation |
| 0x0004 | STAT_REG | R | bit[0]=BUSY, bit[1]=DONE |
| 0x0010 | PARAM_N_PRIME | R/W | N' parameter (32-bit) |
| 0x0100-0x017F | MEM_MODULUS_N | R/W | N[0..31] (32 words, 4-byte stride) |
| 0x0200-0x027F | MEM_EXPONENT_E | R/W | E[0..31] (32 words, 4-byte stride) |
| 0x0300-0x037F | MEM_R_SQUARE | R/W | R^2[0..31] (32 words, 4-byte stride) |

#### AXI4-Stream Protocol
- **Input (sink)**: 32 beats of 32-bit TDATA with tlast on final beat. Message M is sent LSB-first (word 0 first).
- **Output (source)**: 32 beats of 32-bit TDATA with tlast on final beat. Result sent LSB-first (word 0 first).
- **Backpressure**: tready deasserted when module is busy (input) or not in OUTPUT state (output).

---

## 3. Cross-Module Timing

### 3.1 Pipeline Stage Assignment
| Pipeline Stage | Module | Duration (cycles) |
|---------------|--------|-------------------|
| DSP Pipeline Stage 1 | dsp_mac_32 (input registration) | 1 cycle |
| DSP Pipeline Stage 2 | dsp_mac_32 (multiply + add + output reg) | 1 cycle |
| CIOS Inner Loop | mont_word_engine | ~130-140 cycles |
| CIOS Outer Loop | mont_mult_1024 | ~4200-4500 cycles (32 inner iterations) |
| ModExp Loop | rsa_modexp_top | ~12M-20M cycles |

### 3.2 Module-to-Module Timing
| Source | Destination | Signal | Latency (cycles) |
|--------|------------|--------|------------------|
| mont_word_engine.a_j_i | dsp_mac_32.a_i (via MUX) | Operand A | 0 (combinational routing) |
| dsp_mac_32.res_out_o | mont_word_engine.t_wr_data_o (via pipeline) | MAC result | 2 (DSP pipeline) |
| mont_mult_1024.engine_start | mont_word_engine.start_i | Start pulse | 0 |
| mont_word_engine.done_o | mont_mult_1024.engine_done | Completion | 0 |
| rsa_modexp_top.mont_start | mont_mult_1024.start_i | Start pulse | 0 |
| mont_mult_1024.done_o | rsa_modexp_top.mont_done | Completion | 0 |
| RAM addr_rd_o | RAM a_j_i/n_j_i | Synchronous read | 1 |

### 3.3 Critical Path Description

The critical path is through the dsp_mac_32 module: the 32x32 multiplication (a * b) followed by two 64-bit additions (+ c_in + t_in) must complete within one clock period at 250 MHz (4 ns). On Xilinx UltraScale+ with DSP48E2, this path is well within timing closure as the DSP block handles the multiplication internally with dedicated carry chains. The second critical path is the CIOS inner loop control logic (FSM state transition + counter comparison + RAM address generation), which is purely LUT-based and should easily meet 4 ns timing on UltraScale+.
