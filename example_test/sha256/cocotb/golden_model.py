"""SHA-256 golden model — FIPS 180-4 compliant reference implementation.

Used by cocotb testbench to verify RTL output cycle-by-cycle.
Provides sha256_compress(block_int, iv_tuple) → digest_int
"""

# Initial Hash Values (FIPS 180-4 Section 5.3.3)
H0 = 0x6a09e667
H1 = 0xbb67ae85
H2 = 0x3c6ef372
H3 = 0xa54ff53a
H4 = 0x510e527f
H5 = 0x9b05688c
H6 = 0x1f83d9ab
H7 = 0x5be0cd19

IV = (H0, H1, H2, H3, H4, H5, H6, H7)

# Round Constants (FIPS 180-4 Section 4.2.2)
K = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
    0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
    0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
    0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
    0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
    0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]

MASK32 = 0xFFFFFFFF


def ROTR(x: int, n: int) -> int:
    return ((x >> n) | (x << (32 - n))) & MASK32


def SHR(x: int, n: int) -> int:
    return (x >> n) & MASK32


def Ch(x: int, y: int, z: int) -> int:
    return (x & y) ^ (~x & z) & MASK32


def Maj(x: int, y: int, z: int) -> int:
    return (x & y) ^ (x & z) ^ (y & z)


def Sigma0(x: int) -> int:
    return ROTR(x, 2) ^ ROTR(x, 13) ^ ROTR(x, 22)


def Sigma1(x: int) -> int:
    return ROTR(x, 6) ^ ROTR(x, 11) ^ ROTR(x, 25)


def sigma0(x: int) -> int:
    return ROTR(x, 7) ^ ROTR(x, 18) ^ SHR(x, 3)


def sigma1(x: int) -> int:
    return ROTR(x, 17) ^ ROTR(x, 19) ^ SHR(x, 10)


def sha256_compress(
    block: int,
    h_in: tuple[int, ...] = IV,
) -> tuple[int, int, int, int, int, int, int, int]:
    """SHA-256 compression: single 512-bit block → 256-bit digest.

    Args:
        block: 512-bit message block as integer
        h_in:  initial 8 x 32-bit hash values (default: FIPS 180-4 IV)

    Returns:
        (H0..H7) after compression, as 32-bit integers
    """
    # Parse block into 16 big-endian 32-bit words: W[0]=block[511:480], ...
    W = [0] * 64
    for i in range(16):
        shift = 512 - 32 * (i + 1)
        W[i] = (block >> shift) & MASK32

    # Expand to 64 words
    for t in range(16, 64):
        s0 = sigma0(W[t - 15])
        s1 = sigma1(W[t - 2])
        W[t] = (s1 + W[t - 7] + s0 + W[t - 16]) & MASK32

    a, b, c, d, e, f, g, h = h_in

    for t in range(64):
        T1 = (h + Sigma1(e) + Ch(e, f, g) + K[t] + W[t]) & MASK32
        T2 = (Sigma0(a) + Maj(a, b, c)) & MASK32
        h = g
        g = f
        f = e
        e = (d + T1) & MASK32
        d = c
        c = b
        b = a
        a = (T1 + T2) & MASK32

    return (
        (h_in[0] + a) & MASK32,
        (h_in[1] + b) & MASK32,
        (h_in[2] + c) & MASK32,
        (h_in[3] + d) & MASK32,
        (h_in[4] + e) & MASK32,
        (h_in[5] + f) & MASK32,
        (h_in[6] + g) & MASK32,
        (h_in[7] + h) & MASK32,
    )


def digest_to_int(h: tuple[int, ...]) -> int:
    """Pack 8 x 32-bit words into a single 256-bit integer."""
    result = 0
    for word in h:
        result = (result << 32) | word
    return result


# ─── Convenience runners ────────────────────────────────────────────────────


def sha256_empty_string() -> int:
    """SHA-256 of empty string (pre-padded single block)."""
    block = 0x80000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000
    return digest_to_int(sha256_compress(block))


def sha256_abc() -> int:
    """SHA-256 of 'abc' (pre-padded single block)."""
    block = 0x61626380_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000018
    return digest_to_int(sha256_compress(block))


# ─── Self-test ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # NIST test vectors
    empty_result = sha256_empty_string()
    expected_empty = 0xe3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
    print(f"Empty string: 0x{empty_result:064x}")
    print(f"  Expected:   0x{expected_empty:064x}")
    assert empty_result == expected_empty, f"Empty string FAIL"
    print("  PASS")

    abc_result = sha256_abc()
    expected_abc = 0xba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
    print(f"'abc':        0x{abc_result:064x}")
    print(f"  Expected:   0x{expected_abc:064x}")
    assert abc_result == expected_abc, f"'abc' FAIL"
    print("  PASS")

    # Golden model interface for vcd2table.py / vf-pipeline
    def run() -> list[dict]:
        """Standard VeriFlow pipeline interface: returns list[dict] of per-cycle
        expected outputs. For sha256_core, the output only materializes at the
        final cycle (digest_valid), so we provide a single entry keyed by the
        output signal name."""
        return [
            {
                # Empty string test
                "digest": sha256_empty_string(),
                "digest_valid": 1,
            },
            {
                # 'abc' test
                "digest": sha256_abc(),
                "digest_valid": 1,
            },
        ]

    print("\nAll golden model tests PASS")
