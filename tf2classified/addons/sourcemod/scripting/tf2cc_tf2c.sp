/**
 * tf2cc for TF2 Classified: the Open Fortress Mercenary as a role on the Soldier.
 *
 * TF2 Classified already has the Civilian, so only the Mercenary is added. He is
 * a Soldier carrying a role flag:
 *  - model: the TF2C (4dm) Merc mesh with OF animations (models/player/tf2cc/merc.mdl,
 *    tools/tf2c/gen_merc_acts.py); each Merc weapon item selects its OF animation set
 *    through animation_replacement, so no model swapping is needed;
 *  - health/speed/arms: the hidden "tf2cc_merc_body" schema wearable (150 HP, 320 speed,
 *    custom hand viewmodel = the TF2C Merc arms on every weapon);
 *  - weapons: real schema items (tools/tf2c/gen_schema.py), default pistol + crowbar,
 *    more from map ammo packs and from weapons dropped by anyone (OF/MarxVee rules: one
 *    weapon per slot, USE/INSPECT swaps);
 *  - voice: tf2cc's Mercenary persona with the TF2C 4dm pain/death lines; Soldier lines
 *    are rewritten by concept (the death scream too, which the game plays after player_death);
 *    a pitch cvar for non-pain lines; spy callouts both ways; OF jump vocals;
 *  - taunts: the Soldier's taunt scenes carry Soldier voice and exist only for his stock
 *    weapons, so a Merc's taunt key plays the OF Merc taunt sequence for the held weapon
 *    (player anim event + taunt camera), any weapon included;
 *  - scoreboard: the class icon is blanked (no Soldier icon for a Merc).
 *
 * Requires TF2 Classified Tools (library "tf2classified").
 */
#include <sourcemod>
#include <sdktools>
#include <sdkhooks>
#include <tf2>
#include <tf2_stocks>

#pragma semicolon 1
#pragma newdecls required

#define PLUGIN_VERSION "1.0.0"
#define MERC_MODEL_DEFAULT "models/player/tf2cc/merc.mdl"
#define BODY_ITEM "tf2cc_merc_body"
#define AMMOBOX_MODEL "models/items/ammopack_medium.mdl"
#define BOMBLET_MODEL_DEFAULT "models/tf2cc/of/weapons/w_models/w_grenade_bomblet.mdl"   // 4 team skins (gen_schema.py)
#define CFG_ASSETS "configs/tf2cc_tf2c/assets.cfg"
#define PICKUP_SOUND "items/gunpickup2.wav"
#define CFG_WEAPONS "configs/tf2cc_tf2c/weapons.cfg"
#define CFG_VOICE "configs/tf2cc_tf2c/voice.cfg"
#define CFG_DOWNLOADS "configs/tf2cc_tf2c/downloads.txt"
#define CFG_EXEMPT "configs/tf2cc_tf2c/exempt_maps.txt"
#define MERC_ARMS "models/weapons/c_models/c_merc_arms.mdl"
#define SOUNDSCRIPT "scripts/items/custom_level_sounds.txt"
#define DM_MERC_SCRIPT "scripts/vscripts/tf2c_merc_soldieronly.nut"   // packed in every DM-reclassified map
#define SLOTS 3
#define EF_NODRAW 32
#define COLLISION_GROUP_DEBRIS 1
#define LG_ITEM "tf2cc_merc_lightning"
#define LG_BEAM "sprites/laserbeam.vmt"
#define LG_START "tf2cc.Weapon_LightningGun.LightningStart"
#define LG_LOOP "tf2cc.Weapon_LightningGun.LightningLoop"
#define LG_END "tf2cc.Weapon_LightningGun.LightningEnd"
int g_iBeamSprite;
bool g_bLgFiring[MAXPLAYERS + 1];
int g_iLgWeapon[MAXPLAYERS + 1] = { INVALID_ENT_REFERENCE, ... };
float g_flLgNextBeam[MAXPLAYERS + 1];
#define DMG_CRITICAL (1 << 20)
#define PLAYERANIMEVENT_SPAWN 17            // multiplayer_animstate.h: ClearAnimationState()
#define PLAYERANIMEVENT_CUSTOM_SEQUENCE 21  // m_nSpecificMainSequence = nData
#define BOND_SOUND_DEFAULT "tf2cc/of/player/taunt_bond_pistol.wav"
// Staged asset paths (configs/tf2cc_tf2c/assets.cfg, written by tools/tf2c/stage_tf2c.py): a file
// whose content changed since it was first published gets a new path (version_assets.py).
char MERC_MODEL[PLATFORM_MAX_PATH] = MERC_MODEL_DEFAULT;
char BOMBLET_MODEL[PLATFORM_MAX_PATH] = BOMBLET_MODEL_DEFAULT;
char BOND_SOUND[PLATFORM_MAX_PATH] = BOND_SOUND_DEFAULT;
#define DRG_BALL_MODEL "models/weapons/w_models/w_drg_ball.mdl"
#define EF_ITEM_BLINK 0x100
static const char g_sJumpSounds[][] = { "vo/custom/mercenary_jump01.wav", "vo/custom/mercenary_jump02.wav", "vo/custom/mercenary_jump03.wav" };

public Plugin myinfo =
{
	name        = "tf2cc for TF2 Classified",
	author      = "AgitationSkeleton",
	description = "Open Fortress Mercenary as a Soldier role on TF2 Classified",
	version     = PLUGIN_VERSION,
	url         = ""
};

ConVar g_cvEnabled, g_cvBotChance, g_cvPitch, g_cvLevel, g_cvPackChance, g_cvPackRespawn,
	g_cvLifetime, g_cvDropOnDeath, g_cvAllDrop, g_cvAmmoBox, g_cvAutoEmpty, g_cvBotSwap;

ConVar g_cvDebug, g_cvBlankIcon, g_cvAutoSwitch, g_cvAutoJump, g_cvTaunts, g_cvSvAutoJump;
ConVar g_cvRet;              // VScript return channel (LookupSequence)
ConVar g_cvAutoDetect, g_cvRandomMenu, g_cvNoFall, g_cvMarxVee;
bool g_bMapExempt;           // this map already plays the Mercenary itself (DM reclassified): tf2cc stays out
bool g_bInternalJoin[MAXPLAYERS + 1];
float g_flLastDeathDrop[MAXPLAYERS + 1];
int g_iTauntClone[MAXPLAYERS + 1] = { INVALID_ENT_REFERENCE, ... };
float g_flTauntStart[MAXPLAYERS + 1], g_flTauntLen[MAXPLAYERS + 1], g_flCycleIn[MAXPLAYERS + 1], g_flCycleSpan[MAXPLAYERS + 1];
bool g_bCloneManualCycle[MAXPLAYERS + 1];
RenderMode g_iRenderBefore[MAXPLAYERS + 1];
float g_flChargeReady[MAXPLAYERS + 1];
bool g_bExplicit[MAXPLAYERS + 1];
bool g_bDiedLastLife[MAXPLAYERS + 1];   // died as a Merc last life (OF "respawn killed" lines)
bool g_bSchemaHinted[MAXPLAYERS + 1];    // chose (or was set) by command: the bot roll never overrides it
bool g_bMercCorpse[MAXPLAYERS + 1];  // died as a Merc this life: his death scream is still to come
bool g_bDeathLine[MAXPLAYERS + 1];   // the Merc death line for this death has played
bool g_bDeathCrit[MAXPLAYERS + 1];
bool g_bWasOnGround[MAXPLAYERS + 1];
float g_flNextJumpSound[MAXPLAYERS + 1];
// Merc taunts
bool g_bTaunting[MAXPLAYERS + 1];
float g_flNextTaunt[MAXPLAYERS + 1];
Handle g_hTauntEnd[MAXPLAYERS + 1];
int g_iTauntWeapon[MAXPLAYERS + 1] = { INVALID_ENT_REFERENCE, ... };
bool g_bTauntWeaponHidden[MAXPLAYERS + 1];
int g_iTauntCamBefore[MAXPLAYERS + 1];
float g_flTauntYaw[MAXPLAYERS + 1];
bool g_bAlt[MAXPLAYERS + 1];
char g_sLog[PLATFORM_MAX_PATH];
bool g_bWant[MAXPLAYERS + 1];        // chose the Mercenary (persists across lives)
bool g_bMerc[MAXPLAYERS + 1];        // is a Mercenary this life
bool g_bFreshLife[MAXPLAYERS + 1];
bool g_bBotRolled[MAXPLAYERS + 1];
// TFBot class selection (CTFBot::GetPresetClassToSpawn / GetWeightDesiredClassToSpawn) counts
// each teammate's m_iDesiredPlayerClass: a Merc bot with desired class Soldier filled the
// team's Soldier slots, so real Soldier bots almost never spawned. A Merc bot now keeps the
// class its AI chose as its desired class (the roster stays the game's own), and a Merc bot
// whose AI chose Soldier plays an ordinary Soldier that life.
int g_iBotPick[MAXPLAYERS + 1];           // class the bot AI chose for this life
bool g_bBotConverting[MAXPLAYERS + 1];    // the next spawn is our forced Soldier respawn
bool g_bBotSoldierLife[MAXPLAYERS + 1];   // a Merc bot whose AI chose Soldier: plain Soldier this life
bool g_bUseHeld[MAXPLAYERS + 1];
bool g_bOwnEmit;
char g_sInv[MAXPLAYERS + 1][SLOTS][64];    // item names held per slot (survive resupply)
float g_flNextHint[MAXPLAYERS + 1], g_flNextSpeak[MAXPLAYERS + 1], g_flNextPackTouch[MAXPLAYERS + 1];
float g_flPackReady[2049];
float g_vSettle[2049][3];   // last position of a pickup that has not settled yet
float g_flStripAt[MAXPLAYERS + 1];
float g_flOwnGive[MAXPLAYERS + 1];   // GenerateAndWearItem fires post_inventory_application:
                                     // events right after our own grants are ignored (loop guard)

// Merc weapons (weapons.cfg)
ArrayList g_WItem, g_WSlot, g_WWeight, g_WModel, g_WDef, g_WDefault;
StringMap g_ItemNames;       // defindex -> schema item name (base + custom schema)
StringMap g_Pickups;         // entref -> PickupData

enum struct PickupData
{
	int def;
	int slot;
	int dropper;      // userid
	float readyAt;    // dropper cannot take it back before this
	char item[64];
}

StringMap g_StockSlot;        // defindex -> slot the item took on the Merc (learned at each give)

// Voice
int g_iLastVoiceEnt;
float g_flLastVoiceAt;
char g_sLastVoiceIn[PLATFORM_MAX_PATH], g_sLastVoiceOut[PLATFORM_MAX_PATH];
StringMap g_Concepts;        // "persona/concept" or "@targeted/speaker/kind" -> ArrayList
StringMap g_PersonaSamples;  // sample -> true

static const char g_sClassNames[][] = { "", "scout", "sniper", "soldier", "demoman", "medic", "heavy", "pyro", "spy", "engineer", "civilian" };

public APLRes AskPluginLoad2(Handle myself, bool late, char[] error, int err_max)
{
	char game[32];
	GetGameFolderName(game, sizeof(game));
	if (!StrEqual(game, "tf2classified", false))
	{
		strcopy(error, err_max, "tf2cc_tf2c is for TF2 Classified (use tf2cc on stock TF2).");
		return APLRes_Failure;
	}
	return APLRes_Success;
}

public void OnPluginStart()
{
	CreateConVar("tf2cc_tf2c_version", PLUGIN_VERSION, "tf2cc for TF2 Classified version.", FCVAR_NOTIFY | FCVAR_DONTRECORD);
	g_cvEnabled = CreateConVar("tf2cc_merc_enabled", "1", "Allow the Mercenary role.", _, true, 0.0, true, 1.0);
	g_cvBotChance = CreateConVar("tf2cc_merc_bot_chance", "0.2", "Chance that a bot plays the Mercenary (rolled once per connection).", _, true, 0.0, true, 1.0);
	g_cvPitch = CreateConVar("tf2cc_merc_voice_pitch", "100", "Pitch of Mercenary voice lines other than pain/death (100 = normal; old TF2C Merc ~90).", _, true, 50.0, true, 200.0);
	g_cvLevel = CreateConVar("tf2cc_merc_voice_level", "95", "Sound level of Mercenary lines played by the plugin.", _, true, 60.0, true, 140.0);
	g_cvPackChance = CreateConVar("tf2cc_ammopack_weapon_chance", "1.0", "Chance that a map ammo pack touched by a Mercenary drops a Mercenary weapon.", _, true, 0.0, true, 1.0);
	g_cvPackRespawn = CreateConVar("tf2cc_ammopack_respawn", "10.0", "Seconds before an ammo pack a Mercenary used reappears.", _, true, 1.0);
	g_cvLifetime = CreateConVar("tf2cc_pickup_lifetime", "30.0", "Seconds a dropped weapon stays on the ground.", _, true, 1.0);
	g_cvDropOnDeath = CreateConVar("tf2cc_drop_on_death", "1", "Mercenaries drop their active non-default weapon on death.", _, true, 0.0, true, 1.0);
	g_cvAllDrop = CreateConVar("tf2cc_stock_drops", "1", "Every class drops its active weapon on death for Mercenaries to pick up.", _, true, 0.0, true, 1.0);
	g_cvAmmoBox = CreateConVar("tf2cc_deathdrop_ammobox", "1", "Death-dropped ammo packs use the ammo box model, like live TF2.", _, true, 0.0, true, 1.0);
	g_cvAutoEmpty = CreateConVar("tf2cc_pickup_auto_empty_slot", "1", "Walking over a weapon whose slot is empty picks it up (anything else is swapped with USE).", _, true, 0.0, true, 1.0);
	g_cvBotSwap = CreateConVar("tf2cc_bot_pickup_swap_chance", "0.1", "Merc bots standing on a weapon: chance per 0.2 s to swap to it.", _, true, 0.0, true, 1.0);
	g_cvDebug = CreateConVar("tf2cc_tf2c_debug", "0", "Log each Mercenary setup step to logs/tf2cc_tf2c.log.", _, true, 0.0, true, 1.0);
	g_cvBlankIcon = CreateConVar("tf2cc_merc_scoreboard_blank", "1", "Show no class icon for Mercenaries on the scoreboard (instead of the Soldier's).", _, true, 0.0, true, 1.0);
	g_cvAutoSwitch = CreateConVar("tf2cc_pickup_autoswitch", "0", "0 = a picked-up weapon is only drawn when it replaces the weapon in hand (or the hands are empty); 1 = OF of_autoswitchweapons: draw every picked-up weapon unless attacking.", _, true, 0.0, true, 1.0);
	g_cvAutoJump = CreateConVar("tf2cc_merc_autojump", "0", "1 = Mercenaries re-jump while holding jump even when tf2c_autojump is 0 (OF Merc bunnyhop, server side). 0 = follow tf2c_autojump like every class.", _, true, 0.0, true, 1.0);
	g_cvTaunts = CreateConVar("tf2cc_merc_taunts", "1", "Mercenaries taunt with the OF Merc taunts (per held weapon) instead of the Soldier's scenes.", _, true, 0.0, true, 1.0);
	g_cvRet = CreateConVar("tf2cc_tf2c_ret", "", "Internal: VScript return channel.", FCVAR_DONTRECORD | FCVAR_UNLOGGED);
	g_cvSvAutoJump = FindConVar("tf2c_autojump");
	g_cvAutoDetect = CreateConVar("tf2cc_merc_exempt_autodetect", "1", "Treat a map as Mercenary-free when it packs the DM-reclassified Merc VScript (scripts/vscripts/tf2c_merc_soldieronly.nut), in addition to configs/tf2cc_tf2c/exempt_maps.txt.", _, true, 0.0, true, 1.0);
	g_cvRandomMenu = CreateConVar("tf2cc_random_menu", "1", "The class menu's Random (joinclass random/auto) opens the Mercenary menu: Mercenary, Random (Mercenary included) or the game's random class.", _, true, 0.0, true, 1.0);
	g_cvNoFall = CreateConVar("tf2cc_merc_no_fall_damage", "1", "1 = Mercenaries take no fall damage (OF's Merc has none). The damage is refused before it lands, so the fall-damage sound and pain line never play either.", _, true, 0.0, true, 1.0);
	g_cvMarxVee = CreateConVar("tf2cc_marxvee_items", "", "Optional MarxVee-origin Merc weapons offered in ammo-pack grants (space-separated weapon ids, e.g. \"merc_machinegun merc_medkit\"; empty = none).");
	g_cvMarxVee.AddChangeHook(OnMarxVeeChanged);
	MedkitInit();
	g_cvBotChance.AddChangeHook(OnBotChanceChanged);
	g_cvEnabled.AddChangeHook(OnBotChanceChanged);
	BuildPath(Path_SM, g_sLog, sizeof(g_sLog), "logs/tf2cc_tf2c.log");
	AutoExecConfig(true, "tf2cc_tf2c");

	RegConsoleCmd("sm_merc", Cmd_Merc, "Play (or stop playing) the Mercenary.");
	RegConsoleCmd("sm_mercenary", Cmd_Merc, "Play (or stop playing) the Mercenary.");
	RegAdminCmd("sm_setmerc", Cmd_SetMerc, ADMFLAG_SLAY, "sm_setmerc <target> <0|1>");
	RegAdminCmd("sm_tf2cc_givemerc", Cmd_GiveMerc, ADMFLAG_CHEATS, "sm_tf2cc_givemerc <target> <merc weapon id | schema item name> [slot] - give a weapon the way a pickup does (testing).");
	RegAdminCmd("sm_tf2cc_spytest", Cmd_SpyTest, ADMFLAG_CHEATS, "sm_tf2cc_spytest <speaker> <target> - run the Spy! callout as if speaker aimed at target (testing).");
	RegAdminCmd("sm_tf2cc_reload", Cmd_Reload, ADMFLAG_CONFIG, "Reload tf2cc_tf2c configs.");
	RegAdminCmd("sm_tf2cc_use", Cmd_UseTest, ADMFLAG_CHEATS, "sm_tf2cc_use <target> - press USE for the target (pickup swap test).");
	RegAdminCmd("sm_tf2cc_taunt", Cmd_TauntTest, ADMFLAG_CHEATS, "sm_tf2cc_taunt <target> - taunt as if the target pressed the taunt key (testing).");
	RegAdminCmd("sm_tf2cc_drop", Cmd_DropTest, ADMFLAG_CHEATS, "sm_tf2cc_drop <target> - dropitem for the target (testing).");
	RegConsoleCmd("sm_dropweapon", Cmd_DropWeapon, "Mercenary: drop the weapon in hand.");
	AddCommandListener(Listener_DropItem, "dropitem");
	AddCommandListener(Listener_Taunt, "taunt");
	AddCommandListener(Listener_Taunt, "+taunt");
	AddCommandListener(Listener_JoinClass, "joinclass");
	AddCommandListener(Listener_JoinClass, "join_class");
	AddCommandListener(Listener_VoiceMenu, "voicemenu");
	AddCommandListener(Listener_Inspect, "+inspect");
	HookEvent("player_spawn", Event_Spawn);
	HookEvent("post_inventory_application", Event_Inventory);
	HookEvent("player_death", Event_Death);
	AddNormalSoundHook(Hook_Sound);
	AddTempEntHook("TFExplosion", TE_GibExplosion);
	AddNormalSoundHook(Hook_ChainsawSounds);
	ChainsawInit();

	g_Pickups = new StringMap();
	g_StockSlot = new StringMap();
	for (int i = 1; i <= MaxClients; i++)
		if (IsClientInGame(i))
			SDKHook(i, SDKHook_OnTakeDamage, Hook_PlayerDamage);
	LoadWeapons();
	LoadVoice();
	CreateTimer(0.2, Timer_PickupScan, _, TIMER_REPEAT);
	CreateTimer(1.0, Timer_Restamp, _, TIMER_REPEAT);
}

public void OnMapStart()
{
	g_bMapExempt = MapIsExempt();
	LoadAssets();
	PrecacheModel(MERC_MODEL, true);
	PrecacheModel(DRG_BALL_MODEL, true);
	// The arms come from the custom_hand_viewmodel string attribute, which TF2C's schema
	// precache does not cover on build 5205: unprecached, the client's GetModelIndex() was -1
	// and the viewmodel addon (the arms) had no model at all.
	PrecacheModel(MERC_ARMS, true);
	PrecacheModel(AMMOBOX_MODEL, true);
	PrecacheModel(BOMBLET_MODEL, true);
	PrecacheSound(PICKUP_SOUND, true);
	PrecacheSound("items/smallmedkit1.wav", true);
	PrecacheSound(BOND_SOUND, true);
	g_iBeamSprite = PrecacheModel(LG_BEAM, true);
	PrecacheScriptSound(LG_START);
	PrecacheScriptSound(LG_LOOP);
	PrecacheScriptSound(LG_END);
	for (int i = 0; i < sizeof(g_sJumpSounds); i++)
		PrecacheSound(g_sJumpSounds[i], true);
	LoadItemNames();
	if (!g_bMapExempt)
		AddDownloads();
	PrecacheVoice();
	PrecacheSoundScripts();
	char model[PLATFORM_MAX_PATH];
	for (int i = 0; i < g_WModel.Length; i++)
	{
		g_WModel.GetString(i, model, sizeof(model));
		if (model[0])
			PrecacheModel(model, true);
	}
	g_Pickups.Clear();
	// Game time restarts at every map change while players keep their slots: every
	// GetGameTime() stamp must be cleared here or it blocks for as long as the last map ran.
	for (int i = 0; i < sizeof(g_flPackReady); i++)
		g_flPackReady[i] = 0.0;
	for (int i = 1; i <= MaxClients; i++)
	{
		g_flNextHint[i] = g_flNextSpeak[i] = g_flNextPackTouch[i] = g_flChargeReady[i] = 0.0;
		g_flNextTaunt[i] = g_flNextJumpSound[i] = 0.0;
		g_bTaunting[i] = false;
	}
	CreateTimer(1.0, Timer_HookResource, _, TIMER_FLAG_NO_MAPCHANGE);
}

public void OnClientPutInServer(int client)
{
	SDKHook(client, SDKHook_OnTakeDamage, Hook_PlayerDamage);
	g_flNextHint[client] = g_flNextSpeak[client] = g_flNextPackTouch[client] = g_flChargeReady[client] = 0.0;
	g_bWant[client] = g_bMerc[client] = g_bBotRolled[client] = g_bExplicit[client] = false;
	g_bMercCorpse[client] = g_bTaunting[client] = g_bSchemaHinted[client] = false;
	g_iBotPick[client] = 0;
	g_bBotConverting[client] = g_bBotSoldierLife[client] = false;
	g_flNextTaunt[client] = g_flNextJumpSound[client] = 0.0;
	for (int s = 0; s < SLOTS; s++)
		g_sInv[client][s][0] = '\0';
}

