"""Old TF2 Classic Mercenary weapons as tf2cc schema items (called by gen_schema.py).

Assets come from research/tf2c-oldmerc/staging/tf2classified (tools/tf2c/oldmerc_extract.py,
then tools/tf2c/oldmerc_chainsaw.py for the chainsaw's view and world models); every path is
tf2cc-owned (models/tf2cc/oldmerc, materials/models/tf2cc/oldmerc, sound/tf2cc/oldmerc). Sound
scripts tf2cc.oldmerc.* are appended to scripts/items/custom_level_sounds.txt.

Every item is its own schema item (own defindex, models, animations, sounds, attributes); the
plugin never swaps models at runtime. Kinds (weapons.cfg "oldmerc"):

* default: the old spawn weapons (regular 4rdm pistol, presplit crowbar). They replace the OF
  P38 / crowbar per tf2cc_oldmerc_pistol / tf2cc_oldmerc_crowbar and !mercprefs; never dropped,
  never in a pool (pack_weight 0, "default" 1, "pref" names the preference group).
* new: weapons OF never had (Six-Shooter, Frag Grenade, Heavy Artillery, Sten Gun). Always in
  the merged pool (ammo-box grants, pickups, Merc bots).
* variant: other models/animations of a weapon tf2cc already has, or 4rdm Merc-animated copies
  of stock TF2C weapons (stock class, stats and attributes). In the pool while
  tf2cc_oldmerc_variants is 1 (default).

Stats are relative to the TF2C 5205 base weapon script (work/tf2c_research/base/scripts).
"""
import copy
import json
import os
import shutil

import kv

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(ROOT, "research", "tf2c-oldmerc", "staging", "tf2classified")
DEPS = os.path.join(ROOT, "research", "tf2c-oldmerc", "deps.json")
SOUNDS = os.path.join(SRC, "scripts", "items", "oldmerc_level_sounds.txt")
MP = "models/tf2cc/oldmerc/"
ARMS = "models/weapons/c_models/c_merc_arms.mdl"
FIRST_ID = 30200

