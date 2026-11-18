#!/usr/bin/env python3
"""Akimbo stock pistols for the TF2 Classified Mercenary (called by gen_schema.py).

A Merc holding a stock TF2C pistol who picks up another one gets tf2cc_merc_akimbo_stock: Open
Fortress's akimbo (tf2cc_merc_akimbo: its viewmodel animations, third-person set, stats) with the
stock TF2C pistol in both hands. "Stock pistol" = the three items that are the TF2C stock pistol:
22 (Engineer) and 23 (Scout), both prefab weapon_pistol (tf_weapon_pistol, w_pistol.mdl,
v_pistol_engineer/_scout.mdl: the same pistol.smd + mag.smd mesh, bones and rest poses), and
30200 tf2cc_merc_pistol_4rdm, the old TF2 Classic Merc's spawn pistol ("Pistol (TF2 Classic)" in
!mercprefs: TF2C stock pistol stats, v_pistol_4rdm.mdl = the same mesh with the same pistol_improved /
v_pistol materials, weapon_bone/v_slide/v_hammer/v_mag rest poses). The OF P38 (30105) is a
different gun (its own mesh, OF's v_pistol_merc textures) and keeps OF's own akimbo.

Models (new paths under models/tf2cc/akimbo_stock/; nothing existing is overwritten):

* viewmodel: OF's v_akimbo_pistols_mercenary.mdl kept whole (skeleton, every sequence and
  animation, IK, events, hitboxes) with its two P38 meshes replaced by the stock pistol mesh
  (TF2C's v_pistol_engineer LOD0, both bodyparts). Both rigs use the same weapon_bone convention
  (grip at the origin, +Y up, +Z along the barrel; P38 slide / stock slide both recoil along -Z),
  so the stock pistol takes the P38's place unchanged in each weapon_bone_R/_L frame. Bones:
  weapon_bone, v_trigger -> weapon_bone_X; v_slide -> slide_X; v_hammer -> hammer_X; v_mag,
  mag_bullet -> mag_X; v_cover (moves 1.22 u while the slide moves 2.73 u in the stock fire)
  -> slide_X 0.447 + weapon_bone_X 0.553 (a pure translation along the slide axis blends exactly).
  The slide translates only, so OF's slide tracks (2.07 u recoil, locked back in the reload)
  move the stock slide correctly wherever the bone sits; hammer_X and mag_X rotate, so their
  pivots move to the stock v_hammer / v_mag rest positions (bone pos + poseToBone + the linear
  bone table; their tracks are delta tracks, ANIMPOS on rest or none, so the motion is kept).
  The muzzle / eject_brass attachments ride on OF's animated muzzle_attach / eject_attach bones:
  their offsets move from the P38's muzzle/port to the stock pistol's (fire frame of the event).
  The P38-only sound events become the stock pistol's scripts (Weapon_Pistol.ClipOut/ClipIn/
  SlideForward, all defined by TF2/TF2C). Four skin families (RED/BLU/GRN/YLW) that are the
  stock pistol's single family: TF2C's pistol has no team colours (the Merc arms carry them).
* world model: OF's w_pistol_akimbo.mdl (weapon_bone + weapon_bone_L, bonemerged to the Merc's
  hands) with the stock w_pistol mesh rigid on each; the muzzle / eject_brass attachments use the
  stock w_pistol's matrices on weapon_bone (OF hangs them on a root bone the tf2cc Merc player
  model does not have); OF's collision model (.phy) for dropped pickups.

The new geometry (VVD/VTX) is compiled with the SDK 2013 studiomdl from SMDs in OF's model space
and transplanted into OF's MDL (body parts, textures, cdmaterials, skins appended; vertex and
hardware-bone indices remapped to OF's bone order), so OF's animation data is never re-encoded.

Icon (HUD bucket + armory, the stock 512x512 DXT5 clamp format): TF2C's own pistol loadout icon
(vgui/loadout/weapons/pistol) twice, the second gun behind and up-left like OF's bucket_akimbo.

  python -I tools/tf2c/gen_akimbo_stock.py [--out DIR] [--preview DIR]
      builds the files into DIR (default tf2c/staging/tf2classified); --preview renders
      viewmodel frames (idle / fire / reload, with c_merc_arms) and the icon (needs the read-only
      CustomSlop renderer, <WORKDIR>/tf2c-customslop-research/tools).
"""
import copy
import hashlib
import os
import shutil
import struct
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import kv  # noqa: E402
import mdlanim as A  # noqa: E402
import srcmodel as S  # noqa: E402

