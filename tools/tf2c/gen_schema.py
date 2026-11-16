#!/usr/bin/env python3
"""Generate the TF2 Classified Mercenary weapon schema and stage its assets.

Each Mercenary weapon becomes a real schema item (custom_items_game.txt). It is
built from the Open Fortress definition of that weapon
(open_fortress/scripts/items/items_game.txt "Weapons"):

* base class: the closest TF2 Classified weapon class (ROSTER below), slotted
  with the schema "bucket" key (CTFWeaponBase::GetSlot honours it);
* stats: OF WeaponData compared with the TF2C base weapon script, written as
  attributes (damage, pellets, fire delay, clip, reload, spread, max ammo);
* models: the OF viewmodel (attach_to_hands 2, L4D style: TF2C plays its own
  ACT_VM_* activities and takes the arms from custom_hand_viewmodel, which the
  plugin sets to the TF2C Merc arms) and world model;
* sounds: OF SoundData scripts copied whole (channel, level, pitch, every rndwave)
  into scripts/items/custom_level_sounds.txt as "tf2cc.<OF name>" entries, waves
  staged under sound/tf2cc/of/; the items' sound_* keys name those entries. Build
  5205 loads that file on server and client at every level init (both binaries
  carry the path). Raw .wav values never played: CBaseCombatWeapon::WeaponSound
  returns when GetParametersForSound fails, which it does for anything that is
  not a sound script;
* third-person animations: animation_replacement from tf2c/merc_acts.json
  (gen_merc_acts.py), selecting the weapon's OF animation set on the single
  tf2cc Merc model.

Merc items have no used_by_classes at all: build 5205 lists every item a class
may use (used_by_classes) in the loadout/armory, even "hidden" ones, so listing
Soldier showed them to every Soldier (playtest 2026-11-15). Without it they are in
no class's loadout and no bot's random loadout; VScript GenerateAndWearItem still
gives them (verified on the test copy). "hidden" and the bots_cant_use tag stay as
extra guards.

Assets are copied from the OF install into tf2c/staging/tf2classified under
tf2cc-owned paths (models/tf2cc/of/..., sound/tf2cc/of/...). Materials keep
their paths; any path that TF2 Classified already ships is reported and not
staged, so a FastDL download can never change a stock TF2C file.

  python -I tools/tf2c/gen_schema.py [--af <april fools custom_items_game.txt>]

Writes:
  tf2c/staging/tf2classified/scripts/items/custom_items_game.txt  (merged when --af)
  tf2c/schema_report.txt
"""
import argparse
import json
import os
import re
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import kv  # noqa: E402
import fix_vm_sounds as fvs  # noqa: E402
import mdlinfo  # noqa: E402

OFG = r"<STEAMCMD>/sdk2013/open_fortress"
RESEARCH = os.path.join(ROOT, "work", "tf2c_research")
BASE_SCHEMA = os.path.join(RESEARCH, "base", "scripts", "items", "items_game.txt")
BASE_SCRIPTS = os.path.join(RESEARCH, "base", "scripts")
TF2C_LIST = os.path.join(RESEARCH, "list_tf2c_assets.txt")
ACTS = os.path.join(ROOT, "tf2c", "merc_acts.json")
STAGE = os.path.join(ROOT, "tf2c", "staging", "tf2classified")
REPORT = os.path.join(ROOT, "tf2c", "schema_report.txt")
MODEL_PREFIX = "models/tf2cc/of/"
SOUND_PREFIX = "tf2cc/of/"
FIRST_ID = 30100
WEAPONS_CFG = os.path.join(ROOT, "config", "sourcemod", "configs", "tf2cc", "weapons.cfg")
# Stats not derived from OF for these (OF value is a different mechanic or unit):
# fists: OF's only fists entry is the 999-damage Berserk powerup; tf2cc's Merc fists
# are the stock 65 / 0.8 fists. Nail spread is in degrees in OF, a cone scale in TF2C.
# String attributes per weapon (static_attrs). The dynamite is thrown like a grenade
# (contact/fuse) with OF's bundle as the projectile, closer to OF than a sticky launcher.
# mod burstfire "<shots> <x>" (measured on build 5205 with forced fire): the gap between
# bursts is the weapon's fire delay and shots inside a burst are delay * x apart. OF's
# assault rifle: 3 shots 0.07 s apart, BurstFireDelay 0.30 -> fire delay 0.30, x = 0.07/0.30.
# Native and client-predicted (a plugin writing m_flNextPrimaryAttack makes the viewmodel flicker).
STRING_ATTRS = {"merc_dynamite": {"custom projectile model": MODEL_PREFIX + "weapons/w_models/w_dynamite.mdl"},
                "merc_assaultrifle": {"mod burstfire": "3 0.2333"}}
# Extra numeric attributes (class, value) where OF behaviour has no WeaponData counterpart:
#  railgun: OF has no clip (14 shots, 1.5 s apart); on the revolver base the clip holds them all.
#  lightning: OF has no clip (100 cells, 720 u range, no spread); SMG base, clip 100.
#  gib: OF's GIB ball bursts into 6 bomblets. TF2C's rocket launcher would not fire a MIRV via
#       override_projectile_type on build 5205 (tested 26-34), so the plugin adds the bomblets.
# Clips follow OF: OF weapons without a clip (railgun, lightning, GIB, dynamite: clip_size -1)
# fire from the reserve with no reload ("mod max primary clip override" -1). OF's super
# shotgun (clip 1: fire 0.4 s, then a 1.4 s reload) gets a real clip-1 reload on the Engineer's
# primary shotgun class (script bucket 0, TF_AMMO_PRIMARY, the stock 32x32 crosshair; the
# Soldier shotgun is bucket 1 / secondary ammo, the double shotgun draws 96x32). That class
# reloads singly: ACT_RELOAD_START is absent from the OF viewmodel, so the start waits the
# script's TimeReloadStart (0.33 s); ACT_VM_RELOAD plays OF's db_reload and lasts its sequence
# length (134 frames at 60 fps); CTFWeaponBase::SetReloadTimer scales both by
# mult_reload_time and sets the viewmodel playback rate to match, so the OF reload is seen in
# full within 1.4 s.
EXTRA_ATTRS = {
    "merc_lightning": [("set_weapon_range", 720), ("mult_spread_scale", 0.01)],
    "merc_supershotgun": [("mult_reload_time", 1.4 / (0.33 + 134 / 60.0)), ("mod_max_primary_clip_override", 1)],
    "merc_assaultrifle": [("mult_postfiredelay", 0.30 / 0.1)],
    # GIB: the stock-TF2 tf2cc numbers (config/sourcemod/configs/tf2cc/weapons.cfg merc_gib on
    # the TF2 rocket launcher: damage bonus 1.55, fire rate penalty 1.25, projectile speed 0.5,
    # clip 4 x 0.25 = 1, reserve 8), not OF's. TF2's launcher script reloads one rocket in
    # 0.1 s start + 0.83 s (neither viewmodel has reload activities, so script times apply).
    # TF2C's launcher measured on the test copy (bot holding fire, m_flNextPrimaryAttack): the
    # start phase is 0.5 s x m (script), the rocket phase only 0.34 s x m (not the script's
    # 0.83), 0.84 s x m in all; x1.11 gives TF2's 0.93 s: the same 1.0 s fire + 0.93 s reload
    # cycle (1.93 s) as the stock GIB.
    "merc_gib": [("mult_dmg", 1.55), ("mult_postfiredelay", 1.25), ("mult_projectile_speed", 0.5),
                 ("mult_clipsize", 0.25), ("mult_maxammo_primary", 8 / 20.0),
                 ("mult_reload_time", 1.11)],
    # Combat knife: no random crits, as TF2C's Spy knife (CTFKnife overrides both
    # CalcIsAttackCriticalHelper and ...NoCrits with "backstab only"; server.dll vtable
    # +0xe00/+0xe08). The melee helper multiplies its chance by mult_crit_chance.
    "merc_knife": [("mult_crit_chance", 0)],
    # Chainsaw: as the stock-TF2 tf2cc chainsaw, the base melee only drives the looping swing
    # (0.8 s x 0.75 = the 0.6 s cs_rev_idle loop, no damage); the plugin deals OF's 12 dmg every
    # 0.05 s, the wind-up/wind-down, the sounds and the alt-fire charge. "full charge turn
    # control" 50 is the Tide Turner's (TF2C reads charge_turn_control on server and client).
    "merc_chainsaw": [("mult_dmg", 0), ("mult_postfiredelay", 0.75), ("charge_turn_control", 50)],
}
# Item tracers (TF2C appends _<team>[_crit]; these families exist for all four teams).
TRACERS = {"merc_railgun": "tracer_sniper_rifle_PARENT", "merc_lightning": "bullet_bignasty_tracer01"}
EXTRA_MODELS = []
# Weapons whose OF fire sound is a stream played by the plugin (start/loop/end), not per shot.
SILENT_SHOT = {"merc_lightning"}
# Weapons whose every weapon sound is played by the plugin (looping states, not per swing): all
# sound_* keys are silent, the melee ones included; the OF scripts are still defined.
SILENT_ALL = {"merc_chainsaw"}
# OF scripts the plugin plays besides the weapons' own SoundData (defined as tf2cc.<name>).
EXTRA_SCRIPT_SOUNDS = ["Chainsaw.Charge", "ChargeFilled.Ding"]
# GIB bomblets (plugin): OF's w_bfg_bomblet names its texture "  phy" (a missing texture for
# every team), so the plugin uses OF's MIRV bomblet, given four team skins here.
BOMBLET_SRC = "models/weapons/w_models/w_grenade_bomblet.mdl"
BOMBLET_DST = MODEL_PREFIX + "weapons/w_models/w_grenade_bomblet.mdl"
BOMBLET_MAT_DIR = "models/tf2cc/of/bomblet"
# HUD/armory icons: TF2C draws materials/<image_inventory>_large.vmt (the item panel shows the
# middle of a square texture). OF's bucket sprites are 256x128, so they are padded to 256x256
# under a tf2cc path. OF weapons without a backpack_icon use these sprites:
BUCKET_FALLBACK = {"merc_knife": "bucket_classic_knife", "merc_fists": "bucket_berserk",
                   "merc_smg": "bucket_smgDM", "merc_gib": "bucket_gib"}
