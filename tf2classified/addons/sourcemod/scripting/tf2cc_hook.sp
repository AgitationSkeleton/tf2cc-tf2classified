/**
 * tf2cc: the Eternal Shotgun's meat hook (Open Fortress CTFEternalShotgun / CTFMeatHook,
 * OFS shared/tf/tf_weapon_shotgun.cpp, tf_gamemovement.cpp GrapplingMove; see
 * the tf2cc research notes on the missing OF weapons, section 2).
 *
 * One source for both games: live TF2 (tools/build.sh; the weapon is found by its tf2cc_weapons
 * special "eternal_hook") and TF2 Classified (tools/tf2c/build_tf2c.sh compiles it with
 * TF2CC_TF2C=1 against SM-TF2Classified-Tools; the weapon is the schema item
 * tf2cc_merc_eternalshotgun from configs/tf2cc_tf2c/weapons.cfg).
 *
 * OF behaviour reproduced (defaults):
 *  - Right-click fires the hook (3500 u/s, 1500 under water) from the gun; a second right-click
 *    releases it (toggle; letting go of the button does nothing). A new shot needs the button
 *    released in between (m_bCanRefire) and the 1 s cooldown after every release.
 *  - The hook flies straight; it is checked every 0.1 s: 900 u from the shooter or out of sight
 *    = gone. It latches only on enemy players; the world, buildings and teammates = a miss.
 *  - Latched: the target is pinned (OF TF_COND_HOOKED: no acceleration, no air control, no jump;
 *    it can still aim and shoot) and the wielder is pulled at
 *    clamp(|v + 720 dir|, 720, max(|v| + 200, 720)) toward the target's centre every tick, with OF's
 *    air control (MEAT_HOOK_AIRCONTROL 150) bending the pull; 0.75x in water.
 *  - Released by: within 140 u of the target, the target out of sight for 0.15 s, either player
 *    dead, firing the shotgun, right-click again, switching weapons, or the pull being blocked
 *    (speed more than 75 % below the pull).
 * Optional (cvars, off): stun the hooked target (sandman-style small bonk / full bonk), release on
 * letting go of right-click (hold to reel), and hooking the world as a grappling hook (straight pull).
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
#define CFG_TF2C ""
#else
#define CFG_TF2C "configs/tf2cc_tf2c/weapons.cfg"
#endif

#define HOOK_MODEL "models/weapons/c_models/c_grapple_proj/c_grapple_proj.mdl"   // OF HOOK_MODEL (stock TF2)
#define FIRE_SOUND "weapons/crusaders_crossbow_shoot.wav"   // OF Weapon_GHook.Single
#define LATCH_SOUND "weapons/ar2/ar2_reload_push.wav"        // OF Weapon_AR2.Reload_Push (HL2)

#define STATE_NONE 0
#define STATE_FLYING 1
#define STATE_PLAYER 2
#define STATE_WORLD 3

public Plugin myinfo =
{
	name = "tf2cc Eternal Shotgun meat hook",
	author = "AgitationSkeleton",
	description = "Open Fortress Eternal Shotgun alt-fire meat hook",
	version = "1.0.0",
	url = ""
};

ConVar g_cvEnable, g_cvSpeed, g_cvSpeedWater, g_cvRange, g_cvPull, g_cvAirControl, g_cvRelease, g_cvCooldown;
ConVar g_cvLosTime, g_cvBlocked, g_cvStunMode, g_cvStunTime, g_cvHold, g_cvWorld, g_cvBeam, g_cvBeamWidth, g_cvHud, g_cvDebug;
int g_iDef = -1;
int g_iBeamModel;
Handle g_hHud;

// per wielder
int g_iState[MAXPLAYERS + 1];
int g_iWeapon[MAXPLAYERS + 1];      // entref of the shotgun the hook belongs to
int g_iTarget[MAXPLAYERS + 1];      // userid of the hooked player
int g_iProp[MAXPLAYERS + 1];        // entref of the flying hook's model
float g_vHook[MAXPLAYERS + 1][3];   // hook position (flying / world point)
float g_vDir[MAXPLAYERS + 1][3];    // flight direction
float g_flSpeed[MAXPLAYERS + 1];
float g_flPull[MAXPLAYERS + 1];
float g_flNextCheck[MAXPLAYERS + 1];
float g_flLos[MAXPLAYERS + 1];
float g_flNextShot[MAXPLAYERS + 1];
float g_flNextBeam[MAXPLAYERS + 1];
float g_flAttached[MAXPLAYERS + 1];
bool g_bCanRefire[MAXPLAYERS + 1] = {true, ...};
int g_iLastClip[MAXPLAYERS + 1];
int g_iLastClipWeapon[MAXPLAYERS + 1];   // entref the clip above was read from
float g_flGravity[MAXPLAYERS + 1];
// per target
int g_iPinned[MAXPLAYERS + 1];      // number of hooks holding this player
bool g_bStunned[MAXPLAYERS + 1];

public APLRes AskPluginLoad2(Handle myself, bool late, char[] error, int err_max)
{
#if !defined TF2CC_TF2C
	MarkNativeAsOptional("TF2CC_GetWeaponSpecial");
#endif
	return APLRes_Success;
}

public void OnPluginStart()
{
	g_cvEnable = CreateConVar("tf2cc_eternal_hook_enable", "1", "Eternal Shotgun: alt-fire meat hook (OF).", _, true, 0.0, true, 1.0);
	g_cvSpeed = CreateConVar("tf2cc_eternal_hook_speed", "3500", "Hook flight speed (OF BOLT_AIR_VELOCITY 3500).", _, true, 1.0);
	g_cvSpeedWater = CreateConVar("tf2cc_eternal_hook_speed_water", "1500", "Hook flight speed when the wielder is under water (OF 1500).", _, true, 1.0);
	g_cvRange = CreateConVar("tf2cc_eternal_hook_range", "900", "Hook flight range (OF MAX_ROPE_LENGTH 900).", _, true, 1.0);
	g_cvPull = CreateConVar("tf2cc_eternal_hook_pull", "720", "Minimum reel speed (OF HOOK_PULL 720).", _, true, 1.0);
	g_cvAirControl = CreateConVar("tf2cc_eternal_hook_aircontrol", "150", "Air control while reeled (OF MEAT_HOOK_AIRCONTROL 150).", _, true, 0.0);
	g_cvRelease = CreateConVar("tf2cc_eternal_hook_release_dist", "140", "Released within this distance of the target (OF 140).", _, true, 0.0);
	g_cvCooldown = CreateConVar("tf2cc_eternal_hook_cooldown", "1.0", "Seconds after a release before the next hook (OF 1).", _, true, 0.0);
	g_cvLosTime = CreateConVar("tf2cc_eternal_hook_los_time", "0.15", "Released when the target is out of sight this long (OF 0.15).", _, true, 0.0);
	g_cvBlocked = CreateConVar("tf2cc_eternal_hook_blocked", "0.75", "Released when the wielder's speed falls this fraction below the pull (OF 0.75; 0 = never).", _, true, 0.0, true, 1.0);
	g_cvStunMode = CreateConVar("tf2cc_eternal_hook_stun_mode", "0", "Hooked target: 0 = OF pin only (no moving or jumping, can still shoot), 1 = also a sandman-style small bonk (slowed, third person), 2 = also a full bonk (stuck, cannot attack).", _, true, 0.0, true, 2.0);
	g_cvStunTime = CreateConVar("tf2cc_eternal_hook_stun_time", "3.0", "Longest stun (stun modes 1/2); it ends with the hook anyway.", _, true, 0.1);
	g_cvHold = CreateConVar("tf2cc_eternal_hook_hold", "0", "1 = letting go of right-click releases the hook (hold to reel); 0 = OF toggle.", _, true, 0.0, true, 1.0);
	g_cvWorld = CreateConVar("tf2cc_eternal_hook_world", "0", "1 = the hook also latches on the world and pulls straight in (grappling hook); 0 = OF: players only.", _, true, 0.0, true, 1.0);
	g_cvBeam = CreateConVar("tf2cc_eternal_hook_beam", "cable/cable.vmt", "Rope material (OF cable/cable_grey.vmt; stock HL2 cable here).");
	g_cvBeamWidth = CreateConVar("tf2cc_eternal_hook_beam_width", "1.5", "Rope width (OF 1).", _, true, 0.1);
	g_cvHud = CreateConVar("tf2cc_eternal_hook_hud", "1", "Show the hook's cooldown while the Eternal Shotgun is out (OF's 'Hook' meter).", _, true, 0.0, true, 1.0);
	g_cvDebug = CreateConVar("tf2cc_eternal_hook_debug", "0", "Log hook events to the server console (2: also logs/tf2cc_hookprobe.log).", _, true, 0.0, true, 2.0);
	RegAdminCmd("sm_tf2cc_hook_reload", Cmd_Reload, ADMFLAG_CONFIG, "Reload the Eternal Shotgun item definition (TF2 Classified).");
	HookEvent("player_death", Event_Death);
	HookEvent("teamplay_round_start", Event_RoundStart, EventHookMode_PostNoCopy);
	g_hHud = CreateHudSynchronizer();
	CreateTimer(0.1, Timer_Hud, _, TIMER_REPEAT);
	LoadDefs();
	AutoExecConfig(true, "tf2cc_hook");
}

public void OnPluginEnd()
{
	for (int i = 1; i <= MaxClients; i++)
		if (g_iState[i] != STATE_NONE)
			Release(i, false);
}

public void OnMapStart()
{
	PrecacheModel(HOOK_MODEL, true);
	PrecacheSound(FIRE_SOUND, true);
	PrecacheSound(LATCH_SOUND, true);
	char beam[PLATFORM_MAX_PATH];
	g_cvBeam.GetString(beam, sizeof(beam));
	Format(beam, sizeof(beam), "materials/%s", beam);
	g_iBeamModel = PrecacheModel(beam, true);
	for (int i = 1; i <= MaxClients; i++)
	{
		g_iState[i] = STATE_NONE;
		g_flNextShot[i] = 0.0;
		g_iPinned[i] = 0;
		g_bStunned[i] = false;
		g_bCanRefire[i] = true;
	}
	LoadDefs();
}

public Action Cmd_Reload(int client, int args)
{
	LoadDefs();
	ReplyToCommand(client, "[tf2cc] Eternal Shotgun def %d", g_iDef);
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
			if (StrEqual(item, "tf2cc_merc_eternalshotgun"))
				g_iDef = kv.GetNum("defindex", -1);
		}
		while (kv.GotoNextKey());
	}
	else
		LogError("cannot read %s", path);
	delete kv;
#endif
}

void Dbg(const char[] fmt, any ...)
{
	if (!g_cvDebug.BoolValue)
		return;
	char buf[256];
	VFormat(buf, sizeof(buf), fmt, 2);
	PrintToServer("[HOOK] %.3f %s", GetGameTime(), buf);
	if (g_cvDebug.IntValue >= 2)
	{
		char path[PLATFORM_MAX_PATH];
		BuildPath(Path_SM, path, sizeof(path), "logs/tf2cc_hookprobe.log");
		LogToFileEx(path, "[HOOK] %.3f %s", GetGameTime(), buf);
	}
}

bool IsEternal(int weapon)
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
	return TF2CC_GetWeaponSpecial(weapon, special, sizeof(special), v) && StrEqual(special, "eternal_hook");
#endif
}

/* ---------------------------------------------------------------------------------------------- */
/* Geometry helpers                                                                                */
/* ---------------------------------------------------------------------------------------------- */