OFG = r"<STEAMCMD>/sdk2013/open_fortress"
TF2C_VPK = r"<STEAMCMD>/tf2classified-1\tf2classified\vpks\tf2c_assets_dir.vpk"
STUDIOMDL = r"<STEAMCMD>/sdk2013_new/client/bin/studiomdl.exe"
VPKTOOL = os.path.join(ROOT, "tools", "vpktool.py")
STAGE = os.path.join(ROOT, "tf2c", "staging", "tf2classified")
CUSTOMSLOP = r"<WORKDIR>/tf2c-customslop-research/tools"

DEFINDEX = 30290               # 30290-30299: tf2cc akimbo stock pistols
ITEM = "tf2cc_merc_akimbo_stock"
WID = "merc_akimbo_stock"
MATCH = (22, 23, 30200)        # the stock TF2C pistol items that combine (see the docstring)
OF_AKIMBO = "tf2cc_merc_akimbo"
DIR = "models/tf2cc/akimbo_stock/"
VM_REL = DIR + "v_akimbo_stock_pistols.mdl"
WM_REL = DIR + "w_akimbo_stock_pistols.mdl"
ICON_REL = "tf2cc/akimbo_stock/icon_akimbo_stock_pistols"
OF_VM = OFG + "/models/weapons/v_models/v_akimbo_pistols_mercenary"
OF_WM = OFG + "/models/weapons/w_models/w_pistol_akimbo"
ST_VM = "models/weapons/v_models/v_pistol_engineer"
ST_WM = "models/weapons/w_models/w_pistol"
ST_ICON = "materials/vgui/loadout/weapons/pistol.vtf"
SOUNDS = {"single_shot": "Weapon_Pistol.Single", "burst": "Weapon_Pistol.SingleCrit",
          "reload": "Weapon_Pistol.WorldReload", "empty": "Weapon_Pistol.ClipEmpty"}
EVENT_SOUNDS = {"Weapon_Akimbo_Pistols.ClipOut": "Weapon_Pistol.ClipOut",
                "Weapon_Akimbo_Pistols.ClipIn": "Weapon_Pistol.ClipIn",
                "Weapon_Akimbo_Pistols.SlideForward": "Weapon_Pistol.SlideForward"}
COVER = 1.22 / 2.73            # v_cover / v_slide travel in the stock fire sequence
MODEL_EXT = (".mdl", ".vvd", ".dx90.vtx", ".phy")


def i32(b, o):
    return struct.unpack_from("<i", b, o)[0]


def vpk_cat(rel):
    r = subprocess.run([sys.executable, "-I", VPKTOOL, "cat", TF2C_VPK, rel], capture_output=True)
    if r.returncode or not r.stdout:
        raise SystemExit("not in the TF2C VPK: " + rel)
    return r.stdout


def stock_model(rel, tmp):
    for ext in (".mdl", ".vvd", ".dx90.vtx"):
        open(os.path.join(tmp, os.path.basename(rel) + ext), "wb").write(vpk_cat(rel + ext))
    return S.load(os.path.join(tmp, os.path.basename(rel) + ".mdl"))


def bone_index(m):
    return {b["name"]: k for k, b in enumerate(m.bones)}


def mesh_tris(m, bodypart):
    """LOD0 triangles (raw vertex indices) of model 0 of a body part, per texture name."""
    md = m.bodyparts[bodypart]["models"][0]
    if not md["nverts"]:
        return []
    raw = set(m.lod0_map[md["vstart"]:md["vstart"] + md["nverts"]].tolist())
    out = []
    for mat, t in m.tris:
        sel = np.array([v in raw for v in t[:, 0]], bool)
        if sel.any():
            out.append((m.textures[m.skins[0][mat]], t[sel]))
    return out


# --- geometry: SMD in OF model space, compiled by studiomdl ------------------------------------

def smd_triangles(lines, m, tris, xform, bonemap):
    """xform: 4x4 stock bone-space -> OF model space; bonemap(stock bone) -> [(OF bone, weight)]."""
    P = (np.c_[m.raw_pos, np.ones(m.nraw)] @ xform.T)[:, :3]
    N = m.raw_nrm @ xform[:3, :3].T
    for tex, t in tris:
        for tri in t:
            lines.append(tex)
            # Compiled models (VTX) keep their triangles clockwise; an SMD wants them counter-
            # clockwise: written as read, every face was inside out (2026-11-17 playtest; 0 of 3402
            # stock VTX faces agree with their normals in right-hand order).
            for v in tri[::-1]:
                links = {}
                for j in range(m.raw_nb[v]):
                    for ob, w in bonemap(m.bones[m.raw_bones[v, j]]["name"]):
                        links[ob] = links.get(ob, 0.0) + w * m.raw_weights[v, j]
                links = sorted(links.items(), key=lambda kv_: -kv_[1])
                p, n, uv = P[v], N[v], m.raw_uv[v]
                lines.append("%d %.6f %.6f %.6f %.6f %.6f %.6f %.6f %.6f %d %s" % (
                    links[0][0], p[0], p[1], p[2], n[0], n[1], n[2], uv[0], 1.0 - uv[1], len(links),
                    " ".join("%d %.6f" % (b, w) for b, w in links)))


