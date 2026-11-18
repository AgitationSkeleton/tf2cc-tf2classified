# Credits

tf2cc's code was written from scratch. The characters, models, animations, textures,
sounds and voice work were made by other people, credited below, and are included with
thanks.

**This version of the Mercenary** (the player model used on TF2 Classified) **was modelled by
Maxxy and concepted by Blaholtzen, and some viewmodel animations were done by Hex.**

## Original Custom Class plugin

**MarxVee**: the original TF2 Custom Class plugin and its Mercenary and Civilian setup.
*No original code is present* in tf2cc, but its weapon and model assets are used.

## Team Fortress 2 Classic Team

| Role | Credit |
|---|---|
| Voice of Civilian | Benjamoose |
| Modeller (Mercenary) | Maxxy |
| Concept Artist (Mercenary) | Blaholtzen |
| Modeller (weapons) | svdl |

## Open Fortress Team

| Role | Credit |
|---|---|
| Programming | KayDemonLP |
| Voice of Mercenary | Stachekip |
| Modeller | Alaxe |
| Concept Artist | DrPyspy |
| Animators | Hex, Coolchou Zhao, Polybagel |
| Weapon Modellers | Mr. Big, Overpovered, DrPyspy |
| Particles | FissionMetroid101 |

## TF2 Classified Mercenary pack (the 4dm maps)

The Mercenary player model, materials, first-person arms and gibs come from the Mercenary pack
of TF2 Classified's deathmatch maps. Its credits:

| Content | Credit |
|---|---|
| Mercenary | Blaholtzen (concept), Maxxy (model), Game Zombie (renders), Coolchou Zhao (third-person OF animations) |
| Pistol viewmodel animations | Hex |
| Combat Knife (Open Fortress) | scrunt, Coolchou Zhao (viewmodel animations) |
| Respawn particles | FissionMetroid101 |
| Mercenary voice | Stachekip |
| Weapon sounds | Stachekip, Omniary |
| Civilian voice (Mercenary Spy callouts) | Benjamoose |
| Maps and pack | Open Fortress Team; TF2C Presplit / TDC Team (EonDynamo, Pretz, OneFourth, Stev, Rad, Anreol, DrudlyClean) |

## Additional voice work

| Lines | Credit |
|---|---|
| Soldier and Engineer "the Mercenary is a Spy" callouts | Mr. Big |
| Scout "the Mercenary / Civilian is a Spy" callouts; Mercenary revenge and domination lines | Evermatt |

## Where each asset comes from

| Content (under `tf2classified/custom/tf2cc_merc/`) | Origin |
|---|---|
| `models/player/tf2cc/merc*`, `models/player/tf2cc/merc_anim/` | The TF2 Classified Mercenary (Maxxy, Blaholtzen) with Open Fortress animation sets (renamed activities, tf2cc's tools) |
| `materials/models/player/merc_deathmatch/`, `models/weapons/c_models/c_merc_arms*`, `models/player/gibs/` | TF2 Classified Mercenary pack (4dm maps) |
| `models/tf2cc/of/weapons/`, `materials/models/weapons/...` (OF weapon materials) | Open Fortress weapons; crowbar green/yellow skins and the chaingun barrel re-frame by tf2cc's tools |
| `materials/tf2cc/of/bucket*`, `materials/vgui/tf2cc/` | Open Fortress weapon icons (squared, team variants recoloured by tf2cc's tools) |
| `sound/tf2cc/of/`, `scripts/items/custom_level_sounds.txt` | Open Fortress weapon sounds and their sound scripts (renamed `tf2cc.*`) |
| `sound/vo/tf2cc/`, `sound/vo/custom/` | Mercenary voice (Stachekip, Open Fortress / TF2 Classified pack); Civilian lines (Benjamoose) |
| `models/tf2cc/marxvee/` and their materials | MarxVee pack: Machine Gun and Medkit (medkit green/yellow skins by tf2cc's tools) |
| `models/tf2cc/oldmerc/`, `models/tf2cc/oldclass/` and their materials and sounds | TF2 Classic Team: weapons of TF2 Classic 2.0.0 beta 2-4, the TF2 Classic 2.2.3 items (Overhealer, Makeshift Mutilator, Rescue Ranger port) and the 4dm/4rdm map set (TF2C Presplit / TDC Team); green/yellow skins and team icons recoloured by tf2cc's tools |
| `models/tf2cc/akimbo_stock/` | the stock TF2 Classified pistol (TF2 Classic Team) placed in Open Fortress's akimbo rig by tf2cc's tools |
| `resource/svgs/deathnotice/tf2cc_*.svg` | Kill-feed icons made by tf2cc's tools in TF2 Classified's stock icon style. The China Lake, Quad Launcher, Bouncer, Eternal Shotgun and Saw Ballista icons are traced from Open Fortress's own kill-feed sprites (Open Fortress Team); the others are drawn from the weapon models, using Open Fortress's icons as reference |

Some MarxVee-pack assets were made by community members who aren't named in the pack.
If you made one of them, please get in touch so you can be credited.

## Software

| Project | Use | Licence |
|---|---|---|
| [SM-TF2Classified-Tools](https://github.com/AgitationSkeleton/SM-TF2Classified-Tools) | `TF2_*` / VScript natives for TF2 Classified (required; include files bundled) | GPL-3.0 ([THIRD-PARTY/SM-TF2Classified-Tools-LICENSE](THIRD-PARTY/SM-TF2Classified-Tools-LICENSE)) |
| [SourceMod](https://www.sourcemod.net/) and [Metamod:Source](https://www.metamodsource.net/) | Plugin platform (not bundled) | GPL-3.0 / zlib |
| Open Fortress source code, TF2 Classified game data, the 2025 TF2 SDK | Behaviour reference (no code copied) | their respective terms |
