/**
 * tf2cc for TF2 Classified: Open Fortress impact/contact behaviour for the Merc's China Lake and
 * dynamite bundle (OF tf_weapon_grenadelauncher_mercenary / tf_weapon_dynamite_bundle).
 * Research: docs/tf2classified/OF_EXPLOSIVES.md (OF source tf_weapon_grenade_pipebomb.cpp,
 * tf_weapon_pipebomblauncher.cpp; OF items_game.txt).
 *
 * Native (schema, tools/tf2c/gen_schema.py): OF radii (mult_explosion_radius 124/146, 110/146),
 * dynamite 900 u/s base speed,
 * China Lake "grenade no spin" (OF projectile_pipe_dm). 5205 already creates pipes at 60 % damage
 * and restores 100 % for an enemy touch, as OF.
 *
 * Here (plugin):
 *  - China Lake AlwaysEnableTouch: an enemy (player of another team, enemy building, anything of
 *    another team that takes damage) touching the grenade after it bounced detonates it with full
 *    damage and the enemy as the direct-hit target, until the 2 s fuse. The game's own touch does
 *    it: m_bTouched is cleared just for that touch, so ShouldExplodeOnEntity passes.
 *  - China Lake ImpactBeforeTime 0.1: any impact in the first 0.1 s detonates (timer damage).
 *  - China Lake launch as OF FirePipeBombDM: forward 1200 + up 200 + right 1, no random.
 *  - Dynamite ExplodeOnImpact: any collision sets m_bTouched; OnGameFrame detonates it then (at the
 *    60 % timer damage), outside the VPhysics callback. (The schema's "sticky detonate mode" 3 did it
 *    inside the collision callback: engine warnings, and no stock item uses it.)
 *  - Dynamite FuseTime -2: no timer (it explodes on its first contact anyway).
 *  - Dynamite hold-to-charge (OF CTFPipebombLauncher on CTFDynamite): hold fire to wind up, release
 *    to throw at 900 -> 2400 u/s over 2 s (OF launch: forward*speed + up 200 + random +-10);
 *    held for 4 s it explodes in hand (OF ExplodeInHand). The launcher is kept from firing on its
 *    own (m_flNextPrimaryAttack held ahead) so the client never predicts a throw on press; the
 *    plugin fires it on release.
 */
#include <sourcemod>
#include <sdktools>
#include <sdkhooks>

#pragma semicolon 1
#pragma newdecls required

#define CFG_WEAPONS "configs/tf2cc_tf2c/weapons.cfg"
#define KIND_NONE 0
#define KIND_CHINA 1
#define KIND_DYN 2
#define DYN_MIN_SPEED 900.0     // OF ProjectileSpeed
#define DYN_CHARGE_MULT (8.0 / 3.0)   // OF CTFPipebombLauncher::GetProjectileSpeed
#define CHINA_SPEED 1200.0      // OF ProjectileSpeed (TF2C CTFGrenadeLauncher 1200 too)
#define LOCK_AHEAD 1000.0
#define DYN_SHOOT_SOUND "tf2cc.Weapon_DynamiteBundle.Single"
#define DYN_SHOOT_SOUND_CRIT "tf2cc.Weapon_DynamiteBundle.SingleCrit"

public Plugin myinfo =
{
	name = "tf2cc OF explosives (TF2 Classified)",
	author = "AgitationSkeleton",
	description = "Open Fortress impact/contact behaviour for the Merc China Lake and dynamite",
	version = "1.0.0",
	url = ""
};

ConVar g_cvEnable, g_cvChinaTouch, g_cvChinaImpact, g_cvChinaLaunch;
ConVar g_cvDynCharge, g_cvDynChargeTime, g_cvDynCook, g_cvDynNoFuse, g_cvDynImpact, g_cvDebug;
int g_iDefChina = -1, g_iDefDyn = -1;

// per projectile
int g_iKind[2049];
float g_flBorn[2049];
bool g_bUntouched[2049];   // m_bTouched cleared by Hook_ChinaTouch for this touch
ArrayList g_Pipes;         // entrefs of tracked China Lake / dynamite pipes

// per client (dynamite charge)
int g_iLockWeapon[MAXPLAYERS + 1];     // entref of the launcher held back
float g_flLock[MAXPLAYERS + 1];        // the value written to m_flNextPrimaryAttack
float g_flReady[MAXPLAYERS + 1];       // when the launcher would really fire again
float g_flChargeStart[MAXPLAYERS + 1]; // 0 = not charging
int g_iFireTick[MAXPLAYERS + 1];       // tick of a plugin-fired throw
float g_flFireCharge[MAXPLAYERS + 1];
bool g_bFireCook[MAXPLAYERS + 1];
int g_iNewPipe[MAXPLAYERS + 1];        // entref of a pipe spawned by this client this command