def compile_donor(name, bones, bodies, cdmaterials, tmp):
    """bones: names (root bones at the origin; only the geometry and bone names are used);
    bodies: [(body name, smd triangle lines)]. Returns the compiled model's path."""
    src = os.path.join(tmp, "src_" + name)
    game = os.path.join(tmp, "game_" + name)
    os.makedirs(src)
    os.makedirs(os.path.join(game, "models"))
    open(os.path.join(game, "gameinfo.txt"), "w").write(
        '"GameInfo"\n{\n\tgame "tf2cc build"\n\tFileSystem\n\t{\n\t\tSteamAppId 243750\n\t\tSearchPaths\n\t\t{\n'
        '\t\t\tgame |gameinfo_path|.\n\t\t}\n\t}\n}\n')
    skel = ["version 1", "nodes"] + ['%d "%s" -1' % (k, b) for k, b in enumerate(bones)] + \
           ["end", "skeleton", "time 0"] + ["%d 0 0 0 0 0 0" % k for k in range(len(bones))] + ["end"]
    qc = ['$modelname "donor/%s.mdl"' % name]
    for body, tri in bodies:
        open(os.path.join(src, body + ".smd"), "w", newline="\n").write("\n".join(skel + ["triangles"] + tri + ["end"]) + "\n")
        qc.append('$body "%s" "%s.smd"' % (body, body))
    open(os.path.join(src, "idle.smd"), "w", newline="\n").write("\n".join(skel) + "\n")
    qc += ['$cdmaterials "%s"' % c for c in cdmaterials]
    qc += ['$sequence "idle" "idle.smd" fps 30']
    open(os.path.join(src, name + ".qc"), "w", newline="\n").write("\n".join(qc) + "\n")
    r = subprocess.run([STUDIOMDL, "-nop4", "-nox360", "-game", game, os.path.join(src, name + ".qc")],
                       capture_output=True, text=True, cwd=src)
    out = os.path.join(game, "models", "donor", name + ".mdl")
    if r.returncode != 0 or not os.path.exists(out):
        print(r.stdout[-3000:], r.stderr[-2000:])
        raise SystemExit("studiomdl failed for " + name)
    return out


# --- transplant ------------------------------------------------------------------------------

def align4(b):
    while len(b) % 4:
        b.append(0)


def put_str(b, s):
    o = len(b)
    b += s.encode("latin-1") + b"\0"
    return o


