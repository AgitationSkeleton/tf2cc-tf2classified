#!/usr/bin/env python3
"""Build the TF2 Classified Mercenary player model with schema-addressable animations.

Why: on TF2 Classified each Merc weapon is a schema item, and the item's
`animation_replacement` can remap the activity the player's anim state asks for
(e.g. ACT_MP_RUN_SECONDARY) to another activity. Only activities registered when
the schema is parsed resolve, though, and the Open Fortress animation sets use
model-private ACT_MERC_* names that never are (docs/tf2classified/FINDINGS.md 7).

So this script renames every ACT_MERC_* activity in the OF animation files to an
unused built-in activity (the DOD/HL2MP entries of the shared activity list,
registered by both client and server at startup and never used by TF2 models)
and writes a JSON map that the schema generator turns into per-item
animation_replacement blocks. One player model then covers every weapon, and
client prediction picks the right sequences with no model swapping.

Output (under tf2c/staging/tf2classified/, served to clients by FastDL):
  models/player/tf2cc/merc.mdl (+.vvd/.dx90.vtx/.dx80.vtx/.sw.vtx/.phy)
                       the TF2C (HWM) Merc mesh, includes repointed below
  models/player/tf2cc/merc_animations.mdl
                       merc_deathmatch_animations.mdl with its includes repointed
  models/player/tf2cc/merc_anim/animations_<set>.mdl
                       OF set with ACT_MERC_* renamed to built-in activities
tf2c/merc_acts.json    {"acts": {ACT_MERC_x: builtin}, "replace": {set: {group: {act: builtin}}}}

Nothing named like a stock or 4dm file is written, so the 4dm maps' own Merc and
normal Soldiers are unaffected.

  python -I tools/tf2c/gen_merc_acts.py
"""
import json
import os
import re
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gen_merc_variants as gmv  # noqa: E402  (Mdl editor, OF acttable parsing, relabel_map)

SRC = os.path.join(ROOT, "work", "tf2c_merc_extract", "models", "player")
RESEARCH = os.path.join(ROOT, "work", "tf2c_research")
TF2C_WEAPONBASE = r"<SOURCE_TREES>/tf2c-src/src/game/shared/tf/tf_weaponbase.cpp"
STAGE = os.path.join(ROOT, "tf2c", "staging", "tf2classified")
OUT_REL = "models/player/tf2cc"
OUT_JSON = os.path.join(ROOT, "tf2c", "merc_acts.json")
MESH = os.path.join(SRC, "hwm", "merc_deathmatch")
POOL_RE = re.compile(r"^ACT_(DOD|HL2MP)_")


def registered_acts():
    """Activities named in both the server and the client binaries (the shared list)."""
    def grab(name):
        t = open(os.path.join(RESEARCH, name), encoding="latin-1").read()
        return set(re.findall(r"^ACT_[A-Z0-9_]+$", t, re.M))
    return grab("server_strings.txt") & grab("client_strings.txt")


def acts_of(path):
    m = gmv.Mdl(open(path, "rb").read())
    return m, [m.act(k) for k in range(m.nseq)]


def set_name_header(m, name):
    raw = name.encode("latin-1")[:63]
    m.b[12:76] = raw + b"\0" * (64 - len(raw))


