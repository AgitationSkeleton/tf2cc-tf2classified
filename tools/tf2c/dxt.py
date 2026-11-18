"""Small DXT5 (BC3) decoder / encoder for item icons (numpy, no external tools).

decode(payload, w, h, fmt) -> HxWx4 uint8 for fmt 15 (DXT5) or 0 (RGBA8888)
encode_dxt5(rgba) -> bytes (colour endpoints from each block's principal axis, alpha 8-step ramp)
icon_vtf(rgba, flags) -> a VTF 7.2 file (one mip, no thumbnail) of an RGBA image as DXT5
"""
import struct

import numpy as np


def _565(c):
    r = ((c >> 11) & 31) * 255 // 31
    g = ((c >> 5) & 63) * 255 // 63
    b = (c & 31) * 255 // 31
    return np.stack([r, g, b], -1).astype(np.float32)


def decode(payload, w, h, fmt):
    if fmt == 0:
        return np.frombuffer(payload[:w * h * 4], np.uint8).reshape(h, w, 4).copy()
    if fmt != 15:
        raise ValueError("unsupported format %d" % fmt)
    bw, bh = (w + 3) // 4, (h + 3) // 4
    blk = np.frombuffer(payload[:bw * bh * 16], np.uint8).reshape(bh * bw, 16)
    a0 = blk[:, 0].astype(np.int32)
    a1 = blk[:, 1].astype(np.int32)
    abits = np.zeros(len(blk), np.uint64)
    for i in range(6):
        abits |= blk[:, 2 + i].astype(np.uint64) << np.uint64(8 * i)
    aidx = np.stack([(abits >> np.uint64(3 * k)) & np.uint64(7) for k in range(16)], 1).astype(np.int32)
    ramp = np.zeros((len(blk), 8), np.float32)
    ramp[:, 0], ramp[:, 1] = a0, a1
    big = a0 > a1
    for k in range(2, 8):
        ramp[:, k] = np.where(big, ((8 - k) * a0 + (k - 1) * a1) / 7.0,
                              np.where(k < 6, ((6 - k) * a0 + (k - 1) * a1) / 5.0, 0 if k == 6 else 255))
    alpha = np.take_along_axis(ramp, aidx, 1)
    c0 = blk[:, 8].astype(np.int32) | (blk[:, 9].astype(np.int32) << 8)
    c1 = blk[:, 10].astype(np.int32) | (blk[:, 11].astype(np.int32) << 8)
    p0, p1 = _565(c0), _565(c1)
    pal = np.stack([p0, p1, (2 * p0 + p1) / 3.0, (p0 + 2 * p1) / 3.0], 1)
    cbits = blk[:, 12].astype(np.int64) | (blk[:, 13].astype(np.int64) << 8) | (blk[:, 14].astype(np.int64) << 16) | (blk[:, 15].astype(np.int64) << 24)
    cidx = np.stack([(cbits >> (2 * k)) & 3 for k in range(16)], 1)
    col = np.take_along_axis(pal, cidx[..., None].repeat(3, -1), 1)
    px = np.concatenate([col, alpha[..., None]], -1).reshape(bh, bw, 4, 4, 4).transpose(0, 2, 1, 3, 4).reshape(bh * 4, bw * 4, 4)
    return np.clip(px[:h, :w], 0, 255).astype(np.uint8)