/** OF: origin + (eye - origin) * f. */
void BodyPoint(int client, float f, float out[3])
{
	float o[3], e[3];
	GetClientAbsOrigin(client, o);
	GetClientEyePosition(client, e);
	for (int k = 0; k < 3; k++)
		out[k] = o[k] + (e[k] - o[k]) * f;
}

/** Where the hook rope leaves the gun (OF GetProjectileFireSetup offset 30 / 4 / -6 from the eye). */
void GunPoint(int client, float out[3])
{
	float eye[3], ang[3], f[3], r[3], u[3];
	GetClientEyePosition(client, eye);
	GetClientEyeAngles(client, ang);
	GetAngleVectors(ang, f, r, u);
	for (int k = 0; k < 3; k++)
		out[k] = eye[k] + f[k] * 30.0 + r[k] * 4.0 - u[k] * 6.0;
}

public bool Filter_Not(int entity, int mask, any skip)
{
	return entity != skip;
}

/** OF HookLOS: a line from the hook to the wielder's middle that ends within 200 u of it. */
bool HookLOS(int client, const float hookPos[3], int ignore)
{
	float center[3];
	BodyPoint(client, 0.5, center);
	Handle tr = TR_TraceRayFilterEx(hookPos, center, MASK_SOLID, RayType_EndPoint, Filter_Not, ignore);
	float end[3];
	TR_GetEndPosition(end, tr);
	delete tr;
	return GetVectorDistance(end, center) < 200.0;
}