public void OnClientDisconnect(int client)
{
	ChainsawReset(client);
	EndTaunt(client);
	StopLightning(client, false);
}

/** The bot roll runs once per connection: bots whose roll ran with another chance roll again. */
public void OnBotChanceChanged(ConVar cv, const char[] oldValue, const char[] newValue)
{
	for (int i = 1; i <= MaxClients; i++)
		if (IsClientInGame(i) && IsFakeClient(i) && !g_bExplicit[i])
			g_bBotRolled[i] = false;
}

/* ------------------------------------------------------------------ */
/* Maps that already play the Mercenary                               */
/* ------------------------------------------------------------------ */

/**
 * The DM-reclassified maps (4dm_, 4rdm_, 4gg_, 4ig_, inf_, 2mctf_, 4mctf_, 4mdom_, rdm_ on the
 * TF2C servers) make every Soldier a Mercenary through their own packed VScript
 * (tf2c_merc_soldieronly.nut, with their own drops and weapons). tf2cc stays out there:
 * configs/tf2cc_tf2c/exempt_maps.txt (exact names, "prefix*") and, unless turned off, the
 * presence of that script in the map.
 */
bool MapIsExempt()
{
	char map[PLATFORM_MAX_PATH];
	GetCurrentMap(map, sizeof(map));
	GetMapDisplayName(map, map, sizeof(map));
	char path[PLATFORM_MAX_PATH], line[PLATFORM_MAX_PATH];
	BuildPath(Path_SM, path, sizeof(path), CFG_EXEMPT);
	File f = OpenFile(path, "r");
	if (f != null)
	{
		while (f.ReadLine(line, sizeof(line)))
		{
			int c = StrContains(line, "//");
			if (c != -1)
				line[c] = '\0';
			TrimString(line);
			if (!line[0])
				continue;
			int len = strlen(line);
			bool match = line[len - 1] == '*' ? (strncmp(map, line, len - 1, false) == 0) : StrEqual(map, line, false);
			if (match)
			{
				delete f;
				LogMessage("Mercenary off on %s (exempt_maps.txt: %s)", map, line);
				return true;
			}
		}
		delete f;
	}
	if (g_cvAutoDetect.BoolValue && FileExists(DM_MERC_SCRIPT, true))
	{
		LogMessage("Mercenary off on %s (the map plays the Merc itself: %s)", map, DM_MERC_SCRIPT);
		return true;
	}
	Step("Mercenary allowed on %s", map);
	return false;
}

bool MercAllowed()
{
	return g_cvEnabled.BoolValue && !g_bMapExempt;
}

/** The items' OF sound scripts (gen_schema.py): precached by name so every wave is in the table. */
void PrecacheSoundScripts()
{
	// Top-level entries only ("name" on its own line); KeyValues cannot hold a file of roots.
	File f = OpenFile(SOUNDSCRIPT, "r", true);
	int n = 0;
	if (f != null)
	{
		char line[160];
		while (f.ReadLine(line, sizeof(line)))
		{
			TrimString(line);
			int len = strlen(line);
			if (len > 2 && line[0] == '"' && line[len - 1] == '"' && StrContains(line, "tf2cc.") == 1)
			{
				line[len - 1] = '\0';
				if (PrecacheScriptSound(line[1]))
					n++;
			}
		}
		delete f;
	}
	Step("sound scripts precached: %d", n);
}

/* ------------------------------------------------------------------ */
/* Helpers                                                            */
/* ------------------------------------------------------------------ */

void Step(const char[] fmt, any ...)
{
	if (g_cvDebug == null || !g_cvDebug.BoolValue)
		return;
	char buf[256];
	VFormat(buf, sizeof(buf), fmt, 2);
	LogToFileEx(g_sLog, "%s", buf);
}

void RunScriptF(int entity, const char[] fmt, any ...)
{
	char code[512];
	VFormat(code, sizeof(code), fmt, 3);
	TF2C_RunScript(entity, code);
}

bool IsMerc(int client)
{
	return client >= 1 && client <= MaxClients && g_bMerc[client] && IsClientInGame(client) && IsPlayerAlive(client);
}

int SlotIndex(const char[] slot)
{
	if (StrEqual(slot, "primary"))
		return 0;
	if (StrEqual(slot, "secondary"))
		return 1;
	if (StrEqual(slot, "melee"))
		return 2;
	return -1;
}

int ItemDef(int entity)
{
	return HasEntProp(entity, Prop_Send, "m_iItemDefinitionIndex") ? GetEntProp(entity, Prop_Send, "m_iItemDefinitionIndex") : -1;
}

int FindWeaponByDef(int client, int def)
{
	int max = GetEntPropArraySize(client, Prop_Send, "m_hMyWeapons");
	for (int i = 0; i < max; i++)
	{
		int w = GetEntPropEnt(client, Prop_Send, "m_hMyWeapons", i);
		if (w > MaxClients && ItemDef(w) == def)
			return w;
	}
	return -1;
}

/** The most recently created weapon with this definition (a give can briefly leave two). */
int FindNewestWeaponByDef(int client, int def)
{
	int best = -1;
	int max = GetEntPropArraySize(client, Prop_Send, "m_hMyWeapons");
	for (int i = 0; i < max; i++)
	{
		int w = GetEntPropEnt(client, Prop_Send, "m_hMyWeapons", i);
		if (w > MaxClients && ItemDef(w) == def && w > best)
			best = w;
	}
	return best;
}

int MercWeaponIndex(int def)
{
	return g_WDef.FindValue(def);
}

bool IsDefaultItem(int def)
{
	int i = MercWeaponIndex(def);
	return i >= 0 && g_WDefault.Get(i);
}

bool ItemName(int def, char[] out, int maxlen)
{
	char key[12];
	IntToString(def, key, sizeof(key));
	return g_ItemNames.GetString(key, out, maxlen);
}

void GiveItem(int client, const char[] item)
{
	g_flOwnGive[client] = GetEngineTime();
	RunScriptF(client, "self.GenerateAndWearItem(\"%s\")", item);
	OwnItems(client);
}

/**
 * Items made by VScript GenerateAndWearItem carry account 0 and a running item ID (14, 15...),
 * while the player's own loadout items carry his account and item ID = definition index (or
 * -1 for base items) - measured on build 5205 (m_AttributeManager.m_Item netprops). The client
 * resolves a weapon through those: for a foreign account/ID it showed "#TF_Default_ItemDef"
 * (the default item) and drew the base weapon - no arms, icons, world model, sounds, its own
 * crosshair and bucket, a viewmodel flickering against the server's. Every item on a Merc is
 * stamped like a loadout item, in the same tick it is created (before it is ever networked).
 */
void OwnItems(int client)
{
	int account = OwnerAccount(client);
	if (account == 0)
	{
		Step("own items %N: account not known yet", client);
		return;
	}
	int max = GetEntPropArraySize(client, Prop_Send, "m_hMyWeapons");
	for (int i = 0; i < max; i++)
		StampItem(GetEntPropEnt(client, Prop_Send, "m_hMyWeapons", i), account);
	int ent = -1;
	while ((ent = FindEntityByClassname(ent, "tf_wearable*")) != -1)
		if (GetEntPropEnt(ent, Prop_Send, "m_hOwnerEntity") == client)
			StampItem(ent, account);
}

/** The account the player's loadout items carry (bots get a made-up one per slot). */
/**
 * The account the game itself puts on the player's loadout items: the player resource's
 * m_iAccountID (measured on 5205: loadout items and the resource agree, bots included). Humans
 * fall back to the engine's SteamID without waiting for Steam validation (after a map change a
 * player spawns before SourceMod re-validates him: GetSteamAccountID() returned 0 and the old
 * code then guessed "client - 1", stamping foreign items - the "schema falls apart after a map
 * change": Soldier arms, stock sounds, wrong buckets). Returns 0 when unknown: nothing is
 * stamped then, and the 1 s re-stamp (and OnClientAuthorized) fixes it as soon as it is known.
 */
int OwnerAccount(int client)
{
	int res = GetPlayerResourceEntity();
	int acc = (res > MaxClients && HasEntProp(res, Prop_Send, "m_iAccountID")) ? GetEntProp(res, Prop_Send, "m_iAccountID", _, client) : 0;
	if (acc == 0 && !IsFakeClient(client))
		acc = GetSteamAccountID(client, false);
	if (acc == 0 && IsFakeClient(client))
		acc = client - 1;    // what the resource holds for bots (measured), before its first think
	return acc;
}

public void OnClientAuthorized(int client, const char[] auth)
{
	if (IsMerc(client))
		OwnItems(client);
}

/** Every second: Merc items carry the account (a value that only became known later, or an
 *  item the game re-created, is corrected within a second). */
public Action Timer_Restamp(Handle timer)
{
	for (int i = 1; i <= MaxClients; i++)
		if (IsMerc(i))
			OwnItems(i);
	return Plugin_Continue;
}

void StampItem(int ent, int account)
{
	if (ent <= MaxClients || !IsValidEntity(ent) || !HasEntProp(ent, Prop_Send, "m_iAccountID"))
		return;
	int def = ItemDef(ent);
	if (def < 0 || def == 65535)
		return;
	if (GetEntProp(ent, Prop_Send, "m_iAccountID") != account)
		SetEntProp(ent, Prop_Send, "m_iAccountID", account);
	int hi = GetEntProp(ent, Prop_Send, "m_iItemIDHigh"), lo = GetEntProp(ent, Prop_Send, "m_iItemIDLow");
	if (hi == -1 && lo == -1)
		return;    // a base item: no item ID, resolved by definition
	if (hi != 0 || lo != def)
	{
		Step("item %d (def %d) id %d:%d -> 0:%d, account %d", ent, def, hi, lo, def, account);
		SetEntProp(ent, Prop_Send, "m_iItemIDHigh", 0);
		SetEntProp(ent, Prop_Send, "m_iItemIDLow", def);
	}
}

void SwitchTo(int client, int weapon)
{
	if (weapon > MaxClients)
		RunScriptF(client, "self.Weapon_Switch(EntIndexToHScript(%d))", weapon);
}

void RemoveWeapon(int client, int weapon)
{
	// A weapon's extra wearables (the medigun's backpack...) are separate entities: killing the
	// weapon alone left them on the player for good (Merc bots wore Medic backpacks).
	static const char extras[][] = { "m_hExtraWearable", "m_hExtraWearableViewModel" };
	for (int i = 0; i < sizeof(extras); i++)
	{
		if (!HasEntProp(weapon, Prop_Send, extras[i]))
			continue;
		int e = GetEntPropEnt(weapon, Prop_Send, extras[i]);
		if (e > MaxClients && IsValidEntity(e))
			RemoveEntity(e);
	}
	RemovePlayerItem(client, weapon);
	AcceptEntityInput(weapon, "Kill");
}

/** Extra wearables (no item definition) that no held weapon owns: left over from another class
 *  (a Medic turned Merc) or from a weapon he no longer has. */
void RemoveStaleWearables(int client)
{
	int owned[16], n = 0;
	int max = GetEntPropArraySize(client, Prop_Send, "m_hMyWeapons");
	for (int i = 0; i < max; i++)
	{
		int w = GetEntPropEnt(client, Prop_Send, "m_hMyWeapons", i);
		if (w <= MaxClients || !HasEntProp(w, Prop_Send, "m_hExtraWearable"))
			continue;
		int a = GetEntPropEnt(w, Prop_Send, "m_hExtraWearable"), b = GetEntPropEnt(w, Prop_Send, "m_hExtraWearableViewModel");
		if (a > MaxClients && n < sizeof(owned)) owned[n++] = a;
		if (b > MaxClients && n < sizeof(owned)) owned[n++] = b;
	}
	int ent = -1;
	while ((ent = FindEntityByClassname(ent, "tf_wearable*")) != -1)
	{
		if (GetEntPropEnt(ent, Prop_Send, "m_hOwnerEntity") != client || ItemDef(ent) != 65535)
			continue;
		bool keep = false;
		for (int i = 0; i < n && !keep; i++)
			keep = owned[i] == ent;
		if (!keep)
		{
			Step("stale wearable %d removed from %N", ent, client);
			RemoveEntity(ent);
		}
	}
}

void LoadAssets()
{
	char path[PLATFORM_MAX_PATH];
	BuildPath(Path_SM, path, sizeof(path), CFG_ASSETS);
	KeyValues kv = new KeyValues("tf2cc_tf2c_assets");
	if (kv.ImportFromFile(path))
	{
		kv.GetString("merc_model", MERC_MODEL, sizeof(MERC_MODEL), MERC_MODEL_DEFAULT);
		kv.GetString("bomblet_model", BOMBLET_MODEL, sizeof(BOMBLET_MODEL), BOMBLET_MODEL_DEFAULT);
		kv.GetString("bond_sound", BOND_SOUND, sizeof(BOND_SOUND), BOND_SOUND_DEFAULT);
	}
	else
		LogError("cannot read %s; using the default asset paths", path);
	delete kv;
}

/** The weapon's own slot (CTFWeaponBase::GetSlot through VScript): a stock item can land in
 *  another slot on the Soldier than on its owner class (an Engineer's primary shotgun is the
 *  Soldier's secondary shotgun). */
int WeaponSlot(int weapon)
{
	if (weapon <= MaxClients)
		return -1;
	g_cvRet.SetString("-1");
	RunScriptF(weapon, "Convars.SetValue(\"tf2cc_tf2c_ret\", \"\" + self.GetSlot())");
	return g_cvRet.IntValue;
}

/**
 * The slot a stock item takes when it is given to the Merc (a Soldier), known before giving so
 * that walking over it can fill an empty slot. CTFWeaponBase::GetSlot uses the item's schema
 * bucket, else the weapon script's bucket of the class the item is created as for the Soldier:
 * the multi-class shotgun becomes tf_weapon_shotgun_soldier (script bucket 1: an Engineer's
 * primary shotgun is the Soldier's secondary), the class pistols tf_weapon_pistol. A slot seen
 * at an actual give is remembered per item and wins.
 */
int MercSlotOfStock(int def, int weapon, int fallback)
{
	char key[12], cls[64], path[PLATFORM_MAX_PATH], line[256];
	IntToString(def, key, sizeof(key));
	int slot;
	if (g_StockSlot.GetValue(key, slot))
		return slot;
	GetEntityClassname(weapon, cls, sizeof(cls));
	if (StrEqual(cls, "tf_weapon_shotgun_primary") || StrEqual(cls, "tf_weapon_shotgun_hwg") || StrEqual(cls, "tf_weapon_shotgun_pyro"))
		strcopy(cls, sizeof(cls), "tf_weapon_shotgun_soldier");
	else if (StrEqual(cls, "tf_weapon_pistol_scout"))
		strcopy(cls, sizeof(cls), "tf_weapon_pistol");
	FormatEx(path, sizeof(path), "scripts/%s.txt", cls);
	File f = OpenFile(path, "r", true);
	slot = fallback;
	if (f != null)
	{
		while (f.ReadLine(line, sizeof(line)))
		{
			TrimString(line);
			if (StrContains(line, "\"bucket\"", false) != 0)
				continue;
			ReplaceString(line, sizeof(line), "\"bucket\"", "", false);
			StripQuotes(line);
			TrimString(line);
			ReplaceString(line, sizeof(line), "\"", "");
			if (IsCharNumeric(line[0]))
				slot = StringToInt(line);
			break;
		}
		delete f;
	}
	if (slot < 0 || slot >= SLOTS)
		slot = fallback;
	Step("stock slot %d (%s) for the Merc: %d", def, cls, slot);
	return slot;
}

bool WorldModelOf(int weapon, char[] out, int maxlen)
{
	int idx = GetEntProp(weapon, Prop_Send, "m_iWorldModelIndex");
	int table = FindStringTable("modelprecache");
	if (idx <= 0 || table == INVALID_STRING_TABLE)
		return false;
	ReadStringTable(table, idx, out, maxlen);
	return out[0] != '\0';
}

/* ------------------------------------------------------------------ */
/* Config                                                             */
/* ------------------------------------------------------------------ */

void LoadWeapons()
{
	delete g_WItem; delete g_WSlot; delete g_WWeight; delete g_WModel; delete g_WDef; delete g_WDefault;
	g_WItem = new ArrayList(ByteCountToCells(64));
	g_WModel = new ArrayList(ByteCountToCells(PLATFORM_MAX_PATH));
	g_WSlot = new ArrayList();
	g_WWeight = new ArrayList();
	g_WDef = new ArrayList();
	g_WDefault = new ArrayList();
	char path[PLATFORM_MAX_PATH], buf[PLATFORM_MAX_PATH];
	BuildPath(Path_SM, path, sizeof(path), CFG_WEAPONS);
	KeyValues kv = new KeyValues("tf2cc_tf2c_weapons");
	if (!kv.ImportFromFile(path) || !kv.GotoFirstSubKey())
	{
		LogError("cannot read %s", path);
		delete kv;
		return;
	}
	do
	{
		kv.GetString("item", buf, sizeof(buf));
		g_WItem.PushString(buf);
		kv.GetString("slot", buf, sizeof(buf));
		g_WSlot.Push(SlotIndex(buf));
		float weight = kv.GetFloat("pack_weight");
		char itemName[64];
		kv.GetString("item", itemName, sizeof(itemName));
		if (kv.GetNum("marxvee") && !MarxVeeEnabled(itemName))
			weight = 0.0;
		g_WWeight.Push(weight);
		kv.GetString("worldmodel", buf, sizeof(buf));
		g_WModel.PushString(buf);
		g_WDef.Push(kv.GetNum("defindex", -1));
		g_WDefault.Push(kv.GetNum("default") != 0);
	}
	while (kv.GotoNextKey());
	delete kv;
}

/** An optional MarxVee item ("tf2cc_merc_x") listed in tf2cc_marxvee_items. */
bool MarxVeeEnabled(const char[] item)
{
	char list[256], id[64];
	g_cvMarxVee.GetString(list, sizeof(list));
	strcopy(id, sizeof(id), item);
	ReplaceString(id, sizeof(id), "tf2cc_", "", false);
	Format(list, sizeof(list), " %s ", list);
	Format(id, sizeof(id), " %s ", id);
	return StrContains(list, id, false) != -1;
}

public void OnMarxVeeChanged(ConVar cv, const char[] oldValue, const char[] newValue)
{
	LoadWeapons();
}

/** defindex -> item name for every schema item (stock pickups are given by name). */
void LoadItemNames()
{
	delete g_ItemNames;
	g_ItemNames = new StringMap();
	char map[PLATFORM_MAX_PATH], files[3][PLATFORM_MAX_PATH];
	GetCurrentMap(map, sizeof(map));
	strcopy(files[0], sizeof(files[]), "scripts/items/items_game.txt");
	strcopy(files[1], sizeof(files[]), "scripts/items/custom_items_game.txt");
	FormatEx(files[2], sizeof(files[]), "scripts/items/%s_items_game.txt", map);
	char id[12], name[64];
	for (int f = 0; f < sizeof(files); f++)
	{
		KeyValues kv = new KeyValues("items_game");
		if (kv.ImportFromFile(files[f]) && kv.JumpToKey("items") && kv.GotoFirstSubKey())
		{
			do
			{
				kv.GetSectionName(id, sizeof(id));
				kv.GetString("name", name, sizeof(name));
				if (name[0] && IsCharNumeric(id[0]))
					g_ItemNames.SetString(id, name);
			}
			while (kv.GotoNextKey());
		}
		delete kv;
	}
}

void AddDownloads()
{
	char path[PLATFORM_MAX_PATH], line[PLATFORM_MAX_PATH];
	BuildPath(Path_SM, path, sizeof(path), CFG_DOWNLOADS);
	File f = OpenFile(path, "r");
	if (f == null)
		return;
	while (f.ReadLine(line, sizeof(line)))
	{
		TrimString(line);
		if (line[0] && line[0] != '/' && FileExists(line, true))
		{
			AddFileToDownloadsTable(line);
			// Raw .wav/.mp3 paths in the schema (weapon sound_*) and in the viewmodels' sound
			// events are not precached by TF2C's schema precache (PrecacheScriptSound only
			// handles script names): unprecached, the shooter's own predicted shot and melee hit
			// sounds never played. Precache every staged sound at map start.
			if (StrContains(line, "sound/") == 0)
				PrecacheSound(line[6], true);
		}
	}
	delete f;
}

void LoadVoice()
{
	if (g_Concepts != null)
	{
		StringMapSnapshot snap = g_Concepts.Snapshot();
		char key[160];
		for (int i = 0; i < snap.Length; i++)
		{
			snap.GetKey(i, key, sizeof(key));
			ArrayList l;
			g_Concepts.GetValue(key, l);
			delete l;
		}
		delete snap;
	}
	delete g_Concepts;
	delete g_PersonaSamples;
	g_Concepts = new StringMap();
	g_PersonaSamples = new StringMap();
	char path[PLATFORM_MAX_PATH];
	BuildPath(Path_SM, path, sizeof(path), CFG_VOICE);
	KeyValues kv = new KeyValues("tf2cc_voice");
	if (!kv.ImportFromFile(path))
	{
		LogError("cannot read %s", path);
		delete kv;
		return;
	}
	if (kv.JumpToKey("mercenary"))
	{
		ReadConceptLists(kv, "mercenary", true);
		kv.GoBack();
	}
	if (kv.JumpToKey("targeted") && kv.GotoFirstSubKey())
	{
		char speaker[32], role[32], prefix[96];
		do
		{
			kv.GetSectionName(speaker, sizeof(speaker));
			if (kv.GotoFirstSubKey())
			{
				do
				{
					kv.GetSectionName(role, sizeof(role));
					// KeyValues key names are interned case-insensitively: "civilian" can
					// come back as "Civilian" when another KeyValues used that spelling first.
					FormatEx(prefix, sizeof(prefix), "@targeted/%s/%s", speaker, role);
					for (int i = 0; prefix[i]; i++)
						prefix[i] = CharToLower(prefix[i]);
					ReadConceptLists(kv, prefix, false);
				}
				while (kv.GotoNextKey());
				kv.GoBack();
			}
		}
		while (kv.GotoNextKey());
	}
	delete kv;
}

/** Each subsection of the current key = concept -> numbered samples. */
void ReadConceptLists(KeyValues kv, const char[] prefix, bool persona)
{
	if (!kv.GotoFirstSubKey())
		return;
	char concept[64], key[160], sample[PLATFORM_MAX_PATH];
	do
	{
		kv.GetSectionName(concept, sizeof(concept));
		for (int i = 0; concept[i]; i++)
			concept[i] = CharToLower(concept[i]);
		ArrayList list = new ArrayList(ByteCountToCells(PLATFORM_MAX_PATH));
		if (kv.GotoFirstSubKey(false))
		{
			do
			{
				kv.GetString(NULL_STRING, sample, sizeof(sample));
				if (sample[0])
				{
					list.PushString(sample);
					if (persona)
						g_PersonaSamples.SetValue(sample, true);
				}
			}
			while (kv.GotoNextKey(false));
			kv.GoBack();
		}
		FormatEx(key, sizeof(key), "%s/%s", prefix, concept);
		if (!persona)
			Step("voice key %s (%d)", key, list.Length);
		g_Concepts.SetValue(key, list);
	}
	while (kv.GotoNextKey());
	kv.GoBack();
}

