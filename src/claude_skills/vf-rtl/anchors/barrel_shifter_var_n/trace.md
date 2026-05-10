## barrel_shifter_var_n — 5-cycle trace

- wires: barrel_shifter_var_n_out[32]
- inputs: data[32], shift_amount[5]
| cycle | barrel_shifter_var_n_out | data | shift_amount |
|---:|---:|---:|---:|
| 0 | 0x00000001 | 0x00000001 | 0 |
| 1 | 0x00000002 | 0x00000001 | 1 |
| 2 | 0x00000010 | 0x00000001 | 4 |
| 3 | 0x22334411 | 0x11223344 | 8 |
| 4 | 0x33441122 | 0x11223344 | 16 |