/* ---------------------------------------------------------------------------------------------- */
/* Input                                                                                           */
/* ---------------------------------------------------------------------------------------------- */

public Action OnPlayerRunCmd(int client, int &buttons, int &impulse, float vel[3], float angles[3], int &weapon)
{
	bool changed = false;
	// Hooked target (OF TF_COND_HOOKED): no acceleration, no air control, no jump.
	if (g_iPinned[client] > 0 && IsPlayerAlive(client))
	{
		buttons &= ~IN_JUMP;
		vel[0] = vel[1] = vel[2] = 0.0;
		changed = true;
	}
	if (!g_cvEnable.BoolValue || !IsPlayerAlive(client))
		return changed ? Plugin_Changed : Plugin_Continue;

	int active = GetEntPropEnt(client, Prop_Send, "m_hActiveWeapon");
	bool eternal = IsEternal(active);
	bool atk2 = (buttons & IN_ATTACK2) != 0;

	if (g_iState[client] != STATE_NONE)
	{
		int w = EntRefToEntIndex(g_iWeapon[client]);
		if (w != active)
		{
			Release(client, true, "weapon switch");          // OF Holster -> RemoveHook
		}
		else if (atk2 && g_bCanRefire[client] && !g_cvHold.BoolValue)
		{
			Release(client, true, "right-click");          // OF: a second right-click removes the hook
			g_bCanRefire[client] = false;
		}
		else if (!atk2 && g_cvHold.BoolValue)
		{
			Release(client, true, "right-click let go");
		}
		else if (w > MaxClients && EntRefToEntIndex(g_iLastClipWeapon[client]) == w && HasEntProp(w, Prop_Send, "m_iClip1")
			&& GetEntProp(w, Prop_Send, "m_iClip1") < g_iLastClip[client])
		{
			Release(client, true, "shot fired");          // OF PrimaryAttack -> RemoveHook (the shot was fired)
		}
	}
	else if (eternal && atk2 && g_bCanRefire[client] && GetGameTime() >= g_flNextShot[client])
	{
		Fire(client, active);
		g_bCanRefire[client] = false;
	}
	if (!atk2)
		g_bCanRefire[client] = true;
	if (active > MaxClients && HasEntProp(active, Prop_Send, "m_iClip1"))
	{
		g_iLastClip[client] = GetEntProp(active, Prop_Send, "m_iClip1");
		g_iLastClipWeapon[client] = EntIndexToEntRef(active);
	}

	if (g_iState[client] == STATE_PLAYER || g_iState[client] == STATE_WORLD)
	{
		if (Reel(client, vel))
			changed = true;
	}
	return changed ? Plugin_Changed : Plugin_Continue;
}

