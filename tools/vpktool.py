#!/usr/bin/env python3
"""Minimal read-only Valve VPK v1/v2 reader.

  vpktool.py list <x_dir.vpk> [substring ...]
  vpktool.py cat  <x_dir.vpk> <path>
  vpktool.py extract <x_dir.vpk> <outdir> <substring> [substring ...]
"""
import os
import struct
import sys


def read_tree(dirpath):
    with open(dirpath, "rb") as f:
        sig, ver, tree = struct.unpack("<III", f.read(12))
        if sig != 0x55AA1234:
            raise SystemExit("not a vpk: " + dirpath)
        hdr = 12 + (16 if ver == 2 else 0)
        f.seek(hdr)
        data = f.read(tree)

    def cstr(p):
        e = data.index(b"\0", p)
        return data[p:e].decode("latin-1"), e + 1

    entries = {}
    p = 0
    while True:
        ext, p = cstr(p)
        if not ext:
            break
        while True:
            path, p = cstr(p)
            if not path:
                break
            while True:
                name, p = cstr(p)
                if not name:
                    break
                crc, pre, arc, off, length, term = struct.unpack_from("<IHHIIH", data, p)
                p += 18
                preload = data[p:p + pre]
                p += pre
                full = (name + "." + ext) if path.strip() == "" else (path + "/" + name + "." + ext)
                entries[full.lower()] = (arc, off, length, preload)
    return entries, hdr + tree


def read_file(dirpath, entries, base, key):
    arc, off, length, preload = entries[key]
    if length == 0:
        return preload
    if arc == 0x7FFF:
        src = dirpath
        off += base
    else:
        src = dirpath.replace("_dir.vpk", "_%03d.vpk" % arc)
    with open(src, "rb") as f:
        f.seek(off)
        return preload + f.read(length)


def main():
    cmd, vpk = sys.argv[1], sys.argv[2]
    entries, base = read_tree(vpk)
    if cmd == "list":
        subs = [s.lower() for s in sys.argv[3:]]
        for k in sorted(entries):
            if all(s in k for s in subs):
                print(k)
    elif cmd == "cat":
        sys.stdout.buffer.write(read_file(vpk, entries, base, sys.argv[3].lower()))
    elif cmd == "extract":
        out = sys.argv[3]
        subs = [s.lower() for s in sys.argv[4:]]
        n = 0
        for k in sorted(entries):
            if any(s in k for s in subs):
                dst = os.path.join(out, k)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(dst, "wb") as f:
                    f.write(read_file(vpk, entries, base, k))
                n += 1
        print("extracted", n)


if __name__ == "__main__":
    main()
