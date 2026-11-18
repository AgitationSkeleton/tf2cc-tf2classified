/**
 * tf2cc: the Saw Ballista's blade (Open Fortress CTFProjectile_Ripper, OFS shared/of/of_weapon_ripper.cpp;
 * see the tf2cc research notes on the missing OF weapons, section 4). OF ships no weapon script for
 * it; the numbers are the ones the user approved on 2026-11-17.
 *
 * One source for both games (as tf2cc_hook): live TF2 (special "ripper" on the stock rocket launcher)
 * and TF2 Classified (build_tf2c.sh, TF2CC_TF2C=1; schema item tf2cc_merc_sawballista, 30124).
 *
 * The launcher's rocket becomes the blade (no explosion ever):
 *  - it never explodes: the plugin moves it (noclip, through players and buildings, as OF's trigger-solid
 *    blade), traces ahead every frame and reflects it off walls with no speed loss (OF Bounce, total
 *    elasticity); the sky removes it;
 *  - every 0.03 s (OF FlyThink) every enemy player / building whose box overlaps a 100 x 100 x 20 box
 *    around the blade and is in its line of sight takes 4 damage (slash, always gibs; crits x3), at
 *    most 200 per blade per target; the wielder too once the blade has bounced;
 *  - on first contact the blade slows to 15 % of its speed (OF 5 %) until no player or building is
 *    within 64 u (OF CheckIfInside);
 *  - bounces count after 1 s (the first always counts: it arms the wielder damage); past 6 counted
 *    bounces and 1 s, the next wall hit sticks it there (a prop) for 5 s; 6 s safety lifetime.
 */
#include <sourcemod>
#include <sdktools>
#include <sdkhooks>
#include <tf2>
#include <tf2_stocks>

#pragma semicolon 1
#pragma newdecls required

#if !defined TF2CC_TF2C
native bool TF2CC_GetWeaponSpecial(int weapon, char[] special, int maxlen, float &value);
#define BLADE_MODEL "models/weapons/customclasses/w_models/w_saw_ballista_projectile.mdl"
#else
#define CFG_TF2C "configs/tf2cc_tf2c/weapons.cfg"
#define BLADE_MODEL "models/tf2cc/of/weapons/w_models/w_saw_ballista_projectile.mdl"
#endif

#define DMG_ALWAYSGIB_ (1 << 13)
#define DMG_CRIT_ (1 << 20)
#define SURF_SKY_ 0x0004

static const char RICOCHET[][] = {"physics/metal/sawblade_stick1.wav", "physics/metal/sawblade_stick2.wav", "physics/metal/sawblade_stick3.wav"};
static const char FLESH[][] = {"ambient/sawblade_impact1.wav", "ambient/sawblade_impact2.wav"};

public Plugin myinfo =
{
	name = "tf2cc Saw Ballista blade",
	author = "AgitationSkeleton",
	description = "Open Fortress Saw Ballista ricocheting saw blade",
	version = "1.0.0",
	url = ""
};

ConVar g_cvEnable, g_cvDamage, g_cvTick, g_cvCap, g_cvSlow, g_cvBox, g_cvBoxHeight, g_cvBounces, g_cvArmTime, g_cvStick, g_cvLife, g_cvScale, g_cvDebug;
int g_iDef = -1;

// per blade (entity index of the rocket)
int g_iRef[2049];
int g_iOwner[2049];          // userid
int g_iLauncher[2049];       // entref
float g_flBorn[2049];
float g_flNextTick[2049];
int g_iBounces[2049];
bool g_bInside[2049];
float g_flSpeed[2049];
StringMap g_Dealt[2049];     // "entref" -> damage dealt by this blade
ArrayList g_Blades;

public APLRes AskPluginLoad2(Handle myself, bool late, char[] error, int err_max)
{
#if !defined TF2CC_TF2C
	MarkNativeAsOptional("TF2CC_GetWeaponSpecial");
#endif
	return APLRes_Success;
}