public void OnPlayerRunCmdPost(int client, int buttons, int impulse, const float vel[3], const float angles[3], int weapon, int subtype, int cmdnum, int tickcount, int seed, const int mouse[2])
{
	if (g_iState[client] != STATE_PLAYER && g_iState[client] != STATE_WORLD)
		return;
	// OF GrapplingMove: movement halted a lot (TryPlayerMove could not carry the pull) = released.
	if (g_cvBlocked.FloatValue <= 0.0 || GetGameTime() - g_flAttached[client] < 0.1)
		return;
	float v[3];
	GetEntPropVector(client, Prop_Data, "m_vecVelocity", v);
	if (g_flPull[client] - GetVectorLength(v) > g_flPull[client] * g_cvBlocked.FloatValue)
	{
		Dbg("%N: pull blocked (speed %.0f, pull %.0f)", client, GetVectorLength(v), g_flPull[client]);
		Release(client, true, "blocked");
	}
}

/* ---------------------------------------------------------------------------------------------- */
/* Hook flight                                                                                     */
/* ---------------------------------------------------------------------------------------------- */

void Fire(int client, int weapon)
{
	float src[3], eye[3], ang[3], fwd[3], end[3], aim[3];
	GunPoint(client, src);
	// OF GetProjectileFireSetup: the hook flies from the gun to the point under the crosshair.
	GetClientEyePosition(client, eye);
	GetClientEyeAngles(client, ang);
	GetAngleVectors(ang, fwd, NULL_VECTOR, NULL_VECTOR);
	for (int k = 0; k < 3; k++)
		end[k] = eye[k] + fwd[k] * 8192.0;
	Handle tr = TR_TraceRayFilterEx(eye, end, MASK_SHOT, RayType_EndPoint, Filter_Not, client);
	TR_GetEndPosition(aim, tr);
	delete tr;
	MakeVectorFromPoints(src, aim, g_vDir[client]);
	if (GetVectorLength(g_vDir[client]) < 1.0)
		g_vDir[client] = fwd;
	NormalizeVector(g_vDir[client], g_vDir[client]);
	g_vHook[client] = src;
	g_flSpeed[client] = GetEntProp(client, Prop_Data, "m_nWaterLevel") >= 3 ? g_cvSpeedWater.FloatValue : g_cvSpeed.FloatValue;
	g_iWeapon[client] = EntIndexToEntRef(weapon);
	g_iState[client] = STATE_FLYING;
	g_flNextCheck[client] = GetGameTime() + 0.1;
	g_flNextBeam[client] = 0.0;
	g_iTarget[client] = 0;

	int prop = CreateEntityByName("prop_dynamic_override");
	if (prop > MaxClients)
	{
		DispatchKeyValue(prop, "model", HOOK_MODEL);
		DispatchKeyValue(prop, "solid", "0");
		float pang[3];
		GetVectorAngles(g_vDir[client], pang);
		TeleportEntity(prop, src, pang, NULL_VECTOR);
		DispatchSpawn(prop);
		SetEntProp(prop, Prop_Data, "m_CollisionGroup", 1);   // COLLISION_GROUP_DEBRIS
		g_iProp[client] = EntIndexToEntRef(prop);
	}
	EmitSoundToAll(FIRE_SOUND, client, SNDCHAN_AUTO, SNDLEVEL_GUNFIRE);
	Dbg("%N fires the hook", client);
}