# Fields: id, name, kind, item_name, item_class, slot, bucket, anim set (merc_acts.json),
#   v_model, w_model, attributes [(class, value)], string attrs {}, sounds {type: script},
#   extra: variant_of (copy that roster item: attributes, sounds, icon, then override),
#          stock (copy that stock TF2C item: class, attributes, sounds, icon), pref, weight,
#          old_icon (the old TF2C bucket sprite of that weapon, sprites/<name>; "<name>*" = its
#          four team sprites <name>_red/_blue/_green/_yellow). Items without one keep the icon of
#          icon_of / variant_of / stock: the classic chainsaw (old script: the crowbar's sprites),
#          the b4 Tommy Gun (heavy artillery class: bucket_minigun) and the Frag Grenade (grenade
#          launcher: bucket_grenlaunch) had no icon of their own in the old builds.
ITEMS = [
    # --- defaults (old spawn weapons) ---
    dict(id=30200, name="merc_pistol_4rdm", kind="default", pref="pistol", item_name="Pistol (Classic)",
         cls="tf_weapon_pistol", slot="secondary", bucket=1, anim="pistol",
         vm=MP + "v_pistol_4rdm.mdl", wm="models/weapons/w_models/w_pistol.mdl",
         # TF2C stock pistol (15 dmg, 0.15 s, clip 12); reserve 90 like the OF P38
         attrs=[("mult_maxammo_secondary", 0.5)],
         sounds={"single_shot": "Weapon_Pistol.Single", "burst": "Weapon_Pistol.SingleCrit",
                 "reload": "Weapon_Pistol.WorldReload", "empty": "Weapon_Pistol.ClipEmpty"},
         icon_of="merc_pistol", old_icon="bucket_pistol"),
    dict(id=30202, name="merc_crowbar_4rdm", kind="default", pref="crowbar", item_name="Crowbar (Classic)",
         variant_of="merc_crowbar", vm=MP + "v_crowbar_4rdm.mdl", wm=MP + "w_crowbar_4rdm.mdl", old_icon="bucket_crowbar*",
         sounds={"melee_miss": "tf2cc.oldmerc.Weapon_Crowbar.Miss", "burst": "tf2cc.oldmerc.Weapon_Crowbar.MissCrit",
                 "melee_hit": "tf2cc.oldmerc.Weapon_Crowbar.HitFlesh", "melee_hit_world": "tf2cc.oldmerc.Weapon_Crowbar.HitWorld"}),
    # --- variants of roster weapons ---
    dict(id=30201, name="merc_shotgun_4rdm", kind="variant", item_name="Shotgun (Presplit)", weight=3,
         variant_of="merc_shotgun", vm=MP + "v_shotgun_4rdm.mdl", wm="models/weapons/w_models/w_shotgun.mdl",
         old_icon="bucket_shotgun"),
    # TF2 Classic 2.0.0 beta 4's own Super Shotgun (item 9012 "#TF_Weapon_DoubleBarrel" = "Super
    # Shotgun"; v_/w_supershotgun_mercenary, sprites/bucket_supershotgun, Weapon_SuperShotgun.*),
    # with beta 4's stats on its base (tf_weapon_shotgun_primary): 20 pellets, 0.375 s, reload x0.8,
    # spread x2, clip 1, reserve 16 (beta 4: x0.5 of 32; 5205's base is 30). Beta 4's clip x0.2 +
    # "scattergun no reload single" on 5205's shotgun drained the reserve in a reload loop without
    # ever filling the clip (measured; the weapon then could not be selected): the clip is the
    # same 1 through mod_max_primary_clip_override, with the shotgun's own one-shell reload.
    # Beta 4's "spawn ammo override" 8 does not apply to a pickup. The 4dm/4rdm map copy of the
    # model stays with the Merc Twin Barrel (30223).
    dict(id=30203, name="merc_supershotgun_b4", kind="variant", item_name="Super Shotgun", weight=3,
         cls="tf_weapon_shotgun_primary", slot="primary", bucket=0, anim="ssg", icon_of="merc_supershotgun",
         vm="models/tf2cc/oldclass/v_supershotgun_beta4.mdl", wm="models/tf2cc/oldclass/w_supershotgun_beta4.mdl",
         old_icon="bucket_supershotgun",
         attrs=[("mult_bullets_per_shot", 2.0, "bullets per shot bonus"), ("mult_postfiredelay", 0.6, "fire rate bonus"),
                ("mult_reload_time", 0.8, "Reload time decreased"), ("mult_spread_scale", 2.0, "spread penalty"),
                ("mod_max_primary_clip_override", 1, "mod max primary clip override"),
                ("mult_maxammo_primary", 16 / 30.0, "maxammo primary reduced"),
                # beta 4's own "scattergun no reload single": one ACT_VM_RELOAD (reload_loop) and back
                # to idle; the shotgun's start/loop/end chain stuttered into reload_end (user 2026-11-16)
                ("set_scattergun_no_reload_single", 1, "scattergun no reload single")],
         sounds={"single_shot": "tf2cc.oldclass.Weapon_SuperShotgun.Single",
                 "burst": "tf2cc.oldclass.Weapon_SuperShotgun.SingleCrit",
                 "reload": "tf2cc.oldclass.Weapon_SuperShotgun.WorldReload",
                 "empty": "Weapon_Shotgun.Empty"}),
    # Classic chainsaw: a plain melee (beta 4 tf_weapon_chainsaw: 45 dmg every 1.0 s) on the
    # shovel (65 / 0.8 s), not a skin of the OF chainsaw (no rev/charge special).
    dict(id=30204, name="merc_chainsaw_b4", kind="variant", item_name="Chainsaw (Classic)", weight=2,
         cls="tf_weapon_shovel", slot="melee", bucket=2, anim="chainsaw", icon_of="merc_chainsaw",
         old_icon="bucket_chainsaw_b4v2",   # v2 render posed to OF's chainsaw (render_fit_icons.py)
         vm=MP + "v_chainsaw_b4.mdl", wm=MP + "w_chainsaw_b4.mdl",
         attrs=[("mult_dmg", 45 / 65.0), ("mult_postfiredelay", 1.0 / 0.8)],
         sounds={"melee_hit": "tf2cc.oldmerc.Weapon_Chainsaw.HitFlesh",
                 "melee_hit_world": "tf2cc.oldmerc.Weapon_Chainsaw.HitWorld"}),
    dict(id=30205, name="merc_tommygun_b4", kind="variant", item_name="Tommy Gun (Beta 4)", weight=3,
         variant_of="merc_tommygun", vm=MP + "v_tommygun_b4.mdl", wm=MP + "w_tommygun_b4.mdl",
         sounds={"reload": "tf2cc.oldmerc.Weapon_TommyGun.WorldReload"}),
    dict(id=30207, name="merc_fists_b4", kind="variant", item_name="Hammerfists", weight=2,
         variant_of="merc_fists", vm=MP + "v_hammerfists_b4.mdl", wm="", old_icon="bucket_fists"),
    dict(id=30208, name="merc_nailgun_b4", kind="variant", item_name="Nailgun (Beta 4)", weight=3,
         variant_of="merc_nailgun", vm=MP + "v_nailgun_b4.mdl", wm="models/weapons/w_models/w_nailgun.mdl",
         old_icon="bucket_nailgun"),
    # --- new weapons ---
    dict(id=30210, name="merc_sixshooter", kind="new", item_name="Six-Shooter", weight=4,
         cls="tf_weapon_revolver", slot="secondary", bucket=1, anim="revolver", icon_of="merc_revolver",
         old_icon="bucket_snubnose_b4", vm=MP + "v_snubnose_b4.mdl", wm=MP + "w_snubnose_b4.mdl",
         # beta 2-4 item 9013: 45 dmg, 0.5 s, clip 6, reserve 24 (revolver script: 40 / 0.5 / 6 / 24)
         attrs=[("mult_dmg", 1.125)],
         sounds={"single_shot": "tf2cc.oldmerc.Weapon_SixShooter.Single", "burst": "tf2cc.oldmerc.Weapon_SixShooter.SingleCrit",
                 "reload": "Weapon_Revolver.WorldReload", "empty": "Weapon_Revolver.ClipEmpty"}),
    dict(id=30211, name="merc_frag", kind="new", item_name="Frag Grenade", weight=3,
         cls="tf_weapon_grenadelauncher", slot="secondary", bucket=1, anim="dynamite", icon_of="merc_dynamite",
         old_icon="team_frag_b4*", vm=MP + "v_frag_b4.mdl", wm=MP + "w_frag_b4.mdl",   # icon: upright team-skin renders
         # beta 4 item 9015: one pipe grenade per throw, fired from the reserve like merc_dynamite
         # (no reload animation exists): 1.2 s between throws. No max-ammo multiplier: TF2C
         # applies mult_maxammo_* player-wide per ammo type (grenade launchers use primary ammo),
         # so beta 4's 3 grenades would also cap Heavy Artillery / rocket reserves.
         attrs=[("mod_max_primary_clip_override", -1), ("mult_postfiredelay", 2.0)],
         strattrs={"custom projectile model": MP + "w_frag_b4.mdl"},
         sounds={"single_shot": "tf2cc.oldmerc.Weapon_Grenade_Normal.Single", "burst": "tf2cc.oldmerc.Weapon_Grenade_Normal.Single"}),
    # beta 2/3 tf_weapon_heavyartillery: 9 dmg x 2 bullets every 0.075 s, no clip, reserve 100;
    # minigun base (9 dmg x 4 / 0.1 s, reserve 200) spun up like the OF gatling.
    dict(id=30212, name="merc_heavyartillery", kind="new", item_name="Heavy Artillery", weight=2,
         cls="tf_weapon_minigun", slot="primary", bucket=0, anim="chaingun", icon_of="merc_gatling",
         old_icon="bucket_heavyartillery_b2", vm=MP + "v_heavyartillery_b2.mdl", wm=MP + "w_heavyartillery_b2.mdl",
         attrs=[("mult_bullets_per_shot", 0.5), ("mult_postfiredelay", 0.75), ("mult_spread_scale", 0.25),
                ("mult_maxammo_primary", 0.5)],
         sounds={"single_shot": "tf2cc.oldmerc.Weapon_HeavyArtillery.Single", "burst": "tf2cc.oldmerc.Weapon_HeavyArtillery.SingleCrit"}),
    # beta 2-4 item 9011 (tf_weapon_smg_primary): 12 dmg, 0.1 s, clip 30, reserve 90
    dict(id=30213, name="merc_stengun", kind="new", item_name="Sten Gun", weight=3,
         # tf_weapon_shotgun_primary (a primary weapon class: on tf_weapon_smg the client could not switch
         # from it to the secondary); the same numbers relative to its script (6 dmg x10, 0.625 s,
         # spread 0.0675, clip 6, reload 0.5, 30 primary ammo): 12 dmg x1, 0.1 s, 0.02, clip 30, 1.23 s, 90
         cls="tf_weapon_shotgun_primary", slot="primary", bucket=0, anim="combat_smg", icon_of="merc_smg",
         # beta 4 item 9011's world model, stats and sounds; the viewmodel stays the 4rdm one (user 2026-11-16)
         old_icon="bucket_stengun", vm=MP + "v_stengun_4rdm.mdl", wm="models/tf2cc/oldclass/w_stengun_b4.mdl",
         attrs=[("mult_dmg", 12 / 6.0), ("mult_bullets_per_shot", 0.1), ("mult_postfiredelay", 0.1 / 0.625),
                ("mult_spread_scale", 0.02 / 0.0675), ("mult_clipsize", 30 / 6.0), ("mult_reload_time", 1.23 / 0.5),
                ("mult_maxammo_primary", 90 / 30.0),
                ("set_scattergun_no_reload_single", 1, "scattergun no reload single")],
         sounds={"single_shot": "tf2cc.oldclass.Weapon_Sten.Single", "burst": "tf2cc.oldclass.Weapon_Sten.SingleCrit",
                 "reload": "Weapon_SMG.WorldReload", "empty": "Weapon_SMG.ClipEmpty"}),
    # --- 4rdm Merc copies of stock weapons (stock class, stats, attributes and sounds) ---
    dict(id=30220, name="merc_flaregun_4rdm", kind="variant", item_name="Merc Flare Gun", weight=3,
         stock="35", slot="secondary", bucket=1, anim="pistol", vm=MP + "v_flaregun_4rdm.mdl"),
    # Coffee Pot (beta 4 item 9018, tf_weapon_bottle; the models are byte-identical to beta 4's
    # v_coffepot_merc / w_coffepot): the Demoman's bottle reskinned (stock 1: class, stats, sounds),
    # only as a rare ammo-pack drop: pack_rare 0.01 = 1 pack roll in 100 (user 2026-11-16)
    dict(id=30226, name="merc_coffeepot_4rdm", kind="variant", item_name="Coffee Pot", weight=0, pack_rare=0.01,
         stock="1", slot="melee", bucket=2, anim="crowbar", vm=MP + "v_coffeepot_4rdm.mdl", wm=MP + "w_coffeepot_4rdm.mdl",
         old_icon="bucket_coffeepot_b4v2"),
]
GROUP = {"primary": "PRIMARY", "secondary": "SECONDARY", "melee": "MELEE"}
# Staged viewmodels whose vertices of one bone follow another (vm_rebind.py): (model, from, to)
REBIND = [("models/tf2cc/oldmerc/v_snubnose_b4", "vm_weapon_bone_2", "vm_weapon_bone_1")]
# Files of the original chainsaw viewmodel no longer used (its baked hands/sleeves were removed).
UNUSED = ("materials/models/tf2cc/oldmerc/models/player/merc_deathmatch/",)