def transplant(base_mdl, donor, name, checksum, nfamilies=4):
    """OF MDL bytes with the donor's body parts, textures, cdmaterials and skins (nfamilies copies
    of the donor's family 0). Returns the new MDL bytes."""
    b = bytearray(base_mdl)
    d = donor.mdl
    align4(b)
    # body parts -> models -> meshes, laid out contiguously
    nbp, bpi = i32(d, 232), i32(d, 236)
    bp_abs = len(b)
    b += b"\0" * (16 * nbp)
    model_abs, mesh_abs = [], []
    for k in range(nbp):
        o = bpi + 16 * k
        nmod, base, mi = i32(d, o + 4), i32(d, o + 8), i32(d, o + 12)
        ma = len(b)
        model_abs.append(ma)
        b += b"\0" * (148 * nmod)
        struct.pack_into("<iiii", b, bp_abs + 16 * k, 0, nmod, base, ma - (bp_abs + 16 * k))
        for j in range(nmod):
            mo = o + mi + 148 * j
            dst = ma + 148 * j
            b[dst:dst + 148] = d[mo:mo + 148]
            nme, mei = i32(d, mo + 72), i32(d, mo + 76)
            mea = len(b)
            b += b"\0" * (116 * nme)
            struct.pack_into("<i", b, dst + 76, (mea - dst) if nme else 0)
            struct.pack_into("<iiii", b, dst + 92, 0, 0, 0, 0)    # attachments, eyeballs: none
            # runtime pointers (studiomdl leaves its own memory addresses there): zero them so
            # the output is byte-identical between builds (a published path never changes content)
            struct.pack_into("<ii", b, dst + 108, 0, 0)       # vertexdata.pVertexData / pTangentData
            for q in range(nme):
                eo = mo + mei + 116 * q
                md = mea + 116 * q
                b[md:md + 116] = d[eo:eo + 116]
                struct.pack_into("<i", b, md + 4, dst - md)       # modelindex (back to the model)
                struct.pack_into("<ii", b, md + 16, 0, 0)         # numflexes, flexindex
                struct.pack_into("<i", b, md + 48, 0)             # vertexdata.modelvertexdata (runtime)
    for k in range(nbp):
        o = bpi + 16 * k
        so = put_str(b, S.cstr(d, o + i32(d, o)))
        struct.pack_into("<i", b, bp_abs + 16 * k, so - (bp_abs + 16 * k))
    align4(b)
    # textures
    nt, ti = i32(d, 204), i32(d, 208)
    tex_abs = len(b)
    b += b"\0" * (64 * nt)
    for k in range(nt):
        o = ti + 64 * k
        struct.pack_into("<i", b, tex_abs + 64 * k + 4, i32(d, o + 4))        # flags
    for k in range(nt):
        o = ti + 64 * k
        so = put_str(b, S.cstr(d, o + i32(d, o)))
        struct.pack_into("<i", b, tex_abs + 64 * k, so - (tex_abs + 64 * k))
    align4(b)
    # cdmaterials (offsets from the header)
    ncd, cdi = i32(d, 212), i32(d, 216)
    cd_abs = len(b)
    b += b"\0" * (4 * ncd)
    for k in range(ncd):
        so = put_str(b, S.cstr(d, i32(d, cdi + 4 * k)))
        struct.pack_into("<i", b, cd_abs + 4 * k, so)
    align4(b)
    # skins
    nsr = i32(d, 220)
    fam0 = struct.unpack_from("<%dh" % nsr, d, i32(d, 228))
    sk_abs = len(b)
    for _ in range(nfamilies):
        b += struct.pack("<%dh" % nsr, *fam0)
    align4(b)
    struct.pack_into("<ii", b, 204, nt, tex_abs)
    struct.pack_into("<ii", b, 212, ncd, cd_abs)
    struct.pack_into("<iii", b, 220, nsr, nfamilies, sk_abs)
    struct.pack_into("<ii", b, 232, nbp, bp_abs)
    # name (header + studiohdr2 long name), checksum, length
    nm = name.encode("latin-1")
    assert len(nm) < 64
    b[12:76] = nm.ljust(64, b"\0")
    h2 = i32(b, 400)
    if h2:
        so = put_str(b, name)
        struct.pack_into("<i", b, h2 + 20, so - h2)
    struct.pack_into("<i", b, 8, checksum)
    struct.pack_into("<i", b, 76, len(b))
    return b


def remap_vvd(vvd, remap, checksum):
    v = bytearray(vvd)
    struct.pack_into("<i", v, 8, checksum)
    vstart, tstart = i32(v, 56), i32(v, 60)
    n = ((tstart if tstart > vstart else len(v)) - vstart) // 48
    for k in range(n):
        o = vstart + 48 * k
        for j in range(v[o + 15]):
            v[o + 12 + j] = remap[v[o + 12 + j]]
    return bytes(v)


def remap_vtx(vtx, remap, checksum):
    x = bytearray(vtx)
    struct.pack_into("<i", x, 16, checksum)
    nbp, bpo = i32(x, 28), i32(x, 32)
    n = 0
    for k in range(nbp):
        bo = bpo + 8 * k
        nmod, moff = i32(x, bo), i32(x, bo + 4)
        for j in range(nmod):
            mo = bo + moff + 8 * j
            nlod, loff = i32(x, mo), i32(x, mo + 4)
            for lod in range(nlod):
                lo = mo + loff + 12 * lod
                nmesh, meoff = i32(x, lo), i32(x, lo + 4)
                for q in range(nmesh):
                    eo = lo + meoff + 9 * q
                    nsg, sgoff = i32(x, eo), i32(x, eo + 4)
                    for g in range(nsg):
                        go = eo + sgoff + 25 * g
                        nst, sto = i32(x, go + 16), i32(x, go + 20)
                        for s in range(nst):
                            so = go + sto + 27 * s
                            nch, cho = i32(x, so + 19), i32(x, so + 23)
                            for c in range(nch):
                                co = so + cho + 8 * c
                                struct.pack_into("<i", x, co + 4, remap[i32(x, co + 4)])
                                n += 1
    return bytes(x), n