def _to565(c):
    c = np.clip(np.rint(c), 0, 255).astype(np.int32)
    return ((c[..., 0] * 31 + 127) // 255 << 11) | ((c[..., 1] * 63 + 127) // 255 << 5) | ((c[..., 2] * 31 + 127) // 255)


def encode_dxt5(rgba):
    h, w = rgba.shape[:2]
    bh, bw = (h + 3) // 4, (w + 3) // 4
    img = np.zeros((bh * 4, bw * 4, 4), np.float32)
    img[:h, :w] = rgba
    b = img.reshape(bh, 4, bw, 4, 4).transpose(0, 2, 1, 3, 4).reshape(bh * bw, 16, 4)
    rgb, a = b[..., :3], b[..., 3]
    # alpha: 8-step ramp between the block's max and min
    amax, amin = a.max(1), a.min(1)
    a0, a1 = np.rint(amax).astype(np.int32), np.rint(amin).astype(np.int32)
    same = a0 == a1
    a0 = np.where(same & (a0 < 255), a0 + 1, a0)
    a1 = np.where(same & (a0 >= 255), a0 - 1, a1)
    t = (a - a1[:, None]) / np.maximum(a0 - a1, 1)[:, None]          # 0 at a1, 1 at a0
    step = np.clip(np.rint(t * 7), 0, 7).astype(np.int32)             # 0..7 from a1 to a0
    order = np.array([1, 7, 6, 5, 4, 3, 2, 0])                         # code of each step (a0>a1 mode)
    aidx = order[step].astype(np.uint64)
    abits = np.zeros(len(b), np.uint64)
    for k in range(16):
        abits |= aidx[:, k] << np.uint64(3 * k)
    # colour: endpoints along the principal axis of the block's opaque-weighted colours
    wgt = (a / 255.0)[..., None] + 1e-3
    mean = (rgb * wgt).sum(1) / wgt.sum(1)
    d = rgb - mean[:, None]
    cov = np.einsum("nki,nkj->nij", d * wgt, d)
    axis = np.ones((len(b), 3), np.float32)
    for _ in range(8):
        axis = np.einsum("nij,nj->ni", cov, axis)
        axis /= np.maximum(np.linalg.norm(axis, axis=1, keepdims=True), 1e-6)
    proj = np.einsum("nki,ni->nk", d, axis)
    lo, hi = proj.min(1), proj.max(1)
    e0 = mean + axis * hi[:, None]
    e1 = mean + axis * lo[:, None]
    c0, c1 = _to565(e0), _to565(e1)
    swap = c0 < c1
    c0, c1 = np.where(swap, c1, c0), np.where(swap, c0, c1)
    eq = c0 == c1                                                      # flat block: 4-colour mode needs c0 > c1
    c0 = np.where(eq & (c0 < 0xFFFF), c0 + 1, c0)
    c1 = np.where(eq & (c0 >= 0xFFFF), c0 - 1, c1)
    p0, p1 = _565(c0), _565(c1)
    pal = np.stack([p0, p1, (2 * p0 + p1) / 3.0, (p0 + 2 * p1) / 3.0], 1)
    dist = ((rgb[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(-1)
    cidx = dist.argmin(2).astype(np.int64)
    cbits = np.zeros(len(b), np.int64)
    for k in range(16):
        cbits |= cidx[:, k] << (2 * k)
    out = np.zeros((len(b), 16), np.uint8)
    out[:, 0], out[:, 1] = a0, a1
    for i in range(6):
        out[:, 2 + i] = ((abits >> np.uint64(8 * i)) & np.uint64(255)).astype(np.uint8)
    out[:, 8], out[:, 9] = c0 & 255, c0 >> 8
    out[:, 10], out[:, 11] = c1 & 255, c1 >> 8
    for i in range(4):
        out[:, 12 + i] = (cbits >> (8 * i)) & 255
    return out.tobytes()


def icon_vtf(rgba, flags=0x230C):
    """VTF 7.2, DXT5, one mip, no thumbnail. 0x230C = CLAMPS|CLAMPT|NOMIP|NOLOD|EIGHTBITALPHA,
    what TF2 Classified's own vgui/loadout/weapons icons use (512x512)."""
    h, w = rgba.shape[:2]
    hdr = bytearray(80)
    struct.pack_into("<4sIII", hdr, 0, b"VTF\0", 7, 2, 80)
    struct.pack_into("<HHIHH", hdr, 16, w, h, flags, 1, 0)
    struct.pack_into("<fff", hdr, 32, 0.5, 0.5, 0.5)
    struct.pack_into("<f", hdr, 48, 1.0)
    struct.pack_into("<iBiBBH", hdr, 52, 15, 1, -1, 0, 0, 1)
    return bytes(hdr) + encode_dxt5(rgba)
