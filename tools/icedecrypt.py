#!/usr/bin/env python3
"""Decrypt Valve ICE-encrypted script files (.ctx/.ctx class data, weapon .ctx).

Port of public-domain ICE (Matthew Kwan) as shipped in source-sdk-2013
src/mathlib/IceKey.cpp. Valve uses IceKey(0): 8 rounds; trailing bytes
(len % 8) are stored unencrypted.

  icedecrypt.py <file> [key]      (default key: E2NcUkG2, TF2's GetTFEncryptionKey)
"""
import sys

SMOD = [[333, 313, 505, 369], [379, 375, 319, 391], [361, 445, 451, 397], [397, 425, 395, 505]]
SXOR = [[0x83, 0x85, 0x9B, 0xCD], [0xCC, 0xA7, 0xAD, 0x41], [0x4B, 0x2E, 0xD4, 0x33], [0xEA, 0xCB, 0x2E, 0x04]]
PBOX = [0x00000001, 0x00000080, 0x00000400, 0x00002000, 0x00080000, 0x00200000, 0x01000000, 0x40000000,
        0x00000008, 0x00000020, 0x00000100, 0x00004000, 0x00010000, 0x00800000, 0x04000000, 0x20000000,
        0x00000004, 0x00000010, 0x00000200, 0x00008000, 0x00020000, 0x00400000, 0x08000000, 0x10000000,
        0x00000002, 0x00000040, 0x00000800, 0x00001000, 0x00040000, 0x00100000, 0x02000000, 0x80000000]
KEYROT = [0, 1, 2, 3, 2, 1, 3, 0, 1, 3, 2, 0, 3, 1, 0, 2]


def gf_mult(a, b, m):
    res = 0
    while b:
        if b & 1:
            res ^= a
        a <<= 1
        b >>= 1
        if a >= 256:
            a ^= m
    return res


def gf_exp7(b, m):
    if b == 0:
        return 0
    x = gf_mult(b, b, m)
    x = gf_mult(b, x, m)
    x = gf_mult(x, x, m)
    return gf_mult(b, x, m)


def perm32(x):
    res, i = 0, 0
    while x:
        if x & 1:
            res |= PBOX[i]
        i += 1
        x >>= 1
    return res


SBOX = [[0] * 1024 for _ in range(4)]
for i in range(1024):
    col = (i >> 1) & 0xFF
    row = (i & 1) | ((i & 0x200) >> 8)
    SBOX[0][i] = perm32(gf_exp7(col ^ SXOR[0][row], SMOD[0][row]) << 24)
    SBOX[1][i] = perm32(gf_exp7(col ^ SXOR[1][row], SMOD[1][row]) << 16)
    SBOX[2][i] = perm32(gf_exp7(col ^ SXOR[2][row], SMOD[2][row]) << 8)
    SBOX[3][i] = perm32(gf_exp7(col ^ SXOR[3][row], SMOD[3][row]))


def schedule(key):
    kb = [0] * 4
    for i in range(4):
        kb[3 - i] = (key[i * 2] << 8) | key[i * 2 + 1]
    sched = []
    for i in range(8):
        kr = KEYROT[i]
        sk = [0, 0, 0]
        for j in range(15):
            for k in range(4):
                idx = (kr + k) & 3
                bit = kb[idx] & 1
                sk[j % 3] = ((sk[j % 3] << 1) | bit) & 0xFFFFFFFF
                kb[idx] = (kb[idx] >> 1) | ((bit ^ 1) << 15)
        sched.append(sk)
    return sched


def f(p, sk):
    tl = ((p >> 16) & 0x3FF) | ((((p >> 14) | (p << 18)) & 0xFFFFFFFF) & 0xFFC00)
    tr = (p & 0x3FF) | ((p << 2) & 0xFFC00)
    al = sk[2] & (tl ^ tr)
    ar = al ^ tr
    al ^= tl
    al ^= sk[0]
    ar ^= sk[1]
    return SBOX[0][al >> 10] | SBOX[1][al & 0x3FF] | SBOX[2][ar >> 10] | SBOX[3][ar & 0x3FF]


def decrypt(data, key):
    sched = schedule(key)
    out = bytearray()
    n = len(data) - len(data) % 8
    for o in range(0, n, 8):
        l = int.from_bytes(data[o:o + 4], "big")
        r = int.from_bytes(data[o + 4:o + 8], "big")
        for i in range(7, 0, -2):
            l ^= f(r, sched[i])
            r ^= f(l, sched[i - 1])
        out += r.to_bytes(4, "big") + l.to_bytes(4, "big")
    out += data[n:]
    return bytes(out)


if __name__ == "__main__":
    key = (sys.argv[2] if len(sys.argv) > 2 else "E2NcUkG2").encode()
    with open(sys.argv[1], "rb") as fh:
        sys.stdout.buffer.write(decrypt(fh.read(), key))