def set_bone_rest(b, m, bone, pos):
    """Move a bone's rest position (bone table + linear bone table) and its poseToBone."""
    W = S.rest_world(m)
    par = m.bones[bone]["parent"]
    L = np.eye(4)
    L[:3, :3] = S.quat_to_mat(m.bones[bone]["quat"])
    L[:3, 3] = pos
    Wn = (W[par] @ L) if par >= 0 else L
    p2b = np.linalg.inv(Wn)[:3, :4]
    bo = m.bones[bone]["off"]
    struct.pack_into("<3f", b, bo + 32, *pos)
    struct.pack_into("<12f", b, bo + 96, *p2b.ravel())
    h2 = i32(b, 400)
    lb = i32(b, h2 + 16) if h2 else 0
    if lb:
        lo = h2 + lb
        nb = i32(b, lo)
        assert nb == len(m.bones)
        posi, p2bi = i32(b, lo + 12), i32(b, lo + 24)
        struct.pack_into("<3f", b, lo + posi + 12 * bone, *pos)
        struct.pack_into("<12f", b, lo + p2bi + 48 * bone, *p2b.ravel())
    return Wn


def move_attachment(b, m, name, delta_bone_local):
    for a in m.attachments:
        if a["name"].lower() == name:
            t = a["local"][:3, 3] + delta_bone_local
            struct.pack_into("<f", b, a["off"] + 12 + 12, t[0])
            struct.pack_into("<f", b, a["off"] + 12 + 28, t[1])
            struct.pack_into("<f", b, a["off"] + 12 + 44, t[2])
            return t
    raise KeyError(name)


def rename_events(b, m):
    n = 0
    for s in A.sequences(m):
        so = s["off"]
        ne, ei = i32(b, so + 24), i32(b, so + 28)
        for e in range(ne):
            eo = so + ei + 80 * e
            if i32(b, eo + 4) != 5004:
                continue
            opt = bytes(b[eo + 12:eo + 76]).split(b"\0")[0].decode("latin-1")
            new = EVENT_SOUNDS.get(opt)
            if new:
                b[eo + 12:eo + 76] = new.encode("latin-1").ljust(64, b"\0")
                n += 1
    return n


def checksum_of(*parts):
    h = hashlib.sha1()
    for p in parts:
        h.update(p if isinstance(p, bytes) else p.encode())
    return struct.unpack("<i", h.digest()[:4])[0]


def finish(base_path, donor_path, rel, out_root, report, edit=None, phy=None):
    """Transplant donor geometry into the base model, write <rel> (.mdl/.vvd/.dx90.vtx[/.phy])."""
    base = S.load(base_path + ".mdl")
    donor = S.load(donor_path)
    names = bone_index(base)
    remap = list(range(256))
    for k, bo in enumerate(donor.bones):
        remap[k] = names[bo["name"]]
    inv = {remap[k]: k for k in range(len(donor.bones))}
    dvvd = open(donor_path[:-4] + ".vvd", "rb").read()
    dvtx = open(donor_path[:-4] + ".dx90.vtx", "rb").read()
    cs = checksum_of(base.mdl, dvvd, dvtx, rel)
    b = transplant(base.mdl, donor, rel[len("models/"):], cs)
    notes = edit(b, base) if edit else []
    struct.pack_into("<i", b, 76, len(b))
    vvd = remap_vvd(dvvd, remap, cs)
    vtx, nch = remap_vtx(dvtx, remap, cs)
    dst = os.path.join(out_root, rel[:-4])
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst + ".mdl", "wb").write(bytes(b))
    open(dst + ".vvd", "wb").write(vvd)
    open(dst + ".dx90.vtx", "wb").write(vtx)
    files = [rel[:-4] + e for e in (".mdl", ".vvd", ".dx90.vtx")]
    if phy:
        p = bytearray(open(phy, "rb").read())
        struct.pack_into("<i", p, 12, cs)        # phyheader_t: size, id, solidCount, checkSum
        open(dst + ".phy", "wb").write(bytes(p))
        files.append(rel[:-4] + ".phy")
    # self-check: the written model loads, its VVD positions are the SMD's, bone ids are OF's
    chk = S.load(dst + ".mdl")
    used = set(chk.raw_bones[chk.raw_weights > 0].ravel().tolist())
    assert np.allclose(chk.raw_pos, donor.raw_pos), "VVD positions changed"
    assert all(chk.bones[u]["name"] == donor.bones[inv[u]]["name"] for u in used)
    report.append("  %s: %d verts, %d tris, bones %s, %d bone-state changes remapped, checksum %08x%s" % (
        rel, chk.nraw, sum(len(t) for _, t in chk.tris), sorted(chk.bones[u]["name"] for u in used), nch,
        cs & 0xFFFFFFFF, ("; " + "; ".join(notes)) if notes else ""))
    return files


# --- the two models -------------------------------------------------------------------------