public void OnPluginStart()
{
	g_cvEnable = CreateConVar("tf2cc_ofexpl_enable", "1", "OF impact/contact behaviour for the Merc China Lake and dynamite.", _, true, 0.0, true, 1.0);
	g_cvChinaTouch = CreateConVar("tf2cc_chinalake_enemy_touch", "1", "China Lake: an enemy touching the grenade detonates it after it bounced too, until its fuse (OF AlwaysEnableTouch 1).", _, true, 0.0, true, 1.0);
	g_cvChinaImpact = CreateConVar("tf2cc_chinalake_impact_time", "0.1", "China Lake: any impact within this many seconds of firing detonates (OF ImpactBeforeTime 0.1; 0 = off).", _, true, 0.0);
	g_cvChinaLaunch = CreateConVar("tf2cc_chinalake_of_launch", "1", "China Lake: launch as OF (forward 1200 + up 200, no random spread).", _, true, 0.0, true, 1.0);
	g_cvDynCharge = CreateConVar("tf2cc_dynamite_charge", "1", "Dynamite: hold fire to wind up, release to throw (OF 900 -> 2400 u/s).", _, true, 0.0, true, 1.0);
	g_cvDynChargeTime = CreateConVar("tf2cc_dynamite_charge_time", "2.0", "Dynamite: seconds to reach full throw speed (OF TF_DYNAMITE_MAX_CHARGE_TIME 2).", _, true, 0.1);
	g_cvDynCook = CreateConVar("tf2cc_dynamite_cookoff", "4.0", "Dynamite: held this long it explodes in hand (OF max charge + 2 = 4 s; 0 = never).", _, true, 0.0);
	g_cvDynNoFuse = CreateConVar("tf2cc_dynamite_no_fuse", "1", "Dynamite: no timer, it explodes on contact only (OF FuseTime -2).", _, true, 0.0, true, 1.0);
	g_cvDynImpact = CreateConVar("tf2cc_dynamite_impact", "1", "Dynamite: explode on the first contact (OF ExplodeOnImpact; detonated from the game frame).", _, true, 0.0, true, 1.0);
	g_cvDebug = CreateConVar("tf2cc_ofexpl_debug", "0", "Log OF explosive events to the server console.", _, true, 0.0, true, 1.0);
	RegAdminCmd("sm_tf2cc_ofexpl_reload", Cmd_Reload, ADMFLAG_CONFIG, "Reload the China Lake / dynamite item definitions.");
	g_Pipes = new ArrayList();
	LoadDefs();
	for (int i = 1; i <= MaxClients; i++)
		g_flLock[i] = -1.0;
}

public void OnPluginEnd()
{
	for (int i = 1; i <= MaxClients; i++)
		Unlock(i);
}

public Action Cmd_Reload(int client, int args)
{
	LoadDefs();
	ReplyToCommand(client, "[tf2cc] China Lake def %d, dynamite def %d", g_iDefChina, g_iDefDyn);
	return Plugin_Handled;
}

void LoadDefs()
{
	g_iDefChina = g_iDefDyn = -1;
	char path[PLATFORM_MAX_PATH], item[64];
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
		kv.GetString("item", item, sizeof(item));
		if (StrEqual(item, "tf2cc_merc_chinalake"))
			g_iDefChina = kv.GetNum("defindex", -1);
		else if (StrEqual(item, "tf2cc_merc_dynamite"))
			g_iDefDyn = kv.GetNum("defindex", -1);
	}
	while (kv.GotoNextKey());
	delete kv;
}

void Dbg(const char[] fmt, any ...)
{
	if (!g_cvDebug.BoolValue)
		return;
	char buf[256];
	VFormat(buf, sizeof(buf), fmt, 2);
	PrintToServer("[OFX] %.3f %s", GetGameTime(), buf);
}

int WeaponKind(int weapon)
{
	if (weapon <= MaxClients || !IsValidEntity(weapon) || !HasEntProp(weapon, Prop_Send, "m_iItemDefinitionIndex"))
		return KIND_NONE;
	int def = GetEntProp(weapon, Prop_Send, "m_iItemDefinitionIndex");
	return def == g_iDefChina ? KIND_CHINA : def == g_iDefDyn ? KIND_DYN : KIND_NONE;
}

/* ---------------------------------------------------------------------------------------------- */
/* Projectiles                                                                                     */
/* ---------------------------------------------------------------------------------------------- */

