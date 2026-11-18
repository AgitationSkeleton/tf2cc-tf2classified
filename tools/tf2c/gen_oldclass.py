"""Old TF2 Classic class weapons as schema items (called by gen_schema.py).

Ten weapons the classes had in old TF2 Classic (2.0.0 beta 2/4) or, for the Rescue Ranger and the
Overhealer's improved models, the TF2 Classic 2.2.3 (SDK 2013) server install. Unlike the Merc
items these are ordinary class weapons: used_by_classes, shown in the class's armory/loadout,
given to the class's bots like any stock item (no "hidden", no bots_cant_use), attach_to_hands 2
with the class's own arms (no custom hand viewmodel). A Mercenary picks them up like any other
class weapon (tf2cc_tf2c.sp stock pickups: the item itself on the Soldier host, the Merc arms from
his body item); none of them is in the Merc pool.

Assets: research/tf2c-oldclass/staging/tf2classified (tools/tf2c/oldclass_extract.py), all under
tf2cc paths (models/tf2cc/oldclass, materials/models/tf2cc/oldclass, sound/tf2cc/oldclass); the
Sten Guns reuse the old-Merc Sten models and sounds tf2cc already ships (models/tf2cc/oldmerc).
Sound scripts tf2cc.oldclass.* are appended to scripts/items/custom_level_sounds.txt.

Stats: the final old version (beta 4 items; beta 2 for the Scout's SMG script), expressed on the
TF2 Classified 5205 base weapon scripts (work/tf2c_research/base/scripts), which match the old
base scripts for these classes. The Rescue Ranger carries the live TF2 item 997 attributes (all
implemented natively by 5205's CTFShotgunBuildingRescue / repair bolt, see DEPLOY.md).
"""
import json
import os
import shutil

import kv

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(ROOT, "research", "tf2c-oldclass", "staging", "tf2classified")
DEPS = os.path.join(ROOT, "research", "tf2c-oldclass", "deps.json")
NAMES = os.path.join(ROOT, "research", "tf2c-oldclass", "script_names.json")
DONORS = os.path.join(ROOT, "research", "tf2c-oldclass", "oldclass_items.json")
SOUNDS = os.path.join(SRC, "scripts", "items", "oldclass_level_sounds.txt")
MP = "models/tf2cc/oldclass/"
S223_ICONS = r"<STEAMCMD>/sdk2013/tf2classic-2/tf2classic/materials/backpack/weapons/w_models/"
OMP = "models/tf2cc/oldmerc/"
FIRST_ID = 30300            # 30300-30319: tf2cc old class weapons (Merc items 30099-30299)