def build_viewmodel(out_root, tmp, report):
    of = S.load(OF_VM + ".mdl")
    st = stock_model(ST_VM, tmp)
    oi, si = bone_index(of), bone_index(st)
    Ro, Rs = S.rest_world(of), S.rest_world(st)
    bones = ["weapon_bone_R", "slide_R", "hammer_R", "mag_R", "weapon_bone_L", "slide_L", "hammer_L", "mag_L"]
    di = {b: k for k, b in enumerate(bones)}
    bodies = []
    for side in ("R", "L"):
        def bonemap(n, side=side):
            wb, sl = di["weapon_bone_" + side], di["slide_" + side]
            return {"v_slide": [(sl, 1.0)], "v_hammer": [(di["hammer_" + side], 1.0)],
                    "v_mag": [(di["mag_" + side], 1.0)], "mag_bullet": [(di["mag_" + side], 1.0)],
                    "v_cover": [(sl, COVER), (wb, 1.0 - COVER)]}.get(n, [(wb, 1.0)])
        xf = Ro[oi["weapon_bone_" + side]] @ np.linalg.inv(Rs[si["weapon_bone"]])
        tri = []
        for bp in range(len(st.bodyparts)):
            smd_triangles(tri, st, mesh_tris(st, bp), xf, bonemap)
        bodies.append(("pistol_" + side, tri))
    donor = compile_donor("vm", bones, bodies, ["models\\weapons\\v_pistol_improved\\", "models\\weapons\\v_pistol\\"], tmp)

    def edit(b, m):
        notes = []
        W = S.rest_world(m)
        for side in ("R", "L"):
            wb = Ro[oi["weapon_bone_" + side]]
            for ob, sb in (("hammer_", "v_hammer"), ("mag_", "v_mag")):
                k = oi[ob + side]
                # the stock pivot in the stock weapon_bone frame == in OF's weapon_bone_X frame
                piv = (np.linalg.inv(Rs[si["weapon_bone"]]) @ Rs[si[sb]])[:3, 3]
                par = m.bones[k]["parent"]
                pos = (np.linalg.inv(W[par]) @ wb @ np.r_[piv, 1.0])[:3]
                set_bone_rest(b, m, k, pos)
                notes.append("%s%s pivot %s -> %s" % (ob, side, np.round(m.bones[k]["pos"], 2).tolist(), np.round(pos, 2).tolist()))
        # attachments: the P38's muzzle/port -> the stock pistol's, at the fire event frame of the
        # left gun's fire sequence (ACT_VM_PRIMARYATTACK, the one TF2C plays); OF's animated
        # muzzle_attach/eject_attach keep the same orientation to the firing gun in both fire sequences
        seq = A.find(m, "fire_left")
        f = int(round(seq["events"][0][0] * (seq["frames"] - 1))) if seq["events"] else 2
        Wf = A.world_pose(m, seq, f)
        wbL = Wf[oi["weapon_bone_L"]]
        st_att = {a["name"].lower(): a["local"][:3, 3] for a in st.attachments}
        for att, bone in (("muzzle", "muzzle_attach"), ("eject_brass", "eject_attach")):
            a = next(x for x in m.attachments if x["name"].lower() == att)
            Wa = Wf[oi[bone]]
            cur = (np.linalg.inv(wbL) @ Wa @ np.r_[a["local"][:3, 3], 1.0])[:3]
            delta = st_att[att] - cur
            t = move_attachment(b, m, att, (np.linalg.inv(Wa)[:3, :3] @ wbL[:3, :3]) @ delta)
            notes.append("%s %s -> %s (gun frame)" % (att, np.round(cur, 2).tolist(), np.round(st_att[att], 2).tolist()))
        notes.append("%d sound events -> stock pistol scripts" % rename_events(b, m))
        return notes
    return finish(OF_VM, donor, VM_REL, out_root, report, edit)


