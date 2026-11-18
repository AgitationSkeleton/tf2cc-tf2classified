/**
 * tf2cc for TF2 Classified: Open Fortress rocket weapons of the Merc - Quad Launcher and Bouncer.
 * Research: the tf2cc notes on the missing OF weapons (OF source tf_weapon_rocketlauncher.cpp,
 * tf_weaponbase_gun.cpp, tf_projectile_rocket.cpp; OF items_game.txt).
 *
 * Native (schema, tools/tf2c/gen_schema.py), both on tf_weapon_rocketlauncher:
 *  - Quad: damage 75, radius 100, "mod burstfire" "4 0.2" (4 rockets 0.1 s apart, 0.5 s between
 *    bursts), clip 4 / 16, whole-clip reload 3.84 s, the OF quad rocket model.
 *  - Bouncer: damage 90, radius 109.5, no falloff, 750 u/s pitched up (+194 u/s), gravity 1.5
 *    ("rocket gravity": MOVETYPE_FLYGRAVITY as OF's CTFProjectile_BouncyRocket), 2 s fuse ("rocket
 *    limited lifetime": detonates with full damage), the OF bouncer grenade model.
 *
 * Here (plugin):
 *  - Bouncer ricochet (OF CTFProjectile_BouncyRocket::RocketTouch): a world hit faster than 200 u/s
 *    reflects the velocity (v - 2(v.n)n) x 0.9 (0.6 under water) instead of exploding; slower ones
 *    neither bounce nor explode (they rest until the fuse); anything else (players, buildings, props,
 *    doors) explodes it natively. The native touch is blocked for world hits only; the new velocity
 *    is written on the next frame, outside the touch callback. Bounce sound at most every 0.1 s.
 *    (5205's own "set rocket detonate mode" 2 was measured on the LAN test server: elasticity ~0.81
 *    and an explosion on the 6th contact, unlike OF; not used.)
 *  - Quad (OF CTFSuperRocketLauncher): rockets home on the owner's aim point while the Quad is out
 *    and homing is on (OF m_bHoming, on by default); alt-fire toggles homing for all the owner's
 *    rockets (SwitchHomingModes); a ping every second while homing (Weapon_Quad.Ping); each rocket
 *    since the last reload explodes 25 wider (ContinuousFire_BlastRadiusIncrease: 100/125/150/175),
 *    set on the launcher ("Blast radius increased") right before the native explosion reads it.
 */
#include <sourcemod>
#include <sdktools>
#include <sdkhooks>
#include <tf2attributes>

#pragma semicolon 1
#pragma newdecls required

#define CFG_WEAPONS "configs/tf2cc_tf2c/weapons.cfg"
#define CFG_ASSETS "configs/tf2cc_tf2c/assets.cfg"
#define KIND_NONE 0
#define KIND_QUAD 1
#define KIND_BOUNCER 2
#define QUAD_PING_SOUND "ui/cyoa_ping_available.wav"   // OF Weapon_Quad.Ping (stock TF2 sample)
#define BOUNCE_SOUND_DEFAULT "tf2cc/of/weapons/bouncer_nade_impact.wav"

public Plugin myinfo =
{
	name = "tf2cc OF rockets (TF2 Classified)",
	author = "AgitationSkeleton",
	description = "Open Fortress Quad Launcher homing/radius and Bouncer ricochet for the Merc",
	version = "1.0.0",
	url = ""
};

ConVar g_cvEnable, g_cvBounce, g_cvBounceElastic, g_cvBounceElasticWater, g_cvBounceMin;
ConVar g_cvQuadHoming, g_cvQuadTurn, g_cvQuadToggle, g_cvQuadPing, g_cvQuadRadiusStep, g_cvQuadRadiusBase, g_cvDebug;
int g_iDefQuad = -1, g_iDefBouncer = -1;
char g_sBounceSound[PLATFORM_MAX_PATH] = BOUNCE_SOUND_DEFAULT;

// per rocket
int g_iKind[2049];
int g_iLauncher[2049];           // entref
float g_flScale[2049];           // Quad: radius multiplier from the shot index
bool g_bPending[2049];           // Bouncer: a reflected velocity waits for the next frame
float g_vPending[2049][3];
float g_flLastBounce[2049];
ArrayList g_Rockets;             // entrefs of tracked rockets