def main():
    gmv.STOCK = {k: v for k, v in gmv.parse_stock_tables_from(TF2C_WEAPONBASE).items()} \
        if hasattr(gmv, "parse_stock_tables_from") else parse_tables(TF2C_WEAPONBASE)

    anim_dir = os.path.join(SRC, "merc_anim")
    sets = {}       # set name -> file stem
    for key, (stem, _, _) in gmv.OF_SETS.items():
        sets[key] = stem
    files = sorted(os.listdir(anim_dir))
    stems = {os.path.splitext(f)[0] for f in files}
    extra = sorted(stems - set(sets.values()))      # e.g. animations_zombieclaws (no OF table)

    # Activities that must stay untouched: everything the rest of the model uses.
    keep = set()
    for rel in ("merc_deathmatch_animations.mdl", "hwm/merc_deathmatch.mdl"):
        keep |= set(acts_of(os.path.join(SRC, rel))[1])
    merc = set()
    for f in files:
        merc |= {a for a in acts_of(os.path.join(anim_dir, f))[1] if a.startswith("ACT_MERC_")}
    pool = [a for a in sorted(registered_acts()) if POOL_RE.match(a) and a not in keep]
    if len(pool) < len(merc):
        raise SystemExit("activity pool too small: %d < %d" % (len(pool), len(merc)))
    amap = dict(zip(sorted(merc), pool))

    out_anim = os.path.join(STAGE, OUT_REL, "merc_anim")
    os.makedirs(out_anim, exist_ok=True)
    includes = []
    for f in files:
        m, acts = acts_of(os.path.join(anim_dir, f))
        for k, a in enumerate(acts):
            if a in amap:
                o = m.seq_off(k)
                weight = gmv.i32(m.b, o + 20)
                m.set_act(k, amap[a], weight)
        rel = "%s/merc_anim/%s" % (OUT_REL, f)
        set_name_header(m, rel[len("models/"):])
        open(os.path.join(STAGE, rel), "wb").write(m.finish())
        includes.append(rel)

    # Stock weapons a Merc picks up carry no animation_replacement: give the model OF sets
    # relabeled onto TF2C's own groups (ACT_MP_<X>_<GROUP>), weighted to beat the Soldier's
    # sequences for the same activity, as OF falls back to its generic sets (same table as
    # stock tf2cc's DEFAULT_GROUPS). Merc items are unaffected: their remaps point elsewhere.
    defaults = []
    for group, set_name in gmv.DEFAULT_GROUPS.items():
        if gmv.GROUP_TABLE.get(group) not in gmv.STOCK:
            continue
        stem = gmv.OF_SETS[set_name][0]
        m, acts = acts_of(os.path.join(anim_dir, stem + ".mdl"))
        mp, dropped, unserved, fuzzy = gmv.relabel_map(set_name, group, set(acts))
        for k, a in enumerate(acts):
            m.set_label(k, m.label(k) + "__" + group)
            if a in mp:
                m.set_act(k, mp[a], gmv.BIG_WEIGHT)
            else:
                m.set_act(k, "", 0)
        rel = "%s/merc_anim/default_%s__%s.mdl" % (OUT_REL, set_name, group.lower())
        set_name_header(m, rel[len("models/"):])
        open(os.path.join(STAGE, rel), "wb").write(m.finish())
        defaults.append(rel)

    # merc_animations.mdl: same sequences, includes repointed in the original order,
    # after the group defaults.
    m, acts = acts_of(os.path.join(SRC, "merc_deathmatch_animations.mdl"))
    order = [os.path.basename(i) for i in m.includes()]
    m.set_includes(defaults + ["%s/merc_anim/%s" % (OUT_REL, b) for b in order])
    set_name_header(m, "player/tf2cc/merc_animations.mdl")
    open(os.path.join(STAGE, OUT_REL, "merc_animations.mdl"), "wb").write(m.finish())

    # merc.mdl: the mesh; first include swapped to ours, Soldier includes kept.
    m = gmv.Mdl(open(MESH + ".mdl", "rb").read())
    inc = [("%s/merc_animations.mdl" % OUT_REL) if i.lower().endswith("merc_deathmatch_animations.mdl") else i
           for i in m.includes()]
    m.set_includes(inc)
    prepend_cdtexture(m, TEAM_MAT_DIR.replace("/", "\\") + "\\")
    write_team_materials()
    set_name_header(m, "player/tf2cc/merc.mdl")
    dst = os.path.join(STAGE, OUT_REL, "merc")
    open(dst + ".mdl", "wb").write(m.finish())
    for ext in (".vvd", ".dx90.vtx", ".dx80.vtx", ".sw.vtx", ".phy"):
        if os.path.exists(MESH + ext):
            shutil.copyfile(MESH + ext, dst + ext)

    # Per set and per anim group: the activity TF2C asks for -> our built-in activity.
    replace, report = {}, []
    for set_name, stem in sets.items():
        present = set(acts_of(os.path.join(anim_dir, stem + ".mdl"))[1])
        replace[set_name] = {}
        for group in gmv.GROUP_TABLE:
            if gmv.GROUP_TABLE[group] not in gmv.STOCK:
                continue
            mp, dropped, unserved, fuzzy = gmv.relabel_map(set_name, group, present)
            replace[set_name][group] = {tgt: amap[src] for src, tgt in sorted(mp.items(), key=lambda x: x[1])}
        report.append("%-15s %3d acts, SECONDARY keys %d" % (set_name, len(present), len(replace[set_name].get("SECONDARY", {}))))

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    json.dump({"acts": amap, "replace": replace, "unmapped_files": extra}, open(OUT_JSON, "w"), indent=1, sort_keys=True)
    print("group defaults: %s" % ", ".join(os.path.basename(d) for d in defaults))
    print("renamed %d ACT_MERC activities into %d-entry pool; %d anim files; extra: %s" % (len(amap), len(pool), len(files), extra))
    print("\n".join(report))