public void OnGameFrame()
{
	float now = GetGameTime(), dt = GetTickInterval();
	for (int c = 1; c <= MaxClients; c++)
	{
		if (g_iState[c] == STATE_NONE)
			continue;
		if (!IsClientInGame(c) || !IsPlayerAlive(c))
		{
			Release(c, false, "wielder dead");
			continue;
		}
		if (g_iState[c] == STATE_FLYING)
			Fly(c, now, dt);
		if (g_iState[c] != STATE_NONE && now >= g_flNextBeam[c])
		{
			g_flNextBeam[c] = now + 0.05;
			DrawRope(c);
		}
	}
}

void Fly(int c, float now, float dt)
{
	float next[3];
	for (int k = 0; k < 3; k++)
		next[k] = g_vHook[c][k] + g_vDir[c][k] * g_flSpeed[c] * dt;
	// OF CTFMeatHook: a 2x2x2 box, solid mask + hitboxes, no grates.
	Handle tr = TR_TraceHullFilterEx(g_vHook[c], next, view_as<float>({-1.0, -1.0, -1.0}), view_as<float>({1.0, 1.0, 1.0}),
		(MASK_SHOT | CONTENTS_HITBOX) & ~CONTENTS_GRATE, Filter_Not, c);
	if (TR_DidHit(tr))
	{
		float hit[3];
		TR_GetEndPosition(hit, tr);
		int other = TR_GetEntityIndex(tr);
		bool sky = (TR_GetSurfaceFlags(tr) & 0x0004) != 0;     // SURF_SKY
		delete tr;
		g_vHook[c] = hit;
		MoveProp(c);
		if (other >= 1 && other <= MaxClients && IsClientInGame(other) && IsPlayerAlive(other) && GetClientTeam(other) != GetClientTeam(c))
		{
			AttachPlayer(c, other);
			return;
		}
		if (other == 0 && !sky && g_cvWorld.BoolValue)
		{
			AttachWorld(c);
			return;
		}
		Dbg("%N: hook missed (entity %d)", c, other);
		Release(c, true, "miss");       // OF HookTouch: the world, non-players and teammates remove the hook
		return;
	}
	delete tr;
	g_vHook[c] = next;
	MoveProp(c);
	if (now >= g_flNextCheck[c])
	{
		// OF FlyThink every 0.1 s: too far from the gun or out of sight.
		g_flNextCheck[c] = now + 0.1;
		float gun[3];
		GunPoint(c, gun);
		if (GetVectorDistance(g_vHook[c], gun) >= g_cvRange.FloatValue || !HookLOS(c, g_vHook[c], EntRefToEntIndex(g_iProp[c])))
		{
			Release(c, true, "flight: range / sight");
		}
	}
}

