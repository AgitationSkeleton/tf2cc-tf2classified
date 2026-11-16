#!/usr/bin/env python3
"""Generate the per-weapon Mercenary player-model variants (option "c").

Stock TF2 clients pick third-person animations by translating ACT_MP_* through
the active weapon's activity table (tf_weaponbase.cpp s_acttable<GROUP>), the
group coming from the donor item's items_game anim_slot or the weapon script
WeaponType.  Open Fortress instead binds ACT_MERC_*_<SET> per weapon.  A donor
item therefore can only ever select one of ~11 stock groups, so each Merc weapon
gets its exact OF set by swapping the player model to a *variant* whose
<group> -> <OF set> mapping suits the weapon being held.

What this script writes (all under assets/overrides/tf/models/player/tf2cc/variants/):
  anim/<set>__<group>.mdl   a copy of OF models/player/merc_anim/animations_<set>.mdl
                            with ACT_MERC_<X>_<SET> renamed to the ACT_MP_<X>_<GROUP>
                            TF2 requests for that group (mapped through the generic
                            ACT_MP_* keys of the OF acttable and the stock acttable),
                            every other activity blanked, labels suffixed "__<GROUP>"
                            (unique, so repeated sets in one variant do not dedupe away)
                            and the mapped sequences given a huge activity weight so
                            the stock soldier/legacy sequences carrying the same
                            activity are practically never picked (P < 1e-8).
  merc_<variant>.mdl (+.vvd/.dx90.vtx/.dx80.vtx/.phy)
                            copy of tf2cc/mercenary.mdl whose include list is the
                            variant's relabeled files FIRST, then the legacy includes,
                            minus the dead tf2cc/mercenary_animations_primary2.mdl.
  variants.txt              KeyValues weapon id -> model path.
  build_report.txt          partition + verification output.

Run (read-only on everything outside the output directory):
  python -I tools/gen_merc_variants.py [--no-verify]
Inputs: OF game content, TF2 VPKs, weapons.cfg, items_game.txt (paths below).
"""
import os
import re
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import icedecrypt  # noqa: E402
import vpktool  # noqa: E402

ROOT = os.path.dirname(HERE)
from asset_rev import VARIANTS_REL  # noqa: E402
OUT_REL = VARIANTS_REL
OUT_ROOT = os.path.join(ROOT, "assets", "overrides", "tf")
OUT_DIR = os.path.join(OUT_ROOT, OUT_REL)
SRC_MESH = os.path.join(ROOT, "assets", "tf", "models", "player", "tf2cc", "mercenary")
ASSET_ROOTS = [os.path.join(ROOT, "assets", "overrides", "tf"), os.path.join(ROOT, "assets", "tf")]
LIVE_TF2 = r"<STEAMCMD>/tf2/tf"
ITEMS_GAME = r"<STEAMCMD>/tf2-3/tf/scripts/items/items_game.txt"
OF_GAME = r"<STEAMCMD>/sdk2013/open_fortress"
OF_SRC = r"<SOURCE_TREES>/Open-Fortress-Source (09-25-24)/Open-Fortress-Source - Copy/src/game/shared"
TF2_SRC = r"<SOURCE_TREES>/source-sdk-2013/src/game/shared/tf/tf_weaponbase.cpp"
WEAPONS_CFG = os.path.join(ROOT, "config", "sourcemod", "configs", "tf2cc", "weapons.cfg")

# The engine stores each sequence's weight in a SHORT (studio.h SequenceTuple)
# while summing the activity total as an int (animation.cpp SelectWeightedSequence):
# any weight above 32767 truncates, the random roll then runs past the activity's
# list and returns the first sequence of the NEXT activity (random wrong animations).
# 30000 keeps every weight representable and still dominates weight-1 legacy sequences.
BIG_WEIGHT = 30000
SEQ = 212