public void OnPluginStart()
{
	g_cvEnable = CreateConVar("tf2cc_saw_enable", "1", "Saw Ballista: OF ricocheting saw blade.", _, true, 0.0, true, 1.0);
	g_cvDamage = CreateConVar("tf2cc_saw_damage", "4", "Damage per tick to everything the blade overlaps (crits x3).", _, true, 0.0);
	g_cvTick = CreateConVar("tf2cc_saw_tick", "0.03", "Damage tick (OF FlyThink 0.03 s).", _, true, 0.015);
	g_cvCap = CreateConVar("tf2cc_saw_cap", "200", "Most damage one blade deals to one target (0 = no cap).", _, true, 0.0);
	g_cvSlow = CreateConVar("tf2cc_saw_slow", "0.15", "Blade speed while inside a target, fraction of its speed (OF of_ripper_slowed_speed_perc 0.05).", _, true, 0.0, true, 1.0);
	g_cvBox = CreateConVar("tf2cc_saw_box", "50", "Half width of the damage box (OF of_ripper_boxsize 50).", _, true, 1.0);
	g_cvBoxHeight = CreateConVar("tf2cc_saw_box_height", "10", "Half height of the damage box (OF of_ripper_boxsize_height 10).", _, true, 1.0);
	g_cvBounces = CreateConVar("tf2cc_saw_bounces", "6", "Counted bounces before the blade sticks (OF of_ripper_bounces 6).", _, true, 0.0);
	g_cvArmTime = CreateConVar("tf2cc_saw_count_after", "1.0", "Bounces count only after this long, the first excepted (OF of_ripper_projectile_lifetime 1).", _, true, 0.0);
	g_cvStick = CreateConVar("tf2cc_saw_stick_time", "5.0", "A stuck blade stays this long (OF of_ripper_prop_lifetime 5).", _, true, 0.0);
	g_cvLife = CreateConVar("tf2cc_saw_lifetime", "6.0", "Safety: a flying blade is removed after this long (0 = never).", _, true, 0.0);
	g_cvScale = CreateConVar("tf2cc_saw_scale", "2.0", "Blade model scale (OF SetModelScale 2).", _, true, 0.1);
	g_cvDebug = CreateConVar("tf2cc_saw_debug", "0", "Log blade events to the server console.", _, true, 0.0, true, 1.0);
	RegAdminCmd("sm_tf2cc_saw_reload", Cmd_Reload, ADMFLAG_CONFIG, "Reload the Saw Ballista item definition (TF2 Classified).");
	g_Blades = new ArrayList();
	LoadDefs();
	AutoExecConfig(true, "tf2cc_saw");
}

public void OnMapStart()
{
	PrecacheModel(BLADE_MODEL, true);
	for (int i = 0; i < sizeof(RICOCHET); i++)
		PrecacheSound(RICOCHET[i], true);
	for (int i = 0; i < sizeof(FLESH); i++)
		PrecacheSound(FLESH[i], true);
	LoadDefs();
}

public Action Cmd_Reload(int client, int args)
{
	LoadDefs();
	ReplyToCommand(client, "[tf2cc] Saw Ballista def %d", g_iDef);
	return Plugin_Handled;
}

void LoadDefs()
{
#if defined TF2CC_TF2C
	g_iDef = -1;
	char path[PLATFORM_MAX_PATH], item[64];
	BuildPath(Path_SM, path, sizeof(path), CFG_TF2C);
	KeyValues kv = new KeyValues("tf2cc_tf2c_weapons");
	if (kv.ImportFromFile(path) && kv.GotoFirstSubKey())
	{
		do
		{
			kv.GetString("item", item, sizeof(item));
			if (StrEqual(item, "tf2cc_merc_sawballista"))
				g_iDef = kv.GetNum("defindex", -1);
		}
		while (kv.GotoNextKey());
	}
	delete kv;
#endif
}

void Dbg(const char[] fmt, any ...)
{
	if (!g_cvDebug.BoolValue)
		return;
	char buf[256];
	VFormat(buf, sizeof(buf), fmt, 2);
	PrintToServer("[SAW] %.3f %s", GetGameTime(), buf);
}