// per client (Quad)
bool g_bQuadOff[MAXPLAYERS + 1];
bool g_bAtk2[MAXPLAYERS + 1];
float g_flPing[MAXPLAYERS + 1];
int g_iShots[MAXPLAYERS + 1];
int g_iClip[MAXPLAYERS + 1];
int g_iQuadWeapon[MAXPLAYERS + 1];

public void OnPluginStart()
{
	g_cvEnable = CreateConVar("tf2cc_ofrockets_enable", "1", "OF Quad Launcher / Bouncer behaviour for the Merc.", _, true, 0.0, true, 1.0);
	g_cvBounce = CreateConVar("tf2cc_bouncer_bounce", "1", "Bouncer: grenades ricochet off the world instead of exploding (OF CTFProjectile_BouncyRocket).", _, true, 0.0, true, 1.0);
	g_cvBounceElastic = CreateConVar("tf2cc_bouncer_elasticity", "0.9", "Bouncer: speed kept per bounce (OF SetElasticity 0.9).", _, true, 0.0, true, 1.0);
	g_cvBounceElasticWater = CreateConVar("tf2cc_bouncer_elasticity_water", "0.6", "Bouncer: speed kept per bounce fully under water (OF 0.6).", _, true, 0.0, true, 1.0);
	g_cvBounceMin = CreateConVar("tf2cc_bouncer_min_speed", "200", "Bouncer: slower world hits neither bounce nor explode (OF 200).", _, true, 0.0);
	g_cvQuadHoming = CreateConVar("tf2cc_quad_homing", "1", "Quad Launcher rockets home on the point the owner aims at while the Quad is out (OF m_bHoming).", _, true, 0.0, true, 1.0);
	g_cvQuadTurn = CreateConVar("tf2cc_quad_turn_rate", "12.0", "Quad rocket steering per second (fraction of the way to the aim direction; OF snaps every 0.1 s).", _, true, 0.0);
	g_cvQuadToggle = CreateConVar("tf2cc_quad_toggle", "1", "Quad Launcher alt-fire toggles homing (OF SwitchHomingModes).", _, true, 0.0, true, 1.0);
	g_cvQuadPing = CreateConVar("tf2cc_quad_ping", "1", "Quad Launcher: ping every second while homing and the Quad is out (OF Weapon_Quad.Ping).", _, true, 0.0, true, 1.0);
	g_cvQuadRadiusStep = CreateConVar("tf2cc_quad_radius_step", "25", "Quad Launcher: radius added per rocket since the last reload (OF ContinuousFire_BlastRadiusIncrease; 0 = off).", _, true, 0.0);
	g_cvQuadRadiusBase = CreateConVar("tf2cc_quad_radius_base", "100", "Quad Launcher: the OF base radius the step is relative to.", _, true, 1.0);
	g_cvDebug = CreateConVar("tf2cc_ofrockets_debug", "0", "Log Quad/Bouncer events to the server console.", _, true, 0.0, true, 1.0);
	RegAdminCmd("sm_tf2cc_ofrockets_reload", Cmd_Reload, ADMFLAG_CONFIG, "Reload the Quad / Bouncer item definitions.");
	g_Rockets = new ArrayList();
	HookEvent("player_spawn", Event_Spawn);
	LoadDefs();
}

public void Event_Spawn(Event event, const char[] name, bool dontBroadcast)
{
	int client = GetClientOfUserId(event.GetInt("userid"));
	if (client)
	{
		g_bQuadOff[client] = false;   // OF: a new Quad starts homing (m_bHoming = true)
		g_iShots[client] = 0;
		g_iQuadWeapon[client] = 0;
	}
}

public void OnMapStart()
{
	PrecacheSound(QUAD_PING_SOUND, true);
	LoadDefs();
	PrecacheSound(g_sBounceSound, true);
	for (int i = 1; i <= MaxClients; i++)
		g_flPing[i] = 0.0;
}

public Action Cmd_Reload(int client, int args)
{
	LoadDefs();
	ReplyToCommand(client, "[tf2cc] Quad def %d, Bouncer def %d, bounce sound %s", g_iDefQuad, g_iDefBouncer, g_sBounceSound);
	return Plugin_Handled;
}

