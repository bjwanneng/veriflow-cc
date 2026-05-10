## shift_register — 6-cycle trace

- registers: shift_reg[8]
- inputs: shift_en[1], data_in[1]
| cycle | shift_reg | shift_en | data_in |
|---:|---:|:---:|:---:|
| 0 | 0x00 | 1 | 1 |
| 1 | 0x80 | 1 | 0 |
| 2 | 0x00 | 1 | 1 |
| 3 | 0x80 | 1 | 1 |
| 4 | 0x80 | 0 | 0 |
| 5 | 0x80 | 1 | 0 |