void PrecacheVoice()
{
	StringMapSnapshot snap = g_Concepts.Snapshot();
	char key[160], sample[PLATFORM_MAX_PATH];
	for (int i = 0; i < snap.Length; i++)
	{
		snap.GetKey(i, key, sizeof(key));
		ArrayList l;
		g_Concepts.GetValue(key, l);
		for (int j = 0; j < l.Length; j++)
		{
			l.GetString(j, sample, sizeof(sample));
			PrecacheSound(sample, true);
		}
	}
	delete snap;
}

public Action Cmd_Reload(int client, int args)
{
	LoadWeapons();
	LoadVoice();
	PrecacheVoice();
	LoadItemNames();
	ReplyToCommand(client, "[tf2cc] reloaded: %d Merc weapons", g_WItem.Length);
	return Plugin_Handled;
}

/* ------------------------------------------------------------------ */
/* Role                                                               */
/* ------------------------------------------------------------------ */

public Action Cmd_Merc(int client, int args)
{
	if (!client || !g_cvEnabled.BoolValue)
		return Plugin_Handled;
	if (g_bMapExempt)
	{
		PrintToChat(client, "[tf2cc] The Mercenary is off on this map (it already plays him).");
		return Plugin_Handled;
	}
	g_bExplicit[client] = true;
	SetWant(client, !g_bWant[client]);
	PrintToChat(client, "[tf2cc] %s", g_bWant[client] ? "You will play the Mercenary." : "You will no longer play the Mercenary.");
	if (g_bWant[client])
		SchemaHint(client);
	return Plugin_Handled;
}

public Action Cmd_SetMerc(int client, int args)
{
	if (g_bMapExempt)
		ReplyToCommand(client, "[tf2cc] Note: the Mercenary is off on this map; the choice applies from the next normal map.");
	if (args < 2)
	{
		ReplyToCommand(client, "Usage: sm_setmerc <target> <0|1>");
		return Plugin_Handled;
	}
	char pattern[64], val[4], name[64];
	GetCmdArg(1, pattern, sizeof(pattern));
	GetCmdArg(2, val, sizeof(val));
	int targets[MAXPLAYERS];
	bool ml;
	int n = ProcessTargetString(pattern, client, targets, sizeof(targets), 0, name, sizeof(name), ml);
	for (int i = 0; i < n; i++)
	{
		g_bBotRolled[targets[i]] = g_bExplicit[targets[i]] = true;
		SetWant(targets[i], StringToInt(val) != 0);
	}
	ReplyToCommand(client, "[tf2cc] Mercenary %s for %d player(s)", StringToInt(val) ? "on" : "off", n);
	return Plugin_Handled;
}

/** Merc weapons render from the client's copy of the custom item schema, and a game client
 *  never re-downloads a file it already has: an older copy (or another server's) shows the
 *  items as "#TF_Default_ItemDef", without arms, icons, world models or custom sounds. */
void SchemaHint(int client)
{
	if (g_bSchemaHinted[client] || IsFakeClient(client))
		return;
	g_bSchemaHinted[client] = true;
	PrintToChat(client, "[tf2cc] If Merc weapons show '#TF_Default_ItemDef' or have no arms/icons/sounds: quit, delete tf2classified/download/scripts/items/custom_items_game.txt (and custom_level_sounds.txt) and rejoin.");
}

/* OF talker PlayerRespawnMercenary / PlayerRespawnKilledMercenary (as tf2cc on stock TF2): 30%
 * of spawns, 0.5 s in, "_respawnkilled" after a death (else, or as fallback, "_respawn"). Merc
 * persona lines only; any Soldier line from the game is rewritten or blocked by Hook_Sound. */
void RespawnLine(int client)
{
	bool killed = g_bDiedLastLife[client];
	g_bDiedLastLife[client] = false;
	if (GetURandomFloat() >= 0.3)
		return;
	DataPack dp;
	CreateDataTimer(0.5, Timer_RespawnLine, dp, TIMER_FLAG_NO_MAPCHANGE);
	dp.WriteCell(GetClientUserId(client));
	dp.WriteCell(killed);
}

public Action Timer_RespawnLine(Handle timer, DataPack dp)
{
	dp.Reset();
	int client = GetClientOfUserId(dp.ReadCell());
	bool killed = dp.ReadCell() != 0;
	if (IsMerc(client) && !(killed && Speak(client, "_respawnkilled")))
		Speak(client, "_respawn");
	return Plugin_Stop;
}

/** Choose (or drop) the Mercenary; a living player is respawned as one. */
void SetWant(int client, bool want)
{
	Step("SetWant %N %d", client, want);
	g_bWant[client] = want;
	g_bBotRolled[client] = true;    // an explicit choice is never overwritten by the bot roll
	if (!IsClientInGame(client) || GetClientTeam(client) < 2)
		return;
	if (want)
	{
		if (IsFakeClient(client))
		{
			// The respawn below is ours: the bot keeps the class it plays now for the roster.
			int cls = view_as<int>(TF2_GetPlayerClass(client));
			g_iBotPick[client] = cls != view_as<int>(TFClass_Soldier) ? cls : 0;
			g_bBotConverting[client] = true;
			g_bBotSoldierLife[client] = false;
		}
		ForceSoldier(client);
		if (IsPlayerAlive(client))
			TF2_RespawnPlayer(client);
	}
	else if (g_bMerc[client] && IsPlayerAlive(client))
	{
		TF2_RespawnPlayer(client);
	}
}

void ForceSoldier(int client)
{
	RunScriptF(client, "self.SetPlayerClass(3); NetProps.SetPropInt(self, \"m_Shared.m_iDesiredPlayerClass\", 3)");
}

/** "joinclass mercenary" (or merc) picks the Mercenary like !merc; any other class leaves him. */
public Action Listener_JoinClass(int client, const char[] command, int argc)
{
	if (!client)
		return Plugin_Continue;
	char arg[32];
	GetCmdArg(1, arg, sizeof(arg));
	if (g_bInternalJoin[client])
		return Plugin_Continue;
	if (StrEqual(arg, "mercenary", false) || StrEqual(arg, "merc", false))
	{
		if (g_bMapExempt)
			PrintToChat(client, "[tf2cc] The Mercenary is off on this map (it already plays him).");
		else if (g_cvEnabled.BoolValue)
		{
			g_bExplicit[client] = true;
			SetWant(client, true);
		}
		return Plugin_Handled;
	}
	// Random in the class menu: tf2cc's menu, as on stock TF2 (Mercenary / Random with him / game random).
	if ((StrEqual(arg, "random", false) || StrEqual(arg, "auto", false)) && MercAllowed() && g_cvRandomMenu.BoolValue
		&& !IsFakeClient(client) && GetClientTeam(client) >= 2)
	{
		ShowRandomMenu(client);
		return Plugin_Handled;
	}
	if (g_bWant[client] && !IsFakeClient(client))
		g_bWant[client] = false;
	return Plugin_Continue;
}

void ShowRandomMenu(int client)
{
	Menu menu = new Menu(Menu_Random);
	menu.SetTitle("Random class");
	menu.AddItem("merc", "Mercenary");
	menu.AddItem("any", "Random (Mercenary included)");
	menu.AddItem("game", "Random (game classes only)");
	menu.ExitButton = true;
	menu.Display(client, 20);
}

public int Menu_Random(Menu menu, MenuAction action, int client, int item)
{
	if (action == MenuAction_End)
		delete menu;
	else if (action == MenuAction_Select && IsClientInGame(client))
	{
		char info[8];
		menu.GetItem(item, info, sizeof(info));
		ConVar special = FindConVar("tf2c_allow_special_classes");
		int classes = 9 + ((special == null || special.BoolValue) ? 1 : 0);   // + Civilian
		bool merc = StrEqual(info, "merc") || (StrEqual(info, "any") && GetURandomFloat() * float(classes + 1) < 1.0);
		g_bExplicit[client] = true;
		if (merc && MercAllowed())
		{
			SetWant(client, true);
			PrintToChat(client, "[tf2cc] Random: Mercenary.");
		}
		else
		{
			g_bWant[client] = false;
			g_bInternalJoin[client] = true;
			FakeClientCommand(client, "joinclass random");
			g_bInternalJoin[client] = false;
		}
	}
	return 0;
}

public void Event_Spawn(Event event, const char[] name, bool dontBroadcast)
{
	int client = GetClientOfUserId(event.GetInt("userid"));
	if (!client || GetClientTeam(client) < 2)
		return;
	g_bFreshLife[client] = true;
	ChainsawReset(client);
	g_bDiedLastLife[client] = g_bMercCorpse[client];
	g_bMercCorpse[client] = false;
	EndTaunt(client);
	// Bot random loadouts and some regenerates land after post_inventory_application:
	// re-check the Mercenary's inventory a little later.
	CreateTimer(0.6, Timer_Recheck, GetClientUserId(client), TIMER_FLAG_NO_MAPCHANGE);
	CreateTimer(1.5, Timer_Recheck, GetClientUserId(client), TIMER_FLAG_NO_MAPCHANGE);
	if (IsFakeClient(client) && !g_bBotRolled[client])
	{
		g_bBotRolled[client] = true;
		g_bWant[client] = g_cvEnabled.BoolValue && GetURandomFloat() < g_cvBotChance.FloatValue;   // kept off-map: the next normal map applies it
		Step("bot roll %N: %s (chance %.2f)", client, g_bWant[client] ? "Mercenary" : "no", g_cvBotChance.FloatValue);
	}
	if (IsFakeClient(client) && g_bWant[client] && MercAllowed())
	{
		int cls = view_as<int>(TF2_GetPlayerClass(client));
		if (g_bBotConverting[client] && cls == view_as<int>(TFClass_Soldier))
		{
			// Our respawn as the Merc: the roster keeps counting him as his AI's pick.
			g_bBotConverting[client] = false;
			if (g_iBotPick[client] > 0)
				RunScriptF(client, "NetProps.SetPropInt(self, \"m_Shared.m_iDesiredPlayerClass\", %d)", g_iBotPick[client]);
			Step("bot %N: Mercenary, counted by the bot roster as class %d", client, g_iBotPick[client]);
			return;
		}
		g_bBotConverting[client] = false;
		// (a bot made a Merc by an admin, sm_setmerc, stays one whatever its AI chose)
		g_bBotSoldierLife[client] = cls == view_as<int>(TFClass_Soldier) && !g_bExplicit[client];
		if (cls == view_as<int>(TFClass_Soldier) && g_bExplicit[client])
			return;
		if (g_bBotSoldierLife[client])
		{
			Step("bot %N: the bot AI chose Soldier, an ordinary Soldier this life", client);
			return;
		}
		g_iBotPick[client] = cls;
		g_bBotConverting[client] = true;
		// The desired class stays the pick until the respawn itself (Frame_BotConvert), so no
		// other bot choosing its class in between sees an extra Soldier.
		RequestFrame(Frame_BotConvert, GetClientUserId(client));
		return;
	}
	if (g_bWant[client] && MercAllowed() && TF2_GetPlayerClass(client) != TFClass_Soldier)
	{
		ForceSoldier(client);
		RequestFrame(Frame_Respawn, GetClientUserId(client));
	}
}

public Action Timer_Recheck(Handle timer, int userid)
{
	int client = GetClientOfUserId(userid);
	if (IsMerc(client) && !InventoryMatches(client))
	{
		Step("recheck %N: inventory replaced, re-applying", client);
		ApplyMerc(client);
	}
	if (IsMerc(client))
		OwnItems(client);
	return Plugin_Stop;
}

/** The Merc holds his inventory's items in each slot and wears exactly one body item. */
bool InventoryMatches(int client)
{
	if (CountBody(client) != 1)
		return false;
	char key[12], name[64];
	for (int s = 0; s < SLOTS; s++)
	{
		int w = GetPlayerWeaponSlot(client, s);
		if (!g_sInv[client][s][0])
		{
			if (w > MaxClients)
				return false;
			continue;
		}
		if (w <= MaxClients)
			return false;
		IntToString(ItemDef(w), key, sizeof(key));
		if (!g_ItemNames.GetString(key, name, sizeof(name)) || !StrEqual(name, g_sInv[client][s]))
			return false;
	}
	return true;
}

/** Resupply lockers: re-check after a touch (a regenerate can replace his items). */
public void Hook_RegenTouch(int entity, int other)
{
	if (other >= 1 && other <= MaxClients && g_bMerc[other])
		CreateTimer(0.3, Timer_Recheck, GetClientUserId(other), TIMER_FLAG_NO_MAPCHANGE);
}

public void Frame_BotConvert(int userid)
{
	int client = GetClientOfUserId(userid);
	if (!client || !IsPlayerAlive(client) || !g_bBotConverting[client])
		return;
	ForceSoldier(client);           // desired class 3 only for this respawn:
	TF2_RespawnPlayer(client);      // Event_Spawn (synchronous) puts the pick back
}

public void Frame_Respawn(int userid)
{
	int client = GetClientOfUserId(userid);
	if (client && IsPlayerAlive(client))
		TF2_RespawnPlayer(client);
}

public void Event_Inventory(Event event, const char[] name, bool dontBroadcast)
{
	int client = GetClientOfUserId(event.GetInt("userid"));
	if (client && GetEngineTime() - g_flOwnGive[client] > 0.25)
		RequestFrame(Frame_Apply, GetClientUserId(client));
}

public void Frame_Apply(int userid)
{
	int client = GetClientOfUserId(userid);
	Step("Frame_Apply %d", client);
	if (!client || !IsPlayerAlive(client))
		return;
	bool fresh = g_bFreshLife[client];
	g_bFreshLife[client] = false;
	bool merc = g_bWant[client] && MercAllowed() && TF2_GetPlayerClass(client) == TFClass_Soldier
		&& !(IsFakeClient(client) && g_bBotSoldierLife[client]);
	if (!merc)
	{
		if (g_bMerc[client])
		{
			g_bMerc[client] = false;
			ChainsawReset(client);
			SetVariantString("");
			AcceptEntityInput(client, "SetCustomModel");
		}
		StripMercItems(client);
		return;
	}
	g_bMerc[client] = true;
	if (fresh)
	{
		for (int s = 0; s < SLOTS; s++)
			g_sInv[client][s][0] = '\0';
		DefaultInventory(client);
		RespawnLine(client);
	}
	ApplyMerc(client);
}

/** A non-Mercenary never keeps Merc items (e.g. carried over a class change): regenerate. */
void StripMercItems(int client)
{
	int max = GetEntPropArraySize(client, Prop_Send, "m_hMyWeapons");
	bool found = false;
	for (int i = 0; i < max && !found; i++)
	{
		int w = GetEntPropEnt(client, Prop_Send, "m_hMyWeapons", i);
		found = w > MaxClients && MercWeaponIndex(ItemDef(w)) >= 0;
	}
	int ent = -1;
	while (!found && (ent = FindEntityByClassname(ent, "tf_wearable")) != -1)
		found = GetEntPropEnt(ent, Prop_Send, "m_hOwnerEntity") == client && ItemDef(ent) == BodyDef();
	if (!found || GetEngineTime() - g_flStripAt[client] < 1.0)   // never loop with Regenerate
		return;
	g_flStripAt[client] = GetEngineTime();
	Step("strip Merc items from %N", client);
	for (int s = 0; s < SLOTS; s++)
		g_sInv[client][s][0] = '\0';
	ent = -1;
	while ((ent = FindEntityByClassname(ent, "tf_wearable")) != -1)
		if (GetEntPropEnt(ent, Prop_Send, "m_hOwnerEntity") == client && ItemDef(ent) == BodyDef())
			RemoveEntity(ent);
	for (int i = 0; i < max; i++)
	{
		int w = GetEntPropEnt(client, Prop_Send, "m_hMyWeapons", i);
		if (w > MaxClients && MercWeaponIndex(ItemDef(w)) >= 0)
			RemoveWeapon(client, w);
	}
	RunScriptF(client, "self.Regenerate(true)");
}

void DefaultInventory(int client)
{
	char item[64];
	for (int i = 0; i < g_WItem.Length; i++)
	{
		if (!g_WDefault.Get(i))
			continue;
		int s = g_WSlot.Get(i);
		g_WItem.GetString(i, item, sizeof(item));
		strcopy(g_sInv[client][s], sizeof(g_sInv[][]), item);
	}
}

/** Model, body item and the held inventory (re-applied after every resupply). Items already
 *  correct are left alone and the weapon in hand stays in hand: re-giving a matching item
 *  replaced the entity and the old code then drew the first slot (involuntary switches). */
void ApplyMerc(int client)
{
	Step("apply %N: model", client);
	SetVariantString(MERC_MODEL);
	AcceptEntityInput(client, "SetCustomModelWithClassAnimations");
	if (CountBody(client) == 0)
	{
		Step("body");
		GiveItem(client, BODY_ITEM);
	}
	RemoveStaleWearables(client);
	int active = GetEntPropEnt(client, Prop_Send, "m_hActiveWeapon");
	int activeSlot = SlotOfWeapon(client, active);
	char key[12], name[64];
	for (int s = 0; s < SLOTS; s++)
	{
		int w = GetPlayerWeaponSlot(client, s);
		if (g_sInv[client][s][0])
		{
			if (w > MaxClients)
			{
				IntToString(ItemDef(w), key, sizeof(key));
				if (g_ItemNames.GetString(key, name, sizeof(name)) && StrEqual(name, g_sInv[client][s]))
					continue;    // already holds it
				RemoveWeapon(client, w);
			}
			Step("give slot %d %s", s, g_sInv[client][s]);
			GiveItem(client, g_sInv[client][s]);
		}
		else if (w > MaxClients)
		{
			Step("slot %d: remove %d", s, w);
			RemoveWeapon(client, w);
		}
	}
	KeepInHand(client, active, activeSlot);
	Step("done");
	CreateTimer(0.1, Timer_FillHealth, GetClientUserId(client), TIMER_FLAG_NO_MAPCHANGE);
}

/** Slot (0-2) holding this weapon, or -1. */
int SlotOfWeapon(int client, int weapon)
{
	if (weapon <= MaxClients)
		return -1;
	for (int s = 0; s < SLOTS; s++)
		if (GetPlayerWeaponSlot(client, s) == weapon)
			return s;
	return -1;
}

/** After items changed: the weapon that was in hand stays drawn; if it was replaced, its
 *  slot's new weapon is drawn; only with nothing in hand is the first filled slot drawn. */
void KeepInHand(int client, int was, int wasSlot)
{
	int now = GetEntPropEnt(client, Prop_Send, "m_hActiveWeapon");
	int want = -1;
	if (was > MaxClients && IsValidEntity(was) && SlotOfWeapon(client, was) >= 0)
		want = was;
	else if (wasSlot >= 0)
		want = GetPlayerWeaponSlot(client, wasSlot);
	if (want <= MaxClients && now > MaxClients && SlotOfWeapon(client, now) >= 0)
		return;    // nothing to restore and he holds a weapon
	for (int s = 0; s < SLOTS && want <= MaxClients; s++)
		want = GetPlayerWeaponSlot(client, s);
	if (want > MaxClients && want != now)
	{
		Step("keep in hand %N: %d -> %d", client, now, want);
		SwitchTo(client, want);
	}
}

/** Body wearables on the player (exactly one is wanted: each stacks health/speed). */
int CountBody(int client, bool removeExtra = false)
{
	int n = 0, ent = -1;
	while ((ent = FindEntityByClassname(ent, "tf_wearable")) != -1)
	{
		if (GetEntPropEnt(ent, Prop_Send, "m_hOwnerEntity") != client || g_WDef == null || ItemDef(ent) != BodyDef())
			continue;
		if (++n > 1 && removeExtra)
			RemoveEntity(ent);
	}
	return n;
}

int BodyDef()
{
	static int def = -1;
	if (def == -1)
	{
		def = g_WDef.Length ? g_WDef.Get(0) - 1 : -1;   // generated: body = first weapon id - 1
		for (int i = 0; i < g_WDef.Length; i++)
			if (g_WDef.Get(i) - 1 < def)
				def = g_WDef.Get(i) - 1;
	}
	return def;
}

public Action Timer_FillHealth(Handle timer, int userid)
{
	int client = GetClientOfUserId(userid);
	if (IsMerc(client))
	{
		CountBody(client, true);
		// m_iMaxHealth is the class base (200): attributes apply on top, so it overhealed him.
		int res = GetPlayerResourceEntity();
		int max = res > 0 ? GetEntProp(res, Prop_Send, "m_iMaxHealth", _, client) : 0;
		if (max > 0 && GetClientHealth(client) < max)
			SetEntityHealth(client, max);
	}
	return Plugin_Stop;
}

public Action Cmd_GiveMerc(int client, int args)
{
	char pattern[64], wid[64], item[64], name[64];
	GetCmdArg(1, pattern, sizeof(pattern));
	GetCmdArg(2, wid, sizeof(wid));
	FormatEx(item, sizeof(item), "tf2cc_%s", wid);
	int idx = g_WItem.FindString(item);
	int stockDef = -1, stockSlot = -1;
	if (idx < 0)
	{
		// Any schema item by name (stock pickups): "<item name> <slot 0-2>".
		char slotArg[4], key[12], name2[64];
		GetCmdArg(3, slotArg, sizeof(slotArg));
		StringMapSnapshot snap = g_ItemNames.Snapshot();
		for (int k = 0; k < snap.Length && stockDef < 0; k++)
		{
			snap.GetKey(k, key, sizeof(key));
			g_ItemNames.GetString(key, name2, sizeof(name2));
			if (StrEqual(name2, wid, false))
				stockDef = StringToInt(key);
		}
		delete snap;
		stockSlot = slotArg[0] ? StringToInt(slotArg) : 0;
		if (stockDef < 0)
		{
			ReplyToCommand(client, "unknown Merc weapon or item %s", wid);
			return Plugin_Handled;
		}
		strcopy(item, sizeof(item), wid);
	}
	int targets[MAXPLAYERS];
	bool ml;
	int n = ProcessTargetString(pattern, client, targets, sizeof(targets), COMMAND_FILTER_ALIVE, name, sizeof(name), ml);
	for (int i = 0; i < n; i++)
	{
		if (!g_bMerc[targets[i]])
			continue;
		PickupData d;
		d.def = idx >= 0 ? g_WDef.Get(idx) : stockDef;
		d.slot = idx >= 0 ? g_WSlot.Get(idx) : stockSlot;
		strcopy(d.item, sizeof(d.item), item);
		TakeWeapon(targets[i], d, true);
	}
	return Plugin_Handled;
}