void LoadDefs()
{
	g_iDefQuad = g_iDefBouncer = -1;
	char path[PLATFORM_MAX_PATH], item[64];
	BuildPath(Path_SM, path, sizeof(path), CFG_WEAPONS);
	KeyValues kv = new KeyValues("tf2cc_tf2c_weapons");
	if (kv.ImportFromFile(path) && kv.GotoFirstSubKey())
	{
		do
		{
			kv.GetString("item", item, sizeof(item));
			if (StrEqual(item, "tf2cc_merc_quad"))
				g_iDefQuad = kv.GetNum("defindex", -1);
			else if (StrEqual(item, "tf2cc_merc_bouncer"))
				g_iDefBouncer = kv.GetNum("defindex", -1);
		}
		while (kv.GotoNextKey());
	}
	else
		LogError("cannot read %s", path);
	delete kv;
	BuildPath(Path_SM, path, sizeof(path), CFG_ASSETS);
	kv = new KeyValues("tf2cc_tf2c_assets");
	if (kv.ImportFromFile(path))
		kv.GetString("bouncer_sound", g_sBounceSound, sizeof(g_sBounceSound), BOUNCE_SOUND_DEFAULT);
	delete kv;
}

void Dbg(const char[] fmt, any ...)
{
	if (!g_cvDebug.BoolValue)
		return;
	char buf[256];
	VFormat(buf, sizeof(buf), fmt, 2);
	PrintToServer("[OFR] %.3f %s", GetGameTime(), buf);
}

int WeaponKind(int weapon)
{
	if (weapon <= MaxClients || !IsValidEntity(weapon) || !HasEntProp(weapon, Prop_Send, "m_iItemDefinitionIndex"))
		return KIND_NONE;
	int def = GetEntProp(weapon, Prop_Send, "m_iItemDefinitionIndex");
	return def == g_iDefQuad ? KIND_QUAD : def == g_iDefBouncer ? KIND_BOUNCER : KIND_NONE;
}

/* ---------------------------------------------------------------------------------------------- */
/* Rockets                                                                                         */
/* ---------------------------------------------------------------------------------------------- */

public void OnEntityCreated(int entity, const char[] classname)
{
	if (entity <= MaxClients || entity >= sizeof(g_iKind))
		return;
	g_iKind[entity] = KIND_NONE;
	if (StrEqual(classname, "tf_projectile_rocket"))
		SDKHook(entity, SDKHook_SpawnPost, Hook_RocketSpawn);
}

public void OnEntityDestroyed(int entity)
{
	if (entity > MaxClients && entity < sizeof(g_iKind))
	{
		g_iKind[entity] = KIND_NONE;
		g_bPending[entity] = false;
	}
}

public void Hook_RocketSpawn(int rocket)
{
	if (!g_cvEnable.BoolValue || g_iKind[rocket] != KIND_NONE)
		return;    // SpawnPost can run twice for a rocket: track it once
	int owner = GetEntPropEnt(rocket, Prop_Send, "m_hOwnerEntity");
	if (owner < 1 || owner > MaxClients || !IsClientInGame(owner))
		return;
	int weapon = GetEntPropEnt(owner, Prop_Send, "m_hActiveWeapon");
	int kind = WeaponKind(weapon);
	if (kind == KIND_NONE)
		return;
	g_iKind[rocket] = kind;
	g_iLauncher[rocket] = EntIndexToEntRef(weapon);
	g_bPending[rocket] = false;
	g_flLastBounce[rocket] = 0.0;
	g_Rockets.Push(EntIndexToEntRef(rocket));
	if (kind == KIND_QUAD)
	{
		// OF: m_flBlastRadiusIncrease += 25 after every shot, reset by Reload: rocket k (0-based)
		// since the last reload explodes with 100 + 25k.
		int k = g_iShots[owner]++;
		g_flScale[rocket] = (g_cvQuadRadiusBase.FloatValue + g_cvQuadRadiusStep.FloatValue * k) / g_cvQuadRadiusBase.FloatValue;
		SDKHook(rocket, SDKHook_Touch, Hook_QuadTouch);
		Dbg("quad rocket %d shot %d scale %.2f", rocket, k, g_flScale[rocket]);
	}
	else
	{
		// The grenade model has RED/BLU/GRN/YLW families (gen_schema team_skin_patch). TF2C rockets
		// have no team skins of their own (CTFBaseProjectile::HasTeamSkins false): the client draws
		// the networked m_nSkin, so it is set here (GetTeamSkin order: red 0, blue 1, green 2, yellow 3).
		int team = GetEntProp(rocket, Prop_Send, "m_iTeamNum");
		if (team >= 2 && team <= 5)
			SetEntProp(rocket, Prop_Send, "m_nSkin", team - 2);
		SDKHook(rocket, SDKHook_Touch, Hook_BouncerTouch);
		Dbg("bouncer rocket %d", rocket);
	}
}