# Fields: id, name, item_name, type (item_type_name), desc, cls, slot, anim (anim_slot, default
#   the slot), classes, vm, wm, attrs [(attribute name in the 5205 schema, attribute_class, value)],
#   static {name: value}, sounds {type: script}, icon (old TF2C sprite; "<name>*" = 4 team sprites,
#   "<name>~" = red/blue sprites with green/yellow recoloured; or a literal image_inventory path
#   with "/"), extra {schema key: value}, log (item_logname/iconname).
ITEMS = [
    dict(id=30300, name="oldclass_rescueranger", item_name="The Rescue Ranger", type="#TF_Weapon_Shotgun",
         desc="The live TF2 Engineer shotgun as TF2 Classic's 2.2.3 server ported it (four-team art), "
              "with its live TF2 attributes.",
         cls="tf_weapon_shotgun_building_rescue", slot="primary", classes=["Engineer"],
         vm=MP + "v_rescueranger.mdl", wm=MP + "w_rescueranger.mdl",
         # live TF2 items_game 997 / prefab weapon_rescue_ranger, attribute for attribute
         attrs=[("engineer building teleporting pickup", "building_teleporting_pickup", 100),
                ("arrow heals buildings", "arrow_heals_buildings", 60),
                ("override projectile type", "override_projectile_type", 18),
                ("mark for death on building pickup", "mark_for_death_on_building_pickup", 1),
                ("maxammo primary reduced", "mult_maxammo_primary", 0.5),
                ("clip size penalty", "mult_clipsize", 0.66),
                ("repair health to metal ratio DISPLAY ONLY", "repair_health_to_metal_ratio_DISPLAY_ONLY", 4)],
         static={"min_viewmodel_offset": "10 0 -10", "custom projectile model": MP + "w_repair_claw.mdl"},
         sounds={"single_shot": "Weapon_RescueRanger.Single", "burst": "Weapon_RescueRanger.SingleCrit"},
         # batch 16: the stock backpack/workshop/.../c_tele_shotgun icon recoloured per team as its skin textures
         icon="team_rescueranger_skin*", log="rescue_ranger",
         # tf2cc_oldclass.smx: each bolt gets its team's model (the client drew the bolt red on every team)
         plugin={"projectile_" + t: MP + "w_repair_claw_%s.mdl" % t for t in ("red", "blue", "green", "yellow")},
         extra={"mouse_pressed_sound": "ui/item_heavy_gun_pickup.wav", "drop_sound": "ui/item_heavy_gun_drop.wav"}),
    # beta 4 item 9007 (tf_weapon_hunterrifle: 50 dmg, 1.5 s, clip 2, reload 1.5 s, unscoped, the
    # Sniper's primary ammo; item x1.2 dmg, x0.5 fire delay, headshot x0.666, no charge): 60 dmg,
    # 0.75 s, clip 2. Batch 16 (user 2026-11-17: reload and zoom broken; "the hunting rifle for
    # sniper has a clip and a scopeless zoom which is basically a different poacher so use that as
    # reference"): 5205's own Sniper primary with a clip, tf2c_weapon_hunting_revolver (stock item
    # 2003: 40 dmg, 0.6 s, clip 6, reload 1.5 s, reserve 24, alt-fire zoom to FOV 20 with no scope
    # overlay, TF_COND_AIMING; measured on the test server), takes the old hunter rifle's place:
    # x1.5 = 60 dmg, x1.25 = 0.75 s, clip 2, its own 1.5 s reload (= beta 4's), reserve 25,
    # headshots x0.666 (120), no falloff or ramp-up, no random crits. The zoom is the class's own
    # (the tf2cc_oldclass.smx zoom emulation is gone). Batch 17 (user: headshots only while zoomed,
    # as beta 4): no "can headshot"; the class's own rule then crits a head hit only while zoomed
    # (measured at 512 u: unzoomed head 60, zoomed head 120; with "can headshot" 1 every head hit
    # crit, 120; the stock item's "headshot is minicrit unscoped" would make unzoomed ones minicrits).
    dict(id=30301, name="oldclass_poacherspride", item_name="Poacher's Pride", type="#TF_Weapon_SniperRifle",
         desc="TF2 Classic 2.0.0 beta 4's Sniper rifle: two rounds, no scope, headshots.",
         cls="tf2c_weapon_hunting_revolver", slot="primary", classes=["Sniper"],
         vm=MP + "v_poacherspride_b4.mdl", wm=MP + "w_poacherspride_b4.mdl",
         attrs=[("damage bonus", "mult_dmg", 60 / 40.0),
                ("fire rate penalty", "mult_postfiredelay", 0.75 / 0.6), ("clip size penalty", "mult_clipsize", 2 / 6.0),
                ("hidden primary max ammo bonus", "mult_maxammo_primary", 25 / 24.0),
                ("headshot damage increase", "headshot_damage_modify", 0.666),
                ("no damage falloff over distance", "mod_no_dmg_falloff", 1),
                ("no damage increase over distance", "mod_no_dmg_rampup", 1),
                ("crit mod disabled hidden", "mult_crit_chance", 0)],
         sounds={"single_shot": "Weapon_HuntingRifle.Single", "burst": "Weapon_HuntingRifle.SingleCrit"},
         icon="bucket_hunterrifle", log="hunterrifle",
         extra={"mouse_pressed_sound": "ui/item_heavy_gun_pickup.wav", "drop_sound": "ui/item_heavy_gun_drop.wav"}),
    # beta 2-4 item 9011 Sten Gun (12 dmg, 0.1 s, clip 30, reserve 90 = SMG x1.5 / x1.2 / x1.2);
    # beta 2's Scout SMG script (tf_weapon_smg_scout.txt) and Sniper item 9003 "SMG (Scout)" put the
    # Sten in the Scout's and Sniper's hands: beta 4's v_stengun_merc / w_stengun and Weapon_Sten.*
    dict(id=30302, name="oldclass_sten_scout", item_name="Sten Gun", type="#TF_Weapon_SMG",
         desc="TF2 Classic 2.0.0 beta's Sten Gun, the Scout's.",
         cls="tf_weapon_smg", slot="secondary", classes=["Scout"],
         vm=MP + "v_stengun_b4.mdl", wm=MP + "w_stengun_b4.mdl",
         attrs=[("damage bonus", "mult_dmg", 1.5), ("clip size bonus", "mult_clipsize", 1.2),
                ("maxammo secondary increased", "mult_maxammo_secondary", 1.2)],
         sounds={"single_shot": "Weapon_Sten.Single", "burst": "Weapon_Sten.SingleCrit",
                 "reload": "Weapon_SMG.WorldReload", "empty": "Weapon_SMG.ClipEmpty"},
         icon="bucket_stengun", log="stengun",   # killicon: resource/svgs/deathnotice/stengun.svg (shipped)
         extra={"mouse_pressed_sound": "ui/item_light_gun_pickup.wav", "drop_sound": "ui/item_light_gun_drop.wav"}),
    dict(id=30303, name="oldclass_sten_sniper", item_name="Sten Gun", type="#TF_Weapon_SMG",
         desc="TF2 Classic 2.0.0 beta's Sten Gun, the Sniper's.",
         cls="tf_weapon_smg", slot="secondary", classes=["Sniper"],
         vm=MP + "v_stengun_b4.mdl", wm=MP + "w_stengun_b4.mdl",
         attrs=[("damage bonus", "mult_dmg", 1.5), ("clip size bonus", "mult_clipsize", 1.2),
                ("maxammo secondary increased", "mult_maxammo_secondary", 1.2)],
         sounds={"single_shot": "Weapon_Sten.Single", "burst": "Weapon_Sten.SingleCrit",
                 "reload": "Weapon_SMG.WorldReload", "empty": "Weapon_SMG.ClipEmpty"},
         icon="bucket_stengun", log="stengun",   # killicon: resource/svgs/deathnotice/stengun.svg (shipped)
         extra={"mouse_pressed_sound": "ui/item_light_gun_pickup.wav", "drop_sound": "ui/item_light_gun_drop.wav"}),
    # beta 2/4 v_shotgun_medic (unused by their schemas): the Medic's primary shotgun, stock stats
    dict(id=30304, name="oldclass_shotgun_medic", item_name="Medic's Shotgun", type="#TF_Weapon_Shotgun",
         desc="The Medic's shotgun from TF2 Classic 2.0.0 beta 4's files.",
         cls="tf_weapon_shotgun_primary", slot="primary", classes=["Medic"],
         vm=MP + "v_shotgun_medic_b4.mdl", wm="models/weapons/w_models/w_shotgun.mdl", attrs=[],
         sounds={"single_shot": "Weapon_Shotgun.Single", "burst": "Weapon_Shotgun.SingleCrit",
                 "reload": "Weapon_Shotgun.WorldReload", "special1": "Weapon_Shotgun.Pump", "empty": "Weapon_Shotgun.Empty"},
         icon="bucket_shotgun", log="shotgun_primary",
         extra={"mouse_pressed_sound": "ui/item_heavy_gun_pickup.wav", "drop_sound": "ui/item_heavy_gun_drop.wav"}),
    # beta 2 tf_weapon_smg_scout (8 dmg, 0.1 s, clip 25, spread 0.010 = SMG spread x0.5), beta 4 SMG models
    dict(id=30305, name="oldclass_smg_scout", item_name="Scout's SMG", type="#TF_Weapon_SMG",
         desc="The Scout's secondary SMG from TF2 Classic 2.0.0 beta 2.",
         cls="tf_weapon_smg", slot="secondary", classes=["Scout"],
         vm=MP + "v_smg_b4.mdl", wm=MP + "w_smg_b4.mdl",
         attrs=[("weapon spread bonus", "mult_spread_scale", 0.5)],
         sounds={"single_shot": "Weapon_SMG.Single", "burst": "Weapon_SMG.SingleCrit",
                 "reload": "Weapon_SMG.WorldReload", "empty": "Weapon_SMG.ClipEmpty"},
         icon="bucket_smg", log="smg",
         extra={"mouse_pressed_sound": "ui/item_light_gun_pickup.wav", "drop_sound": "ui/item_light_gun_drop.wav"}),
    # beta 4 item 9005 The Cyclops: grenade launcher, blast radius x2.5, clip x0.25
    dict(id=30306, name="oldclass_cyclops_b4", item_name="Beta Cyclops", type="#TF_Weapon_GrenadeLauncher",
         desc="The Cyclops as TF2 Classic 2.0.0 beta 4 had it: one huge grenade at a time.",
         cls="tf_weapon_grenadelauncher", slot="primary", anim="secondary", classes=["Demoman"],
         vm=MP + "v_cyclops_b4.mdl", wm=MP + "w_cyclops_b4.mdl",
         attrs=[("Blast radius increased", "mult_explosion_radius", 2.5), ("clip size penalty", "mult_clipsize", 0.25)],
         sounds={"single_shot": "Weapon_Cyclops.Single", "burst": "Weapon_Cyclops.SingleCrit",
                 "reload": "Weapon_Cyclops.WorldReload"},
         icon="bucket_cyclops_b4v2", log="cyclops",     # posed to the stock grenade launcher (render_fit_icons.py)
         extra={"mouse_pressed_sound": "ui/item_heavy_gun_pickup.wav", "drop_sound": "ui/item_heavy_gun_drop.wav"}),
    # beta 4 item 9004 RPG: reload x0.75, clip x0.25, fire delay x0.75, spawn reserve 10 (5205 has no
    # mod_spawn_ammo_override: tf2cc_tf2c sets the reserve at spawn, see oldclass "spawn_ammo")
    dict(id=30307, name="oldclass_rpg_b4", item_name="Beta R.P.G.", type="#TF_Weapon_RocketLauncher",
         desc="The R.P.G. as TF2 Classic 2.0.0 beta 4 had it.",
         cls="tf_weapon_rocketlauncher", slot="primary", classes=["Soldier"],
         vm=MP + "v_rpg_b4.mdl", wm=MP + "w_rpg_b4.mdl",
         attrs=[("Reload time decreased", "mult_reload_time", 0.75), ("clip size penalty", "mult_clipsize", 0.25),
                ("fire rate bonus HIDDEN", "mult_postfiredelay", 0.75)],
         sounds={"single_shot": "Weapon_BetaRPG.Single", "burst": "Weapon_BetaRPG.SingleCrit",
                 "reload": "Weapon_BetaRPG.WorldReload"},
         icon="bucket_rpg", log="rpg", spawn_ammo=10,
         extra={"mouse_pressed_sound": "ui/item_heavy_gun_pickup.wav", "drop_sound": "ui/item_heavy_gun_drop.wav"}),
    # beta 4 item 9006 The Overhealer (heal rate x3.25, no UberCharge) with TF2 Classic 2.2.3's
    # improved four-team models; the stock Medi Gun's backpack wearable
    dict(id=30308, name="oldclass_overhealer", item_name="The Overhealer", type="#TF_Weapon_Medigun",
         desc="TF2 Classic 2.0.0 beta 4's Medi Gun: heals far faster, builds no UberCharge.",
         cls="tf_weapon_medigun", slot="secondary", classes=["Medic"],
         vm=MP + "v_overhealer.mdl", wm=MP + "w_overhealer.mdl",
         attrs=[("heal rate bonus", "mult_medigun_healrate", 3.25), ("ubercharge rate penalty", "mult_medigun_uberchargerate", 0)],
         static={"min_viewmodel_offset": "10 0 -9"},
         icon="team_overhealer_skin*", log="overhealer", iconname="",   # batch 16: 2.2.3's w_overhealer_large recoloured per team as its skin textures; no killicon (a medigun never kills; the stock Medi Gun has no item_iconname)
         extra={"extra_wearable": "models/player/items/medic_backpack.mdl", "equip_region": "medigun_backpack",
                "mouse_pressed_sound": "ui/item_medigun_pickup.wav", "drop_sound": "ui/item_heavy_gun_drop.wav"}),
    # beta 4 item 37 "The Ubersaw" (the Uberspritze's first form): uber on hit 25 %, 20 % slower swing
    # beta 2-4 item 37 "#TF_Unique_Achievement_Bonesaw1" = "Ubersaw" in their localization (the
    # Uberspritze's first form). Its v_/w_ models (identical in beta 2 and 4; the beta 3 patch has
    # none) render like 5205's v_/w_syringe; they are still the beta files, under tf2cc paths.
    dict(id=30309, name="oldclass_uberspritze_b4", item_name="Ubersaw", type="#TF_Weapon_Bonesaw",
         desc="The Uberspritze as TF2 Classic 2.0.0 beta 4 had it.",
         cls="tf_weapon_bonesaw", slot="melee", classes=["Medic"],
         vm=MP + "v_uberspritze_b4.mdl", wm=MP + "w_uberspritze_b4.mdl",
         attrs=[("add uber charge on hit", "add_onhit_ubercharge", 0.25), ("fire rate penalty", "mult_postfiredelay", 1.2),
                ("lunchbox adds minicrits", "set_weapon_mode", 1), ("special taunt", "special_taunt", 1)],
         icon="bucket_syringe*", log="ubersaw",
         extra={"mouse_pressed_sound": "ui/item_knife_small_pickup.wav", "drop_sound": "ui/item_metal_weapon_drop.wav"}),
    # The Makeshift Mutilator, as the user's TF2 Classic 2.2.3 server defines it (maps/
    # custom_items_game.txt 9035, prefab weapon_flamethrower; v_chemthrower_pyro / w_chemthrower,
    # four team families). Same values; one display fix: its 0.5 max-ammo multiplier sat on
    # "maxammo primary increased" (shown as a positive "-50% increased"), now "maxammo primary
    # reduced".
    dict(id=30310, name="oldclass_makeshiftmutilator", item_name="Makeshift Mutilator", type="#TF_Weapon_FlameThrower",
         desc="", cls="tf_weapon_flamethrower", slot="primary", classes=["Pyro"],
         vm=MP + "v_makeshiftmutilator.mdl", wm=MP + "w_makeshiftmutilator.mdl",
         attrs=[("damage bonus", "mult_dmg", 1.25), ("fire rate bonus", "mult_postfiredelay", 0.5),
                ("airblast disabled", "airblast_disabled", 1), ("flame_spread_degree", "flame_spread_degree", -0.5),
                ("maxammo primary reduced", "mult_maxammo_primary", 0.5)],
         # Batch 16 (user 2026-11-17: "does no damage"): 5205's flames take their speed, life and
         # spread from the item (stock flamethrower 21's static attributes); without them the
         # Mutilator's flames died at the nozzle (measured on the test server: 0 damage at 100 u,
         # a kill at 60 u; the stock flamethrower with the Mutilator's five attributes killed at
         # 100 u). The stock values, all additive: the spread is 2.8 - 0.5 = 2.3 degrees.
         static={"min_viewmodel_offset": "10 0 -10", "flame_gravity": "0", "flame_drag": "8.5",
                 "flame_up_speed": "50", "flame_speed": "2450", "flame_spread_degree": "2.8",
                 "flame_lifetime": "0.6", "flame_random_life_time_offset": "0.1",
                 "flame_velocity_fade_start": "0.3", "flame_velocity_fade_end": "0.5"},
         icon="team_makeshiftmutilator_skin*", log="makeshiftmutilator", iconname="flamethrower",   # batch 16: 2.2.3's w_chemthrower_large recoloured per team as its skin textures; 5205 has no makeshiftmutilator killicon
         extra={"mouse_pressed_sound": "ui/item_heavy_gun_pickup.wav", "drop_sound": "ui/item_heavy_gun_drop.wav"}),
]
BUCKET = {"primary": 0, "secondary": 1, "melee": 2}
# oldclass-staged models other generators use: the Merc's beta 4 Super Shotgun (gen_oldmerc.py 30203)
OTHER_MODELS = [MP + "v_supershotgun_beta4.mdl", MP + "w_supershotgun_beta4.mdl"] +     [MP + "w_repair_claw_%s.mdl" % t for t in ("red", "blue", "green", "yellow")]   # tf2cc_oldclass.smx
# min_viewmodel_offset where the item's class is not the weapon it stands for (else the stock 5205
# item of the same class): the TF2 Classic 2.2.3 port's own values / the matching stock weapon.
MIN_VM = {"oldclass_poacherspride": "10 0 -9",      # TF2 Classic 2.2.3 port (stock sniper rifle "10 0 -10")
          "oldclass_shotgun_medic": "10 0 -9",      # stock shotgun prefab
          "oldclass_cyclops_b4": "10 0 -10",        # stock Cyclops 2021 / 2.2.3 port
          "oldclass_rpg_b4": "10 -3 -10",           # stock R.P.G. 2002
          "oldclass_uberspritze_b4": "10 0 -12"}    # stock Uberspritze 33