void MoveProp(int c)
{
	int prop = EntRefToEntIndex(g_iProp[c]);
	if (prop > MaxClients)
		TeleportEntity(prop, g_vHook[c], NULL_VECTOR, NULL_VECTOR);
}

void KillProp(int c)
{
	int prop = EntRefToEntIndex(g_iProp[c]);
	if (prop > MaxClients)
		AcceptEntityInput(prop, "Kill");
	g_iProp[c] = INVALID_ENT_REFERENCE;
}

void DrawRope(int c)
{
	float start[3], end[3];
	GunPoint(c, start);
	if (g_iState[c] == STATE_PLAYER)
	{
		int t = GetClientOfUserId(g_iTarget[c]);
		if (t <= 0)
			return;
		BodyPoint(t, 0.75, end);            // OF: hookPos += (EyePosition - hookPos) * 0.75
	}
	else
		end = g_vHook[c];
	float w = g_cvBeamWidth.FloatValue;
	TE_SetupBeamPoints(start, end, g_iBeamModel, 0, 0, 0, 0.1, w, w, 0, 0.0, {255, 255, 255, 255}, 0);
	TE_SendToAll();
}

/* ---------------------------------------------------------------------------------------------- */
/* Latched                                                                                         */
/* ---------------------------------------------------------------------------------------------- */

void AttachPlayer(int c, int target)
{
	KillProp(c);
	g_iTarget[c] = GetClientUserId(target);
	g_iState[c] = STATE_PLAYER;
	g_iPinned[target]++;
	EmitSoundToAll(LATCH_SOUND, target, SNDCHAN_AUTO, SNDLEVEL_NORMAL);
	int mode = g_cvStunMode.IntValue;
	if (mode > 0)
	{
		TF2_StunPlayer(target, g_cvStunTime.FloatValue, mode == 1 ? 0.5 : 0.0, mode == 1 ? TF_STUNFLAGS_SMALLBONK : TF_STUNFLAGS_NORMALBONK, c);
		g_bStunned[target] = true;
	}
	float to[3];
	GetClientAbsOrigin(target, to);
	StartReel(c, to);
	Dbg("%N hooked %N (pull %.0f)", c, target, g_flPull[c]);
}

void AttachWorld(int c)
{
	g_iState[c] = STATE_WORLD;
	EmitSoundToAll(LATCH_SOUND, c, SNDCHAN_AUTO, SNDLEVEL_NORMAL);
	StartReel(c, g_vHook[c]);
	Dbg("%N grappled the world (pull %.0f)", c, g_flPull[c]);
}