bool IsSaw(int weapon)
{
	if (weapon <= MaxClients || !IsValidEntity(weapon))
		return false;
#if defined TF2CC_TF2C
	return g_iDef > 0 && HasEntProp(weapon, Prop_Send, "m_iItemDefinitionIndex")
		&& GetEntProp(weapon, Prop_Send, "m_iItemDefinitionIndex") == g_iDef;
#else
	if (GetFeatureStatus(FeatureType_Native, "TF2CC_GetWeaponSpecial") != FeatureStatus_Available)
		return false;
	char special[32];
	float v;
	return TF2CC_GetWeaponSpecial(weapon, special, sizeof(special), v) && StrEqual(special, "ripper");
#endif
}

/* ---------------------------------------------------------------------------------------------- */
/* Blades                                                                                          */
/* ---------------------------------------------------------------------------------------------- */

public void OnEntityCreated(int entity, const char[] classname)
{
	if (entity > MaxClients && entity < 2049 && StrEqual(classname, "tf_projectile_rocket"))
		SDKHook(entity, SDKHook_SpawnPost, Hook_Spawn);
}

public void OnEntityDestroyed(int entity)
{
	if (entity > MaxClients && entity < 2049 && g_iRef[entity] != 0)
	{
		g_iRef[entity] = 0;
		delete g_Dealt[entity];
	}
}

public void Hook_Spawn(int rocket)
{
	int ref = EntIndexToEntRef(rocket);
	if (!g_cvEnable.BoolValue || g_iRef[rocket] == ref)
		return;     // SpawnPost can run twice for a rocket
	int owner = GetEntPropEnt(rocket, Prop_Send, "m_hOwnerEntity");
	if (owner < 1 || owner > MaxClients || !IsClientInGame(owner))
		return;
	int weapon = GetEntPropEnt(owner, Prop_Send, "m_hActiveWeapon");
	if (!IsSaw(weapon))
		return;
	g_iRef[rocket] = ref;
	g_iOwner[rocket] = GetClientUserId(owner);
	g_iLauncher[rocket] = EntIndexToEntRef(weapon);
	float now = GetGameTime();
	g_flBorn[rocket] = now;
	g_flNextTick[rocket] = now;
	g_iBounces[rocket] = 0;
	g_bInside[rocket] = false;
	float v[3];
	GetEntPropVector(rocket, Prop_Data, "m_vecAbsVelocity", v);
	g_flSpeed[rocket] = GetVectorLength(v);
	delete g_Dealt[rocket];
	g_Dealt[rocket] = new StringMap();
#if !defined TF2CC_TF2C
	SetEntityModel(rocket, BLADE_MODEL);      // TF2C: the item's "custom projectile model"
#endif
	SetEntPropFloat(rocket, Prop_Send, "m_flModelScale", g_cvScale.FloatValue);
	SDKHook(rocket, SDKHook_Touch, Hook_Touch);
	g_Blades.Push(ref);
	Dbg("blade %d from %N, speed %.0f", rocket, owner, g_flSpeed[rocket]);
}

/** Walls for the blade: the world and solid map entities (brushes, props, doors, buildings); never
 *  players, projectiles, weapons or wearables (the wielder's attached models touched it at the muzzle). */
bool IsWall(int entity)
{
	if (entity == 0)
		return true;
	if (entity <= MaxClients || !IsValidEntity(entity))
		return false;
	char cls[32];
	GetEntityClassname(entity, cls, sizeof(cls));
	return StrContains(cls, "func_") == 0 || StrContains(cls, "prop_") == 0 || StrContains(cls, "obj_") == 0;
}

public bool Filter_Solid(int entity, int mask, any rocket)
{
	return entity != rocket && IsWall(entity);
}

/** The blade never explodes: the native rocket touch never runs (the plugin moves the blade). */
public Action Hook_Touch(int rocket, int other)
{
	return g_iRef[rocket] == EntIndexToEntRef(rocket) ? Plugin_Handled : Plugin_Continue;
}

/**
 * The blade flies as a noclip entity moved by its velocity (through players and buildings, as OF's
 * trigger-solid ripper); the plugin traces ahead each frame and reflects it off walls (OF Bounce:
 * total elasticity, counting, sticking). Returns false when the blade is gone.
 */
