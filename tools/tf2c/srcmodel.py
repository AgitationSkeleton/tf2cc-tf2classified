"""Read-only Source model (MDL v48 / VVD v4 / VTX v7, SDK 2013) loader for CustomSlop research.

load(mdl_path) -> Model with
  .mdl (bytes), .vvd (bytes), .vtx (bytes), header fields, bones, attachments, textures,
  cdmaterials, skins, bodyparts -> models -> meshes, and LOD0 geometry:
  .verts (N,3) model-space bind-pose positions in *file* order of the VVD,
  .normals, .uvs, .bone_ids, .weights, .nbones
  .tris  list of (mesh material index, (M,3) int array of VVD vertex indices)
Only what CustomSlop needs; everything is little-endian, offsets per the SDK 2013 headers
(studio.h, optimize.h).
"""
import os
import struct

import numpy as np

BONE_SIZE = 216
ATTACH_SIZE = 92
MODEL_SIZE = 148
MESH_SIZE = 116
TEX_SIZE = 64
SEQ_SIZE = 212
HITBOX_SIZE = 68


def i32(b, o):
    return struct.unpack_from("<i", b, o)[0]


def cstr(b, o):
    if o <= 0 or o >= len(b):
        return ""
    return b[o:b.find(b"\0", o)].decode("latin-1")


class Model:
    pass


def vtx_path(mdl_path):
    base = mdl_path[:-4]
    for ext in (".dx90.vtx", ".vtx", ".dx80.vtx", ".sw.vtx"):
        if os.path.exists(base + ext):
            return base + ext
    raise FileNotFoundError(base + ".dx90.vtx")


