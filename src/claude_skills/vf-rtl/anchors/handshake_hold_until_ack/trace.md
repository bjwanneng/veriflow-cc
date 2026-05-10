## handshake_hold_until_ack — 6-cycle trace

- registers: pending[1], valid_reg[1]
- inputs: req[1], ack[1]
| cycle | pending | valid_reg | req | ack |
|---:|:---:|:---:|:---:|:---:|
| 0 | 0 | 0 | 0 | 0 |
| 1 | 0 | 0 | 1 | 0 |
| 2 | 1 | 0 | 0 | 0 |
| 3 | 1 | 1 | 0 | 0 |
| 4 | 1 | 1 | 0 | 1 |
| 5 | 0 | 1 | 0 | 0 |