bool Move(int r, float now, float dt)
{
	float pos[3], vel[3], dir[3], end[3], hit[3], n[3];
	GetEntPropVector(r, Prop_Data, "m_vecAbsOrigin", pos);
	GetEntPropVector(r, Prop_Data, "m_vecAbsVelocity", vel);
	float speed = GetVectorLength(vel);
	if (speed < 1.0)
		return true;
	NormalizeVector(vel, dir);
	for (int k = 0; k < 3; k++)
		end[k] = pos[k] + vel[k] * dt + dir[k] * 4.0;
	Handle tr = TR_TraceHullFilterEx(pos, end, view_as<float>({-2.0, -2.0, -2.0}), view_as<float>({2.0, 2.0, 2.0}), MASK_SOLID, Filter_Solid, r);
	if (!TR_DidHit(tr) || TR_StartSolid(tr))
	{
		delete tr;
		return true;
	}
	TR_GetEndPosition(hit, tr);
	TR_GetPlaneNormal(tr, n);
	bool sky = (TR_GetSurfaceFlags(tr) & SURF_SKY_) != 0;
	delete tr;
	if (sky)
	{
		AcceptEntityInput(r, "Kill");      // OF: the sky removes it
		return false;
	}
	if (GetVectorLength(n) < 0.5)
		for (int k = 0; k < 3; k++)
			n[k] = -dir[k];
	float d = GetVectorDotProduct(vel, n) * 2.0;
	if (d >= 0.0)
		return true;
	// OF Bounce: past the count and the first second, it sticks where it hit.
	if (g_iBounces[r] > g_cvBounces.IntValue && now - g_flBorn[r] >= g_cvArmTime.FloatValue)
	{
		TeleportEntity(r, hit, NULL_VECTOR, view_as<float>({0.0, 0.0, 0.0}));
		Stick(r);
		return false;
	}
	if (now - g_flBorn[r] > g_cvArmTime.FloatValue || g_iBounces[r] == 0)
		g_iBounces[r]++;
	float nv[3], ang[3];
	for (int k = 0; k < 3; k++)
	{
		nv[k] = vel[k] - n[k] * d;              // total elasticity
		hit[k] += n[k] * 2.0;
	}
	GetVectorAngles(nv, ang);
	TeleportEntity(r, hit, ang, nv);
	EmitSoundToAll(RICOCHET[GetRandomInt(0, sizeof(RICOCHET) - 1)], r, SNDCHAN_AUTO, 74);
	Dbg("blade %d bounce %d (age %.2f)", r, g_iBounces[r], now - g_flBorn[r]);
	return true;
}

public void OnGameFrame()
{
	if (g_Blades.Length == 0)
		return;
	float now = GetGameTime();
	for (int i = g_Blades.Length - 1; i >= 0; i--)
	{
		int ref = g_Blades.Get(i);
		int r = EntRefToEntIndex(ref);
		if (r <= MaxClients || g_iRef[r] != ref)
		{
			g_Blades.Erase(i);
			continue;
		}
		float life = g_cvLife.FloatValue;
		int owner = GetClientOfUserId(g_iOwner[r]);
		if (owner <= 0 || (life > 0.0 && now - g_flBorn[r] > life))
		{
			AcceptEntityInput(r, "Kill");
			g_Blades.Erase(i);
			continue;
		}
		if (g_flSpeed[r] < 1.0)
		{
			// The launcher sets the velocity after the spawn: take the blade's speed and model now.
			float v0[3];
			GetEntPropVector(r, Prop_Data, "m_vecAbsVelocity", v0);
			g_flSpeed[r] = GetVectorLength(v0);
#if !defined TF2CC_TF2C
			SetEntityModel(r, BLADE_MODEL);
			SetEntPropFloat(r, Prop_Send, "m_flModelScale", g_cvScale.FloatValue);
#endif
		}
		if (GetEntityMoveType(r) != MOVETYPE_NOCLIP)
			SetEntityMoveType(r, MOVETYPE_NOCLIP);   // outside any callback, from the first frame on
		if (!Move(r, now, GetTickInterval()))
		{
			g_Blades.Erase(i);
			continue;
		}
		if (now >= g_flNextTick[r])
		{
			g_flNextTick[r] = now + g_cvTick.FloatValue;
			Tick(r, owner);
		}
	}
}