def stage_files(stage):
    """Copy every staged asset the items use; returns the copied paths."""
    deps = json.load(open(DEPS))
    want = set()
    for m in [x for it in ITEMS for x in [it["vm"], it["wm"]] + list((it.get("static") or {}).values())] + OTHER_MODELS:
        if m.startswith(MP):
            want |= set(deps.get(m, []))
    for k, v in deps.items():
        if k.startswith("tf2cc.oldclass."):
            want |= set(v)
    out = []
    for rel in sorted(want):
        if rel.endswith("oldclass_level_sounds.txt"):
            continue
        src = os.path.join(SRC, rel)
        if not os.path.exists(src):
            raise SystemExit("oldclass asset missing: " + rel)
        dst = os.path.join(stage, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        out.append(rel)
    # 5205's repair bolt names effects/repair_claw_trail_blu/_grn/_ylw.vmt, which no game ships
    # (TF2 has _red/_blue, TF2C _green/_yellow): copies of those under the names it uses.
    for rel in TRAILS:
        dst = os.path.join(stage, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "w", encoding="latin-1", newline="\n") as f:
            f.write(TRAILS[rel])
        out.append(rel)
    return out


TRAILS = {
    # TF2 tf2_misc_dir.vpk materials/effects/repair_claw_trail_blue.vmt; TF2C 5205
    # repair_claw_trail_green/_yellow.vmt (UnlitGeneric over effects/repair_claw_trail)
    "materials/effects/repair_claw_trail_blu.vmt": None,
    "materials/effects/repair_claw_trail_grn.vmt": None,
    "materials/effects/repair_claw_trail_ylw.vmt": None,
}


def load_trails(stock_text):
    """stock_text(rel) -> text of a stock file; fills TRAILS from the shipped team materials."""
    for new, old in (("blu", "blue"), ("grn", "green"), ("ylw", "yellow")):
        t = stock_text("materials/effects/repair_claw_trail_%s.vmt" % old)
        if not t:
            raise SystemExit("stock repair_claw_trail_%s.vmt not found" % old)
        TRAILS["materials/effects/repair_claw_trail_%s.vmt" % new] = t


def sound_names():
    return json.load(open(NAMES))


def sound_text():
    lines = []
    for line in open(SOUNDS, encoding="latin-1").read().splitlines():
        if line.strip().startswith("//"):
            continue
        lines.append(line)
    return "\n// tf2cc: old TF2 Classic class weapon sounds (research/tf2c-oldclass, gen_oldclass.py)\n" + "\n".join(lines).strip() + "\n"


def build(items, attr_names, report, old_icon, team_icon, min_vm=None, square_icon=None):
    """Add the old class items to `items`. attr_names: lower-case attribute names of the 5205 schema.
    old_icon(name, team) / team_icon(name) stage old TF2C sprites. Returns weapons.cfg rows."""
    names = sound_names()
    rows, donors = [], []
    for it in ITEMS:
        e = kv.KV()
        e.add("name", "tf2cc_" + it["name"])
        e.add("item_name", it["item_name"])
        e.add("item_type_name", it["type"])
        # no item_description: the old builds' items had none of their own (only invented text
        # would fill it); propername 0: the game prefixes "The " to propername items, and the names
        # that have it ("The Rescue Ranger", "The Overhealer") already carry it
        e.add("item_quality", "unique")
        e.add("propername", "0")
        e.add("item_class", it["cls"])
        e.add("item_slot", it["slot"])
        e.add("anim_slot", it.get("anim", it["slot"]))
        e.add("bucket", str(it.get("bucket", BUCKET[it["slot"]])))
        e.add("show_in_armory", "1")
        ubc = kv.KV()
        for c in it["classes"]:
            ubc.add(c, "1")
        e.add("used_by_classes", ubc)
        e.add("model_player", it["vm"])
        if it.get("wm"):
            e.add("model_world", it["wm"])
        e.add("attach_to_hands", "2")
        attrs = kv.KV()
        for nm, cls, val in it["attrs"]:
            if nm.lower() not in attr_names:
                raise SystemExit("%s: attribute %r is not in the 5205 schema" % (it["name"], nm))
            a = kv.KV()
            a.add("attribute_class", cls)
            a.add("value", "%g" % round(val, 4))
            attrs.add(nm, a)
        if attrs.pairs:
            e.add("attributes", attrs)
        st = kv.KV()
        for k, v in (it.get("static") or {}).items():
            st.add(k, v)
        if st.get("min_viewmodel_offset") is None:
            mvo = MIN_VM.get(it["name"]) or (min_vm or {}).get(it["cls"].lower())
            if mvo:
                st.add("min_viewmodel_offset", mvo)
        if st.pairs:
            e.add("static_attrs", st)
        if it.get("sounds"):
            vis = kv.KV()
            for t, s in it["sounds"].items():
                vis.add("sound_" + t, names.get(s, s))
            e.add("visuals", vis)
        icon = it["icon"]
        if icon.startswith("square:"):         # a square backpack icon file (its own art)
            e.add("image_inventory", square_icon(it["name"].replace("oldclass_", "icon_"), icon[7:]))
        elif "/" in icon:
            e.add("image_inventory", icon)
        elif icon.endswith("~"):
            e.add("image_inventory", team_icon(icon[:-1]))
            e.add("image_inventory_teamcolor", "1")
        else:
            inv, team = old_icon(icon.rstrip("*"), icon.endswith("*"))
            e.add("image_inventory", inv)
            if team:
                e.add("image_inventory_teamcolor", "1")
        e.add("item_logname", it["log"])
        icn = it.get("iconname", it["log"])     # the killfeed icon (scripts/mod_textures*.txt d_<name>)
        if icn:
            e.add("item_iconname", icn)
        for k, v in (it.get("extra") or {}).items():
            e.add(k, v)
        items.add(str(it["id"]), e)
        donors.append(dict(id=it["id"], name="tf2cc_" + it["name"], item_name=it["item_name"], item_class=it["cls"],
                           slot=it["slot"], classes=it["classes"], model_player=it["vm"], model_world=it.get("wm") or "",
                           projectile_model=(it.get("static") or {}).get("custom projectile model", ""),
                           source=it["vm"].split("/")[-1], kv=_kv_json(e)))
        rows.append(dict(wid=it["name"], defindex=str(it["id"]), slot=it["slot"], kind="oldclass", weight="0",
                         world=it.get("wm") or "", pref="", canonical="", spawn_ammo=str(it.get("spawn_ammo", "")),
                         cfg=dict(it.get("plugin") or {})))
        report.append("%-26s %-6d %-34s oldclass %s %s" % (it["name"], it["id"], it["cls"], "/".join(it["classes"]), it["slot"]))
    with open(DONORS, "w", encoding="utf-8", newline="\n") as f:
        json.dump(dict(note="tf2cc old TF2 Classic class weapons (gen_oldclass.py): schema items 30300+ as "
                            "built (unversioned asset paths under research/tf2c-oldclass/staging and "
                            "research/tf2c-oldmerc/staging), for CustomSlop's donor roster",
                       items=donors), f, indent=1)
        f.write("\n")
    return rows


def _kv_json(e):
    """KV -> nested [key, value] lists (order and duplicate keys kept)."""
    return [[k, _kv_json(v) if isinstance(v, kv.KV) else v] for k, v in e.pairs]