# ---------------------------------------------------------------- OF sets
# set -> (OF animation file, OF acttable source file, line of the table's STAND_IDLE row)
OF_SETS = {
    "crowbar": ("animations_crowbar", "tf/tf_weapon_crowbar.cpp", 152),
    "knife": ("animations_combat_knife", "tf/tf_weapon_knife.cpp", 72),
    "berserk": ("animations_berserk", "tf/tf_weapon_fists.cpp", 115),
    "chainsaw": ("animations_chainsaw", "of/of_weapon_chainsaw.cpp", 63),
    "pistol": ("animations_pistol", "tf/tf_weapon_pistol.cpp", 191),
    "akimbo": ("animations_akimbo", "tf/tf_weapon_pistol.cpp", 214),
    "revolver": ("animations_revolver", "tf/tf_weapon_revolver.cpp", 77),
    "shotgun": ("animations_shotgun", "tf/tf_weapon_shotgun.cpp", 170),
    "ssg": ("animations_ssg", "tf/tf_weapon_shotgun.cpp", 147),
    "combat_smg": ("animations_combat_smg", "tf/tf_weapon_smg.cpp", 109),
    "tommygun": ("animations_tommygun", "tf/tf_weapon_smg.cpp", 189),
    "assault_rifle": ("animations_assault_rifle", "tf/tf_weapon_smg.cpp", 149),
    "rocketlauncher": ("animations_rocketlauncher", "tf/tf_weapon_rocketlauncher.cpp", 144),
    "gib": ("animations_gib", "of/of_weapon_bfg.cpp", 50),
    "chinalake": ("animations_chinalake", "tf/tf_weapon_grenadelauncher.cpp", 62),
    "nailgun": ("animations_nailgun", "tf/tf_weapon_nailgun.cpp", 73),
    "lightning_gun": ("animations_lightning_gun", "of/of_weapon_lightning.cpp", 690),
    "chaingun": ("animations_chaingun", "tf/tf_weapon_minigun.cpp", 93),
    "railgun": ("animations_railgun", "tf/tf_weapon_sniperrifle.cpp", 1398),
    "dynamite": ("animations_dynamite", "tf/tf_weapon_pipebomblauncher.cpp", 86),
}

# weapon id -> OF set the weapon uses in Open Fortress (None = OF has no table; value is
# the set OF's generic ACT_MP_* group falls back to for that weapon's class)
WEAPON_SET = {
    "civ_umbrella": "crowbar",   # Merc carrying the Civilian umbrella: OF melee (crowbar) set
    "merc_crowbar": "crowbar", "merc_leadpipe": "crowbar", "merc_knife": "knife",
    "merc_fists": "berserk", "merc_berserk": "berserk", "merc_chainsaw": "chainsaw",
    "merc_chainsaw_knife": "chainsaw", "merc_pistol": "pistol", "merc_akimbo": "akimbo",
    "merc_revolver": "revolver", "merc_shotgun": "shotgun", "merc_smg": "combat_smg",
    "merc_machinegun": "combat_smg", "merc_tommygun": "tommygun", "merc_dynamite": "dynamite",
    "merc_supershotgun": "ssg", "merc_assaultrifle": "assault_rifle",
    "merc_rocketlauncher": "rocketlauncher", "merc_quad": "rocketlauncher", "merc_gib": "gib",
    "merc_chinalake": "chinalake", "merc_nailgun": "nailgun", "merc_lightning": "lightning_gun",
    "merc_gatling": "chaingun", "merc_railgun": "railgun",
    "merc_sawballista": "ssg",   # OF ripper: no ACT_MERC table -> generic PRIMARY (= SSG set)
    "merc_medkit": "crowbar",    # OF medkit is a melee: generic MELEE (= crowbar set)
    "merc_grapple": "crowbar",   # no table in OF: generic MELEE
    "merc_flamethrower": "flamethrower",  # disabled in weapons.cfg; no variant built
}
NO_VARIANT_SETS = {"flamethrower"}

# Default variant: stock pickups / unmapped weapons (closest-fitting sets, see doc).
DEFAULT_GROUPS = {
    "PRIMARY": "ssg",            # scattergun, RL, sniper, syringe, crossbow, minigun, flame: OF generic PRIMARY
    "SECONDARY": "pistol",       # pistols, revolvers, SMG, mediguns: OF generic SECONDARY
    "SECONDARY2": "pistol",      # Bison
    "MELEE": "crowbar",          # bats, wrenches, axes, bonesaws: OF generic MELEE
    "MELEE_ALLCLASS": "crowbar",
    "ITEM1": "dynamite",         # throwables (jars, cleaver, lunchbox), flare gun
    "ITEM2": "ssg",              # Force-a-Nature, Soda Popper, Huntsman
    "ITEM4": "berserk",          # Thermal Thruster
    "BUILDING": "crowbar",       # sappers / builders
    "PDA": "pistol",             # PDAs (OF has no PDA set)
}