public void OnEntityCreated(int entity, const char[] classname)
{
	if (entity <= MaxClients || entity >= sizeof(g_iKind))
		return;
	g_iKind[entity] = KIND_NONE;
	if (StrEqual(classname, "tf_projectile_pipe"))
	{
		g_bUntouched[entity] = false;
		SDKHook(entity, SDKHook_SpawnPost, Hook_PipeSpawn);
		SDKHook(entity, SDKHook_Touch, Hook_PipeTouch);
		SDKHook(entity, SDKHook_TouchPost, Hook_PipeTouchPost);
	}
}

public void OnEntityDestroyed(int entity)
{
	if (entity > MaxClients && entity < sizeof(g_iKind))
		g_iKind[entity] = KIND_NONE;
}

public void Hook_PipeSpawn(int pipe)
{
	if (!g_cvEnable.BoolValue)
		return;
	int owner = GetEntPropEnt(pipe, Prop_Send, "m_hOwnerEntity");
	if (owner < 1 || owner > MaxClients || !IsClientInGame(owner))
		return;
	int kind = WeaponKind(GetEntPropEnt(owner, Prop_Send, "m_hActiveWeapon"));
	if (kind == KIND_NONE)
		return;
	g_iKind[pipe] = kind;
	g_flBorn[pipe] = GetGameTime();
	g_iNewPipe[owner] = EntIndexToEntRef(pipe);
	g_Pipes.Push(EntIndexToEntRef(pipe));
	// Pipes made outside a usercmd (none on stock TF2C) are finished next frame.
	RequestFrame(Frame_PipeLaunched, EntIndexToEntRef(pipe));
}

public void Frame_PipeLaunched(int ref)
{
	int pipe = EntRefToEntIndex(ref);
	if (pipe <= MaxClients)
		return;
	int owner = GetEntPropEnt(pipe, Prop_Send, "m_hOwnerEntity");
	if (owner >= 1 && owner <= MaxClients && g_iNewPipe[owner] == ref)
		Launched(owner, pipe);
}

/** The launcher's Create() is done (InitGrenade set velocity, fuse and damage): apply OF's launch. */
void Launched(int owner, int pipe)
{
	g_iNewPipe[owner] = 0;
	float now = GetGameTime();
	if (g_iKind[pipe] == KIND_CHINA)
	{
		if (g_cvChinaLaunch.BoolValue)
		{
			// OF FirePipeBombDM: forward * speed + up * 200 + right, no random, no spin.
			float ang[3], fwd[3], right[3], up[3], vel[3];
			GetClientEyeAngles(owner, ang);
			GetAngleVectors(ang, fwd, right, up);
			for (int i = 0; i < 3; i++)
				vel[i] = fwd[i] * CHINA_SPEED + up[i] * 200.0 + right[i];
			SetLaunch(pipe, vel);
		}
		Dbg("china pipe %d launched", pipe);
		return;
	}
	// Dynamite.
	if (g_cvDynNoFuse.BoolValue)
		SetEntPropFloat(pipe, Prop_Send, "m_flDetonateTime", now + 3600.0);
	if (g_iFireTick[owner] == GetGameTickCount() || g_iFireTick[owner] == GetGameTickCount() - 1)
	{
		g_iFireTick[owner] = 0;
		if (g_bFireCook[owner])
		{
			// OF ExplodeInHand: the bundle is fired and detonated at once.
			SetLaunch(pipe, view_as<float>({0.0, 0.0, 0.0}));
			DetonateNow(pipe);
			Dbg("dynamite %d cooked off in hand", pipe);
			return;
		}
		// OF CTFPipebombLauncher::GetProjectileSpeed + FirePipeBomb launch.
		float speed = DYN_MIN_SPEED + (DYN_MIN_SPEED * DYN_CHARGE_MULT - DYN_MIN_SPEED) * Clamp01(g_flFireCharge[owner] / g_cvDynChargeTime.FloatValue);
		float ang[3], fwd[3], right[3], up[3], vel[3];
		GetClientEyeAngles(owner, ang);
		GetAngleVectors(ang, fwd, right, up);
		float r = GetRandomFloat(-10.0, 10.0), u = GetRandomFloat(-10.0, 10.0);
		for (int i = 0; i < 3; i++)
			vel[i] = fwd[i] * speed + up[i] * (200.0 + u) + right[i] * r;
		SetLaunch(pipe, vel);
		Dbg("dynamite %d thrown: charge %.2f s, speed %.0f", pipe, g_flFireCharge[owner], speed);
	}
}