/* ------------------------------------------------------------------ */
/* Pickups                                                            */
/* ------------------------------------------------------------------ */

int SpawnPickup(PickupData d, const char[] model, const float pos[3], const float vel[3], int skin)
{
	if (!model[0])
		return -1;
	if (!IsModelPrecached(model))
		PrecacheModel(model, true);
	int prop = CreateEntityByName("prop_physics_override");
	if (prop == -1)
		return -1;
	DispatchKeyValue(prop, "model", model);
	DispatchKeyValue(prop, "spawnflags", "4");   // debris: players walk through it
	if (!DispatchSpawn(prop))
	{
		RemoveEntity(prop);
		return -1;
	}
	SetEntProp(prop, Prop_Send, "m_CollisionGroup", COLLISION_GROUP_DEBRIS);
	SetEntProp(prop, Prop_Send, "m_nSkin", skin);
	TeleportEntity(prop, pos, NULL_VECTOR, vel);
	char key[12];
	IntToString(EntIndexToEntRef(prop), key, sizeof(key));
	g_Pickups.SetArray(key, d, sizeof(d));
	CreateTimer(g_cvLifetime.FloatValue, Timer_Expire, EntIndexToEntRef(prop), TIMER_FLAG_NO_MAPCHANGE);
	// Debris props slide a long way on smooth floors (a thrown weapon ended up 800+ u away,
	// out of reach of USE): pin it once it has landed.
	if (prop < sizeof(g_vSettle))
		g_vSettle[prop] = pos;
	CreateTimer(0.5, Timer_Settle, EntIndexToEntRef(prop), TIMER_FLAG_NO_MAPCHANGE);
	return prop;
}

public Action Timer_Expire(Handle timer, int ref)
{
	int prop = EntRefToEntIndex(ref);
	char key[12];
	IntToString(ref, key, sizeof(key));
	g_Pickups.Remove(key);
	if (prop > MaxClients)
		RemoveEntity(prop);
	return Plugin_Stop;
}

/** Pins a pickup once it stops moving (position unchanged for 0.3 s; vphysics props do not
 *  keep m_vecVelocity up to date). */
public Action Timer_Settle(Handle timer, int ref)
{
	int prop = EntRefToEntIndex(ref);
	if (prop <= MaxClients || prop >= sizeof(g_vSettle))
		return Plugin_Stop;
	float p[3];
	GetEntPropVector(prop, Prop_Data, "m_vecAbsOrigin", p);
	if (GetVectorDistance(p, g_vSettle[prop]) > 2.0)
	{
		g_vSettle[prop] = p;
		CreateTimer(0.3, Timer_Settle, ref, TIMER_FLAG_NO_MAPCHANGE);
		return Plugin_Stop;
	}
	AcceptEntityInput(prop, "DisableMotion");
	return Plugin_Stop;
}

/** Drops a held weapon as a pickup (death or swap). */
int DropWeapon(int client, int weapon, int slot, bool death)
{
	int def = ItemDef(weapon);
	PickupData d;
	if (def < 0 || !ItemName(def, d.item, sizeof(d.item)))
		return -1;
	char model[PLATFORM_MAX_PATH];
	int mi = MercWeaponIndex(def);
	if (mi >= 0)
		g_WModel.GetString(mi, model, sizeof(model));
	if (!model[0] && !WorldModelOf(weapon, model, sizeof(model)))
		return -1;
	d.def = def;
	d.slot = mi >= 0 ? slot : MercSlotOfStock(def, weapon, slot);
	d.dropper = GetClientUserId(client);
	d.readyAt = GetGameTime() + (death ? 0.0 : 1.5);
	float pos[3], ang[3], fwd[3], vel[3];
	GetClientEyePosition(client, pos);
	GetClientEyeAngles(client, ang);
	GetAngleVectors(ang, fwd, NULL_VECTOR, NULL_VECTOR);
	pos[2] -= 16.0;
	ScaleVector(fwd, death ? 60.0 : 150.0);
	vel = fwd;
	vel[2] += 120.0;
	// Team-coloured weapons keep the holder's skin (BLU umbrella, australiums...).
	int skin = GetEntProp(weapon, Prop_Send, "m_nSkin");
	return SpawnPickup(d, model, pos, vel, skin);
}

public Action Timer_PickupScan(Handle timer)
{
	StringMapSnapshot snap = g_Pickups.Snapshot();
	if (snap.Length == 0)
	{
		delete snap;
		return Plugin_Continue;
	}
	char key[12];
	for (int c = 1; c <= MaxClients; c++)
	{
		if (!IsMerc(c))
			continue;
		float org[3];
		GetClientAbsOrigin(c, org);
		org[2] += 24.0;
		for (int i = 0; i < snap.Length; i++)
		{
			snap.GetKey(i, key, sizeof(key));
			int prop = EntRefToEntIndex(StringToInt(key));
			if (prop <= MaxClients)
				continue;
			float p[3];
			GetEntPropVector(prop, Prop_Data, "m_vecAbsOrigin", p);
			if (GetVectorDistance(org, p) > 64.0)
				continue;
			PickupData d;
			g_Pickups.GetArray(key, d, sizeof(d));
			if (GetGameTime() < d.readyAt && GetClientUserId(c) == d.dropper)
				continue;
			int cur = GetPlayerWeaponSlot(c, d.slot);
			if (cur > MaxClients && ItemDef(cur) == d.def)
				continue;   // already has it
			// Walking over a weapon only fills an EMPTY slot: it never replaces anything, not even
			// the default pistol/crowbar (an ammo pack's weapon took the pistol away). Swaps are USE.
			// Stock weapons too: d.slot is the slot the item takes on the Merc (MercSlotOfStock).
			bool empty = cur <= MaxClients && d.slot >= 0;
			if ((empty && g_cvAutoEmpty.BoolValue) || (IsFakeClient(c) && GetURandomFloat() < g_cvBotSwap.FloatValue))
			{
				TakePickup(c, prop, key, d, false);
				break;
			}
			if (!IsFakeClient(c) && GetGameTime() >= g_flNextHint[c])
			{
				g_flNextHint[c] = GetGameTime() + 2.0;
				PrintHintText(c, "Press USE or INSPECT to swap weapons");
			}
		}
	}
	delete snap;
	return Plugin_Continue;
}

void TakePickup(int client, int prop, const char[] key, PickupData d, bool pressed)
{
	g_Pickups.Remove(key);
	RemoveEntity(prop);
	TakeWeapon(client, d, pressed);
}

/**
 * One weapon per slot: the held non-default weapon is dropped, the new one given.
 * The weapon in hand stays in hand unless the new one replaces it (same slot) or the hands
 * were empty; tf2cc_pickup_autoswitch 1 draws every pickup like OF's of_autoswitchweapons
 * (not while attacking; bots never, as in OF).
 */
void TakeWeapon(int client, PickupData d, bool pressed)
{
	int active = GetEntPropEnt(client, Prop_Send, "m_hActiveWeapon");
	int activeSlot = SlotOfWeapon(client, active);
	// Merc items have a known slot. A stock item is given first and then placed by the slot
	// it actually took: recording the dropper's slot made the inventory check and the item
	// fight over two slots (a picked-up shotgun flipped between items and never fired).
	bool known = MercWeaponIndex(d.def) >= 0;
	int cur = known ? GetPlayerWeaponSlot(client, d.slot) : -1;
	if (cur > MaxClients && !IsDefaultItem(ItemDef(cur)))
		DropWeapon(client, cur, d.slot, false);
	if (cur > MaxClients)
		RemoveWeapon(client, cur);
	GiveItem(client, d.item);
	int fresh = FindNewestWeaponByDef(client, d.def);
	if (!known && fresh > MaxClients)
	{
		int real = WeaponSlot(fresh);
		if (real >= 0 && real < SLOTS)
		{
			int max = GetEntPropArraySize(client, Prop_Send, "m_hMyWeapons");
			for (int i = 0; i < max; i++)
			{
				int w = GetEntPropEnt(client, Prop_Send, "m_hMyWeapons", i);
				if (w <= MaxClients || w == fresh || WeaponSlot(w) != real)
					continue;
				if (!IsDefaultItem(ItemDef(w)))
					DropWeapon(client, w, real, false);
				RemoveWeapon(client, w);
			}
			char key[12];
			IntToString(d.def, key, sizeof(key));
			g_StockSlot.SetValue(key, real);
			if (real != d.slot)
				Step("take %N: %s goes to slot %d (predicted slot %d)", client, d.item, real, d.slot);
			d.slot = real;
		}
	}
	strcopy(g_sInv[client][d.slot], sizeof(g_sInv[][]), d.item);
	bool draw = activeSlot < 0 || activeSlot == d.slot;
	if (!draw && g_cvAutoSwitch.BoolValue && !IsFakeClient(client) && !(GetClientButtons(client) & IN_ATTACK))
		draw = true;
	Step("take %N: %s slot %d (%s, in hand slot %d) -> %s", client, d.item, d.slot, pressed ? "pressed" : "touch", activeSlot, draw ? "draw" : "keep");
	if (draw)
		SwitchTo(client, fresh);
	else
		KeepInHand(client, active, activeSlot);
	EmitSoundToAll(PICKUP_SOUND, client);
}

bool TrySwapNearby(int client)
{
	if (!IsMerc(client))
		return false;
	// A weapon at his feet (within 96 u around him, from 24 u below his feet to his eyes) or
	// one he looks at within 160 u; the closest to his crosshair line wins. (The old test
	// measured from the eyes and missed weapons lying a step away.)
	float eye[3], feet[3], ang[3], fwd[3];
	GetClientEyePosition(client, eye);
	GetClientAbsOrigin(client, feet);
	GetClientEyeAngles(client, ang);
	GetAngleVectors(ang, fwd, NULL_VECTOR, NULL_VECTOR);
	StringMapSnapshot snap = g_Pickups.Snapshot();
	char key[12], bestKey[12];
	float best = 1.0e9;
	int bestProp = -1;
	for (int i = 0; i < snap.Length; i++)
	{
		snap.GetKey(i, key, sizeof(key));
		int prop = EntRefToEntIndex(StringToInt(key));
		if (prop <= MaxClients)
			continue;
		float p[3], d2[3], to[3];
		GetEntPropVector(prop, Prop_Data, "m_vecAbsOrigin", p);
		d2[0] = p[0] - feet[0];
		d2[1] = p[1] - feet[1];
		bool near = SquareRoot(d2[0] * d2[0] + d2[1] * d2[1]) <= 96.0 && p[2] >= feet[2] - 24.0 && p[2] <= eye[2] + 8.0;
		MakeVectorFromPoints(eye, p, to);
		float dist = GetVectorLength(to);
		NormalizeVector(to, to);
		float dot = GetVectorDotProduct(to, fwd);
		bool aimed = dist <= 160.0 && dot > 0.85;
		Step("use %N: pickup %d horiz %.0f dz %.0f dist %.0f dot %.2f -> %s", client, prop,
			SquareRoot(d2[0] * d2[0] + d2[1] * d2[1]), p[2] - feet[2], dist, dot, (near || aimed) ? "in reach" : "out of reach");
		if (!near && !aimed)
			continue;
		float score = dist * (2.0 - dot);
		if (score < best)
		{
			best = score;
			bestProp = prop;
			strcopy(bestKey, sizeof(bestKey), key);
		}
	}
	delete snap;
	if (bestProp == -1)
		return false;
	PickupData d;
	g_Pickups.GetArray(bestKey, d, sizeof(d));
	if (GetGameTime() < d.readyAt && GetClientUserId(client) == d.dropper)
		return false;
	TakePickup(client, bestProp, bestKey, d, true);
	return true;
}

public Action Listener_Inspect(int client, const char[] command, int argc)
{
	return (client && TrySwapNearby(client)) ? Plugin_Handled : Plugin_Continue;
}

/* ------------------------------------------------------------------ */
/* MarxVee Medkit (stock tf2cc "medkit_pf2", PF2 CTFSyringe):          */
/* a swing every 0.8 s (the viewmodel's "hit" sequence fitted into     */
/* it); a teammate in reach (48) is cleansed and healed 50 (no         */
/* overheal), an enemy takes 50 and an infection (8 every 2 s, 14 s).  */
/* The item's base melee never swings by itself (held off) and deals   */
/* nothing; its swing sounds are silent.                               */
/* ------------------------------------------------------------------ */
#define MEDKIT_ITEM "tf2cc_merc_medkit"
#define MEDKIT_HEAL_SOUND "items/smallmedkit1.wav"
ConVar g_cvMkDelay, g_cvMkHeal, g_cvMkDamage, g_cvMkRange, g_cvMkInfectTime, g_cvMkInfectDmg, g_cvMkInfectTick;
float g_flMkNext[MAXPLAYERS + 1];
float g_flInfectEnd[MAXPLAYERS + 1], g_flInfectTick[MAXPLAYERS + 1];
int g_iInfector[MAXPLAYERS + 1];

void MedkitInit()
{
	g_cvMkDelay = CreateConVar("tf2cc_medkit_pf2_delay", "0.8", "Medkit swing delay (PF2 syringe TimeFireDelay 0.8).", _, true, 0.1);
	g_cvMkHeal = CreateConVar("tf2cc_medkit_pf2_heal", "50", "Medkit heal per hit on a teammate (PF2 Heal 50).", _, true, 0.0);
	g_cvMkDamage = CreateConVar("tf2cc_medkit_pf2_damage", "50", "Medkit damage per hit on an enemy (PF2 Damage 50).", _, true, 0.0);
	g_cvMkRange = CreateConVar("tf2cc_medkit_pf2_range", "48", "Medkit swing reach (PF2 48).", _, true, 0.0);
	g_cvMkInfectTime = CreateConVar("tf2cc_medkit_pf2_infect_time", "14", "Medkit infection duration.", _, true, 0.0);
	g_cvMkInfectDmg = CreateConVar("tf2cc_medkit_pf2_infect_damage", "8", "Medkit infection damage per tick.", _, true, 0.0);
	g_cvMkInfectTick = CreateConVar("tf2cc_medkit_pf2_infect_interval", "2.0", "Medkit infection tick interval.", _, true, 0.1);
	CreateTimer(0.1, Timer_Infection, _, TIMER_REPEAT);
}

bool IsMedkit(int weapon)
{
	int i = g_WItem.FindString(MEDKIT_ITEM);
	return weapon > MaxClients && i >= 0 && ItemDef(weapon) == g_WDef.Get(i);
}

void MedkitThink(int client, int buttons)
{
	int w = GetEntPropEnt(client, Prop_Send, "m_hActiveWeapon");
	if (!IsMerc(client) || !IsMedkit(w))
		return;
	float now = GetGameTime();
	SetEntPropFloat(w, Prop_Send, "m_flNextPrimaryAttack", now + 0.2);   // the base never swings
	if (!(buttons & IN_ATTACK) || now < g_flMkNext[client] || GetEntPropFloat(client, Prop_Send, "m_flNextAttack") > now)
		return;
	float delay = g_cvMkDelay.FloatValue;
	g_flMkNext[client] = now + delay;
	PlayViewSequence(client, w, "hit", 1.167 / delay > 1.0 ? 1.167 / delay : 1.0, delay);
	float eye[3], ang[3], dir[3], end[3];
	GetClientEyePosition(client, eye);
	GetClientEyeAngles(client, ang);
	GetAngleVectors(ang, dir, NULL_VECTOR, NULL_VECTOR);
	ScaleVector(dir, g_cvMkRange.FloatValue);
	AddVectors(eye, dir, end);
	Handle tr = TR_TraceRayFilterEx(eye, end, MASK_SOLID, RayType_EndPoint, Filter_NotSelf, client);
	if (!TR_DidHit(tr) || TR_GetEntityIndex(tr) <= 0)
	{
		delete tr;
		tr = TR_TraceHullFilterEx(eye, end, view_as<float>({ -18.0, -18.0, -18.0 }), view_as<float>({ 18.0, 18.0, 18.0 }),
			MASK_SOLID, Filter_NotSelf, client);
	}
	int hit = TR_GetEntityIndex(tr);
	delete tr;
	Step("medkit swing %N -> %d", client, hit);
	if (hit < 1 || hit > MaxClients || !IsPlayerAlive(hit))
		return;
	if (GetClientTeam(hit) != GetClientTeam(client))
	{
		SDKHooks_TakeDamage(hit, client, client, g_cvMkDamage.FloatValue, DMG_CLUB, w);
		g_iInfector[hit] = GetClientUserId(client);
		g_flInfectEnd[hit] = now + g_cvMkInfectTime.FloatValue;
		g_flInfectTick[hit] = now + g_cvMkInfectTick.FloatValue;
		Step("medkit %N hit %N: %.0f + infection", client, hit, g_cvMkDamage.FloatValue);
		return;
	}
	// Teammate: cleanse, then heal up to max health (no overheal).
	TF2_RemoveCondition(hit, TFCond_OnFire);
	TF2_RemoveCondition(hit, TFCond_Bleeding);
	g_flInfectEnd[hit] = 0.0;
	int maxhp = GetEntProp(GetPlayerResourceEntity(), Prop_Send, "m_iMaxHealth", _, hit);
	int hp = GetClientHealth(hit);
	int amount = hp + g_cvMkHeal.IntValue > maxhp ? maxhp - hp : g_cvMkHeal.IntValue;
	if (amount > 0)
		SetEntityHealth(hit, hp + amount);
	EmitSoundToAll(MEDKIT_HEAL_SOUND, hit);
	Step("medkit %N healed %N: %d (%d -> %d of %d)", client, hit, amount, hp, hp + (amount > 0 ? amount : 0), maxhp);
	Event ev = CreateEvent("player_healed", true);
	if (ev != null)
	{
		ev.SetInt("priority", 1);
		ev.SetInt("patient", GetClientUserId(hit));
		ev.SetInt("healer", GetClientUserId(client));
		ev.SetInt("amount", amount > 0 ? amount : 0);
		ev.Fire();
	}
}

public Action Timer_Infection(Handle timer)
{
	float now = GetGameTime();
	for (int i = 1; i <= MaxClients; i++)
	{
		if (g_flInfectEnd[i] <= now || !IsClientInGame(i) || !IsPlayerAlive(i))
		{
			g_flInfectEnd[i] = 0.0;
			continue;
		}
		if (now < g_flInfectTick[i])
			continue;
		g_flInfectTick[i] = now + g_cvMkInfectTick.FloatValue;
		int attacker = GetClientOfUserId(g_iInfector[i]);
		SDKHooks_TakeDamage(i, attacker ? attacker : i, attacker ? attacker : i, g_cvMkInfectDmg.FloatValue, DMG_PREVENT_PHYSICS_FORCE | DMG_POISON);
	}
	return Plugin_Continue;
}

/* ------------------------------------------------------------------ */
/* Chainsaw (OF CTFChainsaw, of_weapon_chainsaw.cpp), as the stock-TF2 */
/* tf2cc chainsaw (tf2cc_specials.sp):                                 */
/*  out: idle rev loop (Chainsaw.Idle) | hold fire: 1 s wind-up        */
/*  (cs_rev_up, Chainsaw.WindUp), then a hit every 0.05 s (12 dmg,     */
/*  100 reach) with the looping swing (cs_rev_idle, 0.6 s) and          */
/*  Chainsaw.Fire | release: cs_rev_down + Chainsaw.WindDown, idle      */
/*  again. Alt-fire with a full meter: shield charge at 720 u/s,        */
/*  crit-boosted, auto-fires, Chainsaw.Charge, no Demoman yell, 3 s;    */
/*  refills in 8 s (ChargeFilled.Ding, only while a living player       */
/*  holds the saw). The item's base melee (0.6 s swing, no damage, all  */
/*  sounds silent) only drives the looping first/third-person swing.   */
/*  Exactly one loop plays at a time; every loop stops on holster,      */
/*  death, respawn, role change and disconnect.                         */
/* ------------------------------------------------------------------ */
#define CHAINSAW_ITEM "tf2cc_merc_chainsaw"
#define CS_IDLE 0
#define CS_WINDUP 1
#define CS_FIRING 2
#define CS_SND_IDLE "tf2cc.Chainsaw.Idle"
#define CS_SND_WINDUP "tf2cc.Chainsaw.WindUp"
#define CS_SND_FIRE "tf2cc.Chainsaw.Fire"
#define CS_SND_FIRE_CRIT "tf2cc.Chainsaw.FireCrit"
#define CS_SND_WINDDOWN "tf2cc.Chainsaw.WindDown"
#define CS_SND_CHARGE "tf2cc.Chainsaw.Charge"
#define CS_SND_DING "tf2cc.ChargeFilled.Ding"
#define CS_SPEED_ATTR "major move speed bonus"   // mult_player_movespeed
#define TFCOND_SHIELD_CHARGE view_as<TFCond>(17)
#define TFCOND_CRIT_DEMO_CHARGE view_as<TFCond>(35)
ConVar g_cvCsDamage, g_cvCsInterval, g_cvCsRange, g_cvCsWindup, g_cvCsCharge, g_cvCsRecharge, g_cvCsSpeed;
ConVar g_cvCsMeter, g_cvCsMeterX, g_cvCsMeterY;
Handle g_hCsMeter;
int g_iCsState[MAXPLAYERS + 1];
int g_iCsWeapon[MAXPLAYERS + 1] = { INVALID_ENT_REFERENCE, ... };
float g_flCsNext[MAXPLAYERS + 1], g_flCsNextSound[MAXPLAYERS + 1];
float g_flCsChargeEnd[MAXPLAYERS + 1], g_flCsChargeStart[MAXPLAYERS + 1];
bool g_bCsDing[MAXPLAYERS + 1], g_bCsSpeedAttr[MAXPLAYERS + 1];
char g_sCsFireSound[MAXPLAYERS + 1][48];
static const char CS_DEMO_SCREAM[][] = { "weapons/demo_charge_windup1.wav", "weapons/demo_charge_windup2.wav", "weapons/demo_charge_windup3.wav" };