bool BoxOverlap(const float amin[3], const float amax[3], int ent)
{
	float o[3], mn[3], mx[3];
	GetEntPropVector(ent, Prop_Data, "m_vecAbsOrigin", o);
	GetEntPropVector(ent, Prop_Send, "m_vecMins", mn);
	GetEntPropVector(ent, Prop_Send, "m_vecMaxs", mx);
	for (int k = 0; k < 3; k++)
		if (o[k] + mx[k] < amin[k] || o[k] + mn[k] > amax[k])
			return false;
	return true;
}

public bool Filter_World(int entity, int mask, any data)
{
	return entity == 0;
}

bool InSight(const float from[3], int ent)
{
	float c[3], mn[3], mx[3];
	GetEntPropVector(ent, Prop_Data, "m_vecAbsOrigin", c);
	GetEntPropVector(ent, Prop_Send, "m_vecMins", mn);
	GetEntPropVector(ent, Prop_Send, "m_vecMaxs", mx);
	for (int k = 0; k < 3; k++)
		c[k] += (mn[k] + mx[k]) * 0.5;
	Handle tr = TR_TraceRayFilterEx(from, c, MASK_SOLID, RayType_EndPoint, Filter_World, 0);
	bool clear = !TR_DidHit(tr);
	delete tr;
	return clear;
}

bool IsTarget(int r, int owner, int ent)
{
	if (ent >= 1 && ent <= MaxClients)
	{
		if (!IsClientInGame(ent) || !IsPlayerAlive(ent))
			return false;
		if (ent == owner)
			return g_iBounces[r] >= 1;          // OF: the wielder only after the first bounce
		return GetClientTeam(ent) != GetClientTeam(owner);
	}
	if (!HasEntProp(ent, Prop_Send, "m_iTeamNum") || GetEntProp(ent, Prop_Send, "m_iTeamNum") == GetClientTeam(owner))
		return false;
	return GetEntProp(ent, Prop_Data, "m_iHealth") > 0;
}

/** OF FlyThink: damage everything in the box, slow down inside a target, speed up out of it. */
void Tick(int r, int owner)
{
	float pos[3], amin[3], amax[3];
	GetEntPropVector(r, Prop_Data, "m_vecAbsOrigin", pos);
	float w = g_cvBox.FloatValue, h = g_cvBoxHeight.FloatValue;
	amin[0] = pos[0] - w; amin[1] = pos[1] - w; amin[2] = pos[2] - h;
	amax[0] = pos[0] + w; amax[1] = pos[1] + w; amax[2] = pos[2] + h;
	bool crit = HasEntProp(r, Prop_Send, "m_bCritical") && GetEntProp(r, Prop_Send, "m_bCritical") != 0;
	float dmg = g_cvDamage.FloatValue * (crit ? 3.0 : 1.0);
	int type = DMG_SLASH | DMG_ALWAYSGIB_ | (crit ? DMG_CRIT_ : 0);
	int launcher = EntRefToEntIndex(g_iLauncher[r]);
	bool touchedOther = false;
	for (int c = 1; c <= MaxClients; c++)
		if (IsTarget(r, owner, c) && BoxOverlap(amin, amax, c) && InSight(pos, c))
		{
			Hurt(r, owner, c, dmg, type, launcher);
			if (c != owner)
				touchedOther = true;
		}
	static const char objs[][] = {"obj_sentrygun", "obj_dispenser", "obj_teleporter"};
	for (int k = 0; k < sizeof(objs); k++)
	{
		int o = -1;
		while ((o = FindEntityByClassname(o, objs[k])) != -1)
			if (IsTarget(r, owner, o) && BoxOverlap(amin, amax, o) && InSight(pos, o))
			{
				Hurt(r, owner, o, dmg, type, launcher);
				touchedOther = true;
			}
	}
	if (!IsValidEntity(r))
		return;
	float v[3];
	GetEntPropVector(r, Prop_Data, "m_vecAbsVelocity", v);
	if (GetVectorLength(v) < 1.0)
		return;
	NormalizeVector(v, v);
	if (touchedOther && !g_bInside[r])
	{
		// OF: the first contact slows the blade (and plays the saw sound).
		g_bInside[r] = true;
		ScaleVector(v, g_flSpeed[r] * g_cvSlow.FloatValue);
		TeleportEntity(r, NULL_VECTOR, NULL_VECTOR, v);
		EmitSoundToAll(FLESH[GetRandomInt(0, sizeof(FLESH) - 1)], r, SNDCHAN_AUTO, SNDLEVEL_NORMAL);
		Dbg("blade %d inside a target", r);
	}
	else if (g_bInside[r] && !AnyoneNear(pos, 64.0))
	{
		g_bInside[r] = false;
		ScaleVector(v, g_flSpeed[r]);
		TeleportEntity(r, NULL_VECTOR, NULL_VECTOR, v);
		Dbg("blade %d out, full speed", r);
	}
}