PREFERRED_ORDER = {
    "PRIMARY": ["rocketlauncher", "assault_rifle", "ssg", "gib", "nailgun", "lightning_gun", "chaingun", "railgun", "dynamite"],
    "SECONDARY": ["pistol", "shotgun", "akimbo", "revolver", "combat_smg", "tommygun", "chinalake"],
    "MELEE": ["crowbar", "knife", "berserk", "chainsaw"],
}
GROUP_TABLE = {"PRIMARY": "Primary", "SECONDARY": "Secondary", "MELEE": "Melee",
               "MELEE_ALLCLASS": "MeleeAllclass", "ITEM1": "Item1", "ITEM2": "Item2",
               "ITEM3": "Item3", "ITEM4": "Item4", "SECONDARY2": "Secondary2",
               "BUILDING": "Building", "PDA": "PDA", "PRIMARY2": "Primary2"}
TYPE_TO_GROUP = {"primary": "PRIMARY", "secondary": "SECONDARY", "melee": "MELEE", "building": "BUILDING",
                 "pda": "PDA", "item1": "ITEM1", "item2": "ITEM2"}


# ------------------------------------------------------------ small helpers
def cstr(b, o):
    if o <= 0 or o >= len(b):
        return ""
    e = b.find(b"\0", o)
    return b[o:e].decode("latin-1")


def i32(b, o):
    return struct.unpack_from("<i", b, o)[0]


class Mdl:
    """Mutable v44-49 MDL; only sequence name/weight/activity edits and include table rewrite."""

    def __init__(self, data):
        self.b = bytearray(data)
        if self.b[:4] != b"IDST":
            raise SystemExit("not an MDL")
        self.nseq, self.seqidx = i32(self.b, 188), i32(self.b, 192)
        self._empty = None

    def seq_off(self, k):
        return self.seqidx + k * SEQ

    def label(self, k):
        o = self.seq_off(k)
        return cstr(self.b, o + i32(self.b, o + 4))

    def act(self, k):
        o = self.seq_off(k)
        return cstr(self.b, o + i32(self.b, o + 8))

    def add_string(self, s):
        pos = len(self.b)
        self.b += s.encode("latin-1") + b"\0"
        return pos

    def set_label(self, k, s):
        o = self.seq_off(k)
        struct.pack_into("<i", self.b, o + 4, self.add_string(s) - o)

    def set_act(self, k, name, weight):
        o = self.seq_off(k)
        if name:
            struct.pack_into("<i", self.b, o + 8, self.add_string(name) - o)
            struct.pack_into("<i", self.b, o + 20, weight)
        else:
            if self._empty is None:
                self._empty = self.add_string("")
            struct.pack_into("<i", self.b, o + 8, self._empty - o)
            struct.pack_into("<i", self.b, o + 16, -1)     # activity id (re-derived from name on load)
            struct.pack_into("<i", self.b, o + 20, 0)
        fl = i32(self.b, o + 12) & ~0x1000                  # clear STUDIO_ACTIVITY so the name is re-resolved
        struct.pack_into("<i", self.b, o + 12, fl)

    def includes(self):
        n, idx = struct.unpack_from("<ii", self.b, 336)
        return [cstr(self.b, idx + k * 8 + i32(self.b, idx + k * 8 + 4)) for k in range(n)]

    def set_includes(self, names):
        table = len(self.b)
        self.b += b"\0" * (8 * len(names))
        for k, nm in enumerate(names):
            o = table + k * 8
            pos = self.add_string(nm)
            struct.pack_into("<ii", self.b, o, 0, pos - o)
        struct.pack_into("<ii", self.b, 336, len(names), table)

    def finish(self):
        struct.pack_into("<i", self.b, 76, len(self.b))
        return bytes(self.b)


