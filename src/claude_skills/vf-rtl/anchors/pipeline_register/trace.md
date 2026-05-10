## pipeline_register — 6-cycle trace

- registers: data_0_reg[32], data_1_reg[32], data_2_reg[32], valid_0_reg[1], valid_1_reg[1], valid_2_reg[1]
- inputs: data_in[32], valid_in[1]
| cycle | data_0_reg | data_1_reg | data_2_reg | valid_0_reg | valid_1_reg | valid_2_reg | data_in | valid_in |
|---:|---:|---:|---:|:---:|:---:|:---:|---:|:---:|
| 0 | 0x00000000 | 0x00000000 | 0x00000000 | 0 | 0 | 0 | 0x12345678 | 1 |
| 1 | 0x12345678 | 0x00000000 | 0x00000000 | 1 | 0 | 0 | 0xdeadbeef | 1 |
| 2 | 0xdeadbeef | 0x12345678 | 0x00000000 | 1 | 1 | 0 | 0x00000000 | 0 |
| 3 | 0x00000000 | 0xdeadbeef | 0x12345678 | 0 | 1 | 1 | 0xcafe0000 | 1 |
| 4 | 0xcafe0000 | 0x00000000 | 0xdeadbeef | 1 | 0 | 1 | 0x00000000 | 0 |
| 5 | 0x00000000 | 0xcafe0000 | 0x00000000 | 0 | 1 | 0 | 0x00000000 | 0 |