def load(mdl_path):
    m = Model()
    m.path = mdl_path
    b = m.mdl = open(mdl_path, "rb").read()
    assert b[:4] == b"IDST", "not an MDL"
    m.version, m.checksum = i32(b, 4), i32(b, 8)
    m.name = b[12:76].split(b"\0")[0].decode("latin-1")
    m.length = i32(b, 76)
    m.hull = np.array(struct.unpack_from("<6f", b, 104)).reshape(2, 3)
    m.view_bb = np.array(struct.unpack_from("<6f", b, 128)).reshape(2, 3)
    m.flags = i32(b, 152)
    # bones
    m.bones = []
    nb, bi = i32(b, 156), i32(b, 160)
    for k in range(nb):
        o = bi + k * BONE_SIZE
        p2b = np.eye(4)
        p2b[:3] = np.array(struct.unpack_from("<12f", b, o + 96)).reshape(3, 4)
        m.bones.append(dict(off=o, name=cstr(b, o + i32(b, o)), parent=i32(b, o + 4),
                            pos=np.array(struct.unpack_from("<3f", b, o + 32)),
                            quat=np.array(struct.unpack_from("<4f", b, o + 44)), p2b=p2b))
    # attachments
    m.attachments = []
    na, ai = i32(b, 240), i32(b, 244)
    for k in range(na):
        o = ai + k * ATTACH_SIZE
        loc = np.eye(4)
        loc[:3] = np.array(struct.unpack_from("<12f", b, o + 12)).reshape(3, 4)
        m.attachments.append(dict(off=o, name=cstr(b, o + i32(b, o)), bone=i32(b, o + 8), local=loc))
    # textures / cdmaterials / skins
    nt, ti = i32(b, 204), i32(b, 208)
    m.textures = [cstr(b, ti + k * TEX_SIZE + i32(b, ti + k * TEX_SIZE)) for k in range(nt)]
    ncd, cdi = i32(b, 212), i32(b, 216)
    m.cdmaterials = [cstr(b, i32(b, cdi + 4 * k)) for k in range(ncd)]
    nsr, nsf, si = i32(b, 220), i32(b, 224), i32(b, 228)
    m.skins = [list(struct.unpack_from("<%dh" % nsr, b, si + f * nsr * 2)) for f in range(nsf)]
    # sequences (bbox)
    ns, sqi = i32(b, 188), i32(b, 192)
    m.seq_offsets = [sqi + k * SEQ_SIZE for k in range(ns)]
    # hitboxes
    m.hitboxes = []
    nhs, hsi = i32(b, 172), i32(b, 176)
    for s in range(nhs):
        so = hsi + s * 12
        nh, hi = i32(b, so + 4), i32(b, so + 8)
        for h in range(nh):
            ho = so + hi + h * HITBOX_SIZE
            m.hitboxes.append(dict(off=ho, bone=i32(b, ho),
                                   bb=np.array(struct.unpack_from("<6f", b, ho + 8)).reshape(2, 3)))
    # bodyparts / models / meshes
    m.bodyparts = []
    nbp, bpi = i32(b, 232), i32(b, 236)
    for k in range(nbp):
        o = bpi + k * 16
        bp = dict(name=cstr(b, o + i32(b, o)), models=[])
        nmod, mi = i32(b, o + 4), i32(b, o + 12)
        for j in range(nmod):
            mo = o + mi + j * MODEL_SIZE
            md = dict(off=mo, name=b[mo:mo + 64].split(b"\0")[0].decode("latin-1"),
                      radius=struct.unpack_from("<f", b, mo + 68)[0],
                      nverts=i32(b, mo + 80), vstart=i32(b, mo + 84) // 48, meshes=[])
            nme, mei = i32(b, mo + 72), i32(b, mo + 76)
            for q in range(nme):
                eo = mo + mei + q * MESH_SIZE
                md["meshes"].append(dict(off=eo, material=i32(b, eo), nverts=i32(b, eo + 8),
                                         voff=i32(b, eo + 12)))
            bp["models"].append(md)
        m.bodyparts.append(bp)
    # VVD
    v = m.vvd = open(mdl_path[:-4] + ".vvd", "rb").read()
    assert v[:4] == b"IDSV"
    m.vvd_checksum = i32(v, 8)
    m.vvd_nlods = i32(v, 12)
    m.vvd_lodverts = struct.unpack_from("<8i", v, 16)
    nfix, fixstart, vstart, tstart = i32(v, 48), i32(v, 52), i32(v, 56), i32(v, 60)
    m.vvd_vstart, m.vvd_tstart = vstart, tstart
    nraw = (tstart - vstart) // 48 if tstart > vstart else (len(v) - vstart) // 48
    raw = np.frombuffer(v, dtype=np.uint8, count=nraw * 48, offset=vstart).reshape(nraw, 48)
    m.nraw = nraw
    m.raw_weights = raw[:, 0:12].copy().view("<f4").reshape(nraw, 3)
    m.raw_bones = raw[:, 12:15].astype(int)
    m.raw_nb = raw[:, 15].astype(int)
    m.raw_pos = raw[:, 16:28].copy().view("<f4").reshape(nraw, 3).astype(np.float64)
    m.raw_nrm = raw[:, 28:40].copy().view("<f4").reshape(nraw, 3).astype(np.float64)
    m.raw_uv = raw[:, 40:48].copy().view("<f4").reshape(nraw, 2).astype(np.float64)
    m.raw_tan = np.frombuffer(v, dtype="<f4", count=nraw * 4, offset=tstart).reshape(nraw, 4).astype(np.float64) \
        if tstart else None
    # LOD0 logical -> raw index map (fixups)
    if nfix:
        lod0 = []
        for f in range(nfix):
            lod, src, cnt = struct.unpack_from("<3i", v, fixstart + 12 * f)
            if lod >= 0:
                lod0.extend(range(src, src + cnt))
        m.lod0_map = np.array(lod0, dtype=int)
    else:
        m.lod0_map = np.arange(m.vvd_lodverts[0])
    m.nfixups = nfix
    # VTX LOD0 triangles
    m.vtx_file = vtx_path(mdl_path)
    x = m.vtx = open(m.vtx_file, "rb").read()
    m.vtx_version, m.vtx_checksum = i32(x, 0), i32(x, 16)
    nbpx, bpox = i32(x, 28), i32(x, 32)
    m.tris = []
    for k in range(nbpx):
        bo = bpox + k * 8
        nmod, moff = i32(x, bo), i32(x, bo + 4)
        for j in range(nmod):
            mo = bo + moff + j * 8
            nlod, loff = i32(x, mo), i32(x, mo + 4)
            md = m.bodyparts[k]["models"][j]
            if nlod == 0:
                continue
            lo = mo + loff  # LOD 0
            nmesh, meoff = i32(x, lo), i32(x, lo + 4)
            for q in range(nmesh):
                eo = lo + meoff + q * 9
                nsg, sgoff = i32(x, eo), i32(x, eo + 4)
                mesh = md["meshes"][q]
                for g in range(nsg):
                    go = eo + sgoff + g * 25
                    nv, vo, ni, io_, nst, sto = struct.unpack_from("<6i", x, go)
                    vid = np.frombuffer(x, dtype=np.uint8, count=nv * 9, offset=go + vo).reshape(nv, 9)
                    orig = vid[:, 4].astype(int) | (vid[:, 5].astype(int) << 8)
                    idx = np.frombuffer(x, dtype="<u2", count=ni, offset=go + io_).astype(int)
                    for s in range(nst):
                        so = go + sto + s * 27
                        sni, sio = i32(x, so), i32(x, so + 4)
                        sflags = x[so + 18]
                        ii = idx[sio:sio + sni]
                        logical = md["vstart"] + mesh["voff"] + orig[ii]
                        if sflags & 2:  # strip
                            t = [(logical[a], logical[a + 1], logical[a + 2]) if a % 2 == 0 else
                                 (logical[a + 1], logical[a], logical[a + 2]) for a in range(len(logical) - 2)]
                            t = np.array(t, dtype=int)
                        else:
                            t = logical.reshape(-1, 3)
                        m.tris.append((mesh["material"], m.lod0_map[t]))
    return m


def quat_to_mat(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def rest_world(m):
    W = []
    for bo in m.bones:
        L = np.eye(4)
        L[:3, :3] = quat_to_mat(bo["quat"])
        L[:3, 3] = bo["pos"]
        W.append(L if bo["parent"] < 0 else W[bo["parent"]] @ L)
    return W


def summary(m):
    allt = np.concatenate([t for _, t in m.tris]) if m.tris else np.zeros((0, 3), int)
    return dict(name=m.name, version=m.version, checksum=m.checksum, vvd_checksum=m.vvd_checksum,
                vtx_checksum=m.vtx_checksum, vtx_version=m.vtx_version, nraw=m.nraw,
                lodverts=m.vvd_lodverts[:m.vvd_nlods], nfixups=m.nfixups, bones=len(m.bones),
                attachments=[a["name"] for a in m.attachments], textures=m.textures,
                cdmaterials=m.cdmaterials, ntris_lod0=int(len(allt)),
                hull=m.hull.tolist(), view_bb=m.view_bb.tolist(),
                vert_bounds=[m.raw_pos.min(0).tolist(), m.raw_pos.max(0).tolist()],
                max_tri_index=int(allt.max()) if len(allt) else -1)


if __name__ == "__main__":
    import json
    import sys
    print(json.dumps(summary(load(sys.argv[1])), indent=1))