# The mesh's grenades/pack use the texture slots soldier_red/_blue/_green/_yellow. The 4dm pak
# resolves them to materials/models/player/merc_deathmatch/shades/, where the non-red files are
# "Patch" materials including TF2C's own soldier_red.vmt; those rendered as missing textures on
# TF2C clients for BLU/GRN/YLW. tf2cc's model searches its own folder first, holding standalone
# copies of TF2C's Soldier material per team (TF2C ships every team's base texture), so nothing
# depends on a Patch include and no stock or 4dm path is shadowed.
TEAM_MAT_DIR = "models/tf2cc/merc"
TF2C_SOLDIER_VMT = "materials/models/player/soldier/soldier_red.vmt"
TEAM_TEXTURES = {"red": "models/player/soldier/red/soldier_red",
                 "blue": "models/player/soldier/blue/soldier_blue",
                 "green": "models/player/soldier/green/soldier_green",
                 "yellow": "models/player/soldier/yellow/soldier_yellow"}
TF2C_ASSETS_VPK = r"<STEAMCMD>/tf2classified-3/tf2classified/vpks/tf2c_assets_dir.vpk"


def prepend_cdtexture(m, path):
    """Search `path` (relative to materials/) before the model's own $cdmaterials."""
    n, idx = struct.unpack_from("<ii", m.b, 212)
    old = [struct.unpack_from("<i", m.b, idx + k * 4)[0] for k in range(n)]
    while len(m.b) % 4:
        m.b += b"\x00"
    table = len(m.b)
    m.b += b"\x00" * (4 * (n + 1))
    offs = [m.add_string(path)] + old
    for k, o in enumerate(offs):
        struct.pack_into("<i", m.b, table + k * 4, o)
    struct.pack_into("<ii", m.b, 212, n + 1, table)


def write_team_materials():
    import fix_vm_sounds as fvs  # noqa: E402  (vpk reader)
    base = fvs.vpk("cat", TF2C_ASSETS_VPK, TF2C_SOLDIER_VMT).decode("latin-1")
    if '"$basetexture"' not in base:
        raise SystemExit("unexpected TF2C soldier material")
    out = os.path.join(STAGE, "materials", TEAM_MAT_DIR)
    os.makedirs(out, exist_ok=True)
    for team, tex in TEAM_TEXTURES.items():
        body = re.sub(r'"\$basetexture"\s+"[^"]*"', lambda _m: '"$basetexture" "%s"' % tex, base, count=1)
        hdr = "// tf2cc: TF2C Soldier material for the Merc mesh's %s grenades (tools/tf2c/gen_merc_acts.py)\n" % team
        with open(os.path.join(out, "soldier_%s.vmt" % team), "w", encoding="latin-1", newline="\n") as f:
            f.write(hdr + body.replace("\r\n", "\n"))


ROW = re.compile(r"\{\s*(ACT_\w+)\s*,\s*(ACT_\w+)\s*,")


def parse_tables(path):
    t = open(path, encoding="latin-1").read()
    out = {}
    for mm in re.finditer(r"acttable_t CTFWeaponBase::s_acttable(\w+)\[\]\s*=\s*\{(.*?)\n\};", t, re.S):
        out[mm.group(1)] = ROW.findall(mm.group(2))
    return out


if __name__ == "__main__":
    main()