void ChainsawInit()
{
	g_cvCsDamage = CreateConVar("tf2cc_chainsaw_damage", "12", "Chainsaw damage per hit (OF Damage 12).", _, true, 0.0);
	g_cvCsInterval = CreateConVar("tf2cc_chainsaw_interval", "0.05", "Chainsaw seconds between hits (OF TimeFireDelay 0.05).", _, true, 0.01);
	g_cvCsRange = CreateConVar("tf2cc_chainsaw_range", "100", "Chainsaw reach (OF MeleeRange 100).", _, true, 0.0);
	g_cvCsWindup = CreateConVar("tf2cc_chainsaw_windup", "1.0", "Chainsaw wind-up before it cuts (OF_CHAINSAW_WINDUP_TIME 1.0; halved while charging).", _, true, 0.0);
	g_cvCsCharge = CreateConVar("tf2cc_chainsaw_charge_time", "3.0", "Chainsaw alt-fire charge length (OF ChargeDuration 1.5, measured 2x in game).", _, true, 0.0);
	g_cvCsRecharge = CreateConVar("tf2cc_chainsaw_charge_recharge", "8.0", "Seconds for the chainsaw charge to refill (OF ChargeRechargeRate 8).", _, true, 0.0);
	g_cvCsSpeed = CreateConVar("tf2cc_chainsaw_charge_speed", "720", "Chainsaw charge speed (OF of_shield_charge_speed 720).", _, true, 1.0);
	g_cvCsMeter = CreateConVar("tf2cc_chainsaw_charge_meter", "1", "Show the chainsaw charge meter (recharge / ready / charging) while the chainsaw is out.", _, true, 0.0, true, 1.0);
	g_cvCsMeterX = CreateConVar("tf2cc_chainsaw_charge_meter_x", "0.73", "Chainsaw charge meter X (0-1, -1 = centre).");
	g_cvCsMeterY = CreateConVar("tf2cc_chainsaw_charge_meter_y", "0.86", "Chainsaw charge meter Y (0-1).");
	g_hCsMeter = CreateHudSynchronizer();
	CreateTimer(0.1, Timer_ChainsawMeter, _, TIMER_REPEAT);
}

bool IsChainsaw(int weapon)
{
	int i = g_WItem.FindString(CHAINSAW_ITEM);
	return weapon > MaxClients && i >= 0 && ItemDef(weapon) == g_WDef.Get(i);
}

/** A tf2cc.* script on the entity, with the channel forced (the loops must never share one). */
void CsSound(int entity, const char[] script, int channel, bool stop = false)
{
	char sample[PLATFORM_MAX_PATH];
	int ch, level, pitch;
	float volume;
	if (!GetGameSoundParams(script, ch, level, volume, pitch, sample, sizeof(sample), entity))
		return;
	if (stop)
		StopSound(entity, channel, sample);
	else
		EmitSoundToAll(sample, entity, channel, level, SND_NOFLAGS, volume, pitch);
	Step("chainsaw %s %s (ent %d, chan %d)", stop ? "stop" : "play", script, entity, channel);
}

/** Returns true when buttons were changed (auto-fire while charging). */
bool ChainsawThink(int client, int &buttons)
{
	int held = EntRefToEntIndex(g_iCsWeapon[client]);
	int active = GetEntPropEnt(client, Prop_Send, "m_hActiveWeapon");
	bool isSaw = IsMerc(client) && IsChainsaw(active);
	float now = GetGameTime();
	if (!isSaw)
	{
		if (held > MaxClients || g_iCsState[client] != CS_IDLE)
			ChainsawStop(client, held);
		ChainsawChargeTick(client, now, false);
		g_bAlt[client] = (buttons & IN_ATTACK2) != 0;
		return false;
	}
	if (held != active)
	{
		ChainsawStop(client, held);
		g_iCsWeapon[client] = EntIndexToEntRef(active);
		CsSound(active, CS_SND_IDLE, SNDCHAN_STATIC);
		if (g_flChargeReady[client] <= 0.0 || g_flChargeReady[client] - now > g_cvCsCharge.FloatValue + g_cvCsRecharge.FloatValue + 1.0)
			g_flChargeReady[client] = now;   // first draw, or a stamp from a previous map
	}
	bool changed = false;
	bool charging = ChainsawChargeTick(client, now);

	// Alt-fire: shield charge when the meter is full (OF CTFWeaponBaseMelee::SecondaryAttack).
	bool attack2 = (buttons & IN_ATTACK2) != 0;
	if (attack2 && !g_bAlt[client])
		Step("chainsaw alt-fire %N: charging %d, ready in %.1f s", client, charging, g_flChargeReady[client] - now);
	if (attack2 && !g_bAlt[client] && !charging && now >= g_flChargeReady[client] && g_cvCsCharge.FloatValue > 0.0)
	{
		float len = g_cvCsCharge.FloatValue;
		g_flCsChargeEnd[client] = now + len;
		g_flCsChargeStart[client] = now;
		g_flChargeReady[client] = now + len + g_cvCsRecharge.FloatValue;
		g_bCsDing[client] = true;
		if (HasEntProp(client, Prop_Send, "m_flChargeMeter"))
			SetEntPropFloat(client, Prop_Send, "m_flChargeMeter", 100.0);
		TF2_AddCondition(client, TFCOND_SHIELD_CHARGE, len);
		TF2_AddCondition(client, TFCOND_CRIT_DEMO_CHARGE, len);   // OF CritOnChargeLevel 1
		CsSound(client, CS_SND_CHARGE, SNDCHAN_AUTO);
		ChargeSpeedStart(client);
		charging = true;
		Step("chainsaw charge %N (%.1f s)", client, len);
	}
	g_bAlt[client] = attack2;
	if (charging && !(buttons & IN_ATTACK))
	{
		buttons |= IN_ATTACK;   // OF: PrimaryAttack() every frame while charging
		changed = true;
	}

	bool want = (buttons & IN_ATTACK) != 0;
	switch (g_iCsState[client])
	{
		case CS_IDLE:
		{
			// The base melee must not swing (nor the client predict a swing) before the wind-up ends.
			SetEntPropFloat(active, Prop_Send, "m_flNextPrimaryAttack", now + 0.2);
			if (want && GetEntPropFloat(client, Prop_Send, "m_flNextAttack") <= now)
			{
				float windup = g_cvCsWindup.FloatValue * (charging ? 0.5 : 1.0);
				g_iCsState[client] = CS_WINDUP;
				g_flCsNext[client] = now + windup;
				SetEntPropFloat(active, Prop_Send, "m_flNextPrimaryAttack", now + windup);
				CsSound(active, CS_SND_IDLE, SNDCHAN_STATIC, true);
				CsSound(active, CS_SND_WINDUP, SNDCHAN_WEAPON);
				PlayViewSequence(client, active, "cs_rev_up", windup > 0.0 ? g_cvCsWindup.FloatValue / windup : 1.0, windup + 0.1);
			}
		}
		case CS_WINDUP:
		{
			if (!want)
				ChainsawWindDown(client, active);
			else if (now >= g_flCsNext[client])
			{
				g_iCsState[client] = CS_FIRING;
				g_flCsNext[client] = now;
				g_flCsNextSound[client] = 0.0;
				SetEntPropFloat(active, Prop_Send, "m_flNextPrimaryAttack", now);
			}
			else
				SetEntPropFloat(active, Prop_Send, "m_flNextPrimaryAttack", g_flCsNext[client]);
		}
		case CS_FIRING:
		{
			if (!want)
			{
				ChainsawWindDown(client, active);
				return changed;
			}
			bool crit = TF2_IsPlayerInCondition(client, TFCOND_CRIT_DEMO_CHARGE) || TF2_IsPlayerInCondition(client, TFCond_Kritzkrieged);
			char snd[48];
			strcopy(snd, sizeof(snd), crit ? CS_SND_FIRE_CRIT : CS_SND_FIRE);
			// One fire loop: re-sent at its wave length on the same channel (which replaces it).
			if (now >= g_flCsNextSound[client] || !StrEqual(snd, g_sCsFireSound[client]))
			{
				if (g_sCsFireSound[client][0] && !StrEqual(snd, g_sCsFireSound[client]))
					CsSound(active, g_sCsFireSound[client], SNDCHAN_WEAPON, true);
				CsSound(active, snd, SNDCHAN_WEAPON);
				strcopy(g_sCsFireSound[client], sizeof(g_sCsFireSound[]), snd);
				g_flCsNextSound[client] = now + (crit ? 3.3 : 0.598);
			}
			while (g_flCsNext[client] <= now)
			{
				g_flCsNext[client] += g_cvCsInterval.FloatValue;
				ChainsawHit(client, active, crit);
			}
		}
	}
	return changed;
}

/** OF DoSwingTrace: a line from the shoot position, then the duck hull. */
void ChainsawHit(int client, int weapon, bool crit)
{
	float eye[3], ang[3], dir[3], end[3];
	GetClientEyePosition(client, eye);
	GetClientEyeAngles(client, ang);
	GetAngleVectors(ang, dir, NULL_VECTOR, NULL_VECTOR);
	ScaleVector(dir, g_cvCsRange.FloatValue);
	AddVectors(eye, dir, end);
	Handle tr = TR_TraceRayFilterEx(eye, end, MASK_SOLID, RayType_EndPoint, Filter_NotSelf, client);
	if (!TR_DidHit(tr) || TR_GetEntityIndex(tr) <= 0)
	{
		delete tr;
		tr = TR_TraceHullFilterEx(eye, end, view_as<float>({ -18.0, -18.0, -18.0 }), view_as<float>({ 18.0, 18.0, 18.0 }),
			MASK_SOLID, Filter_NotSelf, client);
	}
	int hit = TR_GetEntityIndex(tr);
	delete tr;
	if (hit <= 0 || !IsValidEntity(hit))
		return;
	bool player = hit <= MaxClients;
	if (player && (!IsPlayerAlive(hit) || GetClientTeam(hit) == GetClientTeam(client)))
		return;
	if (!player)
	{
		char cls[32];
		GetEntityClassname(hit, cls, sizeof(cls));
		if (StrContains(cls, "obj_") != 0 || GetEntProp(hit, Prop_Send, "m_iTeamNum") == GetClientTeam(client))
			return;
	}
	SDKHooks_TakeDamage(hit, client, client, g_cvCsDamage.FloatValue, DMG_CLUB | (crit ? DMG_CRITICAL : 0), weapon);
}

void ChainsawWindDown(int client, int weapon)
{
	g_iCsState[client] = CS_IDLE;
	if (g_sCsFireSound[client][0])
		CsSound(weapon, g_sCsFireSound[client], SNDCHAN_WEAPON, true);
	g_sCsFireSound[client][0] = '\0';
	CsSound(weapon, CS_SND_WINDUP, SNDCHAN_WEAPON, true);
	CsSound(weapon, CS_SND_WINDDOWN, SNDCHAN_WEAPON);
	CsSound(weapon, CS_SND_IDLE, SNDCHAN_STATIC);
	PlayViewSequence(client, weapon, "cs_rev_down", 1.0, 1.4);
}

void ChainsawStop(int client, int held)
{
	if (held > MaxClients && IsValidEntity(held))
	{
		CsSound(held, CS_SND_IDLE, SNDCHAN_STATIC, true);
		CsSound(held, CS_SND_WINDUP, SNDCHAN_WEAPON, true);
		if (g_sCsFireSound[client][0])
			CsSound(held, g_sCsFireSound[client], SNDCHAN_WEAPON, true);
	}
	g_sCsFireSound[client][0] = '\0';
	g_iCsState[client] = CS_IDLE;
	g_iCsWeapon[client] = INVALID_ENT_REFERENCE;
	// OF CTFPlayer: the charge ends when the chainsaw is put away.
	if (g_flCsChargeEnd[client] > GetGameTime() && IsClientInGame(client))
	{
		TF2_RemoveCondition(client, TFCOND_SHIELD_CHARGE);
		TF2_RemoveCondition(client, TFCOND_CRIT_DEMO_CHARGE);
	}
	g_flCsChargeEnd[client] = 0.0;
	ChargeSpeedEnd(client);
}

/** Death, respawn, role change, disconnect: every loop off, no pending ding. */
void ChainsawReset(int client)
{
	ChainsawStop(client, EntRefToEntIndex(g_iCsWeapon[client]));
	g_bCsDing[client] = false;
}

/** HUD text meter (the Demoman charge meter is a Demoman HUD element): recharge / READY / CHARGING. */
public Action Timer_ChainsawMeter(Handle timer)
{
	if (!g_cvCsMeter.BoolValue)
		return Plugin_Continue;
	float now = GetGameTime();
	float cd = g_cvCsRecharge.FloatValue;
	char bar[16];
	for (int client = 1; client <= MaxClients; client++)
	{
		if (!IsClientInGame(client) || IsFakeClient(client) || !IsMerc(client)
			|| !IsChainsaw(GetEntPropEnt(client, Prop_Send, "m_hActiveWeapon")))
			continue;
		bool charging = g_flCsChargeEnd[client] > now;
		float left = g_flChargeReady[client] - now;
		if (left > g_cvCsCharge.FloatValue + cd + 1.0)
			left = 0.0;
		int filled;
		if (charging)
			filled = RoundToCeil(10.0 * (g_flCsChargeEnd[client] - now) / (g_cvCsCharge.FloatValue > 0.01 ? g_cvCsCharge.FloatValue : 0.01));
		else
			filled = left <= 0.0 || cd <= 0.0 ? 10 : RoundToFloor(10.0 * (1.0 - left / cd));
		if (filled > 10) filled = 10;
		if (filled < 0) filled = 0;
		for (int i = 0; i < 10; i++)
			bar[i] = i < filled ? '|' : '.';
		bar[10] = '\0';
		int r = 255, g = 110, b = 100;
		switch (GetClientTeam(client))
		{
			case 3: { r = 120; g = 170; b = 255; }
			case 4: { r = 110; g = 230; b = 120; }
			case 5: { r = 255; g = 220; b = 80; }
		}
		bool ready = !charging && left <= 0.0;
		SetHudTextParams(g_cvCsMeterX.FloatValue, g_cvCsMeterY.FloatValue, 0.2, r, g, b, ready || charging ? 255 : 200, 0, 0.0, 0.0, 0.0);
		if (charging)
			ShowSyncHudText(client, g_hCsMeter, "Charge [%s] CHARGING", bar);
		else if (ready)
			ShowSyncHudText(client, g_hCsMeter, "Charge [%s] READY", bar);
		else
			ShowSyncHudText(client, g_hCsMeter, "Charge [%s] %.0fs", bar, left + 0.49);
	}
	return Plugin_Continue;
}

/** Keeps the charge going for the OF length; ding once when the meter has refilled. */
bool ChainsawChargeTick(int client, float now, bool holding = true)
{
	if (g_bCsDing[client] && g_flChargeReady[client] > 0.0 && now >= g_flChargeReady[client])
	{
		g_bCsDing[client] = false;
		// Only for a living player holding the saw (not from a previous life's stamp).
		if (holding && IsMerc(client))
		{
			char sample[PLATFORM_MAX_PATH];
			int ch, level, pitch;
			float volume;
			if (GetGameSoundParams(CS_SND_DING, ch, level, volume, pitch, sample, sizeof(sample), client))
				EmitSoundToClient(client, sample, client, SNDCHAN_AUTO, level, SND_NOFLAGS, volume, pitch);
			Step("chainsaw ding %N", client);
		}
	}
	if (g_flCsChargeEnd[client] <= now)
	{
		ChargeSpeedEnd(client);
		return false;
	}
	if (!TF2_IsPlayerInCondition(client, TFCOND_SHIELD_CHARGE))
	{
		// Bumped into something / stopped by the game: end like OF does.
		g_flCsChargeEnd[client] = 0.0;
		TF2_RemoveCondition(client, TFCOND_CRIT_DEMO_CHARGE);
		ChargeSpeedEnd(client);
		return false;
	}
	if (HasEntProp(client, Prop_Send, "m_flChargeMeter"))
		SetEntPropFloat(client, Prop_Send, "m_flChargeMeter", 100.0);
	ChargeSpeed(client);
	// The shield-charge condition makes the clients yell "DemoCharge.Charging": stop it.
	if (now - g_flCsChargeStart[client] < 0.3)
		for (int i = 0; i < sizeof(CS_DEMO_SCREAM); i++)
			StopSound(client, SNDCHAN_STATIC, CS_DEMO_SCREAM[i]);
	return true;
}

/**
 * The charge movement forces full forward input, but only a Demoman gets the charge speed from
 * the max-speed calculation; the Merc (a Soldier) would charge at his walking speed. A player
 * attribute (mult_player_movespeed, networked: the owner predicts the same speed) lifts it to
 * the charge speed for the charge, as on stock TF2; m_flMaxspeed is the fallback.
 */
void ChargeSpeedStart(int client)
{
	ChargeSpeedEnd(client);
	float cur = GetEntPropFloat(client, Prop_Send, "m_flMaxspeed");
	if (cur > 1.0)
	{
		RunScriptF(client, "self.AddCustomAttribute(\"%s\", %.4f, -1)", CS_SPEED_ATTR, g_cvCsSpeed.FloatValue / cur);
		g_bCsSpeedAttr[client] = true;
	}
	ChargeSpeed(client);
}

void ChargeSpeed(int client)
{
	float speed = g_cvCsSpeed.FloatValue;
	if (GetEntPropFloat(client, Prop_Send, "m_flMaxspeed") < speed)
		SetEntPropFloat(client, Prop_Send, "m_flMaxspeed", speed);
}

void ChargeSpeedEnd(int client)
{
	if (!g_bCsSpeedAttr[client])
		return;
	g_bCsSpeedAttr[client] = false;
	if (IsClientInGame(client))
		RunScriptF(client, "self.RemoveCustomAttribute(\"%s\")", CS_SPEED_ATTR);
}

/** Server-driven viewmodel sequence (cs_rev_up / cs_rev_down have no stock activity). */
void PlayViewSequence(int client, int weapon, const char[] sequence, float rate, float hold)
{
	int vm = GetEntPropEnt(client, Prop_Send, "m_hViewModel");
	if (vm <= MaxClients)
		return;
	g_cvRet.SetString("-1");
	RunScriptF(vm, "Convars.SetValue(\"tf2cc_tf2c_ret\", \"\" + self.LookupSequence(\"%s\"))", sequence);
	int seq = g_cvRet.IntValue;
	if (seq < 0)
		return;
	SetEntProp(vm, Prop_Send, "m_nSequence", seq);
	SetEntPropFloat(vm, Prop_Send, "m_flPlaybackRate", rate);
	SetEntPropFloat(vm, Prop_Data, "m_flCycle", 0.0);
	SetEntProp(vm, Prop_Send, "m_nNewSequenceParity", (GetEntProp(vm, Prop_Send, "m_nNewSequenceParity") + 1) & 7);
	SetEntProp(vm, Prop_Send, "m_nResetEventsParity", (GetEntProp(vm, Prop_Send, "m_nResetEventsParity") + 1) & 7);
	if (HasEntProp(weapon, Prop_Data, "m_flTimeWeaponIdle"))
		SetEntPropFloat(weapon, Prop_Data, "m_flTimeWeaponIdle", GetGameTime() + hold);
	Step("chainsaw vm %s (seq %d, rate %.2f)", sequence, seq, rate);
}

/** OF's charge plays only Chainsaw.Charge: the stock charge whoosh/crit sounds are dropped. */
public Action Hook_ChainsawSounds(int clients[MAXPLAYERS], int &numClients, char sample[PLATFORM_MAX_PATH],
	int &entity, int &channel, float &volume, int &level, int &pitch, int &flags,
	char soundEntry[PLATFORM_MAX_PATH], int &seed)
{
	if (entity < 1 || entity > MaxClients)
		return Plugin_Continue;
	if (StrContains(sample, "demo_charge_windup") != -1 || StrContains(sample, "weapon_crit_charged_o") != -1)
		return (g_flCsChargeEnd[entity] > 0.0 && GetGameTime() <= g_flCsChargeEnd[entity] + 0.5) ? Plugin_Stop : Plugin_Continue;
	return Plugin_Continue;
}

public Action OnPlayerRunCmd(int client, int &buttons, int &impulse, float vel[3], float angles[3], int &weapon)
{
	g_bWasOnGround[client] = (GetEntityFlags(client) & FL_ONGROUND) != 0;
	if (g_bTaunting[client])
	{
		// Like a stock taunt: no walking, jumping or attacking (gravity and platforms still act).
		buttons &= ~(IN_ATTACK | IN_ATTACK2 | IN_ATTACK3 | IN_RELOAD | IN_JUMP | IN_DUCK | IN_USE
			| IN_FORWARD | IN_BACK | IN_MOVELEFT | IN_MOVERIGHT);
		vel[0] = vel[1] = vel[2] = 0.0;
		weapon = 0;
		g_bUseHeld[client] = false;
		return Plugin_Changed;
	}
	bool changed = ChainsawThink(client, buttons);
	MedkitThink(client, buttons);
	bool use = (buttons & IN_USE) != 0;
	if (use && !g_bUseHeld[client] && g_bMerc[client])
		TrySwapNearby(client);
	g_bUseHeld[client] = use;
	// OF Merc bunnyhop when the server has no autojump: holding jump on landing re-jumps
	// (the "jump must be released" latch is m_nOldButtons; not client-predicted).
	if (g_cvAutoJump.BoolValue && (buttons & IN_JUMP) && g_bWasOnGround[client] && IsMerc(client)
		&& (g_cvSvAutoJump == null || !g_cvSvAutoJump.BoolValue)
		&& GetEntityMoveType(client) == MOVETYPE_WALK && GetEntProp(client, Prop_Data, "m_nWaterLevel") < 2)
	{
		int old = GetEntProp(client, Prop_Data, "m_nOldButtons");
		if (old & IN_JUMP)
			SetEntProp(client, Prop_Data, "m_nOldButtons", old & ~IN_JUMP);
	}
	return changed ? Plugin_Changed : Plugin_Continue;
}

/* OF lightning gun (of_weapon_lightning.cpp): a beam from the muzzle to the trace end (720 u,
 * team-coloured "lg_bolt" particle there) while attack is held, with LightningStart, a
 * looping LightningLoop and LightningEnd. TF2C has no lg_bolt particle and the SMG base fires
 * per shot, so: the item's per-shot sound is silent (schema) and the stream is drawn here with
 * beam temp entities, sounds through the tf2cc.* scripts (custom_level_sounds.txt). */

bool HoldsLightning(int client, int &weapon)
{
	weapon = GetEntPropEnt(client, Prop_Send, "m_hActiveWeapon");
	int i = g_WItem.FindString(LG_ITEM);
	return weapon > MaxClients && i >= 0 && ItemDef(weapon) == g_WDef.Get(i);
}

bool LightningHasAmmo(int client, int weapon)
{
	int type = GetEntProp(weapon, Prop_Send, "m_iPrimaryAmmoType");
	return type >= 0 && GetEntProp(client, Prop_Send, "m_iAmmo", _, type) > 0;
}

void StopLightning(int client, bool endSound)
{
	if (!g_bLgFiring[client])
		return;
	g_bLgFiring[client] = false;
	g_iLgWeapon[client] = INVALID_ENT_REFERENCE;
	if (IsClientInGame(client))
	{
		EmitGameSoundToAll(LG_LOOP, client, SND_STOP);
		if (endSound && IsPlayerAlive(client))
			EmitGameSoundToAll(LG_END, client);
	}
	Step("lightning %N: stop", client);
}