/** World hit: reflect (next frame) and skip the native RocketTouch; anything else explodes natively. */
public Action Hook_BouncerTouch(int rocket, int other)
{
	if (other != 0 || !g_cvBounce.BoolValue || g_iKind[rocket] != KIND_BOUNCER)
		return Plugin_Continue;
	float pos[3], vel[3], dir[3], end[3], n[3];
	GetEntPropVector(rocket, Prop_Data, "m_vecAbsOrigin", pos);
	GetEntPropVector(rocket, Prop_Data, "m_vecAbsVelocity", vel);
	float speed = GetVectorLength(vel);
	if (speed < 1.0)
		return Plugin_Handled;
	NormalizeVector(vel, dir);
	// From a little behind the rocket: at the touch it can already sit on (or in) the surface,
	// and a trace starting in solid returns no plane normal.
	float start[3];
	for (int i = 0; i < 3; i++)
	{
		start[i] = pos[i] - dir[i] * 16.0;
		end[i] = pos[i] + dir[i] * 64.0;
	}
	Handle tr = TR_TraceRayFilterEx(start, end, MASK_SOLID, RayType_EndPoint, Filter_World, rocket);
	bool hit = TR_DidHit(tr) && !TR_StartSolid(tr);
	if (hit)
	{
		TR_GetPlaneNormal(tr, n);
		if (GetVectorLength(n) < 0.5)
			hit = false;
		if (TR_GetSurfaceFlags(tr) & SURF_SKY)
		{
			delete tr;
			return Plugin_Continue;     // OF: the sky removes it (the native touch does)
		}
	}
	delete tr;
	if (!hit)
		for (int i = 0; i < 3; i++)
			n[i] = -dir[i];         // no surface found ahead: send it back
	if (speed <= g_cvBounceMin.FloatValue)
		return Plugin_Handled;      // OF: too slow to bounce, and it does not explode either
	float d = GetVectorDotProduct(vel, n) * 2.0;
	if (d >= 0.0)
		return Plugin_Handled;      // already moving away from that surface (a repeated touch)
	float e = GetEntProp(rocket, Prop_Data, "m_nWaterLevel") >= 3 ? g_cvBounceElasticWater.FloatValue : g_cvBounceElastic.FloatValue;
	for (int i = 0; i < 3; i++)
		g_vPending[rocket][i] = (vel[i] - n[i] * d) * e;
	g_bPending[rocket] = true;
	float now = GetGameTime();
	if (now > g_flLastBounce[rocket] + 0.1)
	{
		g_flLastBounce[rocket] = now;
		EmitSoundToAll(g_sBounceSound, rocket, SNDCHAN_AUTO, SNDLEVEL_NORMAL);
	}
	Dbg("bouncer %d bounce: speed %.0f -> %.0f normal %.2f %.2f %.2f", rocket, speed, speed * e, n[0], n[1], n[2]);
	return Plugin_Handled;
}

public bool Filter_World(int entity, int mask, any rocket)
{
	return entity == 0;
}

/** Right before the native explosion reads the launcher's mult_explosion_radius. Attribute value only. */
public Action Hook_QuadTouch(int rocket, int other)
{
	if (g_iKind[rocket] != KIND_QUAD || g_cvQuadRadiusStep.FloatValue <= 0.0)
		return Plugin_Continue;
	int launcher = EntRefToEntIndex(g_iLauncher[rocket]);
	if (launcher > MaxClients)
		TF2Attrib_SetByName(launcher, "Blast radius increased", g_flScale[rocket] > 0.0 ? g_flScale[rocket] : 1.0);
	return Plugin_Continue;
}

public void OnGameFrame()
{
	if (g_Rockets.Length == 0)
		return;
	float dt = GetTickInterval();
	for (int i = g_Rockets.Length - 1; i >= 0; i--)
	{
		int r = EntRefToEntIndex(g_Rockets.Get(i));
		if (r <= MaxClients || g_iKind[r] == KIND_NONE)
		{
			g_Rockets.Erase(i);
			continue;
		}
		if (g_iKind[r] == KIND_BOUNCER)
		{
			if (g_bPending[r])
			{
				g_bPending[r] = false;
				float ang[3];
				GetVectorAngles(g_vPending[r], ang);
				TeleportEntity(r, NULL_VECTOR, ang, g_vPending[r]);
			}
			continue;
		}
		QuadSteer(r, dt);
	}
}