def stage_files(stage):
    """Copy every staged old-Merc asset the items use; returns the copied paths."""
    deps = json.load(open(DEPS))
    want = set()
    used = set()
    for it in ITEMS:
        for k in ("vm", "wm"):
            if it.get(k, "").startswith(MP):
                used.add(it[k])
        for v in (it.get("strattrs") or {}).values():
            if v.startswith(MP):
                used.add(v)
    for m in used:
        want |= set(deps.get(m, []))
        base = m[:-4]
        for ext in (".mdl", ".vvd", ".dx90.vtx", ".dx80.vtx", ".sw.vtx", ".phy"):
            if os.path.exists(os.path.join(SRC, base + ext)):
                want.add(base + ext)
    for k, v in deps.items():
        if k.startswith("tf2cc.oldmerc."):
            want |= set(v)
    out = []
    for rel in sorted(want):
        if rel.startswith(UNUSED) or rel.endswith("oldmerc_level_sounds.txt"):
            continue
        src = os.path.join(SRC, rel)
        if not os.path.exists(src):
            raise SystemExit("oldmerc asset missing: " + rel)
        dst = os.path.join(stage, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        out.append(rel)
    # Six-Shooter snubnose (30210): its loose reload rounds (vm_weapon_bone_2, 446 vertices; measured on
    # the server: 30-38 u from weapon_bone through the reload, the cylinder bones 1/3 stay at 1.7/6.5)
    # sat in the player's face with tf_use_min_viewmodels (user 2026-11-17). They now follow the
    # cylinder bone (vm_weapon_bone_1); in the bind pose they already sit in the cylinder.
    for base, frm, to in REBIND:
        mdl = os.path.join(stage, base + ".mdl")
        if os.path.exists(mdl):
            import vm_rebind
            vm_rebind.rebind(mdl[:-4], frm, to)
    return out


def sound_text():
    """The tf2cc.oldmerc.* scripts (comments dropped: the plugin precaches '"tf2cc.<name>"' lines)."""
    lines = []
    for line in open(SOUNDS, encoding="latin-1").read().splitlines():
        s = line.strip()
        if s.startswith("//"):
            continue
        if s.startswith('"tf2cc.') and "//" in s:
            line = line[:line.index("//")].rstrip()
        lines.append(line)
    return "\n// tf2cc: old TF2 Classic Merc weapon sounds (research/tf2c-oldmerc, gen_oldmerc.py)\n" + "\n".join(lines).strip() + "\n"


def _attr(attrs, by_class, attr_name, cls, val):
    nm = attr_name(by_class, cls, val)
    if not nm:
        raise SystemExit("no attribute for %s" % cls)
    a = kv.KV()
    a.add("attribute_class", cls)
    a.add("value", "%g" % round(val, 4))
    attrs.set(nm, a)


def build(items, by_class, attr_name, acts, base_items, report, old_icon=None, min_vm=None):
    """Add the old-Merc items to `items` (KV of the schema's items). Returns weapons.cfg rows.
    old_icon(name, team) stages an old TF2C bucket sprite, returns (image_inventory, teamcolor)."""
    by_name = {v.get("name"): (k, v) for k, v in items.items() if isinstance(v, kv.KV)}
    rows = []
    for it in ITEMS:
        if it.get("variant_of"):
            src_id, src = by_name["tf2cc_" + it["variant_of"]]
            e = copy.deepcopy(src)
            cls, slot, bucket = e.get("item_class"), e.get("item_slot"), int(e.get("bucket"))
            anim_group = e.get("anim_slot")
        elif it.get("stock"):
            stock = base_items[it["stock"]]
            e = kv.KV()
            cls, slot, bucket = stock.get("item_class"), it["slot"], it["bucket"]
            anim_group = GROUP[slot]
        else:
            e = kv.KV()
            cls, slot, bucket = it["cls"], it["slot"], it["bucket"]
            anim_group = GROUP[slot]
        e.set("name", "tf2cc_" + it["name"])
        e.set("item_name", it["item_name"])
        for k, v in (("item_type_name", "Mercenary Weapon"), ("item_quality", "normal"), ("propername", "0"),
                     ("item_class", cls), ("item_slot", slot), ("anim_slot", anim_group), ("bucket", str(bucket)),
                     ("hidden", "1")):
            e.set(k, v)
        tags = kv.KV()
        tags.add("bots_cant_use", "1")
        e.set("tags", tags)
        e.set("model_player", it["vm"])
        if it.get("wm") is not None or e.get("model_world") is None:
            wm = it.get("wm")
            if wm is None and it.get("stock"):
                wm = base_items[it["stock"]].get("model_world") or ""
            if wm:
                e.set("model_world", wm)
            elif e.get("model_world") is not None:
                e.pairs = [(a, b) for a, b in e.pairs if a.lower() != "model_world"]
        e.set("attach_to_hands", "2")
        attrs = e.get("attributes")
        if attrs is None:
            attrs = kv.KV()
            attrs.add("hidden separator", "1")
            if it.get("stock"):
                for k2, v2 in (base_items[it["stock"]].get("attributes") or kv.KV()).items():
                    if isinstance(v2, kv.KV):
                        attrs.add(k2, copy.deepcopy(v2))
            e.set("attributes", attrs)
        for a_ in it.get("attrs", []):
            if len(a_) > 2:      # explicit attribute name (description reads right for the value)
                a = kv.KV()
                a.add("attribute_class", a_[0])
                a.add("value", "%g" % round(a_[1], 4))
                attrs.set(a_[2], a)
            else:
                _attr(attrs, by_class, attr_name, a_[0], a_[1])
        st = e.get("static_attrs")
        if st is None:
            st = kv.KV()
            e.set("static_attrs", st)
        st.set("custom hand viewmodel", ARMS)
        for k2, v2 in (it.get("strattrs") or {}).items():
            st.set(k2, v2)
        if st.get("min_viewmodel_offset") is None:
            # variants inherit their roster item's (OF) value; others: the roster weapon they stand
            # for (icon_of), the stock item they copy, else the stock 5205 item of the same class
            mvo = None
            if it.get("icon_of"):
                src_st = by_name["tf2cc_" + it["icon_of"]][1].get("static_attrs")
                mvo = src_st.get("min_viewmodel_offset") if src_st is not None else None
            if mvo is None and it.get("stock"):
                sst = base_items[it["stock"]].get("static_attrs")
                mvo = sst.get("min_viewmodel_offset") if sst is not None else None
            if mvo is None and min_vm:
                mvo = min_vm.get(cls.lower())
            if mvo:
                st.set("min_viewmodel_offset", mvo)
        vis = e.get("visuals")
        if vis is None:
            vis = kv.KV()
            if it.get("stock"):
                for k2, v2 in (base_items[it["stock"]].get("visuals") or kv.KV()).items():
                    if k2.lower().startswith("sound_"):
                        vis.add(k2, v2)
            e.set("visuals", vis)
        for t, s in (it.get("sounds") or {}).items():
            vis.set("sound_" + t, s)
        rep = kv.KV()
        for a, b in (acts.get(it.get("anim") or "", {}).get(anim_group) or {}).items():
            rep.add(a, b)
        if rep.pairs:
            vis.set("animation_replacement", rep)
        icon = None
        if it.get("icon_of"):
            icon = by_name["tf2cc_" + it["icon_of"]][1]
        elif it.get("stock"):
            icon = base_items[it["stock"]]
        if icon is not None and icon.get("image_inventory"):
            e.set("image_inventory", icon.get("image_inventory"))
            if icon.get("image_inventory_teamcolor"):
                e.set("image_inventory_teamcolor", icon.get("image_inventory_teamcolor"))
        if it.get("old_icon"):
            if old_icon is None:
                raise SystemExit("gen_oldmerc.build: old_icon stager missing")
            inv, team = old_icon(it["old_icon"].rstrip("*"), it["old_icon"].endswith("*"))
            e.set("image_inventory", inv)
            e.pairs = [(a, b) for a, b in e.pairs if a.lower() != "image_inventory_teamcolor"]
            if team:
                e.set("image_inventory_teamcolor", "1")
        items.add(str(it["id"]), e)
        rows.append(dict(wid=it["name"], defindex=str(it["id"]), slot=slot, kind=it["kind"],
                         weight=str(it.get("weight", 0)), world=e.get("model_world") or "",
                         pref=it.get("pref", ""), canonical=it.get("variant_of") or it.get("icon_of") or "",
                         pack_rare=it.get("pack_rare")))
        report.append("%-22s %-6d %-28s oldmerc %s%s" % (it["name"], it["id"], cls, it["kind"],
                                                       (" (copy of %s)" % it.get("variant_of")) if it.get("variant_of") else
                                                       (" (stock %s)" % it.get("stock")) if it.get("stock") else ""))
    return rows


# --- Merc copies of TF2-style (attach_to_hands 1) April Fools weapons -------------------------
# CTFWeaponBase::UpdateViewModel (TF2C) uses the class hand model for attach_to_hands 1 items
# and reads custom_hand_viewmodel only for attach_to_hands 2: a Merc holding the AF Bible or
# Jarate saw c_soldier_arms. The copy swaps the roles: the viewmodel is c_merc_arms (it includes
# c_soldier_animations, the same activities the Soldier's arms play for these items) and the
# item's c_model is the bonemerged addon (custom_hand_viewmodel). The April Fools definitions
# are untouched; the plugin gives a Merc the copy when he picks up the original.
AF_COPY_FIRST_ID = 30240
AF_SLOT = {"primary": 0, "secondary": 1, "melee": 2}


def build_af_copies(items, af_items, report, min_vm=None):
    rows = []
    n = 0
    for k, v in af_items.items():
        if not isinstance(v, kv.KV) or v.get("attach_to_hands") != "1" or not v.get("model_player"):
            continue
        slot = v.get("item_slot") or "secondary"
        if slot not in AF_SLOT:
            continue
        e = copy.deepcopy(v)
        e.set("name", "tf2cc_afcopy_%s" % k)
        e.pairs = [(a, b) for a, b in e.pairs if a.lower() not in ("used_by_classes", "baseitem", "show_in_armory")]
        e.set("hidden", "1")
        tags = e.get("tags") or kv.KV()
        tags.set("bots_cant_use", "1")
        e.set("tags", tags)
        e.set("attach_to_hands", "2")
        e.set("model_player", ARMS)
        if e.get("bucket") is None:
            e.set("bucket", str(AF_SLOT[slot]))
        st = e.get("static_attrs")
        if st is None:
            st = kv.KV()
            e.set("static_attrs", st)
        st.set("custom hand viewmodel", v.get("model_player"))
        if st.get("min_viewmodel_offset") is None and min_vm and min_vm.get((v.get("item_class") or "").lower()):
            st.set("min_viewmodel_offset", min_vm[(v.get("item_class") or "").lower()])   # the original has none
        new_id = AF_COPY_FIRST_ID + n
        n += 1
        items.add(str(new_id), e)
        rows.append(dict(wid="afcopy_%s" % k, defindex=str(new_id), slot=slot, kind="afcopy", weight="0",
                         world=e.get("model_world") or "", pref="", canonical="", copy_of=k))
        report.append("%-22s %-6d %-28s Merc copy of April Fools %s (%s): arms c_merc_arms, item %s as the addon"
                      % ("afcopy_" + k, new_id, v.get("item_class"), k, v.get("name"), v.get("model_player")))
    return rows