float Clamp01(float f)
{
	return f < 0.0 ? 0.0 : (f > 1.0 ? 1.0 : f);
}

void SetLaunch(int pipe, const float vel[3])
{
	TeleportEntity(pipe, NULL_VECTOR, NULL_VECTOR, vel);
	if (HasEntProp(pipe, Prop_Send, "m_vInitialVelocity"))
		SetEntPropVector(pipe, Prop_Send, "m_vInitialVelocity", vel);
}

/** Detonate now: the grenade's own Detonate input (as OF's SetThink(Detonate) next tick); the
 *  fuse is set too in case the input is missing (the fuse think runs every 0.1 s). */
void DetonateNow(int pipe)
{
	SetEntPropFloat(pipe, Prop_Send, "m_flDetonateTime", GetGameTime());
	AcceptEntityInput(pipe, "Detonate");
}

bool IsEnemyTarget(int pipe, int other)
{
	if (other < 1 || !IsValidEntity(other))
		return false;
	if (other == GetEntPropEnt(pipe, Prop_Send, "m_hOwnerEntity") || other == GetEntPropEnt(pipe, Prop_Send, "m_hThrower"))
		return false;
	if (!HasEntProp(other, Prop_Send, "m_iTeamNum"))
		return false;
	int team = GetEntProp(other, Prop_Send, "m_iTeamNum");
	if (team < 2 || team == GetEntProp(pipe, Prop_Send, "m_iTeamNum"))
		return false;
	if (other <= MaxClients)
		return IsClientInGame(other) && IsPlayerAlive(other);
	// OF: anything of another team that takes damage (buildings, ...).
	return HasEntProp(other, Prop_Data, "m_takedamage") && GetEntProp(other, Prop_Data, "m_takedamage") != 0;
}

/** OF AlwaysEnableTouch: the stock touch stops once m_bTouched is set; clear it for an enemy. */
public Action Hook_PipeTouch(int pipe, int other)
{
	if (g_iKind[pipe] != KIND_CHINA || !g_cvEnable.BoolValue || !g_cvChinaTouch.BoolValue
		|| !GetEntProp(pipe, Prop_Send, "m_bTouched") || !IsEnemyTarget(pipe, other))
		return Plugin_Continue;
	SetEntProp(pipe, Prop_Send, "m_bTouched", 0);
	g_bUntouched[pipe] = true;
	Dbg("china pipe %d: enemy %d touched after a bounce", pipe, other);
	return Plugin_Continue;
}

public void Hook_PipeTouchPost(int pipe, int other)
{
	if (!g_bUntouched[pipe])
		return;
	g_bUntouched[pipe] = false;
	// Still here: the game did not explode (respawn room, ...). Back to a bounced grenade.
	if (IsValidEntity(pipe) && !(GetEntProp(pipe, Prop_Data, "m_fFlags") & FL_KILLME))
		SetEntProp(pipe, Prop_Send, "m_bTouched", 1);
}

public void OnGameFrame()
{
	if (g_Pipes.Length == 0)
		return;
	float now = GetGameTime();
	float window = g_cvChinaImpact.FloatValue;
	for (int i = g_Pipes.Length - 1; i >= 0; i--)
	{
		int pipe = EntRefToEntIndex(g_Pipes.Get(i));
		if (pipe <= MaxClients || g_iKind[pipe] == KIND_NONE)
		{
			g_Pipes.Erase(i);
			continue;
		}
		bool touched = GetEntProp(pipe, Prop_Send, "m_bTouched") != 0;
		if (g_iKind[pipe] == KIND_DYN)
		{
			// OF ExplodeOnImpact: the first collision set m_bTouched; detonate outside the physics callback.
			if (touched && g_cvDynImpact.BoolValue)
			{
				DetonateNow(pipe);
				Dbg("dynamite %d: contact -> detonate", pipe);
				g_Pipes.Erase(i);
			}
			continue;
		}
		// China Lake: ImpactBeforeTime (the entry stays only for the window).
		if (now - g_flBorn[pipe] > window + GetTickInterval())
		{
			g_Pipes.Erase(i);
			continue;
		}
		if (touched)
		{
			DetonateNow(pipe);
			Dbg("china pipe %d: impact %.3f s after firing -> detonate", pipe, now - g_flBorn[pipe]);
			g_Pipes.Erase(i);
		}
	}
}

/* ---------------------------------------------------------------------------------------------- */
/* Dynamite hold-to-charge                                                                         */
/* ---------------------------------------------------------------------------------------------- */

