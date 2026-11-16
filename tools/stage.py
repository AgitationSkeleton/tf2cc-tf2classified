#!/usr/bin/env python3
"""Build the canonical asset tree and per-server drag-and-drop staging folders.

  python tools/stage.py assets     # refresh assets/tf from the live tf2-3 tree + fixes
  python tools/stage.py stage      # build deploy/staging/<server>/ from build/ + config/ + assets/
  python tools/stage.py all

Nothing here writes to a game server. Staging folders mirror a server's
game directory ("tf/...") so they can be merged by drag-and-drop after review.

Asset policy:
  * Source of class assets = live tf2-3 (the only deployment with the classes),
    restricted to the class asset roots below.
  * mercenary_animations2.mdl (first $includemodel of mercenary.mdl) exists only
    on FastDL; it is pulled from assets/overrides (committed, decompressed).
  * VMT fixes for OF-only material proxies live in assets/overrides and win.
  * Generated models (activity-retargeted v_models) come from tools/mdl_retarget.py.
"""
import hashlib
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIVE_TF = r"<STEAMCMD>/tf2-3/tf"
ASSETS = os.path.join(ROOT, "assets", "tf")
OVERRIDES = os.path.join(ROOT, "assets", "overrides", "tf")

ASSET_ROOTS = [
    "models/player/customclasses",
    "models/weapons/customclasses",
    "sound/vo/custom",
    "sound/weapons/custom",
    "models/weapons/custom_new/backupplan",   # legacy Backup Plan models
]
# Materials are NOT copied by directory: build_assets() computes the closure
# from every staged model (cdmaterials x textures -> VMT -> VTF/patch includes).
TEXTURE_KEYS = ("$basetexture", "$basetexture2", "$bumpmap", "$normalmap", "$detail",
                "$envmap", "$envmapmask", "$phongexponenttexture", "$phongwarptexture",
                "$lightwarptexture", "$selfillummask", "$blendmodulatetexture", "include")

RETARGETS = [  # superseded by tools/gen_viewmodels.py (assets/overrides)
    # (source, output, mappings) - see tools/mdl_retarget.py
    ]

# Explicit server allowlist. The vanilla server (Server3-NUC tf2-2) is a hard deny.
SERVERS = {
    "tf2-1_vscript": "<STEAMCMD>/tf2",
    "tf2-2_soapdm": "<STEAMCMD>/tf2-2",
    "tf2-3_secretbase": "<STEAMCMD>/tf2-3",
    "tf2-4_standard": "<STEAMCMD>/tf2-4",
}
DOWNLOAD_EXT = (".mdl", ".vvd", ".vtx", ".phy", ".vmt", ".vtf", ".wav", ".mp3")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def copytree_files(src_root, rel_root, dst_root):
    src = os.path.join(src_root, rel_root)
    n = 0
    if not os.path.isdir(src):
        print("  (missing on source) " + rel_root)
        return 0
    for dirpath, _, files in os.walk(src):
        for name in files:
            s = os.path.join(dirpath, name)
            rel = os.path.relpath(s, src_root).replace("\\", "/")
            d = os.path.join(dst_root, rel)
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy2(s, d)
            n += 1
    return n


def build_assets():
    if os.path.isdir(ASSETS):
        shutil.rmtree(ASSETS)
    os.makedirs(ASSETS)
    total = 0
    for r in ASSET_ROOTS:
        n = copytree_files(LIVE_TF, r, ASSETS)
        print("  %5d  %s" % (n, r))
        total += n

    # Overrides (FastDL-only include, VMT fixes) win over live copies.
    if os.path.isdir(OVERRIDES):
        for dirpath, _, files in os.walk(OVERRIDES):
            for name in files:
                s = os.path.join(dirpath, name)
                rel = os.path.relpath(s, OVERRIDES)
                d = os.path.join(ASSETS, rel)
                os.makedirs(os.path.dirname(d), exist_ok=True)
                shutil.copy2(s, d)
                print("  override " + rel.replace("\\", "/"))
    total += material_closure()
    for src, out, maps in RETARGETS:
        s = os.path.join(ASSETS, src)
        if os.path.exists(s):
            subprocess.check_call([sys.executable, "-I", os.path.join(ROOT, "tools", "mdl_retarget.py"),
                                   s, os.path.join(ASSETS, out)] + maps)
    drop_stock_shadows()
    write_manifest()
    print("assets: %d files from live + overrides" % total)