/* ---------------------------------------------------------------------------------------------- */
/* Quad                                                                                            */
/* ---------------------------------------------------------------------------------------------- */

void QuadSteer(int r, float dt)
{
	if (!g_cvQuadHoming.BoolValue)
		return;
	int owner = GetEntPropEnt(r, Prop_Send, "m_hOwnerEntity");
	if (owner < 1 || owner > MaxClients || !IsClientInGame(owner) || !IsPlayerAlive(owner) || g_bQuadOff[owner])
		return;
	if (WeaponKind(GetEntPropEnt(owner, Prop_Send, "m_hActiveWeapon")) != KIND_QUAD)
		return;     // OF: the dot (and homing) exists only while the Quad is out
	float eye[3], ang[3], dir[3], end[3];
	GetClientEyePosition(owner, eye);
	GetClientEyeAngles(owner, ang);
	GetAngleVectors(ang, dir, NULL_VECTOR, NULL_VECTOR);
	for (int k = 0; k < 3; k++)
		end[k] = eye[k] + dir[k] * 8192.0;
	Handle tr = TR_TraceRayFilterEx(eye, end, MASK_SHOT, RayType_EndPoint, Filter_NotSelf, owner);
	TR_GetEndPosition(end, tr);
	delete tr;
	float pos[3], vel[3], want[3];
	GetEntPropVector(r, Prop_Data, "m_vecAbsOrigin", pos);
	GetEntPropVector(r, Prop_Data, "m_vecAbsVelocity", vel);
	float speed = GetVectorLength(vel);
	if (speed < 1.0)
		return;
	MakeVectorFromPoints(pos, end, want);
	if (GetVectorLength(want) < 16.0)
		return;
	NormalizeVector(want, want);
	NormalizeVector(vel, vel);
	float t = g_cvQuadTurn.FloatValue * dt;
	if (t > 1.0)
		t = 1.0;
	for (int k = 0; k < 3; k++)
		vel[k] += (want[k] - vel[k]) * t;
	NormalizeVector(vel, vel);
	float newAng[3];
	GetVectorAngles(vel, newAng);
	ScaleVector(vel, speed);
	TeleportEntity(r, NULL_VECTOR, newAng, vel);
}

public bool Filter_NotSelf(int entity, int mask, any client)
{
	return entity != client;
}

public void OnPlayerRunCmdPost(int client, int buttons, int impulse, const float vel[3], const float angles[3], int weapon, int subtype, int cmdnum, int tickcount, int seed, const int mouse[2])
{
	bool atk2 = (buttons & IN_ATTACK2) != 0;
	bool edge = atk2 && !g_bAtk2[client];
	g_bAtk2[client] = atk2;
	if (!g_cvEnable.BoolValue || !IsPlayerAlive(client))
		return;
	int w = GetEntPropEnt(client, Prop_Send, "m_hActiveWeapon");
	if (WeaponKind(w) != KIND_QUAD)
		return;
	int clip = GetEntProp(w, Prop_Send, "m_iClip1");
	if (EntRefToEntIndex(g_iQuadWeapon[client]) != w)
	{
		g_iQuadWeapon[client] = EntIndexToEntRef(w);
		g_iShots[client] = 0;
		g_iClip[client] = clip;
	}
	// OF resets the radius increase when a reload starts.
	bool reloading = HasEntProp(w, Prop_Send, "m_iReloadMode") && GetEntProp(w, Prop_Send, "m_iReloadMode") != 0;
	if (reloading || clip > g_iClip[client])
		g_iShots[client] = 0;
	g_iClip[client] = clip;
	if (edge && g_cvQuadToggle.BoolValue)
	{
		g_bQuadOff[client] = !g_bQuadOff[client];
		PrintCenterText(client, g_bQuadOff[client] ? "Homing OFF" : "Homing ON");
		Dbg("quad homing %s for %N", g_bQuadOff[client] ? "off" : "on", client);
	}
	float now = GetGameTime();
	if (!g_bQuadOff[client] && g_cvQuadHoming.BoolValue && g_cvQuadPing.BoolValue && now >= g_flPing[client])
	{
		g_flPing[client] = now + 1.0;
		EmitSoundToAll(QUAD_PING_SOUND, client, SNDCHAN_STATIC, 95);
	}
}

public void OnClientDisconnect(int client)
{
	g_bQuadOff[client] = false;
	g_iShots[client] = 0;
	g_iQuadWeapon[client] = 0;
}