void Unlock(int client)
{
	int w = EntRefToEntIndex(g_iLockWeapon[client]);
	if (w > MaxClients && g_flLock[client] >= 0.0 && GetEntPropFloat(w, Prop_Send, "m_flNextPrimaryAttack") == g_flLock[client])
		SetEntPropFloat(w, Prop_Send, "m_flNextPrimaryAttack", g_flReady[client]);
	g_iLockWeapon[client] = 0;
	g_flLock[client] = -1.0;
	g_flChargeStart[client] = 0.0;
}

public void OnClientDisconnect(int client)
{
	Unlock(client);
	g_iFireTick[client] = 0;
	g_iNewPipe[client] = 0;
}

int ReserveAmmo(int client, int weapon)
{
	int type = GetEntProp(weapon, Prop_Send, "m_iPrimaryAmmoType");
	return type < 0 ? 0 : GetEntProp(client, Prop_Send, "m_iAmmo", _, type);
}

public Action OnPlayerRunCmd(int client, int &buttons, int &impulse, float vel[3], float angles[3], int &weapon)
{
	g_iNewPipe[client] = 0;
	if (!g_cvEnable.BoolValue || !g_cvDynCharge.BoolValue)
		return Plugin_Continue;
	int active = IsPlayerAlive(client) ? GetEntPropEnt(client, Prop_Send, "m_hActiveWeapon") : -1;
	if (WeaponKind(active) != KIND_DYN)
	{
		if (g_iLockWeapon[client])
			Unlock(client);
		return Plugin_Continue;
	}
	int ref = EntIndexToEntRef(active);
	if (g_iLockWeapon[client] != ref)
	{
		Unlock(client);
		g_iLockWeapon[client] = ref;
	}
	// The weapon's own clock for this command (CBasePlayer::PlayerRunCommand: tickbase).
	float now = float(GetEntProp(client, Prop_Send, "m_nTickBase")) * GetTickInterval();
	float next = GetEntPropFloat(active, Prop_Send, "m_flNextPrimaryAttack");
	if (next != g_flLock[client])
		g_flReady[client] = next;   // the game set it (deploy, a throw): that is the real cooldown
	Action result = Plugin_Continue;
	if (g_flChargeStart[client] > 0.0)
	{
		float held = now - g_flChargeStart[client];
		float cook = g_cvDynCook.FloatValue;
		if (cook > 0.0 && held >= cook)
		{
			Fire(client, active, now, held, true);
			buttons |= IN_ATTACK;
			result = Plugin_Changed;
		}
		else if (!(buttons & IN_ATTACK))
		{
			Fire(client, active, now, held, false);
			buttons |= IN_ATTACK;
			result = Plugin_Changed;
		}
	}
	else if ((buttons & IN_ATTACK) && now >= g_flReady[client] && ReserveAmmo(client, active) > 0
		&& GetEntPropFloat(client, Prop_Send, "m_flNextAttack") <= now)
	{
		g_flChargeStart[client] = now;   // OF PrimaryAttack: m_flChargeBeginTime
		Dbg("%N: dynamite wind-up", client);
	}
	if (g_iFireTick[client] != GetGameTickCount())
	{
		// Hold the launcher back so neither the server nor the client's prediction fires it.
		if (g_flLock[client] < 0.0 || g_flLock[client] - now < LOCK_AHEAD * 0.5)
			g_flLock[client] = now + LOCK_AHEAD;
		if (GetEntPropFloat(active, Prop_Send, "m_flNextPrimaryAttack") != g_flLock[client])
			SetEntPropFloat(active, Prop_Send, "m_flNextPrimaryAttack", g_flLock[client]);
	}
	return result;
}

void Fire(int client, int weapon, float now, float held, bool cook)
{
	g_flChargeStart[client] = 0.0;
	g_iFireTick[client] = GetGameTickCount();
	g_flFireCharge[client] = held;
	g_bFireCook[client] = cook;
	SetEntPropFloat(weapon, Prop_Send, "m_flNextPrimaryAttack", now - GetTickInterval());
	// The client did not predict this throw, so its own shoot sound is not played for it.
	EmitGameSoundToClient(client, DYN_SHOOT_SOUND, client);
	Dbg("%N: dynamite %s after %.2f s", client, cook ? "cook-off" : "release", held);
}

public void OnPlayerRunCmdPost(int client, int buttons, int impulse, const float vel[3], const float angles[3], int weapon, int subtype, int cmdnum, int tickcount, int seed, const int mouse[2])
{
	int pipe = EntRefToEntIndex(g_iNewPipe[client]);
	if (pipe > MaxClients)
		Launched(client, pipe);
	g_iNewPipe[client] = 0;
}