void UpdateLightning(int client, int buttons)
{
	int weapon;
	bool want = IsMerc(client) && (buttons & IN_ATTACK) && !g_bTaunting[client] && HoldsLightning(client, weapon)
		&& LightningHasAmmo(client, weapon) && GetEntPropFloat(client, Prop_Send, "m_flNextAttack") <= GetGameTime();
	if (!want)
	{
		StopLightning(client, true);
		return;
	}
	if (!g_bLgFiring[client])
	{
		g_bLgFiring[client] = true;
		g_iLgWeapon[client] = EntIndexToEntRef(weapon);
		EmitGameSoundToAll(LG_START, client);
		EmitGameSoundToAll(LG_LOOP, client);
		g_flLgNextBeam[client] = 0.0;
		Step("lightning %N: start", client);
	}
	float now = GetGameTime();
	if (now < g_flLgNextBeam[client])
		return;
	g_flLgNextBeam[client] = now + 0.05;
	float eye[3], ang[3], fwd[3], right[3], up[3], start[3], end[3];
	GetClientEyePosition(client, eye);
	GetClientEyeAngles(client, ang);
	GetAngleVectors(ang, fwd, right, up);
	for (int k = 0; k < 3; k++)
	{
		start[k] = eye[k] + fwd[k] * 30.0 + right[k] * 8.0 - up[k] * 9.0;   // about the muzzle
		end[k] = eye[k] + fwd[k] * 720.0;                                     // OF Range 720
	}
	Handle tr = TR_TraceRayFilterEx(eye, end, MASK_SHOT, RayType_EndPoint, Filter_NotSelf, client);
	TR_GetEndPosition(end, tr);
	delete tr;
	int color[4];
	switch (GetClientTeam(client))
	{
		case 2: color = { 255, 80, 60, 255 };
		case 3: color = { 70, 140, 255, 255 };
		case 4: color = { 70, 255, 90, 255 };
		case 5: color = { 255, 220, 50, 255 };
		default: color = { 200, 200, 255, 255 };
	}
	TE_SetupBeamPoints(start, end, g_iBeamSprite, 0, 0, 30, 0.1, 3.0, 3.0, 0, 6.0, color, 20);
	TE_SendToAll();
	TE_SetupBeamPoints(start, end, g_iBeamSprite, 0, 0, 30, 0.1, 1.2, 1.2, 0, 2.0, { 255, 255, 255, 200 }, 20);
	TE_SendToAll();
}

/** OF Merc jump vocal ("Mercenary.Jumpsound": volume 0.6, 95 dB, 0.5 s gate) on each ground jump. */
public void OnPlayerRunCmdPost(int client, int buttons, int impulse, const float vel[3], const float angles[3], int weapon, int subtype, int cmdnum, int tickcount, int seed, const int mouse[2])
{
	UpdateLightning(client, buttons);
	if (!g_bWasOnGround[client] || !(buttons & IN_JUMP) || !IsMerc(client) || (GetEntityFlags(client) & FL_ONGROUND))
		return;
	float v[3];
	GetEntPropVector(client, Prop_Data, "m_vecVelocity", v);
	float now = GetGameTime();
	if (v[2] <= 100.0 || now < g_flNextJumpSound[client])
		return;
	g_flNextJumpSound[client] = now + 0.5;
	Step("jump vocal %N", client);
	g_bOwnEmit = true;
	EmitSoundToAll(g_sJumpSounds[GetRandomInt(0, sizeof(g_sJumpSounds) - 1)], client, SNDCHAN_AUTO, SNDLEVEL_SCREAMING, SND_NOFLAGS, 0.6);
	g_bOwnEmit = false;
}

/**
 * tf2cc_merc_no_fall_damage: CMoveHelperServer::PlayerFallingDamage hands the fall to
 * TakeDamage (world, DMG_FALL) and plays "Player.FallDamage" only when damage was taken;
 * refusing it here also skips the pain line (spoken from the damage that never lands).
 * (TF2C's "cancel falling damage" attribute would need the body item to change with the
 * cvar; the hook follows it at once.)
 */
public Action Hook_PlayerDamage(int victim, int &attacker, int &inflictor, float &damage, int &damagetype)
{
	if ((damagetype & DMG_FALL) && g_cvNoFall.BoolValue && IsMerc(victim))
	{
		Step("fall damage %.1f refused for %N", damage, victim);
		damage = 0.0;
		return Plugin_Handled;
	}
	return Plugin_Continue;
}

/* ------------------------------------------------------------------ */
/* Ammo packs                                                         */
/* ------------------------------------------------------------------ */

public void OnEntityCreated(int entity, const char[] classname)
{
	if (entity < 1 || entity >= sizeof(g_flPackReady))
		return;
	if (StrContains(classname, "item_ammopack_") == 0)
	{
		g_flPackReady[entity] = 0.0;
		SDKHook(entity, SDKHook_StartTouch, Hook_PackTouch);
	}
	else if (StrEqual(classname, "func_regenerate"))
	{
		SDKHook(entity, SDKHook_StartTouchPost, Hook_RegenTouch);
	}
	else if (StrEqual(classname, "tf_projectile_rocket"))
	{
		SDKHook(entity, SDKHook_SpawnPost, Hook_RocketSpawned);
	}
	else if (StrEqual(classname, "tf_ammo_pack"))
	{
		SDKHook(entity, SDKHook_Spawn, Hook_AmmoPackSpawn);
	}
}

/*
 * GIB (OF tf_weapon_gib), matching the stock-TF2 tf2cc GIB (tf2cc_specials.sp bomblets_gib):
 * the rocket is the Cow Mangler's energy ball (w_drg_ball + drg_cow_rockettrail_normal[_blue])
 * and bursts into 6 bomblets (45 damage, radius 124) thrown OF-style off the surface it hit
 * (normal pitched 40-60 degrees, spread evenly around it, 275-300 u/s, 4 u off the surface).
 * Each bomblet trails the Cow Mangler trail, explodes on its first impact (OF BombletImpact 1)
 * or after 1 s + 0-1 s, with the Cow Mangler's explosion core. Team colours: RED and yellow
 * use the red particles, BLU and green the blue ones (the effects exist only in red/blue).
 */
#define GIB_ITEM "tf2cc_merc_gib"
#define BOMBLET_COUNT 6          // OF BombletAmount
#define BOMBLET_DAMAGE "45"      // OF BombletDamage
#define BOMBLET_RADIUS "124"     // OF BombletDamageRadius
#define BOMBLET_TIMER 1.0        // OF BombletTimer
#define BOMBLET_TIMER_RANDOM 1.0 // OF adds 0-1 s
#define BOMBLET_POLL 0.1   // SourceMod timers run at 0.1 s at best
bool g_bGibRocket[2049];
float g_vGibNormal[2049][3];
bool g_bGibNormal[2049];
float g_vBombVel[2049][3];
float g_flBombFuse[2049];
float g_flBombBorn[2049];
float g_vBombPos[2049][3];
float g_flBombLast[2049];
int g_iGibRocketRef[2049];

bool BlueParticles(int team)
{
	return team == 3 || team == 4;
}

int ParticleIndex(const char[] name)
{
	int table = FindStringTable("ParticleEffectNames");
	if (table == INVALID_STRING_TABLE)
		return INVALID_STRING_INDEX;
	int idx = FindStringIndex(table, name);
	if (idx == INVALID_STRING_INDEX)
	{
		bool save = LockStringTables(false);
		AddToStringTable(table, name);
		LockStringTables(save);
		idx = FindStringIndex(table, name);
	}
	return idx;
}

/** TE TFParticleEffect following the entity (PATTACH_ABSORIGIN_FOLLOW), or at pos when entity is 0. */
void ParticleOn(int entity, const char[] name, const float pos[3])
{
	int idx = ParticleIndex(name);
	if (idx == INVALID_STRING_INDEX)
		return;
	TE_Start("TFParticleEffect");
	TE_WriteFloat("m_vecOrigin[0]", pos[0]);
	TE_WriteFloat("m_vecOrigin[1]", pos[1]);
	TE_WriteFloat("m_vecOrigin[2]", pos[2]);
	TE_WriteNum("m_iParticleSystemIndex", idx);
	if (entity > 0)
	{
		TE_WriteNum("entindex", entity);
		TE_WriteNum("m_iAttachType", 1);
	}
	TE_SendToAll();
}

public void Hook_RocketSpawned(int entity)
{
	RequestFrame(Frame_CheckRocket, EntIndexToEntRef(entity));
}

public void Frame_CheckRocket(int ref)
{
	int rocket = EntRefToEntIndex(ref);
	if (rocket <= MaxClients || !HasEntProp(rocket, Prop_Send, "m_hLauncher") || g_iGibRocketRef[rocket] == ref)
		return;   // (TF2C runs SpawnPost twice for rockets: one model swap and trail)
	g_iGibRocketRef[rocket] = ref;
	int launcher = GetEntPropEnt(rocket, Prop_Send, "m_hLauncher");
	int i = g_WItem.FindString(GIB_ITEM);
	g_bGibRocket[rocket] = launcher > MaxClients && i >= 0 && ItemDef(launcher) == g_WDef.Get(i);
	g_bGibNormal[rocket] = false;
	if (!g_bGibRocket[rocket])
		return;
	SetEntityModel(rocket, DRG_BALL_MODEL);
	float pos[3];
	GetEntPropVector(rocket, Prop_Data, "m_vecAbsOrigin", pos);
	ParticleOn(rocket, BlueParticles(GetEntProp(rocket, Prop_Send, "m_iTeamNum")) ? "drg_cow_rockettrail_normal_blue" : "drg_cow_rockettrail_normal", pos);
	Step("gib rocket %d: energy ball + trail", rocket);
}

/** The rocket's explosion: the Cow Mangler core instead of the rocket blast, and the surface
 *  normal for the bomblets (the rocket is removed right after). */
public Action TE_GibExplosion(const char[] te_name, const int[] players, int numClients, float delay)
{
	float origin[3], pos[3];
	origin[0] = TE_ReadFloat("m_vecOrigin[0]");
	origin[1] = TE_ReadFloat("m_vecOrigin[1]");
	origin[2] = TE_ReadFloat("m_vecOrigin[2]");
	int e = -1;
	while ((e = FindEntityByClassname(e, "tf_projectile_rocket")) != -1)
	{
		if (e >= sizeof(g_bGibRocket) || !g_bGibRocket[e])
			continue;
		GetEntPropVector(e, Prop_Data, "m_vecAbsOrigin", pos);
		if (GetVectorDistance(pos, origin, true) > 48.0 * 48.0)
			continue;
		TE_ReadVector("m_vecNormal", g_vGibNormal[e]);
		g_bGibNormal[e] = true;
		int fx = ParticleIndex(BlueParticles(GetEntProp(e, Prop_Send, "m_iTeamNum")) ? "drg_cow_explosioncore_normal_blue" : "drg_cow_explosioncore_normal");
		if (fx != INVALID_STRING_INDEX)
			TE_WriteNum("m_iCustomParticleIndex", fx);
		break;
	}
	return Plugin_Continue;
}

public void OnEntityDestroyed(int entity)
{
	if (entity <= MaxClients || entity >= sizeof(g_bGibRocket) || !g_bGibRocket[entity])
		return;
	g_bGibRocket[entity] = false;
	int owner = GetEntPropEnt(entity, Prop_Send, "m_hOwnerEntity");
	if (owner < 1 || owner > MaxClients || !IsClientInGame(owner))
		return;
	float pos[3], normal[3];
	GetEntPropVector(entity, Prop_Data, "m_vecAbsOrigin", pos);
	normal = g_vGibNormal[entity];
	if (!g_bGibNormal[entity] || NormalizeVector(normal, normal) < 0.5)
		normal = view_as<float>({ 0.0, 0.0, 1.0 });   // mid-air: as OF, straight up
	int team = GetClientTeam(owner);
	// OF SpawnBomblets: pitch the normal by 40-60 degrees, rotate evenly around the normal.
	float ang[3], base[3], src[3], cross[3];
	GetVectorAngles(normal, ang);
	ang[0] += GetRandomFloat(40.0, 60.0);
	GetAngleVectors(ang, base, NULL_VECTOR, NULL_VECTOR);
	GetVectorCrossProduct(normal, base, cross);
	float dot = GetVectorDotProduct(normal, base);
	for (int i = 0; i < 3; i++)
		src[i] = pos[i] + normal[i] * 4.0;
	for (int b = 0; b < BOMBLET_COUNT; b++)
	{
		float rot = DegToRad(360.0 / float(BOMBLET_COUNT) * float(b));
		float c = Cosine(rot), sn = Sine(rot), speed = GetRandomFloat(275.0, 300.0);
		float vel[3];
		for (int i = 0; i < 3; i++)
			vel[i] = (base[i] * c + cross[i] * sn + normal[i] * dot * (1.0 - c)) * speed;
		SpawnBomblet(owner, team, src, vel);
	}
}

void SpawnBomblet(int owner, int team, const float pos[3], const float vel[3])
{
	int prop = CreateEntityByName("prop_physics_override");
	if (prop == -1)
		return;
	if (prop >= sizeof(g_flBombFuse))
	{
		RemoveEntity(prop);
		return;
	}
	DispatchKeyValue(prop, "model", BOMBLET_MODEL);
	DispatchKeyValue(prop, "spawnflags", "4");
	if (!DispatchSpawn(prop))
	{
		RemoveEntity(prop);
		return;
	}
	SetEntProp(prop, Prop_Send, "m_CollisionGroup", COLLISION_GROUP_DEBRIS);
	SetEntProp(prop, Prop_Send, "m_nSkin", (team >= 2 && team <= 5) ? team - 2 : 0);   // RED BLU GRN YLW
	TeleportEntity(prop, pos, NULL_VECTOR, vel);
	ParticleOn(prop, BlueParticles(team) ? "drg_cow_rockettrail_normal_blue" : "drg_cow_rockettrail_normal", pos);
	g_vBombVel[prop] = vel;
	g_vBombPos[prop] = pos;
	g_flBombBorn[prop] = g_flBombLast[prop] = GetGameTime();
	g_flBombFuse[prop] = GetGameTime() + BOMBLET_TIMER + GetURandomFloat() * BOMBLET_TIMER_RANDOM;
	DataPack dp;
	CreateDataTimer(BOMBLET_POLL, Timer_Bomblet, dp, TIMER_FLAG_NO_MAPCHANGE | TIMER_REPEAT);
	dp.WriteCell(EntIndexToEntRef(prop));
	dp.WriteCell(GetClientUserId(owner));
	dp.WriteCell(team);
}

/** Impact (a sharp turn or loss of speed of the physics prop, OF BombletImpact) or fuse. The
 *  velocity is measured from the position (a physics prop's m_vecAbsVelocity stays at the
 *  launch value). */
public Action Timer_Bomblet(Handle timer, DataPack dp)
{
	dp.Reset();
	int prop = EntRefToEntIndex(dp.ReadCell());
	int owner = GetClientOfUserId(dp.ReadCell());
	int team = dp.ReadCell();
	if (prop <= MaxClients)
		return Plugin_Stop;
	float now = GetGameTime(), v[3], p[3];
	GetEntPropVector(prop, Prop_Data, "m_vecAbsOrigin", p);
	SubtractVectors(p, g_vBombPos[prop], v);
	float dt = now - g_flBombLast[prop];
	ScaleVector(v, 1.0 / (dt > 0.001 ? dt : 0.001));
	g_vBombPos[prop] = p;
	g_flBombLast[prop] = now;
	float prev = GetVectorLength(g_vBombVel[prop]), cur = GetVectorLength(v);
	bool impact = now - g_flBombBorn[prop] >= BOMBLET_POLL * 1.5 && prev > 1.0
		&& (cur < prev * 0.6 || GetVectorDotProduct(v, g_vBombVel[prop]) < 0.8 * prev * cur);
	g_vBombVel[prop] = v;
	if (!impact && now < g_flBombFuse[prop])
		return Plugin_Continue;
	float pos[3];
	GetEntPropVector(prop, Prop_Data, "m_vecAbsOrigin", pos);
	RemoveEntity(prop);
	BombletExplode(owner, team, pos, impact);
	return Plugin_Stop;
}

void BombletExplode(int owner, int team, const float pos[3], bool impact)
{
	int boom = CreateEntityByName("env_explosion");
	if (boom == -1)
		return;
	DispatchKeyValue(boom, "iMagnitude", BOMBLET_DAMAGE);
	DispatchKeyValue(boom, "iRadiusOverride", BOMBLET_RADIUS);
	DispatchKeyValue(boom, "spawnflags", "44");   // no fireball, smoke or sparks: the energy core instead
	DispatchSpawn(boom);
	if (owner)
	{
		SetEntPropEnt(boom, Prop_Send, "m_hOwnerEntity", owner);   // kill credit; team rules apply
		SetEntProp(boom, Prop_Send, "m_iTeamNum", GetClientTeam(owner));
	}
	TeleportEntity(boom, pos, NULL_VECTOR, NULL_VECTOR);
	AcceptEntityInput(boom, "Explode");
	ParticleOn(0, BlueParticles(team) ? "drg_cow_explosioncore_normal_blue" : "drg_cow_explosioncore_normal", pos);
	Step("gib bomblet exploded (%s)", impact ? "impact" : "fuse");
	CreateTimer(0.5, Timer_KillEnt, EntIndexToEntRef(boom), TIMER_FLAG_NO_MAPCHANGE);
}

public Action Timer_KillEnt(Handle timer, int ref)
{
	int e = EntRefToEntIndex(ref);
	if (e > MaxClients)
		RemoveEntity(e);
	return Plugin_Stop;
}

/**
 * Live TF2 drops an ammo box on death, not the weapon model (option, on by default).
 * CTFAmmoPack::Create sets the weapon's model name and spawns at once; Spawn() calls
 * SetModel(GetModelName()) and the physics object is built from that model. Swapping the model
 * afterwards (rounds 1-5) kept the weapon's collision (it rolled like a ball): the name is
 * replaced before Spawn instead, so the box gets ammopack_medium's own .phy.
 * TF2C's client adds EF_ITEM_BLINK to every new tf_ammo_pack (C_TFAmmoPack::OnDataChanged,
 * client cvar tf2c_highlight_ammo, default 1): the pulsing additive pass looks fullbright on
 * the box. m_fEffects is networked and the client's RecvProxy replaces its local flags, so
 * the server sends the flag once and clears it: the box is then lit like a map ammo pack.
 */
public Action Hook_AmmoPackSpawn(int entity)
{
	if (!g_cvAmmoBox.BoolValue || g_bMapExempt)
		return Plugin_Continue;
	// Only a player's death drop: destroyed buildings throw their metal gibs as tf_ammo_pack
	// too (CBaseObject gibs, owned by the building, gib models) and stay stock.
	int owner = GetEntPropEnt(entity, Prop_Send, "m_hOwnerEntity");
	char model[PLATFORM_MAX_PATH];
	GetEntPropString(entity, Prop_Data, "m_ModelName", model, sizeof(model));
	if (owner < 1 || owner > MaxClients || StrContains(model, "gib", false) != -1)
	{
		Step("ammo pack %d left stock (owner %d, model %s)", entity, owner, model);
		return Plugin_Continue;
	}
	DispatchKeyValue(entity, "model", AMMOBOX_MODEL);
	CreateTimer(0.15, Timer_AmmoBlink, EntIndexToEntRef(entity), TIMER_FLAG_NO_MAPCHANGE);
	return Plugin_Continue;
}

public Action Timer_AmmoBlink(Handle timer, int ref)
{
	int entity = EntRefToEntIndex(ref);
	if (entity <= MaxClients)
		return Plugin_Stop;
	int fx = GetEntProp(entity, Prop_Send, "m_fEffects");
	if (!(fx & EF_ITEM_BLINK))
	{
		SetEntProp(entity, Prop_Send, "m_fEffects", fx | EF_ITEM_BLINK);
		CreateTimer(0.25, Timer_AmmoBlink, ref, TIMER_FLAG_NO_MAPCHANGE);
	}
	else
		SetEntProp(entity, Prop_Send, "m_fEffects", fx & ~EF_ITEM_BLINK);
	return Plugin_Stop;
}

public Action Hook_PackTouch(int pack, int other)
{
	if (!IsMerc(other))
		return Plugin_Continue;
	float now = GetGameTime();
	if ((GetEntProp(pack, Prop_Send, "m_fEffects") & EF_NODRAW) || now < g_flPackReady[pack] || now < g_flNextPackTouch[other])
		return Plugin_Continue;
	g_flNextPackTouch[other] = now + 0.5;
	if (GetURandomFloat() >= g_cvPackChance.FloatValue)
		return Plugin_Continue;
	g_flPackReady[pack] = now + g_cvPackRespawn.FloatValue;
	SpawnPackWeapon(other, pack);
	// The game consumes the pack itself when he needs ammo; otherwise it is used up here,
	// as OF/MarxVee ammo packs were (one weapon per pack until it respawns).
	DataPack dp = new DataPack();
	dp.WriteCell(EntIndexToEntRef(pack));
	RequestFrame(Frame_ConsumePack, dp);
	return Plugin_Continue;
}

public void Frame_ConsumePack(DataPack dp)
{
	dp.Reset();
	int pack = EntRefToEntIndex(dp.ReadCell());
	delete dp;
	if (pack <= MaxClients || (GetEntProp(pack, Prop_Send, "m_fEffects") & EF_NODRAW))
		return;
	AcceptEntityInput(pack, "Disable");
	CreateTimer(g_cvPackRespawn.FloatValue, Timer_EnablePack, EntIndexToEntRef(pack), TIMER_FLAG_NO_MAPCHANGE);
}

public Action Timer_EnablePack(Handle timer, int ref)
{
	int pack = EntRefToEntIndex(ref);
	if (pack > MaxClients)
		AcceptEntityInput(pack, "Enable");
	return Plugin_Stop;
}

void SpawnPackWeapon(int client, int pack)
{
	float total = 0.0;
	for (int i = 0; i < g_WWeight.Length; i++)
		if (FindWeaponByDef(client, g_WDef.Get(i)) == -1)
			total += view_as<float>(g_WWeight.Get(i));
	if (total <= 0.0)
		return;
	float roll = GetURandomFloat() * total;
	int pick = -1;
	for (int i = 0; i < g_WWeight.Length; i++)
	{
		float w = g_WWeight.Get(i);
		if (w <= 0.0 || FindWeaponByDef(client, g_WDef.Get(i)) != -1)
			continue;
		roll -= w;
		pick = i;
		if (roll <= 0.0)
			break;
	}
	if (pick < 0)
		return;
	PickupData d;
	d.def = g_WDef.Get(pick);
	d.slot = g_WSlot.Get(pick);
	g_WItem.GetString(pick, d.item, sizeof(d.item));
	char model[PLATFORM_MAX_PATH];
	g_WModel.GetString(pick, model, sizeof(model));
	float pos[3];
	GetEntPropVector(pack, Prop_Data, "m_vecAbsOrigin", pos);
	pos[2] += 16.0;
	int skin = GetClientTeam(client) == 3 ? 1 : 0;
	SpawnPickup(d, model, pos, view_as<float>({ 0.0, 0.0, 120.0 }), skin);
}