def build_worldmodel(out_root, tmp, report):
    """Both guns rigid on weapon_bone / weapon_bone_L (bonemerged to the Merc's hands). The muzzle and
    eject_brass attachments move from OF's root-level "muzzle" bone (not in the tf2cc Merc player
    model, so it is not bonemerged and sits at the player's origin) to weapon_bone with the stock
    w_pistol's own attachment matrices: third-person flashes and brass come from the right gun."""
    of = S.load(OF_WM + ".mdl")
    st = stock_model(ST_WM, tmp)
    oi, si = bone_index(of), bone_index(st)
    Ro, Rs = S.rest_world(of), S.rest_world(st)
    bones = ["weapon_bone", "weapon_bone_L"]
    tri = []
    for k, wb in enumerate(bones):
        xf = Ro[oi[wb]] @ np.linalg.inv(Rs[si["weapon_bone"]])
        for bp in range(len(st.bodyparts)):
            smd_triangles(tri, st, mesh_tris(st, bp), xf, lambda n, k=k: [(k, 1.0)])
    donor = compile_donor("wm", bones, [("pistols", tri)], ["models\\weapons\\w_pistol1\\"], tmp)

    def edit(b, m):
        notes = []
        for att in ("muzzle", "eject_brass"):
            a = next(x for x in m.attachments if x["name"].lower() == att)
            sa = next(x for x in st.attachments if x["name"].lower() == att)
            assert st.bones[sa["bone"]]["name"] == "weapon_bone"
            struct.pack_into("<i", b, a["off"] + 8, oi["weapon_bone"])
            struct.pack_into("<12f", b, a["off"] + 12, *sa["local"][:3, :4].ravel())
            notes.append("%s: %s -> weapon_bone %s" % (att, m.bones[a["bone"]]["name"], np.round(sa["local"][:3, 3], 2).tolist()))
        return notes
    return finish(OF_WM, donor, WM_REL, out_root, report, edit, phy=OF_WM + ".phy")


# --- icon ------------------------------------------------------------------------------------