BUCKET_DIR = "tf2cc/of/bucket"
# Icons with team variants live apart: the item panel lookup (client.dll 0x3d8730) asks the
# material system for "<image>_large" first, then "<image>_<team>", then "<image>", and takes the
# first material that is not the error material. Round 5 shipped <image>_large.vmt for every
# icon (and only _<team>.vtf textures, no materials), so the team step never ran; clients keep
# that _large.vmt cached, hence a new folder with no _large but <image>_<team>.vmt materials.
TEAM_BUCKET_DIR = "tf2cc/of/bucket_team"
# Sounds the plugin plays (taunts), copied under the tf2cc prefix.
EXTRA_SOUNDS = {"player/taunt_bond_pistol.wav": SOUND_PREFIX + "player/taunt_bond_pistol.wav"}
SKIP_STATS = {"merc_fists": {"*"}, "merc_nailgun": {"Spread"}, "merc_assaultrifle": {"TimeFireDelay"},
              "merc_supershotgun": {"TimeReload", "clip_size"}, "merc_gib": {"*"},
              "merc_chainsaw": {"*"}}

# id, OF weapon key, TF2C item_class, loadout slot, bucket, anim group, OF anim set
ROSTER = [
    ("merc_crowbar", "tf_weapon_crowbar", "tf_weapon_shovel", "melee", 2, "MELEE", "crowbar"),
    ("merc_leadpipe", "tf_weapon_lead_pipe", "tf_weapon_shovel", "melee", 2, "MELEE", "crowbar"),
    ("merc_knife", "tf_weapon_combatknife", "tf_weapon_shovel", "melee", 2, "MELEE", "knife"),
    ("merc_fists", "tf_weapon_berserk", "tf_weapon_fists", "melee", 2, "MELEE", "berserk"),
    ("merc_chainsaw", "tf_weapon_chainsaw", "tf_weapon_shovel", "melee", 2, "MELEE", "chainsaw"),
    ("merc_pistol", "tf_weapon_pistol_mercenary", "tf_weapon_pistol", "secondary", 1, "SECONDARY", "pistol"),
    ("merc_akimbo", "tf_weapon_pistol_akimbo", "tf_weapon_pistol", "secondary", 1, "SECONDARY", "akimbo"),
    ("merc_revolver", "tf_weapon_revolver_mercenary", "tf_weapon_revolver", "secondary", 1, "SECONDARY", "revolver"),
    ("merc_shotgun", "tf_weapon_shotgun", "tf_weapon_shotgun_soldier", "secondary", 1, "SECONDARY", "shotgun"),
    ("merc_smg", "tf_weapon_smg_mercenary", "tf_weapon_smg", "secondary", 1, "SECONDARY", "combat_smg"),
    ("merc_tommygun", "tf_weapon_tommygun", "tf_weapon_smg", "secondary", 1, "SECONDARY", "tommygun"),
    ("merc_dynamite", "tf_weapon_dynamite_bundle", "tf_weapon_grenadelauncher", "secondary", 1, "SECONDARY", "dynamite"),
    ("merc_supershotgun", "tf_weapon_supershotgun", "tf_weapon_shotgun_primary", "primary", 0, "PRIMARY", "ssg"),
    ("merc_assaultrifle", "tf_weapon_assaultrifle", "tf_weapon_smg", "primary", 0, "PRIMARY", "assault_rifle"),
    ("merc_rocketlauncher", "tf_weapon_rocketlauncher_dm", "tf_weapon_rocketlauncher", "primary", 0, "PRIMARY", "rocketlauncher"),
    ("merc_chinalake", "tf_weapon_grenadelauncher_mercenary", "tf_weapon_grenadelauncher", "primary", 0, "PRIMARY", "chinalake"),
    ("merc_nailgun", "tf_weapon_nailgun", "tf2c_weapon_nailgun", "primary", 0, "PRIMARY", "nailgun"),
    ("merc_gatling", "tf_weapon_gatlinggun", "tf_weapon_minigun", "primary", 0, "PRIMARY", "chaingun"),
    ("merc_railgun", "tf_weapon_railgun", "tf_weapon_revolver", "primary", 0, "PRIMARY", "railgun"),
    ("merc_lightning", "tf_weapon_lightning_gun", "tf_weapon_smg", "primary", 0, "PRIMARY", "lightning_gun"),
    ("merc_gib", "tf_weapon_gib", "tf_weapon_rocketlauncher", "primary", 0, "PRIMARY", "gib"),
]

# OF SoundData key -> TF2C weapon sound type (scripts sound_<type>, shareddefs WeaponSound_t)
SOUND_TYPES = {"empty": "empty", "single_shot": "single_shot", "single_shot_npc": "single_shot_npc",
               "double_shot": "double_shot", "double_shot_npc": "double_shot_npc", "burst": "burst",
               "reload": "reload", "reload_npc": "reload_npc", "melee_miss": "melee_miss",
               "melee_hit": "melee_hit", "melee_hit_world": "melee_hit_world", "special1": "special1",
               "special2": "special2", "special3": "special3", "taunt": "taunt", "deploy": "deploy"}

# Stat -> (attribute_class, OF key, base key); value = OF / base when both are positive.
STATS = [
    ("mult_dmg", "Damage"),
    ("mult_bullets_per_shot", "BulletsPerShot"),
    ("mult_postfiredelay", "TimeFireDelay"),
    ("mult_clipsize", "clip_size"),
    ("mult_reload_time", "TimeReload"),
    ("mult_spread_scale", "Spread"),
]


BODY_ID = FIRST_ID - 1
MERC_HEALTH, MERC_SPEED = 150, 320          # OF Mercenary (Soldier host: 200 / 240)
MERC_ARMS = "models/weapons/c_models/c_merc_arms.mdl"