/* ------------------------------------------------------------------ */
/* Death                                                              */
/* ------------------------------------------------------------------ */

public void Event_Death(Event event, const char[] name, bool dontBroadcast)
{
	int victim = GetClientOfUserId(event.GetInt("userid"));
	int attacker = GetClientOfUserId(event.GetInt("attacker"));
	int flags = event.GetInt("death_flags");
	if (victim)
		ChainsawReset(victim);
	// One drop per death, never on maps that run their own drops (exempt).
	if (victim && !(flags & 32) && !g_bMapExempt && GetEngineTime() - g_flLastDeathDrop[victim] > 1.0)
	{
		g_flLastDeathDrop[victim] = GetEngineTime();
		int weapon = GetEntPropEnt(victim, Prop_Send, "m_hActiveWeapon");
		if (weapon > MaxClients)
		{
			int slot = -1;
			for (int s = 0; s < SLOTS; s++)
				if (GetPlayerWeaponSlot(victim, s) == weapon)
					slot = s;
			bool drop = slot >= 0 && (g_bMerc[victim] ? (g_cvDropOnDeath.BoolValue && !IsDefaultItem(ItemDef(weapon))) : g_cvAllDrop.BoolValue);
			if (drop)
				DropWeapon(victim, weapon, slot, true);
		}
	}
	if (victim)
	{
		EndTaunt(victim);
		StopLightning(victim, false);
	}
	if (victim && g_bMerc[victim])
	{
		// The game plays the class death scream (Soldier.Death / CritDeath / MeleeDeath /
		// ExplosionDeath) right after this event, when g_bMerc is already off: the corpse flag
		// keeps the sound hook rewriting it to one Merc death line. If no scream comes (silent
		// kills, a scream the hook never sees), the line is played next frame.
		if (!(flags & 32))
		{
			g_bMercCorpse[victim] = true;
			g_bDeathLine[victim] = false;
			g_bDeathCrit[victim] = event.GetInt("customkill") == 1 || (event.GetInt("damagebits") & DMG_CRITICAL) != 0;
			RequestFrame(Frame_DeathLine, GetClientUserId(victim));
		}
		g_bMerc[victim] = false;
	}

	if (attacker && attacker != victim && IsMerc(attacker))
	{
		if (flags & 1)
			Speak(attacker, "_domination");
		else if (flags & 4)
			Speak(attacker, "_revenge");
	}
	// Other classes' OF lines about a Mercenary victim (e.g. Scout dominating him).
	if (attacker && attacker != victim && victim && g_bWant[victim] && !g_bMerc[attacker] && (flags & (1 | 4)))
	{
		DataPack dp = new DataPack();
		dp.WriteCell(GetClientUserId(attacker));
		dp.WriteString((flags & 1) ? "domination" : "revenge");
		CreateTimer(0.15, Timer_Targeted, dp, TIMER_FLAG_NO_MAPCHANGE | TIMER_DATA_HNDL_CLOSE);
	}
}

public void Frame_DeathLine(int userid)
{
	int client = GetClientOfUserId(userid);
	if (!client || !g_bMercCorpse[client] || g_bDeathLine[client] || IsPlayerAlive(client))
		return;
	g_bDeathLine[client] = true;
	char concept[24];
	DeathConcept(client, concept, sizeof(concept));
	Speak(client, concept);
}

void DeathConcept(int client, char[] out, int maxlen)
{
	strcopy(out, maxlen, g_bDeathCrit[client] ? "_paincrticialdeath" : "_painsevere");
}

public Action Timer_Targeted(Handle timer, DataPack dp)
{
	dp.Reset();
	int speaker = GetClientOfUserId(dp.ReadCell());
	char kind[16];
	dp.ReadString(kind, sizeof(kind));
	if (speaker && IsPlayerAlive(speaker))
		SpeakTargeted(speaker, kind);
	return Plugin_Stop;
}

/* ------------------------------------------------------------------ */
/* Voice                                                              */
/* ------------------------------------------------------------------ */

ArrayList ConceptList(const char[] concept)
{
	char key[160];
	ArrayList l;
	FormatEx(key, sizeof(key), "mercenary/%s", concept);
	if (g_Concepts.GetValue(key, l) && l.Length)
		return l;
	FormatEx(key, sizeof(key), "mercenary/%s0", concept);
	if (g_Concepts.GetValue(key, l) && l.Length)
		return l;
	return null;
}

bool IsPainConcept(const char[] concept)
{
	return StrContains(concept, "_pain") == 0;
}

int VoicePitch(const char[] concept)
{
	return IsPainConcept(concept) ? SNDPITCH_NORMAL : g_cvPitch.IntValue;
}

bool Speak(int client, const char[] concept)
{
	ArrayList l = ConceptList(concept);
	if (l == null)
		return false;
	char sample[PLATFORM_MAX_PATH];
	l.GetString(GetRandomInt(0, l.Length - 1), sample, sizeof(sample));
	Step("speak %N %s: %s pitch %d", client, concept, sample, VoicePitch(concept));
	if (client == g_iLastVoiceEnt || g_iLastVoiceEnt == 0)
		g_flLastVoiceAt = GetEngineTime();
	g_iLastVoiceEnt = client;
	g_bOwnEmit = true;
	EmitSoundToAll(sample, client, SNDCHAN_VOICE, g_cvLevel.IntValue, SND_CHANGEPITCH, SNDVOL_NORMAL, VoicePitch(concept));
	g_bOwnEmit = false;
	return true;
}

/** Other classes' lines about a Mercenary (voice.cfg "targeted" <class>/mercenary/<kind>). */
bool SpeakTargeted(int speaker, const char[] kind, const char[] role = "mercenary")
{
	int cls = view_as<int>(TF2_GetPlayerClass(speaker));
	if (cls < 1 || cls > 10)
		return false;
	char key[160], sample[PLATFORM_MAX_PATH];
	FormatEx(key, sizeof(key), "@targeted/%s/%s/%s", g_sClassNames[cls], role, kind);
	ArrayList l;
	Step("targeted lookup %s", key);
	if (!g_Concepts.GetValue(key, l) || l.Length == 0)
		return false;
	l.GetString(GetRandomInt(0, l.Length - 1), sample, sizeof(sample));
	Step("targeted %N %s: %s", speaker, kind, sample);
	g_bOwnEmit = true;
	EmitSoundToAll(sample, speaker, SNDCHAN_VOICE, g_cvLevel.IntValue);
	g_bOwnEmit = false;
	return true;
}

/** Coated in Jarate / Mad Milk / gas: a random negative or jeers line (cooldown 3 s). */
float g_flNextCoatLine[MAXPLAYERS + 1];

public void TF2_OnConditionAdded(int client, TFCond condition)
{
	int c = view_as<int>(condition);
	// A Soldier taunt scene that did not come from the taunt key (bots call Taunt() directly):
	// stop it and play the Merc taunt instead.
	if (c == 7 && g_cvTaunts.BoolValue && IsMerc(client) && !g_bTaunting[client] && !HoldsLunchbox(client))
	{
		Step("native taunt on %N replaced", client);
		TF2_RemoveCondition(client, condition);
		RequestFrame(Frame_MercTaunt, GetClientUserId(client));
		return;
	}
	if ((c != 24 && c != 27 && c != 123) || !IsMerc(client))   // TF_COND_URINE, _MAD_MILK, _GAS
		return;
	float now = GetEngineTime();
	if (now < g_flNextCoatLine[client])
		return;
	g_flNextCoatLine[client] = now + 3.0;
	if (!Speak(client, GetURandomFloat() < 0.5 ? "_negativevocalization" : "_jeers"))
		Speak(client, "_negativevocalization");
}

/** "vo/soldier_painsharp03.mp3" -> "_painsharp". */
bool StockConcept(const char[] path, char[] concept, int maxlen)
{
	int slash = FindCharInString(path, '/', true);
	char base[96];
	strcopy(base, sizeof(base), path[slash + 1]);
	int us = FindCharInString(base, '_');
	if (us < 0)
		return false;
	int dot = FindCharInString(base, '.', true);
	if (dot > 0)
		base[dot] = '\0';
	int end = strlen(base);
	while (end > us + 1 && (IsCharNumeric(base[end - 1]) || (end - 1 > us + 1 && base[end - 1] == 'b' && IsCharNumeric(base[end - 2]))))
		end--;
	base[end] = '\0';
	FormatEx(concept, maxlen, "_%s", base[us + 1]);
	for (int i = 0; concept[i]; i++)
		concept[i] = CharToLower(concept[i]);   // TF2C files mix case: soldier_PainSharp03
	return end > us + 1;
}

/**
 * Soldier speech from a Mercenary (response rules, pain, death, auto lines) is rewritten
 * to the Mercenary line of the same concept; Soldier lines with no Merc equivalent are
 * silenced. Non-pain lines get the pitch cvar.
 */
public Action Hook_Sound(int clients[MAXPLAYERS], int &numClients, char sample[PLATFORM_MAX_PATH], int &entity, int &channel, float &volume, int &level, int &pitch, int &flags, char soundEntry[PLATFORM_MAX_PATH], int &seed)
{
	if (g_bOwnEmit || entity < 1 || entity > MaxClients || !(g_bMerc[entity] || g_bMercCorpse[entity]) || !IsClientInGame(entity))
		return Plugin_Continue;
	int start = 0;
	while (sample[start] == ')' || sample[start] == '^' || sample[start] == '*' || sample[start] == '#' || sample[start] == '<' || sample[start] == '>')
		start++;
	if (StrContains(sample[start], "vo/", false) != 0)
		return Plugin_Continue;
	bool v;
	if (g_PersonaSamples.GetValue(sample[start], v))
		return Plugin_Continue;
	// The Heavy's "om nom nom" when the Merc eats a Sandvich (TF2C plays vo/SandwichEat09 for
	// any class eating a lunchbox): kept, as in the stock tf2cc (voice.cfg "sandwicheat").
	if (StrContains(sample[start], "vo/sandwicheat", false) == 0 && !g_bMercCorpse[entity])
	{
		Step("voice %N: %s kept (Sandvich)", entity, sample);
		return Plugin_Continue;
	}
	char concept[64];
	bool corpse = !g_bMerc[entity] && g_bMercCorpse[entity];
	float now = GetEngineTime();
	bool sameEmit = entity == g_iLastVoiceEnt && now - g_flLastVoiceAt < 0.05 && StrEqual(sample, g_sLastVoiceIn);
	if (corpse)
	{
		// The Soldier death scream (or any Soldier line from the corpse): one Merc death line
		// per death, the same one for every recipient group of that emit.
		if (g_bDeathLine[entity] && !sameEmit)
		{
			Step("voice %N (dead): %s blocked", entity, sample);
			return Plugin_Stop;
		}
		g_bDeathLine[entity] = true;
		DeathConcept(entity, concept, sizeof(concept));
	}
	else if (!StockConcept(sample[start], concept, sizeof(concept)))
	{
		Step("voice %N: %s blocked (no concept)", entity, sample);
		return Plugin_Stop;
	}
	ArrayList l = ConceptList(concept);
	if (l == null)
	{
		Step("voice %N: %s blocked (no Merc %s)", entity, sample, concept);
		return Plugin_Stop;
	}
	char orig[PLATFORM_MAX_PATH];
	strcopy(orig, sizeof(orig), sample);
	// The hook runs once per recipient group: every group hears the same chosen line.
	if (sameEmit)
		strcopy(sample, sizeof(sample), g_sLastVoiceOut);
	else
	{
		l.GetString(GetRandomInt(0, l.Length - 1), sample, sizeof(sample));
		g_iLastVoiceEnt = entity;
		g_flLastVoiceAt = now;
		strcopy(g_sLastVoiceIn, sizeof(g_sLastVoiceIn), orig);
		strcopy(g_sLastVoiceOut, sizeof(g_sLastVoiceOut), sample);
	}
	pitch = VoicePitch(concept);
	Step("voice %N: %s -> %s pitch %d", entity, orig, sample, pitch);
	flags |= SND_CHANGEPITCH;
	return Plugin_Changed;
}

/**
 * "Spy!" (voicemenu 1 1):
 *  - a Mercenary names what is under his crosshair: any of the ten classes (Civilian
 *    included; a disguised enemy by his disguise) or another Mercenary;
 *  - Scout, Soldier, Engineer and Civilian aiming at a Mercenary use their tf2cc line
 *    for him.
 */
public Action Listener_VoiceMenu(int client, const char[] command, int argc)
{
	if (!client || !IsPlayerAlive(client) || argc < 2)
		return Plugin_Continue;
	char a[4], b[4];
	GetCmdArg(1, a, sizeof(a));
	GetCmdArg(2, b, sizeof(b));
	if (StringToInt(a) != 1 || StringToInt(b) != 1)
		return Plugin_Continue;
	float now = GetGameTime();
	if (g_bMerc[client])
	{
		if (now >= g_flNextSpeak[client])
		{
			g_flNextSpeak[client] = now + 1.5;
			MercSpyCallout(client);
		}
		return Plugin_Handled;
	}
	int target = SpyTarget(client);
	// tf2cc lines for a target that shows as a Mercenary, or as TF2C's own Civilian (a real
	// Civilian, or an enemy Spy disguised as one): Evermatt's Scout "the Civilian's a Spy!".
	char role[16];
	if (target > 0 && g_bMerc[target])
		strcopy(role, sizeof(role), "mercenary");
	else if (target > 0 && VisibleClass(client, target) == 10)
		strcopy(role, sizeof(role), "civilian");
	else
		return Plugin_Continue;
	if (now < g_flNextSpeak[client])
		return Plugin_Handled;
	if (!SpeakTargeted(client, "cloakedspy", role))
		return Plugin_Continue;
	g_flNextSpeak[client] = now + 1.5;
	return Plugin_Handled;
}

/** The class the viewer sees: an enemy Spy's disguise, else the real class. */
int VisibleClass(int viewer, int target)
{
	int cls = view_as<int>(TF2_GetPlayerClass(target));
	if (GetClientTeam(target) != GetClientTeam(viewer) && TF2_IsPlayerInCondition(target, TFCond_Disguised))
		cls = GetEntProp(target, Prop_Send, "m_nDisguiseClass");
	return cls;
}

void MercSpyCallout(int client)
{
	int target = SpyTarget(client);
	char concept[64];
	if (target > 0)
	{
		if (g_bMerc[target])
		{
			if (Speak(client, "_spy_mercenary"))
				return;
		}
		else
		{
			int cls = view_as<int>(TF2_GetPlayerClass(target));
			if (GetClientTeam(target) != GetClientTeam(client))
			{
				if (TF2_IsPlayerInCondition(target, TFCond_Cloaked))
					cls = TF2_IsPlayerInCondition(target, TFCond_CloakFlicker) ? view_as<int>(TFClass_Spy) : 0;
				else if (TF2_IsPlayerInCondition(target, TFCond_Disguised))
					cls = GetEntProp(target, Prop_Send, "m_nDisguiseClass");
			}
			if (cls >= 1 && cls <= 10)
			{
				FormatEx(concept, sizeof(concept), "_spy_%s", g_sClassNames[cls]);
				if (Speak(client, concept))
					return;
			}
		}
	}
	Speak(client, "_cloakedspy");
}

int g_iForcedTarget = -1;

public Action Cmd_SpyTest(int client, int args)
{
	char a[64], b[64];
	GetCmdArg(1, a, sizeof(a));
	GetCmdArg(2, b, sizeof(b));
	int sp = FindTarget(client, a, false, false), tg = FindTarget(client, b, false, false);
	if (sp <= 0 || tg <= 0)
		return Plugin_Handled;
	g_iForcedTarget = tg;
	g_flNextSpeak[sp] = 0.0;
	if (g_bMerc[sp])
		MercSpyCallout(sp);
	else if (!SpeakTargeted(sp, "cloakedspy", g_bMerc[tg] ? "mercenary" : (VisibleClass(sp, tg) == 10 ? "civilian" : "none")))
		ReplyToCommand(client, "no targeted line for that class");
	g_iForcedTarget = -1;
	return Plugin_Handled;
}

/** Player under the crosshair, or the visible player closest to it within ~18 degrees. */
int SpyTarget(int client)
{
	if (g_iForcedTarget > 0)
		return g_iForcedTarget;
	float eye[3], ang[3], fwd[3];
	GetClientEyePosition(client, eye);
	GetClientEyeAngles(client, ang);
	GetAngleVectors(ang, fwd, NULL_VECTOR, NULL_VECTOR);
	Handle tr = TR_TraceRayFilterEx(eye, ang, MASK_SHOT, RayType_Infinite, Filter_NotSelf, client);
	int hit = TR_GetEntityIndex(tr);
	delete tr;
	if (hit >= 1 && hit <= MaxClients && IsPlayerAlive(hit))
		return hit;
	int best = -1;
	float bestDot = 0.95;
	for (int i = 1; i <= MaxClients; i++)
	{
		if (i == client || !IsClientInGame(i) || !IsPlayerAlive(i))
			continue;
		float pos[3], dir[3];
		GetClientEyePosition(i, pos);
		pos[2] -= 20.0;
		MakeVectorFromPoints(eye, pos, dir);
		if (GetVectorLength(dir) > 2000.0)
			continue;
		NormalizeVector(dir, dir);
		float dot = GetVectorDotProduct(dir, fwd);
		if (dot <= bestDot)
			continue;
		Handle t = TR_TraceRayFilterEx(eye, pos, MASK_SOLID_BRUSHONLY, RayType_EndPoint, Filter_NotSelf, client);
		bool clear = !TR_DidHit(t);
		delete t;
		if (clear)
		{
			bestDot = dot;
			best = i;
		}
	}
	return best;
}

public bool Filter_NotSelf(int entity, int mask, int self)
{
	return entity != self;
}

/* ------------------------------------------------------------------ */
/* Dropping the weapon in hand (dropitem / !dropweapon)               */
/* ------------------------------------------------------------------ */

/** The game's drop key ("dropitem") drops the intelligence or a powerup when he carries one;
 *  otherwise a Mercenary drops the weapon in hand. */
public Action Listener_DropItem(int client, const char[] command, int argc)
{
	if (!client || !IsMerc(client) || CarriesItem(client))
		return Plugin_Continue;
	return DropActive(client, false) ? Plugin_Handled : Plugin_Continue;
}

public Action Cmd_DropWeapon(int client, int args)
{
	if (client && IsMerc(client))
		DropActive(client, true);
	return Plugin_Handled;
}

bool CarriesItem(int client)
{
	return HasEntProp(client, Prop_Send, "m_hItem") && GetEntPropEnt(client, Prop_Send, "m_hItem") > MaxClients;
}

/**
 * OF/MarxVee rules: the default pistol and crowbar are never dropped (each slot falls back
 * to its default); a dropped weapon is a normal pickup (its dropper cannot take it back for
 * 1.5 s). The slot gets its default weapon back, or stays empty (primary); he then holds that
 * default, or his next weapon. He never drops his last weapon.
 */
bool DropActive(int client, bool tell)
{
	int w = GetEntPropEnt(client, Prop_Send, "m_hActiveWeapon");
	int s = SlotOfWeapon(client, w);
	Step("drop request %N: active %d slot %d", client, w, s);
	if (s < 0)
		return false;
	int def = ItemDef(w);
	if (IsDefaultItem(def))
	{
		if (tell)
			PrintHintText(client, "Your default weapons cannot be dropped");
		return false;
	}
	char fallback[64];
	DefaultForSlot(s, fallback, sizeof(fallback));
	int others = 0;
	for (int k = 0; k < SLOTS; k++)
		if (k != s && GetPlayerWeaponSlot(client, k) > MaxClients)
			others++;
	if (!fallback[0] && others == 0)
	{
		if (tell)
			PrintHintText(client, "You cannot drop your last weapon");
		return false;
	}
	if (DropWeapon(client, w, s, false) == -1)
	{
		Step("drop %N: no pickup for def %d", client, def);
		return false;
	}
	Step("drop %N: slot %d def %d (default back: %s)", client, s, def, fallback[0] ? fallback : "none");
	RemoveWeapon(client, w);
	strcopy(g_sInv[client][s], sizeof(g_sInv[][]), fallback);
	if (fallback[0])
		GiveItem(client, fallback);
	KeepInHand(client, -1, s);
	return true;
}

void DefaultForSlot(int slot, char[] out, int maxlen)
{
	out[0] = '\0';
	for (int i = 0; i < g_WItem.Length; i++)
		if (g_WDefault.Get(i) && g_WSlot.Get(i) == slot)
		{
			g_WItem.GetString(i, out, maxlen);
			return;
		}
}

public Action Cmd_DropTest(int client, int args)
{
	char pattern[64], name[64];
	GetCmdArg(1, pattern, sizeof(pattern));
	int targets[MAXPLAYERS];
	bool ml;
	int n = ProcessTargetString(pattern, client, targets, sizeof(targets), COMMAND_FILTER_ALIVE, name, sizeof(name), ml);
	for (int i = 0; i < n; i++)
		ReplyToCommand(client, "[tf2cc] drop %N (merc %d, carrying %d): %s", targets[i], IsMerc(targets[i]), CarriesItem(targets[i]),
			IsMerc(targets[i]) && !CarriesItem(targets[i]) && DropActive(targets[i], true) ? "dropped" : "nothing dropped");
	return Plugin_Handled;
}

public Action Cmd_UseTest(int client, int args)
{
	char pattern[64], name[64];
	GetCmdArg(1, pattern, sizeof(pattern));
	int targets[MAXPLAYERS];
	bool ml;
	int n = ProcessTargetString(pattern, client, targets, sizeof(targets), COMMAND_FILTER_ALIVE, name, sizeof(name), ml);
	for (int i = 0; i < n; i++)
		ReplyToCommand(client, "[tf2cc] use %N: %s", targets[i], TrySwapNearby(targets[i]) ? "took a weapon" : "nothing in reach");
	return Plugin_Handled;
}

/* ------------------------------------------------------------------ */
/* Taunts                                                             */
/* ------------------------------------------------------------------ */

