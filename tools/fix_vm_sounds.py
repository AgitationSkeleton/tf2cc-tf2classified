#!/usr/bin/env python3
"""Make OF/TF2C viewmodel sound events audible on stock TF2 clients.

Viewmodel sequences fire AE_CL_PLAYSOUND (event 5004) with a SOUND SCRIPT name
in the event options (e.g. "Weapon_Nailgun.Draw"). Stock clients only know
stock scripts, so OF/TF2C-only names play nothing. This rewrites each such
option to the raw wave path the script resolves to (EmitSound accepts raw
paths; the options field is 64 bytes, in place) and copies the wave files
into assets/overrides/tf/sound/.

  python -I tools/fix_vm_sounds.py            # dry run
  python -I tools/fix_vm_sounds.py --apply

Patched models: assets/overrides/tf/models/weapons/tf2cc_<rev>/v_*.mdl (generated
viewmodels; copied from assets/tf when only there).
"""
import os
import re
import shutil
import struct
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OVR = os.path.join(ROOT, "assets", "overrides", "tf")
LIVE = os.path.join(ROOT, "assets", "tf")
OFG = r"<STEAMCMD>/sdk2013\open_fortress"
TF2C_VPK = r"<STEAMCMD>/tf2classified-1\tf2classified\vpks\tf2c_assets_dir.vpk"
TF2_VPK = r"<STEAMCMD>/tf2\tf\tf2_misc_dir.vpk"
VPKTOOL = os.path.join(ROOT, "tools", "vpktool.py")
BS = chr(92)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from asset_rev import VIEWMODELS_REL  # noqa: E402


def vpk(cmd, vpkfile, *args):
    return subprocess.run([sys.executable, "-I", VPKTOOL, cmd, vpkfile] + list(args), capture_output=True).stdout


def script_names(text):
    return set(m.group(1).lower() for m in re.finditer(r'^\s*"([^"\s]+\.[^"\s]+)"\s*$', text, re.M))


def parse_scripts(text):
    """script name (lower) -> list of wave paths."""
    out = {}
    for m in re.finditer(r'"([^"\s]+\.[^"\s]+)"\s*\{(.*?)\n\}', text, re.S):
        waves = re.findall(r'"wave"\s+"([^"]+)"', m.group(2))
        if not waves:
            waves = re.findall(r'"wave"\s+"([^"]+)"', m.group(2).split('"rndwave"')[-1])
        rnd = re.search(r'"rndwave"\s*\{(.*?)\}', m.group(2), re.S)
        if rnd:
            waves = re.findall(r'"wave"\s+"([^"]+)"', rnd.group(1)) or waves
        if waves:
            out[m.group(1).lower()] = waves
    return out


def load_stock():
    """stock script name (lower) -> waves"""
    out = {}
    for path in vpk("list", TF2_VPK, "scripts/game_sounds").decode().split():
        t = vpk("cat", TF2_VPK, path).decode("latin-1")
        for n in script_names(t):
            out.setdefault(n, [])
        out.update(parse_scripts(t))
    return out


def load_custom():
    scripts = {}
    for f in os.listdir(os.path.join(OFG, "scripts")):
        if f.startswith("game_sounds") and f.endswith(".txt"):
            scripts.update(parse_scripts(open(os.path.join(OFG, "scripts", f), encoding="latin-1").read()))
    for path in vpk("list", TF2C_VPK, "scripts/game_sounds").decode().split():
        for k, v in parse_scripts(vpk("cat", TF2C_VPK, path).decode("latin-1")).items():
            scripts.setdefault(k, v)
    return scripts


def wave_source(rel):
    rel = rel.lstrip(")^*#<>@").replace(BS, "/")
    p = os.path.join(OFG, "sound", rel)
    if os.path.exists(p):
        return rel, open(p, "rb").read()
    data = vpk("cat", TF2C_VPK, "sound/" + rel.lower())
    if data:
        return rel, data
    return rel, None


def events(b):
    n, idx = struct.unpack_from("<ii", b, 188)
    for k in range(n):
        o = idx + k * 212
        ne, ei = struct.unpack_from("<ii", b, o + 24)
        for e in range(ne):
            eo = o + ei + e * 80
            cyc, ev, typ = struct.unpack_from("<fii", b, eo)
            yield eo, ev, b[eo + 12:eo + 76].split(b"\0")[0].decode("latin-1")


def main():
    apply = "--apply" in sys.argv
    stock = load_stock()
    custom = load_custom()
    vmdir_o = os.path.join(OVR, *VIEWMODELS_REL.split("/"))
    vmdir_l = os.path.join(LIVE, *VIEWMODELS_REL.split("/"))
    files = set(f for d in (vmdir_o, vmdir_l) if os.path.isdir(d) for f in os.listdir(d) if f.endswith(".mdl"))
    changed, waves_needed, missing = 0, {}, set()
    for f in sorted(files):
        src = os.path.join(vmdir_o, f) if os.path.exists(os.path.join(vmdir_o, f)) else os.path.join(vmdir_l, f)
        b = bytearray(open(src, "rb").read())
        edits = []
        for eo, ev, opt in events(bytes(b)):
            if ev != 5004 or not opt or "/" in opt:
                continue
            waves = custom.get(opt.lower())
            # Stock scripts play as they are unless OF/TF2C define them differently
            # (e.g. Weapon_NailGun.Draw: stock draw_primary.wav, OF nail_gun_draw.wav).
            if opt.lower() in stock and (not waves or [w.lstrip(")^*#<>@").lower() for w in waves] == [w.lstrip(")^*#<>@").lower() for w in stock[opt.lower()]]):
                continue
            if not waves:
                missing.add(opt)
                continue
            rel = waves[-1].lstrip(")^*#<>@").replace(BS, "/")   # last definition wins (OF overrides)
            if len(rel) > 63:
                missing.add(opt + " (path too long)")
                continue
            edits.append((eo, opt, rel))
            waves_needed[rel] = waves[-1]
        if not edits:
            continue
        print(f)
        for eo, opt, rel in edits:
            print("   %-32s -> %s" % (opt, rel))
            b[eo + 12:eo + 76] = rel.encode("latin-1").ljust(64, b"\0")
        changed += 1
        if apply:
            base = f[:-4]
            if not src.startswith(vmdir_o):
                for ext in (".vvd", ".dx90.vtx", ".dx80.vtx", ".sw.vtx", ".phy"):
                    if os.path.exists(os.path.join(vmdir_l, base + ext)):
                        os.makedirs(vmdir_o, exist_ok=True)
                        shutil.copyfile(os.path.join(vmdir_l, base + ext), os.path.join(vmdir_o, base + ext))
            os.makedirs(vmdir_o, exist_ok=True)
            open(os.path.join(vmdir_o, f), "wb").write(bytes(b))
    print("%d viewmodel(s) %s; %d wave file(s)" % (changed, "patched" if apply else "to patch", len(waves_needed)))
    for rel in sorted(waves_needed):
        r, data = wave_source(rel)
        dst = os.path.join(OVR, "sound", r)
        if data is None:
            print("   MISSING WAVE", rel)
            continue
        if apply and not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            open(dst, "wb").write(data)
    if missing:
        print("unresolved scripts:", sorted(missing))


if __name__ == "__main__":
    main()