def body_item(by_class):
    """Hidden wearable the plugin gives every Mercenary: health, speed and the TF2C Merc arms.

    Attributes on a schema item are known to the client, so movement prediction matches
    (a player attribute added at runtime would stutter). custom_hand_viewmodel is read from
    the player (CALL_ATTRIB_HOOK_STRING_ON_OTHER in CTFWeaponBase::UpdateViewModel), so the
    arms apply to every weapon he holds, picked-up stock weapons included.
    """
    it = kv.KV()
    for k, v in (("name", "tf2cc_merc_body"), ("item_name", "Mercenary"), ("item_quality", "normal"),
                 ("item_class", "tf_wearable"), ("item_slot", "misc"), ("hidden", "1")):
        it.add(k, v)
    tags = kv.KV()
    tags.add("bots_cant_use", "1")
    it.add("tags", tags)
    attrs = kv.KV()
    attrs.add("hidden separator", "1")
    for cls, val in (("add_maxhealth", MERC_HEALTH - 200), ("mult_player_movespeed", round(MERC_SPEED / 240.0, 4))):
        a = kv.KV()
        a.add("attribute_class", cls)
        a.add("value", "%g" % val)
        attrs.add(attr_name(by_class, cls, 0.5 if val < 1 or val < 0 else 2.0), a)
    it.add("attributes", attrs)
    st = kv.KV()
    st.add("custom hand viewmodel", MERC_ARMS)
    it.add("static_attrs", st)
    return it


def num(v):
    try:
        return float(str(v).split("//")[0].strip())
    except (TypeError, ValueError):
        return None


def load_attr_names():
    root, _ = kv.load(BASE_SCHEMA)
    attrs = root["items_game"]["attributes"]
    by_class = {}
    for _, a in attrs.blocks():
        c = (a.get("attribute_class") or "").lower()
        n = a.get("name")
        if c and n:
            by_class.setdefault(c, []).append(n)
    return by_class


def attr_name(by_class, cls, value):
    names = by_class.get(cls.lower(), [])
    if not names:
        return None
    pick = [n for n in names if ("penalty" if value < 1 else "bonus") in n.lower()]
    return (pick or names)[0]


def weapon_data(name):
    p = os.path.join(BASE_SCRIPTS, name + ".txt")
    if not os.path.exists(p):
        return kv.KV()
    root, _ = kv.load(p, "latin-1")
    return root.get("WeaponData") or kv.KV()


def tf2c_files():
    out = set()
    for line in open(TF2C_LIST, encoding="latin-1"):
        out.add(line.rsplit(" ", 1)[0].strip().lower())
    return out