/** OF CheckIfInside: any living player or building within `radius`. */
bool AnyoneNear(const float pos[3], float radius)
{
	float o[3];
	for (int c = 1; c <= MaxClients; c++)
	{
		if (!IsClientInGame(c) || !IsPlayerAlive(c))
			continue;
		GetClientAbsOrigin(c, o);
		o[2] += 40.0;
		if (GetVectorDistance(o, pos) <= radius + 24.0)
			return true;
	}
	return false;
}

void Hurt(int r, int owner, int target, float dmg, int type, int launcher)
{
	float cap = g_cvCap.FloatValue;
	char key[16];
	IntToString(EntIndexToEntRef(target), key, sizeof(key));
	float dealt = 0.0;
	g_Dealt[r].GetValue(key, dealt);
	if (cap > 0.0)
	{
		if (dealt >= cap)
			return;
		if (dealt + dmg > cap)
			dmg = cap - dealt;
	}
	g_Dealt[r].SetValue(key, dealt + dmg);
	float pos[3];
	GetEntPropVector(r, Prop_Data, "m_vecAbsOrigin", pos);
	SDKHooks_TakeDamage(target, r, owner, dmg, type, launcher > MaxClients ? launcher : -1, NULL_VECTOR, pos);
	Dbg("blade %d hurts %d for %.1f (total %.1f)", r, target, dmg, dealt + dmg);
}

/** OF Bounce past the count: a prop where the blade hit, gone after 5 s. */
void Stick(int r)
{
	float pos[3], ang[3];
	GetEntPropVector(r, Prop_Data, "m_vecAbsOrigin", pos);
	GetEntPropVector(r, Prop_Data, "m_angRotation", ang);
	char model[PLATFORM_MAX_PATH];
	GetEntPropString(r, Prop_Data, "m_ModelName", model, sizeof(model));
	AcceptEntityInput(r, "Kill");
	int prop = CreateEntityByName("prop_dynamic_override");
	if (prop <= MaxClients)
		return;
	DispatchKeyValue(prop, "model", model[0] ? model : BLADE_MODEL);
	DispatchKeyValue(prop, "solid", "0");
	TeleportEntity(prop, pos, ang, NULL_VECTOR);
	DispatchSpawn(prop);
	SetEntPropFloat(prop, Prop_Send, "m_flModelScale", g_cvScale.FloatValue);
	SetEntProp(prop, Prop_Data, "m_CollisionGroup", 1);
	CreateTimer(g_cvStick.FloatValue, Timer_KillProp, EntIndexToEntRef(prop), TIMER_FLAG_NO_MAPCHANGE);
	Dbg("blade %d stuck at %.0f %.0f %.0f", r, pos[0], pos[1], pos[2]);
}

public Action Timer_KillProp(Handle timer, int ref)
{
	int prop = EntRefToEntIndex(ref);
	if (prop > MaxClients)
		AcceptEntityInput(prop, "Kill");
	return Plugin_Stop;
}