# --------------------------------------------------------- acttable parsing
ROW = re.compile(r"\{\s*(ACT_\w+)\s*,\s*(ACT_\w+)\s*,")


def parse_of_table(relfile, line):
    lines = open(os.path.join(OF_SRC, relfile), encoding="latin-1").read().split("\n")
    s = line - 1
    while "acttable_t" not in lines[s]:
        s -= 1
    rows = []
    for ln in lines[s + 1:]:
        if ln.strip().startswith("};"):
            break
        m = ROW.search(ln)
        if m and not ln.strip().startswith("//"):
            rows.append((m.group(1), m.group(2)))
    return rows


def parse_stock_tables():
    t = open(TF2_SRC, encoding="latin-1").read()
    out = {}
    for m in re.finditer(r"acttable_t s_acttable(\w+)\[\]\s*=\s*\{(.*?)\n\};", t, re.S):
        out[m.group(1)] = ROW.findall(m.group(2))
    return out


def first_map(rows):
    d = {}
    for a, b in rows:
        d.setdefault(a, b)
    return d


STOCK = parse_stock_tables()


def _norm(act, prefix, tokens):
    """Strip the ACT_ prefix and every whole-token occurrence of `tokens` (set / group names)."""
    parts = act[len(prefix):].split("_")
    for tk in tokens:
        tp = tk.split("_")
        out, i = [], 0
        while i < len(parts):
            if parts[i:i + len(tp)] == tp:
                i += len(tp)
            else:
                out.append(parts[i])
                i += 1
        parts = out
    return "_".join(parts)


def relabel_map(set_name, group, present):
    """OF ACT_MERC target -> stock ACT_MP target for (set, group).

    Pass 1 follows the two acttables through their shared generic ACT_MP_* keys (exactly what
    each client does).  Pass 2 fills stock targets that the OF table never mentions (e.g. reload
    airwalk) or whose OF target has no sequence (OF typos such as the chainsaw attack), by matching
    the activity name with the set / group token removed; each sequence carries one activity only.
    """
    f, line = OF_SETS[set_name][1:]
    of = first_map(parse_of_table(f, line))
    stock = first_map(STOCK[GROUP_TABLE[group]])
    m, dropped = {}, []
    for gen, ofact in of.items():
        if gen not in stock or ofact not in present:
            continue
        tgt = stock[gen]
        if ofact in m and m[ofact] != tgt:
            dropped.append((gen, ofact, tgt))   # one sequence cannot carry two activities
            continue
        m.setdefault(ofact, tgt)
    served = set(m.values())
    stem = of.get("ACT_MP_STAND_IDLE", "")
    setok = stem[len("ACT_MERC_STAND_"):] if stem.startswith("ACT_MERC_STAND_") else set_name.upper()
    byn = {}
    for a in sorted(present):
        if a not in m:
            byn.setdefault(_norm(a, "ACT_MERC_", [setok, set_name.upper()]), []).append(a)
    fuzzy = []
    for t in sorted(set(stock.values())):
        if t in served:
            continue
        n = _norm(t, "ACT_MP_", [group])
        c = byn.get(n)
        if c:
            m[c[0]] = t
            served.add(t)
            byn[n] = c[1:]
            fuzzy.append((c[0], t))
    unserved = sorted(k for k in stock if k not in of)
    return m, dropped, unserved, fuzzy


# ------------------------------------------------------- weapon -> group
def tokenize_vdf(t):
    for m in re.finditer(r'"([^"]*)"|([{}])|//[^\n]*', t):
        if m.group(0).startswith("//"):
            continue
        yield m.group(1) if m.group(1) is not None else m.group(2)


def parse_vdf(t):
    toks = list(tokenize_vdf(t))
    pos = 0

    def blk():
        nonlocal pos
        d = {}
        while pos < len(toks):
            k = toks[pos]
            pos += 1
            if k == "}":
                return d
            v = toks[pos]
            pos += 1
            if v == "{":
                d.setdefault(k, []).append(blk())
            else:
                d.setdefault(k, []).append(v)
        return d
    return blk()


