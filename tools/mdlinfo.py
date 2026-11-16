#!/usr/bin/env python3
"""Read-only Source MDL (v44-v49) inspector.

Prints bones, attachments, sequences (label + activity), include models,
skin families and material names, so donor/arms/player models can be checked
for activity and skeleton compatibility without a game client.

  mdlinfo.py <file.mdl> [--seq] [--bones] [--att] [--inc] [--mat] [--acts]
  (no flags = summary of everything)
  --acts prints the sorted unique activity-name set only.
"""
import struct
import sys

SEQDESC_SIZE = 212
BONE_SIZE = 216
ATTACH_SIZE = 92


def cstr(buf, off):
    if off <= 0 or off >= len(buf):
        return ""
    end = buf.find(b"\0", off)
    return buf[off:end].decode("latin-1")


def parse(path):
    with open(path, "rb") as f:
        b = f.read()
    if b[:4] != b"IDST":
        raise SystemExit("not an MDL: " + path)
    i = lambda o: struct.unpack_from("<i", b, o)[0]
    info = {
        "version": i(4),
        "checksum": i(8) & 0xFFFFFFFF,
        "name": b[12:76].split(b"\0")[0].decode("latin-1"),
        "flags": i(152),
    }
    nb, bi = i(156), i(160)
    info["bones"] = [cstr(b, bi + k * BONE_SIZE + i(bi + k * BONE_SIZE)) for k in range(nb)]
    ns, si = i(188), i(192)
    seqs = []
    for k in range(ns):
        o = si + k * SEQDESC_SIZE
        seqs.append((cstr(b, o + i(o + 4)), cstr(b, o + i(o + 8)), i(o + 16)))
    info["sequences"] = seqs
    nt, ti = i(204), i(208)
    info["textures"] = [cstr(b, ti + k * 64 + i(ti + k * 64)) for k in range(nt)]
    ncd, cdi = i(212), i(216)
    info["cdtextures"] = [cstr(b, i(cdi + k * 4)) for k in range(ncd)]
    info["skinref"], info["skinfamilies"] = i(220), i(224)
    sk = i(228)
    info["skins"] = [[struct.unpack_from("<h", b, sk + (f * i(220) + r) * 2)[0] for r in range(i(220))]
                     for f in range(i(224))]
    na, ai = i(240), i(244)
    info["attachments"] = [cstr(b, ai + k * ATTACH_SIZE + i(ai + k * ATTACH_SIZE)) for k in range(na)]
    ninc, inci = i(336), i(340)
    info["includes"] = [cstr(b, inci + k * 8 + i(inci + k * 8 + 4)) for k in range(ninc)]
    return info


def main():
    path = sys.argv[1]
    flags = set(sys.argv[2:])
    m = parse(path)
    show = lambda f: not flags or f in flags
    if "--acts" in flags:
        for a in sorted({s[1] for s in m["sequences"] if s[1]}):
            print(a)
        return
    print("name=%s version=%d checksum=%08x bones=%d seqs=%d skins=%d attachments=%d includes=%d" % (
        m["name"], m["version"], m["checksum"], len(m["bones"]), len(m["sequences"]),
        m["skinfamilies"], len(m["attachments"]), len(m["includes"])))
    if show("--inc"):
        for x in m["includes"]:
            print("include", x)
    if show("--mat"):
        for x in m["cdtextures"]:
            print("cdmaterials", x)
        for x in m["textures"]:
            print("material", x)
    if show("--att"):
        for x in m["attachments"]:
            print("attachment", x)
    if show("--bones"):
        for x in m["bones"]:
            print("bone", x)
    if show("--seq"):
        for label, act, _ in m["sequences"]:
            print("seq %-40s %s" % (label, act))


if __name__ == "__main__":
    main()