def _vmt_refs(path):
    refs = []
    with open(path, encoding="latin-1") as f:
        for line in f:
            t = line.strip().replace("	", " ")
            low = t.lower()
            for k in TEXTURE_KEYS:
                if low.startswith('"%s"' % k) or low.startswith(k + " ") or low.startswith(k + "	"):
                    parts = [x for x in t.replace('"', " ").split(" ") if x]
                    if len(parts) >= 2:
                        refs.append((k, parts[1].replace("\\", "/").lower()))
    return refs


def material_closure():
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import mdlinfo
    wanted, missing, n = set(), set(), 0
    for dirpath, _, files in os.walk(ASSETS):
        for name in files:
            if not name.endswith(".mdl"):
                continue
            try:
                m = mdlinfo.parse(os.path.join(dirpath, name))
            except Exception as e:  # noqa
                print("  !! cannot parse %s: %s" % (name, e))
                continue
            for cd in m["cdtextures"] or [""]:
                cd = cd.replace("\\", "/").lower().strip("/")
                for tex in m["textures"]:
                    rel = "materials/%s/%s.vmt" % (cd, tex.replace("\\", "/").lower()) if cd else "materials/%s.vmt" % tex.lower()
                    wanted.add(rel.replace("//", "/"))
    queue = list(wanted)
    seen = set()
    while queue:
        rel = queue.pop()
        if rel in seen:
            continue
        seen.add(rel)
        src = os.path.join(LIVE_TF, rel)
        if not os.path.exists(src):
            continue  # stock VPK material or alternate cdmaterials path
        dst = os.path.join(ASSETS, rel)
        if not os.path.exists(dst):  # never clobber overrides (VMT fixes)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            n += 1
        src = dst
        if rel.endswith(".vmt"):
            for key, ref in _vmt_refs(src):
                if key == "include":
                    queue.append(ref if ref.startswith("materials/") else "materials/" + ref)
                    continue
                vtf = "materials/%s.vtf" % ref
                if os.path.exists(os.path.join(LIVE_TF, vtf)):
                    queue.append(vtf)
                    hdr = vtf[:-4] + ".hdr.vtf"
                    if os.path.exists(os.path.join(LIVE_TF, hdr)):
                        queue.append(hdr)
                else:
                    missing.add(vtf)
    found_vmt = {r for r in seen if r.endswith(".vmt") and os.path.exists(os.path.join(LIVE_TF, r))}
    print("  %5d  materials (closure; %d VMTs found of %d candidate paths)" % (n, len(found_vmt), len(wanted)))
    with open(os.path.join(ROOT, "assets", "material_refs_not_in_live.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write("# VTFs referenced by staged VMTs but absent from live tf2-3 (stock VPK or genuinely missing)\n")
        for m in sorted(missing):
            f.write(m + "\n")
    return n


STOCK_VPKS = ["tf2_misc_dir.vpk", "tf2_textures_dir.vpk", "tf2_sound_misc_dir.vpk", "tf2_sound_vo_english_dir.vpk"]


def drop_stock_shadows():
    """Loose files override VPK files for every class: never ship a stock path."""
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import vpktool
    stock = set()
    for v in STOCK_VPKS:
        p = os.path.join(LIVE_TF, v)
        if os.path.exists(p):
            stock.update(vpktool.read_tree(p)[0].keys())
    dropped = []
    for dirpath, _, files in os.walk(ASSETS):
        for name in files:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, ASSETS).replace("\\", "/").lower()
            if rel in stock:
                os.remove(full)
                dropped.append(rel)
    with open(os.path.join(ROOT, "assets", "stock_shadow_excluded.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write("# Live tf2-3 loose files that shadow stock VPK files; excluded from staging\n")
        for d in sorted(dropped):
            f.write(d + "\n")
    print("  dropped %d stock-shadowing file(s)" % len(dropped))


def write_manifest():
    rows = []
    for dirpath, _, files in os.walk(ASSETS):
        for name in files:
            p = os.path.join(dirpath, name)
            rel = os.path.relpath(p, ASSETS).replace("\\", "/")
            origin = "override" if os.path.exists(os.path.join(OVERRIDES, rel)) else (
                "generated" if rel.startswith("models/weapons/tf2cc") else "tf2-3")
            rows.append((rel, os.path.getsize(p), sha256(p), origin))
    rows.sort()
    man = os.path.join(ROOT, "assets", "manifest.tsv")
    with open(man, "w", encoding="utf-8", newline="\n") as f:
        f.write("path\tbytes\tsha256\torigin\n")
        for r in rows:
            f.write("%s\t%d\t%s\t%s\n" % r)
    dl = os.path.join(ROOT, "config", "sourcemod", "configs", "tf2cc", "downloads.txt")
    with open(dl, "w", encoding="utf-8", newline="\n") as f:
        f.write("// Generated by tools/stage.py from assets/manifest.tsv. Do not edit.\n")
        for r in rows:
            if r[0].endswith(DOWNLOAD_EXT):
                f.write(r[0] + "\n")
    print("manifest: %d files" % len(rows))


# Classic Movement fork (src/compat): who keeps classic movement on each server,
# matching what the server's current build does (mphe 1.0.1 = everyone;
# tf2-3's reconstructed build defaults cm_merc_only 1).
CM_SCOPE = {
    "tf2-1_vscript": "all",
    "tf2-2_soapdm": "all",
    "tf2-3_secretbase": "mercenary",
    "tf2-4_standard": "all",
}


def stage_classicmovement_cfg(server, live, dst):
    """The server's own plugin.classicmovement.cfg plus the fork's cm_scope line."""
    src = os.path.join(live, "tf", "cfg", "sourcemod", "plugin.classicmovement.cfg")
    lines = []
    if os.path.exists(src):
        lines = [l.rstrip("\r\n") for l in open(src, encoding="utf-8", errors="replace")]
    lines = [l for l in lines if not l.strip().startswith(("cm_scope", "cm_merc_only"))]
    lines += ["", "// tf2cc Classic Movement fork: who gets classic movement", 'cm_scope "%s"' % CM_SCOPE[server]]
    out = os.path.join(dst, "cfg", "sourcemod")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "plugin.classicmovement.cfg"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def stage():
    out_root = os.path.join(ROOT, "deploy", "staging")
    if os.path.isdir(out_root):
        shutil.rmtree(out_root)
    plugins = os.path.join(ROOT, "build", "plugins")
    if not os.path.isdir(plugins) or not os.listdir(plugins):
        raise SystemExit("build/plugins is empty - run tools/build.sh first")
    for server, live in SERVERS.items():
        dst = os.path.join(out_root, server, "tf")
        pdir = os.path.join(dst, "addons", "sourcemod", "plugins", "tf2cc")
        os.makedirs(pdir)
        for name in sorted(os.listdir(plugins)):
            shutil.copy2(os.path.join(plugins, name), pdir)
        copytree_files(os.path.join(ROOT, "config"), "sourcemod", os.path.join(dst, "addons"))
        n = copytree_files(os.path.join(ROOT, "assets"), "tf", os.path.join(out_root, server))
        stage_classicmovement_cfg(server, live, dst)
        with open(os.path.join(out_root, server, "TARGET.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write("Target game dir: %s/tf\nMerge this folder's tf/ into it after reviewing docs/DEPLOYMENT.md.\n" % live)
        print("staged %s (%d asset files)" % (server, n))


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("assets", "all"):
        build_assets()
    if what in ("stage", "all"):
        stage()