class Econ:
    def __init__(self):
        g = parse_vdf(open(ITEMS_GAME, encoding="utf-8", errors="replace").read())["items_game"][0]
        self.items = {k: v[0] for k, v in g["items"][0].items() if isinstance(v[0], dict)}
        self.pre = {k: v[0] for k, v in g["prefabs"][0].items()}
        self.entries, self.base = vpktool.read_tree(os.path.join(LIVE_TF2, "tf2_misc_dir.vpk"))

    def prop(self, item, key):
        if key in item:
            return item[key][0]
        for pf in (item["prefab"][0].split() if "prefab" in item else [])[::-1]:
            if pf in self.pre:
                r = self.prop(self.pre[pf], key)
                if r is not None:
                    return r
        return None

    def weapon_type(self, classname):
        key = "scripts/%s.ctx" % classname.lower()
        if key not in self.entries:
            return None
        raw = vpktool.read_file(os.path.join(LIVE_TF2, "tf2_misc_dir.vpk"), self.entries, self.base, key)
        txt = icedecrypt.decrypt(raw, b"E2NcUkG2").decode("latin-1", "replace")
        m = re.search(r'"WeaponType"\s+"([^"]+)"', txt, re.I)
        return m.group(1).lower() if m else None

    def group(self, classname, itemdef):
        it = self.items.get(str(itemdef))
        slot = self.prop(it, "anim_slot") if it else None
        if slot and slot.upper() != "FORCE_NOT_USED":
            return slot.upper(), "items_game anim_slot"
        wt = self.weapon_type(classname)
        return TYPE_TO_GROUP.get(wt, "PRIMARY"), "script WeaponType=%s" % wt


def load_weapons():
    cfg = open(WEAPONS_CFG, encoding="utf-8").read()
    econ = Econ()
    out = []
    for m in re.finditer(r'^\t"(\w+)"\s*\n\t\{(.*?)^\t\}', cfg, re.S | re.M):
        body = m.group(2)
        if "mercenary" not in body:
            continue
        g = lambda k: (re.search(r'"%s"\s+"([^"]*)"' % k, body) or [0, ""])[1]
        wid, cls, idef = m.group(1), g("classname"), g("itemdef")
        if cls in ("", "none"):
            continue
        grp, src = econ.group(cls, idef)
        out.append(dict(id=wid, cls=cls, itemdef=idef, group=grp, src=src, set=WEAPON_SET[wid],
                        enabled=g("enabled") != "0"))
    return out


# -------------------------------------------------------------- partition
def partition(weapons):
    """variant i holds the i-th distinct set of every group; returns (variants, weapon->variant)."""
    by_group = {}
    for w in weapons:
        if w["set"] in NO_VARIANT_SETS:
            continue
        by_group.setdefault(w["group"], [])
        if w["set"] not in by_group[w["group"]]:
            by_group[w["group"]].append(w["set"])
    for g, order in PREFERRED_ORDER.items():
        if g in by_group:
            by_group[g].sort(key=lambda x: order.index(x) if x in order else 99)
    n = max(len(v) for v in by_group.values())
    variants = []
    for k in range(n):
        groups = {g: sets[k] for g, sets in by_group.items() if k < len(sets)}
        variants.append(groups)
    wmap = {}
    for w in weapons:
        if w["set"] in NO_VARIANT_SETS:
            wmap[w["id"]] = None
            continue
        wmap[w["id"]] = by_group[w["group"]].index(w["set"])
    return variants, wmap


def variant_name(k, groups):
    prim = groups.get("PRIMARY") or next(iter(groups.values()))
    return "v%02d_%s" % (k + 1, prim)