def icon_image():
    """TF2C's pistol loadout icon twice: a copy behind, up and to the left (OF bucket_akimbo)."""
    import dxt
    from PIL import Image, ImageEnhance
    data = vpk_cat(ST_ICON)
    w, h = struct.unpack_from("<HH", data, 16)
    assert struct.unpack_from("<i", data, 52)[0] == 15
    img = Image.fromarray(dxt.decode(data[len(data) - w * h:], w, h, 15), "RGBA")
    bb = img.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    gun = img.crop(bb)
    back = ImageEnhance.Brightness(gun).enhance(0.72)
    dx, dy = int(gun.width * 0.30), int(gun.height * 0.22)
    pair = Image.new("RGBA", (gun.width + dx, gun.height + dy), (0, 0, 0, 0))
    pair.alpha_composite(back, (0, 0))
    pair.alpha_composite(gun, (dx, dy))
    # the stock icon's gun spans about 0.40 x 0.40 of the square; the pair keeps the gun's scale
    # but fits within 0.86 of the frame
    s = min(1.0, 0.86 * 512 / max(pair.width, pair.height))
    pair = pair.resize((round(pair.width * s), round(pair.height * s)), Image.LANCZOS)
    out = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    out.alpha_composite(pair, ((512 - pair.width) // 2, (512 - pair.height) // 2))
    return out


def icon_vmt(rel):
    return ('"UnlitGeneric"\n{\n\t"$basetexture" "%s"\n\t"$translucent" "1"\n\t"$vertexcolor" "1"\n'
            '\t"$vertexalpha" "1"\n\t"$ignorez" "1"\n}\n' % rel)


def build_icon(out_root):
    import dxt
    img = icon_image()
    files = []
    path = os.path.join(out_root, "materials", ICON_REL + ".vtf")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").write(dxt.icon_vtf(np.asarray(img)))
    files.append("materials/" + ICON_REL + ".vtf")
    # materials/<image_inventory>[_large].vmt and their materials/vgui/ copies (gen_schema.write_icon_vmt)
    for base in ("materials/", "materials/vgui/"):
        for suffix in ("", "_large"):
            rel = base + ICON_REL + suffix + ".vmt"
            p = os.path.join(out_root, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "w", encoding="latin-1", newline="\n").write(icon_vmt(ICON_REL))
            files.append(rel)
    return files, img


# --- schema / plugin config -------------------------------------------------------------------

def stage(stage_root, report):
    """Build the models and the icon into stage_root; returns the staged paths."""
    report.append("\nakimbo stock pistols (gen_akimbo_stock.py):")
    tmp = tempfile.mkdtemp(prefix="akimbo_stock_")
    try:
        files = build_viewmodel(stage_root, tmp, report)
        files += build_worldmodel(stage_root, tmp, report)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    icon_files, _ = build_icon(stage_root)
    return files + icon_files


def build(items, report):
    """Add the schema item (a copy of tf2cc_merc_akimbo: class, slot, OF akimbo animations and
    stats, Merc arms, min_viewmodel_offset, kill icon) with the stock pistol's models, sounds and
    icon. Returns the weapons.cfg row (gen_schema.write_plugin_cfg)."""
    src = next((v for k, v in items.items() if isinstance(v, kv.KV) and v.get("name") == OF_AKIMBO), None)
    if src is None:
        raise SystemExit("gen_akimbo_stock: %s not in the schema" % OF_AKIMBO)
    names = {v.get("name"): k for k, v in items.items() if isinstance(v, kv.KV)}
    for d in MATCH:
        if str(d) not in items and d >= 30000:
            raise SystemExit("gen_akimbo_stock: matching item %d not in the schema" % d)
    e = copy.deepcopy(src)
    e.set("name", ITEM)
    e.set("item_name", "Akimbo Pistols (Classic)")
    e.set("model_player", VM_REL)
    e.set("model_world", WM_REL)
    e.set("image_inventory", ICON_REL)
    e.pairs = [(a, b) for a, b in e.pairs if a.lower() != "image_inventory_teamcolor"]
    vis = e.get("visuals")
    for t in ("single_shot", "burst", "reload", "empty", "double_shot", "special1"):
        vis.pairs = [(a, b) for a, b in vis.pairs if a.lower() != "sound_" + t]
    for t, s in SOUNDS.items():
        vis.set("sound_" + t, s)
    items.add(str(DEFINDEX), e)
    report.append("%-22s %-6d %-28s akimbo of %s (copy of %s); stats %s" % (
        WID, DEFINDEX, e.get("item_class"), "/".join(str(d) for d in MATCH), OF_AKIMBO,
        ", ".join("%s %s" % (a.get("attribute_class"), a.get("value")) for _, a in (e.get("attributes") or kv.KV()).blocks())))
    assert ITEM not in names
    return dict(wid=WID, defindex=str(DEFINDEX), slot=e.get("item_slot") or "secondary", kind="akimbo", weight="0",
                world=WM_REL, pref="", canonical="merc_akimbo", akimbo_from=" ".join(str(d) for d in MATCH))


# --- previews --------------------------------------------------------------------------------

def preview(out_root, dst):
    """Viewmodel frames (idle, fire_left, reload) with c_merc_arms bonemerged, and the icon."""
    sys.path.insert(0, CUSTOMSLOP)
    import types
    import vfs as VFS
    import vmrender as VR
    from PIL import Image, ImageDraw
    os.makedirs(dst, exist_ok=True)
    fs = VFS.VFS([("dir", out_root)] + VFS.DEFAULT_ORDER)
    ctx = types.SimpleNamespace(fs=fs)
    vm = S.load(os.path.join(out_root, VM_REL))
    tmp = tempfile.mkdtemp(prefix="akimbo_prev_")
    arms_rel = "models/weapons/c_models/c_merc_arms.mdl"
    for ext in (".mdl", ".vvd", ".dx90.vtx"):
        open(os.path.join(tmp, "arms" + ext), "wb").write(fs.read(arms_rel[:-4] + ext))
    arms = S.load(os.path.join(tmp, "arms.mdl"))
    names = bone_index(vm)
    vtex, vmat = VR.textures_for(ctx, vm, out_root), VR.materials_for(ctx, vm, out_root)
    atex, amat = VR.textures_for(ctx, arms, None), VR.materials_for(ctx, arms, None)
    shots = [("idle", 0), ("fire_left", 0), ("fire_left", 2), ("fire_left", 4), ("fire_left", 10),
             ("reload", 25), ("reload", 60), ("reload", 120), ("reload", 165), ("reload", 175)]
    tiles = []
    for seq, f in shots:
        W = A.world_pose(vm, seq, f)
        P, N = VR.skinned(vm, W)
        AW = VR.bonemerge(arms, names, W)
        AP, AN = VR.skinned(arms, AW)
        img = VR.raster([(P, N, vm.raw_uv, vm.tris, vtex), (AP, AN, arms.raw_uv, arms.tris, atex)],
                        (640, 360), mats_list=[vmat, amat])
        ImageDraw.Draw(img).text((8, 8), "%s frame %d" % (seq, f), fill=(255, 255, 0))
        img.save(os.path.join(dst, "vm_%s_%03d.png" % (seq, f)))
        tiles.append(img)
    sheet = Image.new("RGB", (640 * 2, 360 * ((len(tiles) + 1) // 2)))
    for k, t in enumerate(tiles):
        sheet.paste(t, (640 * (k % 2), 360 * (k // 2)))
    sheet.save(os.path.join(dst, "vm_sheet.png"))
    _, icon = build_icon(tempfile.mkdtemp(prefix="akimbo_icon_"))
    bg = Image.new("RGBA", icon.size, (60, 66, 74, 255))
    bg.alpha_composite(icon)
    bg.save(os.path.join(dst, "icon.png"))
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=STAGE)
    ap.add_argument("--preview")
    a = ap.parse_args()
    rep = []
    print("\n".join(stage(a.out, rep)))
    print("\n".join(rep))
    if a.preview:
        preview(a.out, a.preview)
