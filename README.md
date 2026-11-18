# tf2cc for TF2 Classified

The Open Fortress **Mercenary** as a playable role on **TF2 Classified** (build 5205) servers,
done server-side with SourceMod. A Mercenary is a Soldier underneath, with the Mercenary player
model and voice, his own weapons (real schema items: viewmodels, world models, sounds, stats and
third-person animations), weapon pickups and drops, ammo-pack weapon grants, OF weapon specials,
taunts and HUD bits. Players opt in with `!merc` (or the class menu's Random); bots roll it.

This is the TF2 Classified port of tf2cc (the stock-TF2 version is a separate project).

## What's in it

* **Mercenary weapons** with Open Fortress stats, models, sounds and animations: Crowbar, Lead
  Pipe, Combat Knife, Fists, Chainsaw, Pistol and Akimbo, Revolver, Shotgun, Combat SMG, Tommy
  Gun, Dynamite, Super Shotgun, Eternal Shotgun (alt-fire meat hook), Assault Rifle, Rocket
  Launcher, Quad Launcher, China Lake, Bouncer, Nailgun, Gatling Gun, Railgun (scoped, on the
  sniper rifle), Lightning Gun, G.I.B., Saw Ballista (ricocheting blade); the older TF2 Classic
  Mercenary weapons (2.0.0 betas and the 4dm map set) as alternatives; two stock pistols make
  Akimbo pistols.
* **Old TF2 Classic class weapons** for the normal classes (ordinary loadout items): Rescue
  Ranger, Poacher's Pride (on the hunting revolver: clip, scopeless zoom, headshots while zoomed),
  Sten Gun, Medic shotgun, old SMG, old Cyclops, old R.P.G., Overhealer, old Uberspritze,
  Makeshift Mutilator.
* **Kill-feed icons** for every tf2cc weapon (`resource/svgs/deathnotice/`).

## Plugins

All in `tf2classified/addons/sourcemod/plugins/`; load them all.

| Plugin | Does |
|---|---|
| `tf2cc_tf2c` | the Mercenary role, weapons, pickups, drops, ammo packs, voice, taunts, HUD |
| `tf2cc_oldclass` | old class weapons: spawn reserves, Rescue Ranger team bolts |
| `tf2cc_ofexpl` | OF explosives: China Lake contact mines, Dynamite charge / cook-off / impact |
| `tf2cc_ofrockets` | Quad Launcher homing, ping and radius growth; Bouncer ricochets |
| `tf2cc_hook` | the Eternal Shotgun's meat hook |
| `tf2cc_saw` | the Saw Ballista's blade (never explodes, 4 dmg every 0.03 s through targets, ricochets, sticks after 6 bounces) |

## Requirements

* TF2 Classified dedicated server, build 5205 (x64), Metamod:Source and SourceMod 1.12+.
* [SM-TF2Classified-Tools](https://github.com/AgitationSkeleton/SM-TF2Classified-Tools):
  `tf2classified.smx` (the `TF2_*` / VScript natives the plugin uses). Its include files are
  bundled under `tf2classified/addons/sourcemod/scripting/include/` for compiling.
* A FastDL host: clients must download the Merc model, weapons, sounds and the item schema.

## Install

1. Copy `tf2classified/addons` into the server's `tf2classified/` folder
   (plugins, sources, `configs/tf2cc_tf2c/`).
2. Copy `tf2classified/custom/tf2cc_merc/` into the server's `tf2classified/custom/`.
3. Item schema: build the server's `custom_items_game.txt` with
   `python -I tools/tf2c/merge_schema.py schema/tf2cc_items.txt <out> [<your current custom_items_game.txt>]`
   (your own items are kept; tf2cc's are ids 30099 and up) and put it in
   `custom/tf2cc_merc/scripts/items/`. `custom_level_sounds.txt` there already holds the
   weapons' sound scripts.
   * **VPKs in `custom/` beat loose folders.** If another VPK in `custom/` carries its own
     `scripts/items/custom_items_game.txt`, the server reads that one. Pack the merged schema and
     `custom_level_sounds.txt` into a VPK that sorts first (e.g. `custom/00tf2cc_schema.vpk`, made
     with the SDK's `vpk.exe`), and update both the loose files and that VPK whenever the schema
     changes.
   * **`custom/` is only scanned when srcds starts.** A map change does not mount new custom
     content: restart the server process after installing or updating.
4. Upload the files of `custom/tf2cc_merc/` (bzip2-compressed, `<path>.bz2`) and the merged
   schema to your FastDL (`sv_downloadurl`), keeping their paths. A client never downloads a path
   it already has again, so a file whose content changes must get a new path: the generators do
   that (`tools/tf2c/version_assets.py`).
5. Restart the server. Players type `!merc`.

Maps that already play the Mercenary through their own VScript (the DM-reclassified `4dm_` and
similar maps) are left alone (`configs/tf2cc_tf2c/exempt_maps.txt`, plus auto-detection).

## Commands and cvars

Commands: `!merc` / `!mercenary` (toggle), `joinclass mercenary`, `!dropweapon` / `dropitem`,
USE or INSPECT to swap with a weapon on the ground. Admin: `sm_setmerc <target> <0|1>`,
`sm_tf2cc_reload`, and test commands `sm_tf2cc_givemerc`, `sm_tf2cc_use`, `sm_tf2cc_drop`,
`sm_tf2cc_taunt`, `sm_tf2cc_spytest`.

Main cvars (all in `cfg/sourcemod/tf2cc_tf2c.cfg`, created on first load):

| Cvar | Default | Meaning |
|---|---|---|
| `tf2cc_merc_enabled` | 1 | allow the Mercenary role |
| `tf2cc_merc_bot_chance` | 0.2 | chance a bot plays the Mercenary (rolled per connection) |
| `tf2cc_merc_no_fall_damage` | 1 | Mercenaries take no fall damage |
| `tf2cc_merc_taunts` | 1 | OF Merc taunts per held weapon |
| `tf2cc_merc_autojump` | 0 | Merc bunny-hop even when `tf2c_autojump` is 0 |
| `tf2cc_random_menu` | 1 | the class menu's Random offers the Mercenary |
| `tf2cc_ammopack_weapon_chance` / `tf2cc_ammopack_respawn` | 1.0 / 10 | map ammo packs grant Merc weapons |
| `tf2cc_pickup_lifetime` / `tf2cc_pickup_auto_empty_slot` / `tf2cc_pickup_autoswitch` | 30 / 1 / 0 | dropped weapons |
| `tf2cc_drop_on_death` / `tf2cc_stock_drops` / `tf2cc_deathdrop_ammobox` | 1 / 1 / 1 | death drops |
| `tf2cc_marxvee_items` | "" | optional MarxVee weapons offered (`merc_machinegun merc_medkit`) |
| `tf2cc_chainsaw_*`, `tf2cc_medkit_pf2_*` | | chainsaw and medkit tuning |
| `tf2cc_merc_exempt_autodetect` | 1 | skip maps that run their own Merc script |
| `tf2cc_tf2c_debug` | 0 | step log in `logs/tf2cc_tf2c.log` |

The other plugins write their own `cfg/sourcemod/<plugin>.cfg`: `tf2cc_eternal_hook_*` (hook
speed, range, pull, cooldown; optional stun, hold-to-reel and world grapple, off by default),
`tf2cc_saw_*` (blade damage, tick, cap, slow-down, bounces, stick time), `tf2cc_quad_*` and
`tf2cc_bouncer_*` (`tf2cc_ofrockets`), `tf2cc_chinalake_*` and `tf2cc_dynamite_*` (`tf2cc_ofexpl`).

## Rebuilding

`tools/` holds the generators that produce `custom/tf2cc_merc` and the schema from an Open
Fortress install, the TF2 Classified game files and the 4dm Merc pack
(`python -I tools/tf2c/stage_tf2c.py`). Their source paths are constants at the top of each
tool. `fastdl_publish_tf2c.py` publishes to a GitHub-Pages FastDL repository through the `gh`
CLI (your own login; nothing is stored here).

The rebuild tools read the game installs and source trees they work from through path constants
near the top of each script. In this release those are placeholders: `<STEAMCMD>/` stands for the
folder holding your server installs (TF2, TF2 Classified, Open Fortress under `sdk2013/`),
`<SOURCE_TREES>/` for checkouts of the Source SDK 2013, TF2 Classified and Open Fortress sources,
`<WORKDIR>/` for the working folders of the extracted old-build assets and research notes, and
`<STEAM_GAMES>/` for a Steam client library (the team icon tool reads TF2's texture VPK there).
Replace them with your own paths before running the tools. The plugin and the shipped assets don't
need them.

## Known limits

* Server-side only: everything a client sees comes from the downloaded schema and assets.
* The Mercenary's "class" is the Soldier for the game (scoreboard, class limits).
* The Merc model has no Sandvich-eating animation (TF2's Soldier animations have none).

## Licence

GPL-3.0 (see `LICENSE`). Assets belong to their authors (see `CREDITS.md`).