/*
 * TF2C's taunt key asks the Soldier's response rules for a scene: there are scenes only for
 * his rocket launcher, shotgun, shovel and a few items (talker tf.txt), so with the Merc
 * pistol or a picked-up weapon nothing happened, and the shovel scene is the Soldier's own,
 * with his scream. A Mercenary's taunt key instead plays the OF Merc taunt sequence for the
 * held weapon on the player model (PlayerAnimEvent CUSTOM_SEQUENCE, as tf2cc does on stock
 * TF2), in the taunt camera, frozen like a stock taunt. Lines are Merc lines only.
 * Weapon -> taunt (tf2cc roles.cfg "weapon_taunts", OF talker): seq:seconds[:concept[:delay]].
 */
static const char g_sWeaponTaunts[][] =
{
	"merc_supershotgun=taunt01:3.37", "merc_rocketlauncher=taunt01:3.37", "merc_railgun=taunt01:3.37",
	"merc_gatling=taunt01:3.37", "merc_lightning=taunt01:3.37",
	"merc_shotgun=taunt02:2.93:_laughevil:1.66", "merc_dynamite=taunt02:2.93:_laughevil:1.66",
	"merc_nailgun=taunt02:2.93:_laughevil:1.66", "merc_chinalake=taunt02:2.93:_laughevil:1.66",
	"merc_tommygun=taunt02:2.93:_laughevil:1.66", "merc_assaultrifle=taunt02:2.93:_laughevil:1.66",
	"merc_smg=taunt02:2.93:_laughevil:1.66",
	"merc_crowbar=taunt03:1.83", "merc_leadpipe=taunt03:1.83", "merc_knife=taunt03:1.83",
	"merc_fists=taunt04:2.23", "merc_gib=taunt04:2.23", "merc_chainsaw=taunt04:2.23",
	"merc_pistol=taunt_bond:2.95", "merc_akimbo=taunt_bond:2.95", "merc_revolver=taunt_bond:2.95",
	// Stock weapons he picked up: by slot, like OF's group fallbacks (PRIMARY -> super shotgun set...).
	"slot0=taunt01:3.37", "slot1=taunt02:2.93:_laughevil:1.66", "slot2=taunt03:1.83",
	"default=taunt01:3.37"
};

public void Frame_MercTaunt(int userid)
{
	int client = GetClientOfUserId(userid);
	if (client)
		TryMercTaunt(client);
}

/** Lunchbox items eat through the game's own taunt (that is what heals): leave those alone. */
bool HoldsLunchbox(int client)
{
	int w = GetEntPropEnt(client, Prop_Send, "m_hActiveWeapon");
	char cls[64];
	return w > MaxClients && GetEntityClassname(w, cls, sizeof(cls)) && StrContains(cls, "lunchbox") != -1;
}

public Action Listener_Taunt(int client, const char[] command, int argc)
{
	if (!client || !g_bMerc[client] || !g_cvTaunts.BoolValue || HoldsLunchbox(client))
		return Plugin_Continue;
	TryMercTaunt(client);
	return Plugin_Handled;     // never the Soldier's scene
}

public Action Cmd_TauntTest(int client, int args)
{
	char pattern[64], name[64];
	GetCmdArg(1, pattern, sizeof(pattern));
	int targets[MAXPLAYERS];
	bool ml;
	int n = ProcessTargetString(pattern, client, targets, sizeof(targets), COMMAND_FILTER_ALIVE, name, sizeof(name), ml);
	for (int i = 0; i < n; i++)
		ReplyToCommand(client, "[tf2cc] taunt %N: %s", targets[i], TryMercTaunt(targets[i]) ? "started" : "not allowed now");
	return Plugin_Handled;
}

bool TryMercTaunt(int client)
{
	float now = GetGameTime();
	if (g_flNextTaunt[client] - now > 30.0)    // stale stamp from the previous map
		g_flNextTaunt[client] = 0.0;
	if (!IsMerc(client) || g_bTaunting[client] || now < g_flNextTaunt[client]
		|| !(GetEntityFlags(client) & FL_ONGROUND) || GetEntProp(client, Prop_Data, "m_nWaterLevel") > 2
		|| TF2_IsPlayerInCondition(client, TFCond_Cloaked) || TF2_IsPlayerInCondition(client, view_as<TFCond>(17)))
		return false;
	char spec[64];
	WeaponTauntSpec(client, spec, sizeof(spec));
	char p[4][32];
	ExplodeString(spec, ":", p, sizeof(p), sizeof(p[]));
	float dur = p[1][0] ? StringToFloat(p[1]) : 3.0;
	int seq = LookupPlayerSequence(client, p[0]);
	Step("taunt %N: %s seq %d", client, spec, seq);
	if (seq < 0)
		return false;
	StartMercTaunt(client, seq, p[0], dur > 0.5 ? dur : 3.0, p[2], p[3][0] ? StringToFloat(p[3]) : 0.0);
	return true;
}

void WeaponTauntSpec(int client, char[] spec, int maxlen)
{
	char id[48] = "default";
	int w = GetEntPropEnt(client, Prop_Send, "m_hActiveWeapon");
	int mi = w > MaxClients ? MercWeaponIndex(ItemDef(w)) : -1;
	if (mi >= 0)
	{
		g_WItem.GetString(mi, id, sizeof(id));
		if (StrContains(id, "tf2cc_") == 0)
			strcopy(id, sizeof(id), id[6]);
	}
	else if (w > MaxClients)
	{
		int s = SlotOfWeapon(client, w);
		if (s >= 0)
			FormatEx(id, sizeof(id), "slot%d", s);
	}
	char fallback[64];
	for (int i = 0; i < sizeof(g_sWeaponTaunts); i++)
	{
		int eq = FindCharInString(g_sWeaponTaunts[i], '=');
		char key[48];
		strcopy(key, eq + 1 < sizeof(key) ? eq + 1 : sizeof(key), g_sWeaponTaunts[i]);
		if (StrEqual(key, id))
		{
			strcopy(spec, maxlen, g_sWeaponTaunts[i][eq + 1]);
			return;
		}
		if (StrEqual(key, "default"))
			strcopy(fallback, sizeof(fallback), g_sWeaponTaunts[i][eq + 1]);
	}
	strcopy(spec, maxlen, fallback);
}

/** Sequence index on the player's current model (VScript LookupSequence), -1 if missing. */
int LookupPlayerSequence(int client, const char[] name)
{
	g_cvRet.SetString("-1");
	RunScriptF(client, "Convars.SetValue(\"tf2cc_tf2c_ret\", \"\" + self.LookupSequence(\"%s\"))", name);
	char out[16];
	g_cvRet.GetString(out, sizeof(out));
	return out[0] ? StringToInt(out) : -1;
}

/** Upright part of each OF taunt sequence (cycle in-out, tf2cc roles.cfg taunt_windows): the
 *  sequences ramp from and back to a pose collapsed at the origin for scene blending. */
void TauntWindow(const char[] seqName, float &cin, float &cout)
{
	cin = 0.05;
	cout = 0.90;
	if (StrEqual(seqName, "taunt01")) { cin = 0.05; cout = 0.88; }
	else if (StrEqual(seqName, "taunt02")) { cin = 0.05; cout = 0.89; }
	else if (StrEqual(seqName, "taunt03")) { cin = 0.07; cout = 0.80; }
	else if (StrEqual(seqName, "taunt04")) { cin = 0.07; cout = 0.92; }
	else if (StrEqual(seqName, "taunt_bond")) { cin = 0.07; cout = 0.80; }
}

float SequenceDurationOf(int client, int seq)
{
	g_cvRet.SetString("0");
	RunScriptF(client, "Convars.SetValue(\"tf2cc_tf2c_ret\", \"\" + self.SequenceDuration(%d))", seq);
	return g_cvRet.FloatValue;
}

/** Team skin the hidden player would show (C_TFPlayer::GetSkin: RED 0, BLU 1, GRN 4, YLW 5; +2 invulnerable). */
int CloneSkin(int client)
{
	int team = GetClientTeam(client);
	int skin = team == 3 ? 1 : team == 4 ? 4 : team == 5 ? 5 : 0;
	if (TF2_IsPlayerInCondition(client, TFCond_Ubercharged))
		skin += 2;
	return skin;
}

/**
 * The taunt plays on a clone standing where the player stands, facing where he faced when it
 * started; the player is hidden. Mouse look moves only the (third-person) camera, as in a
 * stock taunt: on the player model itself the body turned with the view.
 * tf_taunt_prop (flex: eyes keep their irises) has no animation think of its own, so its
 * cycle is advanced every frame; prop_dynamic is the fallback.
 */
int CreateTauntClone(int client, const char[] seqName, int seq, float cin)
{
	float pos[3], ang[3];
	GetClientAbsOrigin(client, pos);
	ang[1] = g_flTauntYaw[client];
	// funCBaseFlex: a flex entity (eyes keep their irises) WITHOUT client-side animation, so the
	// cycle set here every frame is what clients draw. tf_taunt_prop animates on the client
	// from cycle 0 and ignores it: the collapsed blend-in pose (sunk in the floor) showed.
	int prop = CreateEntityByName("funCBaseFlex");
	g_bCloneManualCycle[client] = prop != -1;
	if (prop != -1)
	{
		DispatchKeyValue(prop, "model", MERC_MODEL);
		DispatchSpawn(prop);
		SetEntityModel(prop, MERC_MODEL);
		SetEntProp(prop, Prop_Send, "m_nSolidType", 0);
		SetEntityMoveType(prop, MOVETYPE_NONE);
		SetEntProp(prop, Prop_Send, "m_nSequence", seq);
		SetEntPropFloat(prop, Prop_Send, "m_flPlaybackRate", 0.0);    // the cycle is driven from here only
		SetEntPropFloat(prop, Prop_Data, "m_flCycle", cin);
		SetEntProp(prop, Prop_Send, "m_nNewSequenceParity", (GetEntProp(prop, Prop_Send, "m_nNewSequenceParity") + 1) & 7);
		SetEntProp(prop, Prop_Send, "m_nResetEventsParity", (GetEntProp(prop, Prop_Send, "m_nResetEventsParity") + 1) & 7);
	}
	else
	{
		prop = CreateEntityByName("prop_dynamic_override");
		if (prop == -1)
			return -1;
		DispatchKeyValue(prop, "model", MERC_MODEL);
		DispatchKeyValue(prop, "solid", "0");
		DispatchKeyValue(prop, "DefaultAnim", seqName);
		DispatchKeyValue(prop, "HoldAnimation", "1");
		if (!DispatchSpawn(prop))
		{
			RemoveEntity(prop);
			return -1;
		}
		SetEntPropFloat(prop, Prop_Data, "m_flCycle", cin);
	}
	SetEntProp(prop, Prop_Send, "m_nSkin", CloneSkin(client));
	if (HasEntProp(prop, Prop_Send, "m_nBody"))
		SetEntProp(prop, Prop_Send, "m_nBody", GetEntProp(client, Prop_Send, "m_nBody"));
	TeleportEntity(prop, pos, ang, NULL_VECTOR);
	return prop;
}

void SetWearablesNoDraw(int client, bool hide)
{
	int ent = -1;
	while ((ent = FindEntityByClassname(ent, "tf_wearable*")) != -1)
	{
		if (GetEntPropEnt(ent, Prop_Send, "m_hOwnerEntity") != client)
			continue;
		int fx = GetEntProp(ent, Prop_Send, "m_fEffects");
		SetEntProp(ent, Prop_Send, "m_fEffects", hide ? (fx | EF_NODRAW) : (fx & ~EF_NODRAW));
	}
}

public void OnGameFrame()
{
	float now = GetGameTime();
	for (int i = 1; i <= MaxClients; i++)
	{
		if (!g_bTaunting[i])
			continue;
		int prop = EntRefToEntIndex(g_iTauntClone[i]);
		if (prop <= MaxClients || !IsClientInGame(i))
			continue;
		// Only input is locked: the player still falls and rides platforms; the clone follows.
		float pos[3];
		GetClientAbsOrigin(i, pos);
		TeleportEntity(prop, pos, NULL_VECTOR, NULL_VECTOR);
		if (g_bCloneManualCycle[i] && g_flTauntLen[i] > 0.0)
		{
			float f = (now - g_flTauntStart[i]) / g_flTauntLen[i];
			if (f > 1.0)
				f = 1.0;
			SetEntPropFloat(prop, Prop_Data, "m_flCycle", g_flCycleIn[i] + f * g_flCycleSpan[i]);
		}
	}
}

void StartMercTaunt(int client, int seq, const char[] seqName, float duration, const char[] concept, float voiceDelay)
{
	float eyes0[3];
	GetClientEyeAngles(client, eyes0);
	g_flTauntYaw[client] = eyes0[1];
	float cin, cout;
	TauntWindow(seqName, cin, cout);
	float seqLen = SequenceDurationOf(client, seq);
	if (seqLen > 0.5)
		duration = seqLen * (cout - cin) - 0.05;   // show the upright part only, then the player is back
	g_flCycleIn[client] = cin;
	g_flCycleSpan[client] = cout - cin;
	g_flTauntStart[client] = GetGameTime();
	g_flTauntLen[client] = duration;
	int clone = CreateTauntClone(client, seqName, seq, cin);
	g_iTauntClone[client] = clone > MaxClients ? EntIndexToEntRef(clone) : INVALID_ENT_REFERENCE;
	if (clone > MaxClients)
	{
		g_iRenderBefore[client] = GetEntityRenderMode(client);
		SetEntityRenderMode(client, RENDER_NONE);
		SetWearablesNoDraw(client, true);
	}
	else
		SendAnimEvent(client, PLAYERANIMEVENT_CUSTOM_SEQUENCE, seq);   // no clone: on the player model
	// Model events, timed from the start of the shown part.
	if (seqLen > 0.5)
		voiceDelay = voiceDelay > cin * seqLen ? voiceDelay - cin * seqLen : 0.05;
	int weapon = GetEntPropEnt(client, Prop_Send, "m_hActiveWeapon");
	g_iTauntWeapon[client] = INVALID_ENT_REFERENCE;
	if (weapon > MaxClients)
	{
		// The OF taunts are empty-handed poses (the Bond taunt draws its own pistol).
		int fx = GetEntProp(weapon, Prop_Send, "m_fEffects");
		g_bTauntWeaponHidden[client] = (fx & EF_NODRAW) != 0;
		g_iTauntWeapon[client] = EntIndexToEntRef(weapon);
		SetEntProp(weapon, Prop_Send, "m_fEffects", fx | EF_NODRAW);
	}
	g_bTaunting[client] = true;
	float until = GetGameTime() + duration;
	SetEntPropFloat(client, Prop_Send, "m_flNextAttack", until);
	if (weapon > MaxClients && HasEntProp(weapon, Prop_Send, "m_flNextPrimaryAttack"))
	{
		SetEntPropFloat(weapon, Prop_Send, "m_flNextPrimaryAttack", until);
		SetEntPropFloat(weapon, Prop_Send, "m_flNextSecondaryAttack", until);
	}
	if (GetEntPropEnt(client, Prop_Send, "m_hGroundEntity") != -1)
	{
		float v[3];
		GetEntPropVector(client, Prop_Data, "m_vecVelocity", v);
		v[0] = v[1] = 0.0;
		TeleportEntity(client, NULL_VECTOR, NULL_VECTOR, v);
	}
	// Third person for the taunt; whatever sm_thirdperson had set is restored afterwards.
	g_iTauntCamBefore[client] = GetEntProp(client, Prop_Send, "m_nForceTauntCam");
	SetVariantInt(1);
	AcceptEntityInput(client, "SetForcedTauntCam");
	if (concept[0])
	{
		DataPack dp;
		CreateDataTimer(voiceDelay > 0.0 ? voiceDelay : 0.05, Timer_TauntVoice, dp, TIMER_FLAG_NO_MAPCHANGE);
		dp.WriteCell(GetClientUserId(client));
		dp.WriteString(concept);
	}
	if (StrEqual(seqName, "taunt_bond"))
	{
		// OF taunt_bond model event: the pistol shot at cycle 0.537 (1.584 s); OF TF_TAUNT_BOND
		// SetTauntEffect 1.6 s: a 500 u line, 500 bullet damage to an enemy.
		float shot = seqLen > 0.5 ? (0.537 - cin) * seqLen : 1.584;
		CreateTimer(shot, Timer_BondSound, GetClientUserId(client), TIMER_FLAG_NO_MAPCHANGE);
		CreateTimer(shot + 0.016, Timer_BondShot, GetClientUserId(client), TIMER_FLAG_NO_MAPCHANGE);
	}
	delete g_hTauntEnd[client];
	g_hTauntEnd[client] = CreateTimer(duration, Timer_TauntEnd, GetClientUserId(client), TIMER_FLAG_NO_MAPCHANGE);
	g_flNextTaunt[client] = GetGameTime() + duration + 1.0;
}

public Action Timer_TauntVoice(Handle timer, DataPack dp)
{
	dp.Reset();
	int client = GetClientOfUserId(dp.ReadCell());
	char concept[64];
	dp.ReadString(concept, sizeof(concept));
	if (client && g_bTaunting[client])
		Speak(client, concept);
	return Plugin_Stop;
}

public Action Timer_BondSound(Handle timer, int userid)
{
	int client = GetClientOfUserId(userid);
	if (client && g_bTaunting[client])
		EmitSoundToAll(BOND_SOUND, client);
	return Plugin_Stop;
}

public Action Timer_BondShot(Handle timer, int userid)
{
	int client = GetClientOfUserId(userid);
	if (!client || !g_bTaunting[client] || !IsPlayerAlive(client))
		return Plugin_Stop;
	float eye[3], ang[3], dir[3], end[3];
	GetClientEyePosition(client, eye);
	ang[1] = g_flTauntYaw[client];
	GetAngleVectors(ang, dir, NULL_VECTOR, NULL_VECTOR);
	ScaleVector(dir, 500.0);
	AddVectors(eye, dir, end);
	Handle tr = TR_TraceRayFilterEx(eye, end, MASK_SOLID | CONTENTS_HITBOX, RayType_EndPoint, Filter_NotSelf, client);
	int hit = TR_GetEntityIndex(tr);
	float pos[3];
	TR_GetEndPosition(pos, tr);
	delete tr;
	if (hit < 1 || hit > MaxClients || !IsPlayerAlive(hit) || GetClientTeam(hit) == GetClientTeam(client))
		return Plugin_Stop;
	float force[3], fang[3];
	fang[0] = -45.0;
	fang[1] = ang[1];
	GetAngleVectors(fang, force, NULL_VECTOR, NULL_VECTOR);
	ScaleVector(force, 25000.0);
	int weapon = GetEntPropEnt(client, Prop_Send, "m_hActiveWeapon");
	SDKHooks_TakeDamage(hit, client, client, 500.0, DMG_BULLET, weapon > MaxClients ? weapon : -1, force, pos);
	return Plugin_Stop;
}

public Action Timer_TauntEnd(Handle timer, int userid)
{
	int client = GetClientOfUserId(userid);
	if (client)
	{
		g_hTauntEnd[client] = null;
		EndTaunt(client);
	}
	return Plugin_Stop;
}

void EndTaunt(int client)
{
	delete g_hTauntEnd[client];
	if (!g_bTaunting[client])
		return;
	g_bTaunting[client] = false;
	int clone = EntRefToEntIndex(g_iTauntClone[client]);
	g_iTauntClone[client] = INVALID_ENT_REFERENCE;
	if (clone > MaxClients)
		RemoveEntity(clone);
	if (!IsClientInGame(client))
		return;
	if (clone > MaxClients)
	{
		SetEntityRenderMode(client, g_iRenderBefore[client] == RENDER_NONE ? RENDER_NORMAL : g_iRenderBefore[client]);
		SetWearablesNoDraw(client, false);
	}
	else if (IsPlayerAlive(client))
		SendAnimEvent(client, PLAYERANIMEVENT_SPAWN, 0);   // back to normal animation
	int w = EntRefToEntIndex(g_iTauntWeapon[client]);
	g_iTauntWeapon[client] = INVALID_ENT_REFERENCE;
	if (w > MaxClients && !g_bTauntWeaponHidden[client])
		SetEntProp(w, Prop_Send, "m_fEffects", GetEntProp(w, Prop_Send, "m_fEffects") & ~EF_NODRAW);
	float now = GetGameTime();
	if (GetEntPropFloat(client, Prop_Send, "m_flNextAttack") > now)
		SetEntPropFloat(client, Prop_Send, "m_flNextAttack", now);
	int aw = GetEntPropEnt(client, Prop_Send, "m_hActiveWeapon");
	if (aw > MaxClients && HasEntProp(aw, Prop_Send, "m_flNextPrimaryAttack"))
	{
		if (GetEntPropFloat(aw, Prop_Send, "m_flNextPrimaryAttack") > now + 0.1)
			SetEntPropFloat(aw, Prop_Send, "m_flNextPrimaryAttack", now + 0.1);
		if (GetEntPropFloat(aw, Prop_Send, "m_flNextSecondaryAttack") > now + 0.1)
			SetEntPropFloat(aw, Prop_Send, "m_flNextSecondaryAttack", now + 0.1);
	}
	SetVariantInt(g_iTauntCamBefore[client]);
	AcceptEntityInput(client, "SetForcedTauntCam");
}

/** PlayerAnimEvent temp entity (DT_TEPlayerAnimEvent: m_hPlayer, m_iEvent, m_nData on build 5205). */
void SendAnimEvent(int client, int event, int data)
{
	TE_Start("PlayerAnimEvent");
	TE_WriteNum("m_hPlayer", EntIndexToEntRef(client) & ~(1 << 31));
	TE_WriteNum("m_iEvent", event);
	TE_WriteNum("m_nData", data);
	TE_SendToAll();
}

/* ------------------------------------------------------------------ */
/* Scoreboard class icon                                              */
/* ------------------------------------------------------------------ */

/** The player resource's class drives the scoreboard icon: 0 shows none (like tf2cc on stock
 *  TF2) instead of the Soldier's. TF2C ships no Mercenary class icon, and replacing a stock
 *  class icon file would change it for that class everywhere. */
public Action Timer_HookResource(Handle timer)
{
	int res = GetPlayerResourceEntity();
	if (res > MaxClients && HasEntProp(res, Prop_Send, "m_iPlayerClass"))
	{
		SDKUnhook(res, SDKHook_ThinkPost, Hook_ResourceThinkPost);
		SDKHook(res, SDKHook_ThinkPost, Hook_ResourceThinkPost);
	}
	return Plugin_Stop;
}

public void Hook_ResourceThinkPost(int res)
{
	if (!g_cvBlankIcon.BoolValue)
		return;
	for (int i = 1; i <= MaxClients; i++)
		if (IsClientInGame(i) && (g_bMerc[i] || (g_bWant[i] && GetClientTeam(i) >= 2 && !IsPlayerAlive(i))))
			SetEntProp(res, Prop_Send, "m_iPlayerClass", 0, _, i);
}