/** OF InitiateHook: lift off the ground and work out the pull speed. */
void StartReel(int c, const float to[3])
{
	float o[3], v[3], rope[3];
	GetClientAbsOrigin(c, o);
	GetEntPropVector(c, Prop_Data, "m_vecVelocity", v);
	MakeVectorFromPoints(o, to, rope);
	NormalizeVector(rope, rope);
	float pull = g_cvPull.FloatValue;
	float nv[3];
	for (int k = 0; k < 3; k++)
		nv[k] = v[k] + rope[k] * pull;
	float cap = GetVectorLength(v) + 200.0;
	if (cap < pull)
		cap = pull;
	float p = GetVectorLength(nv);
	g_flPull[c] = p < pull ? pull : (p > cap ? cap : p);
	if (GetEntPropEnt(c, Prop_Send, "m_hGroundEntity") != -1)
	{
		o[2] += 10.0;
		TeleportEntity(c, o, NULL_VECTOR, NULL_VECTOR);
	}
	SetEntPropEnt(c, Prop_Send, "m_hGroundEntity", -1);
	g_flGravity[c] = GetEntityGravity(c);
	SetEntityGravity(c, 0.0001);            // the pull sets the whole velocity every tick (OF GrapplingMove)
	g_flAttached[c] = GetGameTime();
	g_flLos[c] = GetGameTime();
}

/** Every tick while latched (from OnPlayerRunCmd, before the movement): OF GrapplingMove. */
bool Reel(int c, float vel[3])
{
	float now = GetGameTime();
	float to[3], hookPos[3];
	int target = 0;
	if (g_iState[c] == STATE_PLAYER)
	{
		target = GetClientOfUserId(g_iTarget[c]);
		if (target <= 0 || !IsClientInGame(target) || !IsPlayerAlive(target))
		{
			Release(c, true, "target gone");
			return false;
		}
		BodyPoint(target, 0.5, to);
		BodyPoint(target, 0.75, hookPos);
		float a[3], b[3];
		GetClientAbsOrigin(target, a);
		GetClientAbsOrigin(c, b);
		if (GetVectorDistance(a, b) <= g_cvRelease.FloatValue)
		{
			Release(c, true, "reached the target");
			return false;
		}
	}
	else
	{
		to = g_vHook[c];
		hookPos = g_vHook[c];
		float b[3];
		GetClientAbsOrigin(c, b);
		if (GetVectorDistance(to, b) <= g_cvRelease.FloatValue)
		{
			Release(c, true, "reached the point");
			return false;
		}
	}
	if (HookLOS(c, hookPos, target > 0 ? target : c))
		g_flLos[c] = now;
	else if (now > g_flLos[c] + g_cvLosTime.FloatValue)
	{
		Release(c, true, "out of sight");
		return false;
	}

	float center[3], dir[3], v[3];
	BodyPoint(c, 0.5, center);
	MakeVectorFromPoints(center, to, dir);
	NormalizeVector(dir, dir);
	float water = GetEntProp(c, Prop_Data, "m_nWaterLevel") >= 2 ? 0.75 : 1.0;
	float pull = g_flPull[c];
	for (int k = 0; k < 3; k++)
		v[k] = dir[k] * pull * water;
	if (g_iState[c] == STATE_PLAYER)
	{
		// OF meat hook air control: the wish direction (flat) bends the pull.
		float ang[3], f[3], r[3], wish[3];
		GetClientEyeAngles(c, ang);
		GetAngleVectors(ang, f, r, NULL_VECTOR);
		f[2] = 0.0;
		r[2] = 0.0;
		NormalizeVector(f, f);
		NormalizeVector(r, r);
		for (int k = 0; k < 2; k++)
			wish[k] = (f[k] * vel[0] + r[k] * vel[1]) * g_cvAirControl.FloatValue;
		wish[2] = 0.0;
		float nw[3], nv[3];
		NormalizeVector(wish, nw);
		nv = v;
		nv[2] = 0.0;
		NormalizeVector(nv, nv);
		float dot = GetVectorDotProduct(nv, nw);
		float ft = GetTickInterval();
		if (dot >= 0.0)
		{
			for (int k = 0; k < 3; k++)
				v[k] += wish[k] * ft * water;
			NormalizeVector(v, v);
			ScaleVector(v, pull);
		}
		else
		{
			float d = 1.0 + dot;
			if (d < 0.0)
				d = 0.0;
			for (int k = 0; k < 3; k++)
				v[k] += wish[k] * ft * d * water;
		}
	}
	SetEntPropEnt(c, Prop_Send, "m_hGroundEntity", -1);
	SetEntityFlags(c, GetEntityFlags(c) & ~FL_ONGROUND);
	TeleportEntity(c, NULL_VECTOR, NULL_VECTOR, v);
	// The movement code would add the player's own acceleration on top: OF's GrapplingMove replaces it.
	vel[0] = vel[1] = 0.0;
	return true;
}