class Stager:
    def __init__(self, report):
        self.report = report
        self.stock = tf2c_files()
        self.copied = set()
        self.collisions = []
        self.missing = []

    def copy(self, src, rel):
        rel = rel.replace("\\", "/")
        if rel.lower() in self.copied:
            return True
        if not os.path.exists(src):
            self.missing.append(rel)
            return False
        if rel.lower() in self.stock:
            self.collisions.append(rel)
            return True     # TF2C already ships it: never override, use theirs
        dst = os.path.join(STAGE, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        self.copied.add(rel.lower())
        return True

    def model(self, of_rel, root=None, prefix=None):
        """Copy an OF model to models/tf2cc/of/<name>, plus companions and materials (root and
        prefix: another source tree and tf2cc folder, e.g. the stock tf2cc MarxVee assets)."""
        of_rel = of_rel.replace("\\", "/")
        self.root = root or OFG
        src = os.path.join(self.root, of_rel)
        if not os.path.exists(src):
            self.missing.append(of_rel)
            return None
        new_rel = (prefix or MODEL_PREFIX) + of_rel[len("models/"):]
        base_src, base_dst = src[:-4], new_rel[:-4]
        for ext in (".mdl", ".vvd", ".dx90.vtx", ".dx80.vtx", ".sw.vtx", ".phy"):
            if os.path.exists(base_src + ext):
                self.copy(base_src + ext, base_dst + ext)
        try:
            m = mdlinfo.parse(src)
        except Exception as e:  # noqa
            self.report.append("  !! cannot parse %s: %s" % (of_rel, e))
            return new_rel
        for cd in m["cdtextures"] or [""]:
            cd = cd.replace("\\", "/").strip("/").lower()
            for tex in m["textures"]:
                rel = ("materials/%s/%s.vmt" % (cd, tex.lower())) if cd else "materials/%s.vmt" % tex.lower()
                self.material(rel.replace("//", "/"))
        self.root = None
        return new_rel

    def material(self, rel, depth=0):
        src = os.path.join(getattr(self, "root", None) or OFG, rel)
        if not os.path.exists(src) or depth > 4:
            return
        if not self.copy(src, rel):
            return
        if rel.endswith(".vmt"):
            refs = list(self.vmt_refs(src))
            # stage.py's key list lacks $texture2..4 / $iris / $corneatexture (the lightning
            # gun screen's $texture2 gradient was never shipped: a missing texture).
            for m in re.finditer(r'"?\$(texture[2-4]|iris|corneatexture|ambientoccltexture|bumpmap2|detail2|envmapmask2)"?\s+"?([^"\s]+)"?',
                                 open(src, encoding="latin-1").read(), re.I):
                refs.append((m.group(1).lower(), m.group(2).replace("\\", "/").lower()))
            for _, ref in refs:
                r = ref if ref.startswith("materials/") else "materials/" + ref
                if not r.endswith((".vtf", ".vmt")):
                    self.material(r + ".vtf", depth + 1)
                else:
                    self.material(r, depth + 1)

    @staticmethod
    def vmt_refs(path):
        import stage
        return stage._vmt_refs(path)


MERC_EXTRACT = os.path.join(ROOT, "work", "tf2c_merc_extract")


def stage_merc_body(stager):
    """TF2C Merc materials, viewmodel arms and gibs from the 4dm pak (the player model itself
    is written by gen_merc_acts.py). Never c_soldier_arms: the 4dm maps override Soldier's arms
    because they are a total conversion; tf2cc only ships c_merc_arms."""
    for sub in ("materials/models/player/merc_deathmatch", "models/player/gibs"):
        base = os.path.join(MERC_EXTRACT, sub)
        for dp, _, files in os.walk(base):
            for f in files:
                if f.lower().startswith("c_soldier_arms"):
                    continue
                full = os.path.join(dp, f)
                stager.copy(full, os.path.relpath(full, MERC_EXTRACT).replace(os.sep, "/"))
    arms = os.path.join(MERC_EXTRACT, "models", "weapons", "c_models")
    for f in os.listdir(arms):
        if f.lower().startswith("c_merc_arms."):
            stager.copy(os.path.join(arms, f), "models/weapons/c_models/" + f)


def resolve_sound(scripts, name):
    waves = scripts.get((name or "").lower())
    return waves[0] if waves else None


def stage_wave(stager, wave):
    bare = wave.lstrip(")^*#<>@").replace("\\", "/").lower()
    if ("sound/" + bare) in getattr(stager, "stock_waves", ()) and not os.path.exists(os.path.join(OFG, "sound", bare)):
        return bare     # stock TF2/TF2C sound every client has
    rel, data = fvs.wave_source(wave)
    if data is None:
        stager.missing.append("sound/" + rel)
        return None
    dst_rel = "sound/" + SOUND_PREFIX + rel.lower()
    if dst_rel.lower() not in stager.copied:
        p = os.path.join(STAGE, dst_rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").write(data)
        stager.copied.add(dst_rel.lower())
    return SOUND_PREFIX + rel.lower()


def fix_viewmodel_sounds(stager, model_rel, scripts, tf2c_scripts, sounds=None):
    """Point AE_CL_PLAYSOUND events at the tf2cc.* copy of OF's script (OF's own sound, defined
    for every client by custom_level_sounds.txt); scripts OF does not define keep TF2C's, and
    anything else becomes a staged raw wave."""
    p = os.path.join(STAGE, model_rel)
    if not os.path.exists(p):
        return 0
    b = bytearray(open(p, "rb").read())
    n = 0
    for eo, ev, opt in list(fvs.events(bytes(b))):
        if ev != 5004 or not opt or "." not in opt:
            continue
        name = sounds.name_for(opt) if sounds is not None and not opt.lower().endswith((".wav", ".mp3")) else None
        if name and len(name) < 64:
            b[eo + 12:eo + 76] = name.encode("latin-1") + b"\0" * (64 - len(name))
            n += 1
            continue
        if opt.lower() in tf2c_scripts:
            continue
        if opt.lower().endswith((".wav", ".mp3")):
            continue
        wave = resolve_sound(scripts, opt)
        if not wave:
            continue
        new = stage_wave(stager, wave)
        if new and len(new) < 64:
            b[eo + 12:eo + 76] = new.encode("latin-1") + b"\0" * (64 - len(new))
            n += 1
    open(p, "wb").write(bytes(b))
    return n


def vtf_highres(data):
    """(width, height, format, mip count, trailing high-res bytes) of a single-frame VTF."""
    w, h = struct.unpack_from("<HH", data, 16)
    fmt = struct.unpack_from("<i", data, 52)[0]
    mips = data[56]
    bpb = {13: 8, 14: 16, 15: 16}.get(fmt)          # DXT1 / DXT3 / DXT5 bytes per 4x4 block
    bpp = {0: 4, 1: 4, 2: 3, 3: 3, 12: 4}.get(fmt)  # RGBA8888 ABGR8888 RGB888 BGR888 BGRA8888
    size = 0
    for m in range(mips):
        mw, mh = max(1, w >> m), max(1, h >> m)
        size += ((mw + 3) // 4) * ((mh + 3) // 4) * bpb if bpb else mw * mh * bpp
    return w, h, fmt, mips, data[len(data) - size:]


def write_vtf(path, w, h, fmt, flags, mips, payload):
    """Minimal VTF 7.2 (no low-res thumbnail)."""
    hdr = bytearray(80)
    struct.pack_into("<4sIII", hdr, 0, b"VTF\0", 7, 2, 80)
    struct.pack_into("<HHIHH", hdr, 16, w, h, flags, 1, 0)
    struct.pack_into("<fff", hdr, 32, 0.5, 0.5, 0.5)
    struct.pack_into("<f", hdr, 48, 1.0)
    struct.pack_into("<iBiBBH", hdr, 52, fmt, mips, -1, 0, 0, 1)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").write(bytes(hdr) + payload)


def has_team_icons(wid, icon):
    name = BUCKET_FALLBACK.get(wid) or (icon or "").replace("\\", "/").split("/")[-1]
    sp = os.path.join(OFG, "materials", "sprites")
    return bool(name) and all(os.path.exists(os.path.join(sp, name + t + ".vtf")) for t in ("_red", "_blue"))


def icon_vmt(rel):
    return ('"UnlitGeneric"\n{\n\t"$basetexture" "%s"\n\t"$translucent" "1"\n\t"$vertexcolor" "1"\n'
            '\t"$vertexalpha" "1"\n\t"$ignorez" "1"\n}\n' % rel)


def write_icon_vmt(stager, rel_vmt, rel_tex):
    """materials/<rel_vmt>.vmt and its materials/vgui/ copy (the client also has a "vgui/%s" lookup)."""
    for base in ("materials/", "materials/vgui/"):
        dst = os.path.join(STAGE, base + rel_vmt + ".vmt")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "w", encoding="latin-1", newline="\n") as f:
            f.write(icon_vmt(rel_tex))
        stager.copied.add((base + rel_vmt + ".vmt").lower())


def stage_bucket_icon(stager, wid, icon):
    name = BUCKET_FALLBACK.get(wid)
    if not name and icon:
        name = icon.replace("\\", "/").split("/")[-1]
    src = os.path.join(OFG, "materials", "sprites", (name or "") + ".vtf")
    if not name or not os.path.exists(src):
        stager.missing.append("bucket icon for %s" % wid)
        return None
    data = open(src, "rb").read()
    w, h, fmt, mips, pix = vtf_highres(data)
    if mips != 1 or w != 256 or h != 128 or fmt not in (0, 15):
        stager.missing.append("bucket icon %s: unexpected %dx%d fmt %d mips %d" % (name, w, h, fmt, mips))
        return None
    # Pad top and bottom with transparent rows (zero bytes are transparent in RGBA8888 and DXT5).
    pad = (h // 2 // 4) * (w // 4) * 16 if fmt == 15 else (h // 2) * w * 4
    flags = struct.unpack_from("<I", data, 20)[0]
    team = has_team_icons(wid, icon)
    rel = "%s/%s" % (TEAM_BUCKET_DIR if team else BUCKET_DIR, name.lower())
    write_vtf(os.path.join(STAGE, "materials", rel + ".vtf"), w, w, fmt, flags, 1, b"\0" * pad + pix + b"\0" * pad)
    # materials/<image_inventory>[_large].vmt is what the item panels draw (the _large one wins);
    # team icons get no _large so that <image>_<team>.vmt is reached (stage_team_icons).
    write_icon_vmt(stager, rel, rel)
    if not team:
        write_icon_vmt(stager, rel + "_large", rel)
    stager.copied.add(("materials/" + rel + ".vtf").lower())
    return rel


def dxt5_recolor(pix, fn):
    """Apply fn(r5, g6, b5) -> (r5, g6, b5) to every DXT5 colour endpoint (always 4-colour mode)."""
    b = bytearray(pix)
    for o in range(0, len(b) - 15, 16):
        for e in (o + 8, o + 10):
            c = struct.unpack_from("<H", b, e)[0]
            r, g, bl = fn(c >> 11, (c >> 5) & 63, c & 31)
            struct.pack_into("<H", b, e, (min(r, 31) << 11) | (min(g, 63) << 5) | min(bl, 31))
    return bytes(b)


def stage_bomblet(stager):
    import gen_merc_variants as gmv
    src = os.path.join(OFG, BOMBLET_SRC)
    m = gmv.Mdl(open(src, "rb").read())
    base_src, base_dst = src[:-4], os.path.join(STAGE, BOMBLET_DST[:-4])
    os.makedirs(os.path.dirname(base_dst), exist_ok=True)
    for ext in (".vvd", ".dx90.vtx", ".dx80.vtx", ".sw.vtx", ".phy"):
        if os.path.exists(base_src + ext):
            shutil.copyfile(base_src + ext, base_dst + ext)
            stager.copied.add((BOMBLET_DST[:-4] + ext).lower())
    b = m.b
    i32 = lambda o: struct.unpack_from("<i", b, o)[0]  # noqa: E731
    nt, ti, nref, nfam = i32(204), i32(208), i32(220), i32(224)
    if nt != 2 or nref != 2 or nfam != 2:
        raise SystemExit("unexpected bomblet model layout")
    teams = ("red", "blue", "green", "yellow")
    template = bytes(b[ti:ti + 64])
    while len(b) % 4:
        b += b"\0"
    tex = len(b)
    b += template * len(teams)
    for k, team in enumerate(teams):
        o = tex + k * 64
        struct.pack_into("<i", b, o, m.add_string("bomblet_" + team) - o)
    struct.pack_into("<ii", b, 204, len(teams), tex)
    while len(b) % 4:
        b += b"\0"
    cd = len(b)
    b += b"\0" * 4
    struct.pack_into("<i", b, cd, m.add_string(BOMBLET_MAT_DIR.replace("/", "\\") + "\\"))
    struct.pack_into("<ii", b, 212, 1, cd)
    while len(b) % 4:
        b += b"\0"
    sk = len(b)
    for k in range(len(teams)):            # skin = team - 2 (RED, BLU, GRN, YLW)
        b += struct.pack("<hh", k, 1)
    struct.pack_into("<ii", b, 224, len(teams), sk)
    open(base_dst + ".mdl", "wb").write(m.finish())
    stager.copied.add(BOMBLET_DST.lower())
    # Materials: OF's red and blue textures; green and yellow recoloured from the red one.
    of_dir = os.path.join(OFG, "materials", "models", "weapons", "w_grenade_bomblet")
    red = open(os.path.join(of_dir, "w_grenade_bomblet.vtf"), "rb").read()
    blue = open(os.path.join(of_dir, "w_grenade_bomblet_blue.vtf"), "rb").read()
    w, h, fmt, mips, pix = vtf_highres(red)
    if fmt != 15:
        raise SystemExit("bomblet texture is not DXT5")
    flags = struct.unpack_from("<I", red, 20)[0]
    g6 = lambda r5: (r5 << 1) | (r5 >> 4)  # noqa: E731
    variants = {"red": red, "blue": blue,
                "green": dxt5_recolor(pix, lambda r, g, bl: (g >> 1, g6(r), bl)),
                "yellow": dxt5_recolor(pix, lambda r, g, bl: (r, max(g, g6(r) * 7 // 8), bl))}
    out = os.path.join(STAGE, "materials", BOMBLET_MAT_DIR)
    os.makedirs(out, exist_ok=True)
    vmt = open(os.path.join(of_dir, "w_grenade_bomblet.vmt"), encoding="latin-1").read()
    for team, data in variants.items():
        dst = os.path.join(out, "bomblet_%s.vtf" % team)
        if team in ("red", "blue"):
            open(dst, "wb").write(data)
        else:
            write_vtf(dst, w, h, fmt, flags, mips, data)
        body = re.sub(r'"\$baseTexture"\s+"[^"]*"',
                      lambda _m: '"$baseTexture" "%s/bomblet_%s"' % (BOMBLET_MAT_DIR, team), vmt, flags=re.I)
        with open(os.path.join(out, "bomblet_%s.vmt" % team), "w", encoding="latin-1", newline="\n") as f:
            f.write(body)
        for ext in (".vtf", ".vmt"):
            stager.copied.add(("materials/%s/bomblet_%s%s" % (BOMBLET_MAT_DIR, team, ext)).lower())
    # The vmt's other textures (weapon lightwarp, flat normal) are stock TF2/TF2C files.


def stage_extra_sounds(stager):
    roots = [os.path.join(ROOT, "assets", "overrides", "tf", "sound"), os.path.join(ROOT, "assets", "tf", "sound")]
    for src_rel, dst_rel in EXTRA_SOUNDS.items():
        src = next((os.path.join(r, src_rel) for r in roots if os.path.exists(os.path.join(r, src_rel))), None)
        if not src:
            stager.missing.append("sound/" + src_rel)
            continue
        stager.copy(src, "sound/" + dst_rel)


SOUNDSCRIPT_REL = "scripts/items/custom_level_sounds.txt"
SOUND_PREFIX_SCRIPT = "tf2cc."


def load_of_soundscripts():
    """OF sound script name (lower) -> (name, KV), in OF manifest order (first definition wins)."""
    sdir = os.path.join(OFG, "scripts")
    man, _ = kv.load(os.path.join(sdir, "game_sounds_manifest.txt"), "latin-1")
    order = [v.replace("\\", "/").split("/")[-1] for k, v in (man.get("game_sounds_manifest") or man).items()
             if isinstance(v, str) and k.lower().endswith("_file")]
    order += sorted(f for f in os.listdir(sdir) if f.startswith("game_sounds") and f.endswith(".txt") and f not in order)
    out = {}
    for f in order:
        path = os.path.join(sdir, f)
        if not os.path.exists(path) or f == "game_sounds_manifest.txt":
            continue
        root, _ = kv.load(path, "latin-1")
        for name, entry in root.blocks():
            out.setdefault(name.lower(), (name, entry))
    return out


class SoundScripts:
    """Collects the tf2cc copies of OF sound scripts for custom_level_sounds.txt."""

    def __init__(self, stager, of_scripts):
        self.stager, self.of, self.entries, self.missing = stager, of_scripts, {}, []

    def _rewrite(self, entry):
        out = kv.KV()
        for k, v in entry.items():
            if isinstance(v, kv.KV):
                out.add(k, self._rewrite(v))
            elif k.lower() == "wave":
                prefix = re.match(r"^[)^*#<>@!?]*", v).group(0)
                new = stage_wave(self.stager, v)
                if new:
                    out.add(k, prefix + new)
                else:
                    self.missing.append(v)
            else:
                out.add(k, v)
        return out

    def name_for(self, of_name):
        """tf2cc script name for an OF script, or None when OF does not define it."""
        hit = self.of.get(of_name.lower())
        if not hit:
            return None
        name = SOUND_PREFIX_SCRIPT + hit[0]
        if name.lower() not in self.entries:
            self.entries[name.lower()] = (name, self._rewrite(hit[1]))
        return name

    def silent(self):
        name = SOUND_PREFIX_SCRIPT + "Silent"
        e = kv.KV()
        for k, v in (("channel", "CHAN_STATIC"), ("volume", "0"), ("soundlevel", "SNDLVL_NONE"), ("wave", "common/null.wav")):
            e.add(k, v)
        self.entries[name.lower()] = (name, e)
        return name

    def raw(self, key, wave):
        """A script entry for a bare wave (OF value that is a file, not a script)."""
        name = SOUND_PREFIX_SCRIPT + key
        new = stage_wave(self.stager, wave)
        if not new:
            return None
        e = kv.KV()
        for k, v in (("channel", "CHAN_WEAPON"), ("soundlevel", "SNDLVL_GUNFIRE"), ("volume", "1.0"), ("wave", new)):
            e.add(k, v)
        self.entries[name.lower()] = (name, e)
        return name

    def write(self):
        body = kv.KV()
        for _, (name, entry) in sorted(self.entries.items()):
            body.add(name, entry)
        dst = os.path.join(STAGE, SOUNDSCRIPT_REL)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "w", encoding="utf-8", newline="\n") as f:
            f.write("// tf2cc for TF2 Classified: Open Fortress weapon sound scripts for the Mercenary items\n"
                    "// (generated by tools/tf2c/gen_schema.py; loaded by TF2C from scripts/items/ at level init)\n")
            f.write(kv.dump(body, 0))
        self.stager.copied.add(SOUNDSCRIPT_REL)
        return len(self.entries)


def pad_square(data):
    """256x128 single-mip VTF -> (w, fmt, flags, square payload padded with transparent rows)."""
    w, h, fmt, mips, pix = vtf_highres(data)
    if mips != 1 or w != 256 or h != 128 or fmt not in (0, 15):
        return None
    pad = (h // 2 // 4) * (w // 4) * 16 if fmt == 15 else (h // 2) * w * 4
    return w, fmt, struct.unpack_from("<I", data, 20)[0], b"\0" * pad + pix + b"\0" * pad


def stage_team_icons(stager, wid, icon, rel):
    """<rel>_red/_blue/_green/_yellow textures from OF's bucket_<x>_red/_blue sprites; green and
    yellow recoloured from red (vtfcolor). False when OF has no team variants."""
    import vtfcolor
    name = BUCKET_FALLBACK.get(wid) or (icon or "").replace("\\", "/").split("/")[-1]
    sp = os.path.join(OFG, "materials", "sprites")
    red, blue = os.path.join(sp, name + "_red.vtf"), os.path.join(sp, name + "_blue.vtf")
    if not (os.path.exists(red) and os.path.exists(blue)):
        return False
    r = pad_square(open(red, "rb").read())
    b = pad_square(open(blue, "rb").read())
    if not r or not b:
        return False
    w, fmt, flags, rpix = r
    teams = {"red": (fmt, flags, rpix), "blue": (b[1], b[2], b[3]),
             "green": (fmt, flags, vtfcolor.recolor_pixels(rpix, fmt, "green")),
             "yellow": (fmt, flags, vtfcolor.recolor_pixels(rpix, fmt, "yellow"))}
    for team, (f, fl, pix) in teams.items():
        write_vtf(os.path.join(STAGE, "materials", "%s_%s.vtf" % (rel, team)), w, w, f, fl, 1, pix)
        stager.copied.add(("materials/%s_%s.vtf" % (rel, team)).lower())
        write_icon_vmt(stager, "%s_%s" % (rel, team), "%s_%s" % (rel, team))
    return True


TEAMSKIN_MAT_DIR = "models/tf2cc/of/teamskin"


def find_vmt(cdtextures, tex):
    for cd in cdtextures or [""]:
        cd = cd.replace("\\", "/").strip("/").lower()
        rel = ("materials/%s/%s.vmt" % (cd, tex.lower())) if cd else "materials/%s.vmt" % tex.lower()
        rel = rel.replace("//", "/")
        for root in (STAGE, OFG):
            if os.path.exists(os.path.join(root, rel)):
                return os.path.join(root, rel), rel
    return None, None


def team_skin_patch(stager, model_rel, report):
    """OF weapon models have RED (skin 0) and BLU (skin 1) families and OF-only families after
    them; TF2C draws GRN with skin 2 and YLW with skin 3 (GetTeamSkin()). Families 2 and 3
    become green and yellow: every texture that differs between the RED and BLU families gets
    a recoloured copy of its RED texture under materials/models/tf2cc/of/teamskin/."""
    import gen_merc_variants as gmv
    import vtfcolor
    path = os.path.join(STAGE, model_rel)
    m = mdlinfo.parse(path)
    skins = m["skins"]
    if len(skins) < 2 or skins[0] == skins[1]:
        return
    nref = len(skins[0])
    diff = [i for i in range(nref) if skins[0][i] != skins[1][i]]
    texnames = m["textures"]
    md = gmv.Mdl(open(path, "rb").read())
    b = md.b
    nt, ti = struct.unpack_from("<ii", b, 204)
    new_tex = []          # (name, team, source red texture index)
    for team in ("green", "yellow"):
        for i in diff:
            src = skins[0][i]
            new_tex.append(("%s_%s" % (texnames[src].lower().replace("/", "_"), team), team, src))
    made = {}
    for name, team, src in new_tex:
        vmt_path, vmt_rel = find_vmt(m["cdtextures"], texnames[src])
        if not vmt_path:
            report.append("  !! teamskin %s: no material for %s" % (model_rel, texnames[src]))
            return
        text = open(vmt_path, encoding="latin-1").read()
        mm = re.search(r'"?\$basetexture"?\s+"?([^"\s]+)"?', text, re.I)
        if not mm:
            report.append("  !! teamskin %s: %s has no $basetexture" % (model_rel, vmt_rel))
            return
        base = mm.group(1).replace("\\", "/")
        vtf_src = None
        for root in (STAGE, OFG):
            cand = os.path.join(root, "materials", base + ".vtf")
            if os.path.exists(cand):
                vtf_src = cand
                break
        if vtf_src is None:
            tf2c_data = fvs.vpk("cat", fvs.TF2C_VPK, "materials/%s.vtf" % base.lower())
            if not tf2c_data:
                report.append("  !! teamskin %s: texture %s not found" % (model_rel, base))
                return
            data = tf2c_data
        else:
            data = open(vtf_src, "rb").read()
        new_base = "%s/%s" % (TEAMSKIN_MAT_DIR, name)
        try:
            out = vtfcolor.recolor_vtf(data, team)
        except ValueError as e:
            report.append("  !! teamskin %s: %s" % (model_rel, e))
            return
        dst = os.path.join(STAGE, "materials", new_base + ".vtf")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, "wb").write(out)
        body = text[:mm.start(1)] + new_base + text[mm.end(1):]
        with open(os.path.join(STAGE, "materials", new_base + ".vmt"), "w", encoding="latin-1", newline="\n") as f:
            f.write(body)
        for ext in (".vtf", ".vmt"):
            stager.copied.add(("materials/" + new_base + ext).lower())
        made[(team, src)] = name
    # append textures (copies of the red texture's struct with new names)
    while len(b) % 4:
        b += b"\0"
    tex = len(b)
    b += bytes(b[ti:ti + 64 * nt])
    names = list(made.items())
    b += b"\0" * (64 * len(names))
    idx = {}
    for k, ((team, src), name) in enumerate(names):
        o = tex + 64 * (nt + k)
        b[o:o + 64] = b[ti + 64 * src:ti + 64 * src + 64]
        struct.pack_into("<i", b, o, md.add_string(name) - o)
        idx[(team, src)] = nt + k
    for k in range(nt):             # re-point the copied originals' name offsets
        o_old, o_new = ti + 64 * k, tex + 64 * k
        struct.pack_into("<i", b, o_new, struct.unpack_from("<i", b, o_old)[0] + o_old - o_new)
    struct.pack_into("<ii", b, 204, nt + len(names), tex)
    # $cdmaterials: our folder first
    ncd, cdi = struct.unpack_from("<ii", b, 212)
    old = [struct.unpack_from("<i", b, cdi + 4 * k)[0] for k in range(ncd)]
    while len(b) % 4:
        b += b"\0"
    cdt = len(b)
    b += b"\0" * (4 * (ncd + 1))
    offs = [md.add_string(TEAMSKIN_MAT_DIR.replace("/", "\\") + "\\")] + old
    for k, o in enumerate(offs):
        struct.pack_into("<i", b, cdt + 4 * k, o)
    struct.pack_into("<ii", b, 212, ncd + 1, cdt)
    # skin families: 0 red, 1 blue, 2 green, 3 yellow, then the model's own extra families
    fam = [list(skins[0]), list(skins[1])]
    for team in ("green", "yellow"):
        f = list(skins[0])
        for i in diff:
            f[i] = idx[(team, skins[0][i])]
        fam.append(f)
    fam += [list(x) for x in skins[2:]]
    while len(b) % 4:
        b += b"\0"
    sk = len(b)
    for f in fam:
        b += struct.pack("<%dh" % nref, *f)
    struct.pack_into("<ii", b, 224, len(fam), sk)
    open(path, "wb").write(md.finish())
    report.append("  teamskin %s: %d textures, families %d -> %d" % (model_rel, len(names), len(skins), len(fam)))


PLUGIN_CFG = os.path.join(ROOT, "config", "sourcemod", "configs", "tf2cc_tf2c", "weapons.cfg")
DEFAULTS = {"merc_pistol": "secondary", "merc_crowbar": "melee"}

# MarxVee-origin Merc items of the stock tf2cc (config/sourcemod/configs/tf2cc/weapons.cfg),
# models from its assets. Optional: the plugin offers them only when listed in the cvar
# tf2cc_marxvee_items (empty by default; the test and live servers enable both).
# id, item_class, slot, bucket, anim slot, viewmodel, world model, attributes, activity renames
MARXVEE_ROOT = os.path.join(ROOT, "assets", "tf")
MARXVEE_PREFIX = "models/tf2cc/marxvee/"
MARXVEE_FIRST_ID = 30150
MARXVEE = [
    # Machine Gun (MarxVee Merc_2_Machine_Gun on the SMG, stock tf2cc profile): clip 40, reserve
    # 120, the SMG's own fire rate, damage and sounds.
    ("merc_machinegun", "tf_weapon_smg", "secondary", 1, "SECONDARY",
     "models/weapons/customclasses/v_models/v_machinegun_merc.mdl",
     "models/weapons/customclasses/w_models/w_machinegun_merc.mdl",
     [("mod_max_primary_clip_override", 40), ("mult_maxammo_secondary", 120 / 75.0)],
     {"ACT_SECONDARY_VM_DRAW": "ACT_VM_DRAW", "ACT_SECONDARY_VM_IDLE": "ACT_VM_IDLE",
      "ACT_SECONDARY_VM_PRIMARYATTACK": "ACT_VM_PRIMARYATTACK", "ACT_SECONDARY_VM_RELOAD": "ACT_VM_RELOAD"}),
    # Medkit (PF2 syringe profile, stock tf2cc "medkit_pf2"): the plugin swings every 0.8 s,
    # heals a teammate 50 (cleanse) or hits an enemy for 50 + infection; the base melee never
    # swings by itself and deals nothing.
    # (On the Wrangler class like the stock tf2cc: a secondary class; a melee class given as a
    # secondary still took the melee loadout slot and removed the crowbar.)
    ("merc_medkit", "tf_weapon_laser_pointer", "secondary", 1, "SECONDARY",
     "models/weapons/customclasses/v_models/v_classic_medkit.mdl",
     "models/weapons/customclasses/w_models/w_classic_medkit.mdl",
     [],
     {"ACT_ITEM1_VM_DRAW": "ACT_VM_DRAW", "ACT_ITEM1_VM_IDLE": "ACT_VM_IDLE",
      "ACT_ITEM1_VM_PRIMARYATTACK": "ACT_VM_HITCENTER"}),
]
MARXVEE_WEIGHT = {"merc_machinegun": "4", "merc_medkit": "3"}
MARXVEE_NAMES = {"merc_machinegun": "Machine Gun", "merc_medkit": "Medkit"}


def rename_acts(path, renames):
    import gen_merc_variants as gmv
    m = gmv.Mdl(open(path, "rb").read())
    n = 0
    for k in range(m.nseq):
        a = m.act(k)
        if a in renames:
            m.set_act(k, renames[a], 1)
            n += 1
    open(path, "wb").write(m.finish())
    return n


def build_marxvee(stager, items, sounds, by_class, report):
    for n, (wid, cls, slot, bucket, group, vm, wm, attrs_l, renames) in enumerate(MARXVEE):
        it = kv.KV()
        it.add("name", "tf2cc_" + wid)
        it.add("item_name", MARXVEE_NAMES[wid])
        it.add("item_type_name", "Mercenary Weapon")
        it.add("item_quality", "normal")
        it.add("propername", "0")
        it.add("item_class", cls)
        it.add("item_slot", slot)
        it.add("anim_slot", group)
        it.add("bucket", str(bucket))
        it.add("hidden", "1")
        tags = kv.KV()
        tags.add("bots_cant_use", "1")
        it.add("tags", tags)
        vm_new = stager.model(vm, MARXVEE_ROOT, MARXVEE_PREFIX)
        wm_new = stager.model(wm, MARXVEE_ROOT, MARXVEE_PREFIX)
        nacts = rename_acts(os.path.join(STAGE, vm_new), renames) if vm_new else 0
        it.add("model_player", vm_new)
        it.add("model_world", wm_new)
        it.add("attach_to_hands", "2")
        attrs = kv.KV()
        attrs.add("hidden separator", "1")
        for acls, val in attrs_l:
            nm = attr_name(by_class, acls, val)
            if nm:
                a = kv.KV()
                a.add("attribute_class", acls)
                a.add("value", "%g" % round(val, 4))
                attrs.add(nm, a)
        it.add("attributes", attrs)
        st = kv.KV()
        st.add("custom hand viewmodel", MERC_ARMS)
        it.add("static_attrs", st)
        vis = kv.KV()
        if wid == "merc_medkit":
            for t in ("melee_miss", "melee_hit", "melee_hit_world", "burst", "single_shot"):
                vis.add("sound_" + t, sounds.silent())
        if vis.pairs:
            it.add("visuals", vis)
        for mdl in (vm_new, wm_new):
            if mdl:
                team_skin_patch(stager, mdl, report)
        items.add(str(MARXVEE_FIRST_ID + n), it)
        report.append("%-20s %-6d %-28s marxvee, %d activities renamed" % (wid, MARXVEE_FIRST_ID + n, cls, nacts))
# Weapons whose OF behaviour needs a plugin special that is not written yet: never handed out.
NOT_YET = set()


def write_plugin_cfg(items, cfg):
    """Plugin weapon list: item name, slot, ammo-pack weight, world model, default flag."""
    out = kv.KV()
    for wid, ofkey, cls, slot, bucket, group, aset in ROSTER:
        it = next((v for k, v in items.items() if v.get("name") == "tf2cc_" + wid), None)
        if it is None:
            continue
        e = kv.KV()
        e.add("item", "tf2cc_" + wid)
        e.add("defindex", next(k for k, v in items.items() if v is it))
        e.add("slot", slot)
        w = cfg.get(wid)
        weight = (w.get("pack_weight") if w is not None else None) or ("0" if wid in DEFAULTS else "10")
        if wid in NOT_YET or wid in DEFAULTS:
            weight = "0"
        e.add("pack_weight", weight)
        e.add("worldmodel", it.get("model_world") or "")
        e.add("default", "1" if wid in DEFAULTS else "0")
        out.add(wid, e)
    for wid, cls, slot, bucket, group, vm, wm, attrs_l, renames in MARXVEE:
        k = next((k for k, v in items.items() if v.get("name") == "tf2cc_" + wid), None)
        if k is None:
            continue
        e = kv.KV()
        e.add("item", "tf2cc_" + wid)
        e.add("defindex", k)
        e.add("slot", slot)
        e.add("pack_weight", MARXVEE_WEIGHT.get(wid, "3"))
        e.add("worldmodel", items.get(k).get("model_world") or "")
        e.add("default", "0")
        e.add("marxvee", "1")     # offered only when listed in tf2cc_marxvee_items
        out.add(wid, e)
    os.makedirs(os.path.dirname(PLUGIN_CFG), exist_ok=True)
    open(PLUGIN_CFG, "w", encoding="utf-8", newline="\n").write(
        "// tf2cc for TF2 Classified: Mercenary weapons (generated by tools/tf2c/gen_schema.py; do not edit)\n"
        "// pack_weight: chance weight for ammo-pack weapon drops (0 = never).\n"
        '"tf2cc_tf2c_weapons"\n{\n' + kv.dump(out, 1) + "}\n")


def build(af_path):
    report = []
    stager = Stager(report)
    acts = json.load(open(ACTS))["replace"]
    by_class = load_attr_names()
    of_root, _ = kv.load(os.path.join(OFG, "scripts", "items", "items_game.txt"), "latin-1")
    of_weapons = (of_root.get("items_game") or of_root)["Weapons"]
    scripts = fvs.load_custom()     # OF scripts first, then TF2C's
    tf2c_scripts = set()
    for path in fvs.vpk("list", fvs.TF2C_VPK, "scripts/game_sounds").decode().split():
        tf2c_scripts |= fvs.script_names(fvs.vpk("cat", fvs.TF2C_VPK, path).decode("latin-1"))
    for path in fvs.vpk("list", fvs.TF2_VPK, "scripts/game_sounds").decode().split():
        tf2c_scripts |= fvs.script_names(fvs.vpk("cat", fvs.TF2_VPK, path).decode("latin-1"))

    cfg_root, _ = kv.load(WEAPONS_CFG, "latin-1")
    cfg = cfg_root["tf2cc_weapons"]
    tf2_snd = fvs.TF2_VPK.replace("tf2_misc_dir.vpk", "tf2_sound_misc_dir.vpk")
    stock_waves = set(p.lower() for p in fvs.vpk("list", tf2_snd, "sound/").decode().split())
    stock_waves |= set(p.lower() for p in fvs.vpk("list", fvs.TF2C_VPK, "sound/").decode().split())
    # TF2C mounts TF2's hl2/ sound VPK too (gameinfo): HL2 waves are stock for every client.
    hl2_snd = os.path.join(os.path.dirname(os.path.dirname(fvs.TF2_VPK)), "hl2", "hl2_sound_misc_dir.vpk")
    stock_waves |= set(p.lower() for p in fvs.vpk("list", hl2_snd, "sound/").decode().split())
    stager.stock_waves = stock_waves
    stage_merc_body(stager)
    for extra in EXTRA_MODELS:          # models only the plugin uses
        stager.model(extra)
    stage_bomblet(stager)
    stage_extra_sounds(stager)
    sounds = SoundScripts(stager, load_of_soundscripts())
    items = kv.KV()
    items.add(str(BODY_ID), body_item(by_class))
    for n, (wid, ofkey, cls, slot, bucket, group, aset) in enumerate(ROSTER):
        ofw = of_weapons.get(ofkey)
        if ofw is None:
            report.append("!! %s: OF weapon %s not found" % (wid, ofkey))
            continue
        wd = ofw["WeaponData"]
        base = weapon_data(cls)
        it = kv.KV()
        it.add("name", "tf2cc_" + wid)
        printname = (cfg.get(wid).get("name") if cfg.get(wid) is not None else None) or wid
        it.add("item_name", printname)
        it.add("item_type_name", "Mercenary Weapon")
        it.add("item_quality", "normal")
        it.add("propername", "0")
        it.add("item_class", cls)
        it.add("item_slot", slot)
        it.add("anim_slot", group)
        it.add("bucket", str(bucket))
        # Build 5205 lists every non-hidden item a class may use in the armory and in bot
        # random loadouts (tf2c_bot_random_loadouts): "hidden" keeps Merc items out of both,
        # bots_cant_use is a second guard. GenerateAndWearItem still gives hidden items.
        it.add("hidden", "1")
        tags = kv.KV()
        tags.add("bots_cant_use", "1")
        it.add("tags", tags)

        vm = wd.get("viewmodel")
        wm = wd.get("playermodel")
        vm_new = stager.model(vm) if vm else None
        wm_new = stager.model(wm) if wm else None
        if vm_new:
            it.add("model_player", vm_new)
            nfix = fix_viewmodel_sounds(stager, vm_new, scripts, tf2c_scripts, sounds)
        else:
            nfix = 0
        if wm_new:
            it.add("model_world", wm_new)
        it.add("attach_to_hands", "2")

        attrs = kv.KV()
        attrs.add("hidden separator", "1")
        notes = []
        skip = SKIP_STATS.get(wid, set())
        for acls, key in STATS:
            if "*" in skip or key in skip:
                continue
            o, b = num(wd.get(key)), num(base.get(key))
            if o is None or b is None or o <= 0 or b <= 0:
                continue
            v = round(o / b, 4)
            if abs(v - 1.0) < 0.005:
                continue
            nm = attr_name(by_class, acls, v)
            if not nm:
                notes.append("no attribute for %s" % acls)
                continue
            a = kv.KV()
            a.add("attribute_class", acls)
            a.add("value", "%g" % v)
            attrs.add(nm, a)
            notes.append("%s %g (OF %g / base %g)" % (key, v, o, b))
        # Clip model (see EXTRA_ATTRS): OF clip-less weapons fire from the reserve, OF clips on
        # clip-less bases get that clip.
        oclip, bclip = num(wd.get("clip_size")), num(base.get("clip_size"))
        override = None
        if oclip is not None and bclip is not None and "*" not in skip:
            if oclip < 0 < bclip:
                override = -1
            # (OF clips on TF2C's clip-less bases are not given: the shotgun bases reload one
            # shell at a time with ACT_VM_RELOAD_START/FINISH, which the OF viewmodels lack, and
            # a clip override there broke the reload; see the super shotgun in EXTRA_ATTRS.)
        if override is not None:
            for nm in [n for n, v in attrs.items() if isinstance(v, kv.KV) and v.get("attribute_class") in ("mult_clipsize",)
                       or (isinstance(v, kv.KV) and override == -1 and v.get("attribute_class") == "mult_reload_time")]:
                attrs.pairs = [(a, b) for a, b in attrs.pairs if a != nm]
            a = kv.KV()
            a.add("attribute_class", "mod_max_primary_clip_override")
            a.add("value", "%d" % override)
            attrs.add("mod max primary clip override", a)
            notes.append("clip override %d (OF clip %g, base %g)" % (override, oclip, bclip))
        omax, bmax = num(wd.get("MaxAmmo")), num(base.get("MaxAmmo"))
        if "*" not in skip and omax and bmax and omax > 0 and bmax > 0 and abs(omax / bmax - 1) > 0.005:
            acls = "mult_maxammo_primary" if slot == "primary" else "mult_maxammo_secondary"
            nm = attr_name(by_class, acls, omax / bmax)
            if nm:
                a = kv.KV()
                a.add("attribute_class", acls)
                a.add("value", "%g" % round(omax / bmax, 4))
                attrs.add(nm, a)
                notes.append("MaxAmmo %g (OF %g / base %g)" % (omax / bmax, omax, bmax))
        for acls, val in EXTRA_ATTRS.get(wid, []):
            nm = attr_name(by_class, acls, val)
            if nm:
                a = kv.KV()
                a.add("attribute_class", acls)
                a.add("value", "%g" % round(val, 4))
                attrs.add(nm, a)
                notes.append("extra %s %g" % (acls, val))
        it.add("attributes", attrs)
        # The Merc arms on the weapon itself as well as on the body item: the client resolves
        # custom_hand_viewmodel when the weapon deploys, and the weapon is certain to be
        # providing its attributes by then (the body wearable may arrive later on the client).
        st = kv.KV()
        st.add("custom hand viewmodel", MERC_ARMS)
        for k, v in STRING_ATTRS.get(wid, {}).items():
            st.add(k, v)
        it.add("static_attrs", st)

        vis = kv.KV()
        sd = wd.get("SoundData") or kv.KV()
        snd_notes = []
        for k, v in sd.items():
            t = SOUND_TYPES.get(k.lower())
            if not t or isinstance(v, kv.KV) or not v.strip():
                continue
            if wid in SILENT_ALL or (wid in SILENT_SHOT and t in ("single_shot", "burst")):
                sounds.name_for(v)                  # still defined: the plugin plays it
                vis.add("sound_" + t, sounds.silent())
                continue
            name = sounds.name_for(v)               # OF's own definition, always preferred
            if not name and v.lower() in tf2c_scripts:
                name = v                            # only TF2C/TF2 define it: every client has it
            if not name and v.lower().endswith((".wav", ".mp3")):
                name = sounds.raw("%s.%s" % (wid, t), v)
            if not name:
                wave = resolve_sound(scripts, v)
                name = sounds.raw("%s.%s" % (wid, t), wave) if wave else None
            if name:
                vis.add("sound_" + t, name)
                snd_notes.append(t)
            else:
                report.append("  !! %s: no sound for %s %s" % (wid, t, v))
        if wid in SILENT_ALL:
            for t in ("melee_miss", "melee_hit", "melee_hit_world", "burst", "single_shot", "special1"):
                if vis.get("sound_" + t) is None:
                    vis.add("sound_" + t, sounds.silent())
        if wid in TRACERS:
            vis.add("tracer_effect", TRACERS[wid])
        rep = kv.KV()
        for src_act, dst_act in (acts.get(aset, {}).get(group) or {}).items():
            rep.add(src_act, dst_act)
        if rep.pairs:
            vis.add("animation_replacement", rep)
        it.add("visuals", vis)
        icon = stage_bucket_icon(stager, wid, ofw.get("backpack_icon"))
        if icon:
            it.add("image_inventory", icon)
            if stage_team_icons(stager, wid, ofw.get("backpack_icon"), icon):
                # TF2C 5205 (client.dll, item panel image lookup): with image_inventory_teamcolor
                # the texture "<image_inventory>_<red|blue|green|yellow>" is used for the
                # panel's team (team names table: red, blue, green, yellow).
                it.add("image_inventory_teamcolor", "1")
        for mdl in (vm_new, wm_new):
            if mdl:
                team_skin_patch(stager, mdl, report)
                if cls == "tf_weapon_minigun":
                    # TF2C spins "v_minigun_barrel" about its local X (first person) and "barrel"
                    # about local Z (world): OF's viewmodel barrel runs along Z (barrel_fix.py).
                    import barrel_fix
                    barrel_fix.fix_minigun_barrel(os.path.join(STAGE, mdl), report)
        items.add(str(FIRST_ID + n), it)
        report.append("%-20s %-6d %-28s anim %-14s acts %2d  sounds[%s]  vm-events fixed %d\n    %s"
                      % (wid, FIRST_ID + n, cls, aset, len(rep.pairs), ",".join(snd_notes), nfix, "; ".join(notes)))

    build_marxvee(stager, items, sounds, by_class, report)
    for name in EXTRA_SCRIPT_SOUNDS:
        if not sounds.name_for(name):
            report.append("  !! extra sound script %s not in OF" % name)
    n_scripts = sounds.write()
    report.append("sound scripts: %d (%s); missing waves: %s" % (n_scripts, SOUNDSCRIPT_REL, ", ".join(sorted(set(sounds.missing))) or "none"))
    write_plugin_cfg(items, cfg)
    out = kv.KV()
    out.add("items", items)
    body = kv.dump(out, 1)
    header = ('// TF2 Classified: tf2cc Mercenary weapons (generated by tools/tf2c/gen_schema.py; do not edit)\n')
    if af_path:
        af, _ = kv.load(af_path)
        afg = af["items_game"]
        merged = kv.KV()
        merged_items = kv.KV()
        for k, v in (afg.get("items") or kv.KV()).items():
            merged_items.add(k, v)
        for k, v in items.items():
            merged_items.add(k, v)
        merged.add("items", merged_items)
        for k, v in afg.items():
            if k.lower() != "items":
                merged.add(k, v)
        body = kv.dump(merged, 1)
        header += "// Merged with the April Fools pack: %s\n" % os.path.basename(af_path)
    text = header + '#base "items_game.txt"\n\n"items_game"\n{\n' + body + "}\n"
    dst = os.path.join(STAGE, "scripts", "items", "custom_items_game.txt")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, "w", encoding="utf-8", newline="\n").write(text)

    report.append("\nstaged files: %d" % len(stager.copied))
    report.append("TF2C already ships (not staged, theirs used): %d" % len(stager.collisions))
    report += ["  " + c for c in stager.collisions[:60]]
    report.append("missing sources: %d" % len(stager.missing))
    report += ["  " + c for c in stager.missing[:60]]
    open(REPORT, "w", encoding="utf-8").write("\n".join(report) + "\n")
    print("\n".join(report[:len(ROSTER) * 2 + 8]))
    print("wrote", dst)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--af", help="April Fools custom_items_game.txt to merge (read-only)")
    a = ap.parse_args()
    build(a.af)
