"""Team recolouring of VTF textures without decompressing them (TF2 Classified fork).

Open Fortress (and TF2) team textures exist for RED and BLU only; TF2 Classified also has GRN
and YLW teams (weapon skin 2 and 3, TF2C GetTeamSkin()). These helpers make green and yellow
textures from the red one by rotating the hue of reddish colours (other colours, such as wood or
metal, keep theirs):

* DXT1/DXT3/DXT5: only the two RGB565 endpoints of every 4x4 block are transformed; the
  interpolated colours follow. DXT1 blocks keep their 3/4-colour mode (endpoint order is
  restored, with the index remap, when the transform swaps it).
* RGBA8888 / ABGR8888 / BGRA8888 / RGB888 / BGR888: per pixel.
"""
import colorsys
import struct

# VTF image formats
FMT = {0: "RGBA8888", 1: "ABGR8888", 2: "RGB888", 3: "BGR888", 12: "BGRA8888", 13: "DXT1", 14: "DXT3", 15: "DXT5"}
BPP = {0: 4, 1: 4, 2: 3, 3: 3, 12: 4}
BLOCK = {13: 8, 14: 16, 15: 16}
TEAM_HUE = {"green": 120.0, "yellow": 50.0}


def recolor_rgb(r, g, b, team):
    """r, g, b in 0..255 -> recoloured for team ('green'/'yellow'); only reddish hues move."""
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    deg = h * 360.0
    dist = min(deg, 360.0 - deg)          # distance from pure red
    if s < 0.18 or dist > 45.0:
        return r, g, b
    w = 1.0 if dist <= 30.0 else (45.0 - dist) / 15.0
    target = TEAM_HUE[team]
    off = deg if deg <= 180 else deg - 360.0   # signed offset from red
    nh = ((target + off) % 360.0) / 360.0
    if team == "yellow":
        v2 = min(1.0, v * 1.08)
    else:
        v2 = v * 0.92
    nr, ng, nb = colorsys.hsv_to_rgb(nh, s, v2)
    nr, ng, nb = nr * 255, ng * 255, nb * 255
    return (int(round(r + (nr - r) * w)), int(round(g + (ng - g) * w)), int(round(b + (nb - b) * w)))


def _565(c):
    r, g, b = (c >> 11) & 31, (c >> 5) & 63, c & 31
    return (r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)


def _to565(r, g, b):
    r, g, b = max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))
    return ((r * 31 + 127) // 255) << 11 | ((g * 63 + 127) // 255) << 5 | ((b * 31 + 127) // 255)


def _dxt_color_block(b, o, team, dxt1, cache):
    c0, c1 = struct.unpack_from("<HH", b, o)
    four = c0 > c1 or not dxt1          # DXT3/5 colour blocks are always 4-colour
    n0 = cache.get(c0)
    if n0 is None:
        n0 = cache[c0] = _to565(*recolor_rgb(*_565(c0), team))
    n1 = cache.get(c1)
    if n1 is None:
        n1 = cache[c1] = _to565(*recolor_rgb(*_565(c1), team))
    idx = struct.unpack_from("<I", b, o + 4)[0]
    if dxt1:
        if four and n0 <= n1:
            if n0 == n1:
                idx = 0                  # flat block: all endpoint 0
            else:
                n0, n1 = n1, n0          # keep 4-colour mode: swap and remap 0<->1, 2<->3
                idx ^= 0x55555555
        elif not four and n0 > n1:
            n0, n1 = n1, n0              # keep 3-colour mode: swap, remap 0<->1 (2, 3 stay)
            m = 0
            for k in range(16):
                v = (idx >> (2 * k)) & 3
                if v < 2:
                    v ^= 1
                m |= v << (2 * k)
            idx = m
    struct.pack_into("<HHI", b, o, n0, n1, idx)


def recolor_pixels(pix, fmt, team):
    b = bytearray(pix)
    if fmt in BLOCK:
        step = BLOCK[fmt]
        coff = 8 if step == 16 else 0
        cache = {}
        for o in range(0, len(b) - step + 1, step):
            _dxt_color_block(b, o + coff, team, fmt == 13, cache)
        return bytes(b)
    if fmt not in BPP:
        raise ValueError("unsupported VTF format %d" % fmt)
    n = BPP[fmt]
    order = {0: (0, 1, 2), 1: (3, 2, 1), 2: (0, 1, 2), 3: (2, 1, 0), 12: (2, 1, 0)}[fmt]
    cache = {}
    for o in range(0, len(b) - n + 1, n):
        key = bytes(b[o:o + n])
        if key in cache:
            b[o:o + n] = cache[key]
            continue
        r, g, bl = b[o + order[0]], b[o + order[1]], b[o + order[2]]
        nr, ng, nb = recolor_rgb(r, g, bl, team)
        b[o + order[0]], b[o + order[1]], b[o + order[2]] = nr, ng, nb
        cache[key] = bytes(b[o:o + n])
    return bytes(b)


def image_size(w, h, fmt, mips, frames=1, depth=1):
    total = 0
    for m in range(mips):
        mw, mh = max(1, w >> m), max(1, h >> m)
        if fmt in BLOCK:
            total += ((mw + 3) // 4) * ((mh + 3) // 4) * BLOCK[fmt]
        else:
            total += mw * mh * BPP[fmt]
    return total * frames * depth


def recolor_vtf(data, team):
    """Whole VTF file -> recoloured VTF file (header, resources and low-res thumbnail kept)."""
    w, h = struct.unpack_from("<HH", data, 16)
    frames = struct.unpack_from("<H", data, 24)[0] or 1
    fmt = struct.unpack_from("<i", data, 52)[0]
    mips = data[56]
    if fmt not in FMT:
        raise ValueError("unsupported VTF format %d" % fmt)
    size = image_size(w, h, fmt, mips, frames)
    hi = data[len(data) - size:]
    return data[:len(data) - size] + recolor_pixels(hi, fmt, team)