/* ---------------------------------------------------------------------------------------------- */
/* Release / cleanup                                                                               */
/* ---------------------------------------------------------------------------------------------- */

/** OF RemoveHook: drop the hook or the hooked player, and the 1 s cooldown (always). */
void Release(int c, bool cooldown, const char[] why = "")
{
	int state = g_iState[c];
	g_iState[c] = STATE_NONE;
	KillProp(c);
	if (state == STATE_PLAYER)
	{
		int t = GetClientOfUserId(g_iTarget[c]);
		if (t > 0 && g_iPinned[t] > 0 && --g_iPinned[t] == 0 && g_bStunned[t])
		{
			g_bStunned[t] = false;
			if (IsClientInGame(t) && IsPlayerAlive(t))
				TF2_RemoveCondition(t, TFCond_Dazed);
		}
	}
	if ((state == STATE_PLAYER || state == STATE_WORLD) && IsClientInGame(c))
		SetEntityGravity(c, g_flGravity[c] > 0.0 ? g_flGravity[c] : 1.0);
	g_iTarget[c] = 0;
	if (cooldown)
		g_flNextShot[c] = GetGameTime() + g_cvCooldown.FloatValue;
	if (state != STATE_NONE)
		Dbg("%N: hook released (%s)", c, why);
}

public void Event_Death(Event event, const char[] name, bool dontBroadcast)
{
	int victim = GetClientOfUserId(event.GetInt("userid"));
	if (victim <= 0)
		return;
	if (g_iState[victim] != STATE_NONE)
		Release(victim, true, "wielder died");
	// A hooked player died: free every hook holding it (OF: m_iAttached && !target alive).
	for (int c = 1; c <= MaxClients; c++)
		if (g_iState[c] == STATE_PLAYER && GetClientOfUserId(g_iTarget[c]) == victim)
			Release(c, true, "target died");
	g_iPinned[victim] = 0;
	g_bStunned[victim] = false;
}

public void Event_RoundStart(Event event, const char[] name, bool dontBroadcast)
{
	for (int c = 1; c <= MaxClients; c++)
	{
		if (g_iState[c] != STATE_NONE)
			Release(c, false);
		g_iPinned[c] = 0;
		g_bStunned[c] = false;
		g_flNextShot[c] = 0.0;
	}
}

public void OnClientDisconnect(int client)
{
	if (g_iState[client] != STATE_NONE)
		Release(client, false);
	for (int c = 1; c <= MaxClients; c++)
		if (g_iState[c] == STATE_PLAYER && GetClientOfUserId(g_iTarget[c]) == client)
			Release(c, true);
	g_iPinned[client] = 0;
	g_bStunned[client] = false;
	g_bCanRefire[client] = true;
	g_flNextShot[client] = 0.0;
}

/* OF tf_hud_lungemeter "Hook": the cooldown while the Eternal Shotgun is out. */
public Action Timer_Hud(Handle timer)
{
	if (!g_cvHud.BoolValue || !g_cvEnable.BoolValue)
		return Plugin_Continue;
	float now = GetGameTime();
	for (int c = 1; c <= MaxClients; c++)
	{
		if (!IsClientInGame(c) || IsFakeClient(c) || !IsPlayerAlive(c))
			continue;
		if (!IsEternal(GetEntPropEnt(c, Prop_Send, "m_hActiveWeapon")))
			continue;
		float left = g_flNextShot[c] - now;
		char bar[32];
		if (g_iState[c] != STATE_NONE)
			strcopy(bar, sizeof(bar), "HOOK: on");
		else if (left > 0.0)
			Format(bar, sizeof(bar), "HOOK: %.1f", left);
		else
			strcopy(bar, sizeof(bar), "HOOK: ready");
		SetHudTextParams(0.85, 0.80, 0.15, 255, left > 0.0 ? 153 : 255, left > 0.0 ? 0 : 255, 255, 0, 0.0, 0.0, 0.0);
		ShowSyncHudText(c, g_hHud, "%s", bar);
	}
	return Plugin_Continue;
}