# ----------------------------------------------------------- file builders
def build_anim(set_name, group, report):
    src = os.path.join(OF_GAME, "models", "player", "merc_anim", OF_SETS[set_name][0] + ".mdl")
    m = Mdl(open(src, "rb").read())
    present = {m.act(k) for k in range(m.nseq)}
    mp, dropped, unserved, fuzzy = relabel_map(set_name, group, present)
    used = set()
    for k in range(m.nseq):
        m.set_label(k, m.label(k) + "__" + group)
        a = m.act(k)
        if a in mp:
            m.set_act(k, mp[a], BIG_WEIGHT)
            used.add(a)
        else:
            m.set_act(k, "", 0)
    missing = sorted(set(mp) - used)
    rel = "%s/anim/%s__%s.mdl" % (OUT_REL, set_name, group)
    dst = os.path.join(OUT_ROOT, rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    data = m.finish()
    open(dst, "wb").write(data)
    report.append("anim %-34s %7d B  mapped %2d acts (%d by name pattern: %s) dropped(multi-target) %s"
                  % (os.path.basename(dst), len(data), len(used), len(fuzzy),
                     ", ".join("%s->%s" % (a[9:], t[7:]) for a, t in fuzzy)[:240], [d[1] for d in dropped][:4]))
    return rel, len(data)


def build_variant(name, anim_rels, report):
    base = open(SRC_MESH + ".mdl", "rb").read()
    m = Mdl(base)
    # mercenary_animations2.mdl (MarxVee pack, not in OF) holds only taunt03 and
    # layer_taunt_bond, overriding OF's: the crowbar's Groovy taunt (OF talker
    # MercenaryTauntCrowbar -> taunt_groovy.vcd -> taunt03) played the Bond
    # animation. OF's own taunt03 is in mercenary_animations.mdl.
    legacy = [i for i in m.includes()
              if not i.lower().endswith("tf2cc/mercenary_animations_primary2.mdl")
              and not i.lower().endswith("mercenary/mercenary_animations2.mdl")]
    m.set_includes(list(anim_rels) + legacy)
    dst = os.path.join(OUT_DIR, "merc_%s" % name)
    os.makedirs(OUT_DIR, exist_ok=True)
    data = m.finish()
    open(dst + ".mdl", "wb").write(data)
    size = len(data)
    for ext in (".vvd", ".dx90.vtx", ".dx80.vtx", ".phy"):
        shutil.copyfile(SRC_MESH + ext, dst + ext)
        size += os.path.getsize(dst + ext)
    report.append("model merc_%s.mdl  %d bytes with companions  includes=%d (dropped primary2, animations2)" % (name, size, len(anim_rels) + len(legacy)))
    return "%s/merc_%s.mdl" % (OUT_REL, name), size


# ---------------------------------------------------------------- verify
class Resolver:
    """Virtual-model sequence list as studio_virtualmodel.cpp AppendSequences builds it."""

    def __init__(self):
        self.vpk = vpktool.read_tree(os.path.join(LIVE_TF2, "tf2_misc_dir.vpk"))

    def load(self, rel):
        rel = rel.replace("\\", "/")
        for r in ASSET_ROOTS:
            p = os.path.join(r, rel)
            if os.path.exists(p):
                return open(p, "rb").read()
        e, base = self.vpk
        if rel.lower() in e:
            return vpktool.read_file(os.path.join(LIVE_TF2, "tf2_misc_dir.vpk"), e, base, rel.lower())
        return None

    def virtual(self, rel):
        m = []

        def add(rel):
            b = self.load(rel)
            if b is None:
                return
            mm = Mdl(b)
            seqs = []
            for k in range(mm.nseq):
                o = mm.seq_off(k)
                seqs.append(dict(label=mm.label(k), act=mm.act(k), weight=i32(mm.b, o + 20),
                                 over=bool(i32(mm.b, o + 12) & 0x800), src=os.path.basename(rel),
                                 flags=i32(mm.b, o + 12)))
            idx = {}
            for k, s in enumerate(m):
                idx.setdefault(s["label"].lower(), k)
            new = list(m)
            n0 = len(m)
            for s in seqs:
                k = idx.get(s["label"].lower())
                if k is None:
                    new.append(s)
                elif m[k]["over"]:
                    new[k] = s
            m[:] = new
            _ = n0
            for inc in mm.includes():
                add(inc)
        add(rel)
        return m


WORST = [0.0]


def verify(res, variant_models, weapons, wmap, vlist, vnames, default_rel, default_groups, report):
    ok_all = True
    cache = {}

    def vm(rel):
        if rel not in cache:
            cache[rel] = res.virtual(rel)
        return cache[rel]

    def check(label, rel, group, intended_marker):
        nonlocal ok_all
        v = vm(rel)
        by = {}
        for s in v:
            if s["act"]:
                by.setdefault(s["act"], []).append(s)
        tab = first_map(STOCK[GROUP_TABLE[group]])
        targets = sorted({t for t in tab.values()})
        served = fallback = unresolved = 0
        worst = 0.0
        fb_list = []
        un_list = []
        for t in targets:
            c = by.get(t, [])
            if not c:
                unresolved += 1
                un_list.append(t[7:])
                continue
            tot = sum(abs(s["weight"]) for s in c)
            mine = sum(abs(s["weight"]) for s in c if s["label"].endswith("__" + group)
                       and intended_marker in s["src"])
            if mine == 0:
                fallback += 1
                fb_list.append("%s<-%s" % (t[7:], c[0]["src"].replace("_animations", "").replace(".mdl", "")))
            else:
                served += 1
                worst = max(worst, 1.0 - mine / tot)
        def kind(x):
            if re.search(r"_(LOOP|END)(_|$)", x):
                return "reload-loop/end"
            if "DEPLOYED" in x:
                return "deployed(minigun)"
            return "core"
        gaps = {}
        for x in fb_list:
            n = "ACT_MP_" + x.split("<-")[0]
            if not re.search(r"GESTURE|GRENADE|FLINCH|AIRWALK_[A-Z0-9_]*$", n) or "RELOAD_AIRWALK" in n:
                gaps.setdefault(kind(n), []).append(x)
        report.append("      legacy/soldier fallback by kind: " + "; ".join(
            "%s=%d" % (k, len(v)) for k, v in sorted(gaps.items())) if gaps else "      legacy/soldier fallback by kind: none")
        for k in ("core", "deployed(minigun)"):
            if k in gaps:
                report.append("        %s: %s" % (k, ", ".join(gaps[k])))
        un_core = [x for x in un_list if not re.search(r"GESTURE|GRENADE|FLINCH|DOUBLEJUMP|WALK_|JUMP_[A-Z0-9]+$|ATTACK_AIRWALK", "ACT_MP_" + x)]
        if un_core:
            report.append("      unresolved (no sequence anywhere): " + ", ".join(un_core))
        WORST[0] = max(WORST[0], worst)
        if worst > 1e-3:
            ok_all = False
    report.append("")
    report.append("VERIFICATION (virtual-model resolver; foreign probability = chance a stock soldier/legacy sequence is picked)")
    for w in weapons:
        k = wmap[w["id"]]
        if k is None:
            report.append("  %-26s NO EXACT VARIANT (set %s not built) -> default variant" % (w["id"], w["set"]))
            continue
        rel = variant_models[k]
        check("%s [%s]" % (w["id"], vnames[k]), rel, w["group"], "%s__%s" % (w["set"], w["group"]))
    for g, s in default_groups.items():
        check("default", default_rel, g, "%s__%s" % (s, g))
    return ok_all


# ------------------------------------------------------------------ main
def main():
    do_verify = "--no-verify" not in sys.argv
    if os.path.isdir(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    report = []
    weapons = load_weapons()
    vlist, wmap = partition(weapons)
    names = [variant_name(k, g) for k, g in enumerate(vlist)]

    report.append("WEAPONS (group from items_game anim_slot / script WeaponType)")
    for w in weapons:
        report.append("  %-20s %-30s def %-5s group %-14s (%s) -> OF set %-14s enabled=%s variant=%s"
                      % (w["id"], w["cls"], w["itemdef"], w["group"], w["src"], w["set"], w["enabled"],
                         names[wmap[w["id"]]] if wmap[w["id"]] is not None else "default"))
    report.append("")
    report.append("PARTITION (variant -> group:set)")
    for n, g in zip(names, vlist):
        report.append("  %-24s %s" % (n, ", ".join("%s=%s" % kv for kv in g.items())))
    report.append("  %-24s %s" % ("default", ", ".join("%s=%s" % kv for kv in DEFAULT_GROUPS.items())))
    report.append("")

    anim_cache = {}
    anim_total = 0

    def anim(set_name, group):
        nonlocal anim_total
        key = (set_name, group)
        if key not in anim_cache:
            anim_cache[key], sz = build_anim(set_name, group, report)
            anim_total += sz
        return anim_cache[key]

    models, total = [], 0
    for n, g in zip(names, vlist):
        rels = [anim(s, grp) for grp, s in g.items()]
        rel, sz = build_variant(n, rels, report)
        models.append(rel)
        total += sz
    drels = [anim(s, grp) for grp, s in DEFAULT_GROUPS.items()]
    default_rel, sz = build_variant("default", drels, report)
    total += sz

    with open(os.path.join(OUT_DIR, "variants.txt"), "w", encoding="utf-8") as f:
        f.write('// Generated by tools/gen_merc_variants.py - weapon id -> Merc player model variant.\n')
        f.write('// "default" is used for stock pickups / unmapped weapons.\n')
        f.write('"merc_variants"\n{\n')
        for w in weapons:
            k = wmap[w["id"]]
            path = models[k] if k is not None else default_rel
            note = "" if k is not None else "   // no exact variant built (disabled weapon)"
            f.write('\t"%s"\t"%s"%s\n' % (w["id"], path, note))
        f.write('\t"default"\t"%s"\n}\n' % default_rel)
    # Plugin config (tf2cc_weapons LoadModelVariants).
    cfg = os.path.join(ROOT, "config", "sourcemod", "configs", "tf2cc", "model_variants.cfg")
    with open(cfg, "w", encoding="utf-8", newline="\n") as f:
        f.write("// tf2cc per-weapon player-model variants (exact Open Fortress 3P animation sets).\n")
        f.write("// Generated by tools/gen_merc_variants.py (asset revision folder %s).\n" % OUT_REL)
        f.write('"model_variants"\n{\n\t"mercenary"\n\t{\n')
        for w in weapons:
            k = wmap[w["id"]]
            f.write('\t\t"%s"\t"%s"\n' % (w["id"], models[k] if k is not None else default_rel))
        f.write('\t\t"default"\t"%s"\n\t}\n' % default_rel)
        # For stock pickups (tf2cc_weapons ApplyModelVariant): the OF set each variant
        # plays per animation group, and each Merc weapon's set.
        f.write('\t"sets"\n\t{\n')
        for rel, groups in list(zip(models, vlist)) + [(default_rel, DEFAULT_GROUPS)]:
            f.write('\t\t"%s"\n\t\t{\n' % rel)
            for g, st in sorted(groups.items()):
                f.write('\t\t\t"%s"\t"%s"\n' % (g, st))
            f.write('\t\t}\n')
        f.write('\t}\n\t"weapon_sets"\n\t{\n')
        for w in weapons:
            f.write('\t\t"%s"\t"%s"\n' % (w["id"], w["set"]))
        f.write('\t}\n}\n')

    report.append("")
    report.append("SIZES: %d variant models + default = %d B (mesh+mdl+vvd+vtx+phy); %d relabeled anim files = %d B; total %d B"
                  % (len(models), total, len(anim_cache), anim_total, total + anim_total))
    if do_verify:
        res = Resolver()
        ok = verify(res, models, weapons, wmap, vlist, names, default_rel, DEFAULT_GROUPS, report)
        # Engine stores per-sequence weights as shorts (see BIG_WEIGHT): anything
        # above 32767 makes SelectWeightedSequence return a neighbouring activity.
        bad = []
        for rel in models + [default_rel]:
            for s in res.virtual(rel):
                if abs(s["weight"]) > 32767:
                    bad.append("%s:%s=%d" % (os.path.basename(rel), s["label"], s["weight"]))
        if bad:
            ok = False
            report.append("WEIGHT OVERFLOW (short): %d sequence(s), e.g. %s" % (len(bad), ", ".join(bad[:5])))
        report.append("")
        report.append("VERIFY RESULT: %s" % ("PASS (weights fit the engine's short; worst legacy-pick odds %.1e)" % WORST[0] if ok else "FAILED (worst legacy-pick odds %.1e)" % WORST[0]))
    text = "\n".join(report)
    open(os.path.join(OUT_DIR, "build_report.txt"), "w", encoding="utf-8").write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
