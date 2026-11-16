#!/usr/bin/env python3
"""Make TF2 Classified spin an Open Fortress minigun barrel about its own long axis.

TF2C 5205 (x64 client.dll, same code as the Source SDK 2013 TF2 client) spins a minigun barrel
two different ways:

  * view model  (C_TFViewModel::StandardBlendingRules, client.dll 0x1805ead50):
        bone = Studio_BoneIndexByName(hdr, "v_minigun_barrel")
        QuaternionAngles(q[bone], a);  a.x = GetBarrelRotation();  AngleQuaternion(a, q[bone]);
    -> the bone's RadianEuler ROLL is overwritten, i.e. the barrel turns about the bone's own
       local X axis (pitch/yaw of the animated pose are kept).
  * world model (C_TFMinigun::StandardBlendingRules, client.dll 0x1806702a0, bone "barrel"
    looked up in OnNewModel):
        AngleQuaternion(RadianEuler(0, 0, m_flBarrelAngle), q[bone]);
    -> the bone's local rotation is REPLACED by a pure rotation about local Z, so the rest
       rotation must be identity and the barrel must run along the parent's Z axis.

Stock TF2 obeys both: v_minigun_heavy's v_minigun_barrel mesh runs along the bone's local X,
c_minigun / w_minigun's "barrel" has an identity rest rotation and its mesh runs along local Z.
OF's v_minigun_dm builds the barrel along v_minigun_barrel's local *Z* (OF spins it itself), so
TF2C rolls it about local X, which is perpendicular to the barrel: it swings round like a
clock hand. OF's w_minigun_dm "barrel" already satisfies the world-model rule.

fix_minigun_barrel() re-frames the barrel bone without moving a single vertex at rest:
the bone's frame becomes F' = F * X (X = rotation C plus an origin shift t onto the real axis),
the bone's local pos/quat/rot/qAlignment take X, its poseToBone becomes X^-1 * poseToBone
(vertices in the .vvd are model space, skinned as boneToWorld * poseToBone * v), and anything
else expressed in the bone's frame (child bones, attachments) is pre-multiplied by X^-1.
The mstudiolinearbone_t copy (studiohdr2) is patched too. The bone name is NOT changed: the
view model code looks the bone up as "v_minigun_barrel"; renaming it would stop it spinning.

Only bones without animation tracks are re-framed (true for both OF minigun models); a bone
with tracks, or with hitboxes when a rotation is needed, is reported and left alone (hitboxes
just follow a pure origin shift, as on w_minigun_dm's barrel).

    fix_minigun_barrel(mdl_path, report) -> True if the file was changed
    python barrel_fix.py <model.mdl> [...]          patch in place + self-check
    python barrel_fix.py --check <model.mdl> [...]  self-check only (no writes)
"""
import math
import os
import struct
import sys

import numpy as np

BONE_SIZE = 216
ANIMDESC_SIZE = 100
ATTACH_SIZE = 92
SNAP_DEG = 3.0          # snap the measured mesh axis to a bone axis closer than this
CENTRE_EPS = 0.02       # origin shifts below this (units) are not worth applying
VM_BONE, WM_BONE = "v_minigun_barrel", "barrel"


# ---------------------------------------------------------------- Source mathlib (ports)
def quat_to_mat(q):
    x, y, z, w = (float(v) for v in q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def mat_to_quat(m):
    t = np.trace(m)
    if t > 0:
        s = math.sqrt(t + 1.0) * 2
        q = [(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, 0.25 * s]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        q = [0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s, (m[2, 1] - m[1, 2]) / s]
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        q = [(m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s, (m[0, 2] - m[2, 0]) / s]
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        q = [(m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s, (m[1, 0] - m[0, 1]) / s]
    q = np.array(q)
    if q[3] < 0:
        q = -q
    return q / np.linalg.norm(q)


def euler_to_mat(e):
    """AngleQuaternion(RadianEuler): x = roll about X, y = pitch about Y, z = yaw about Z,
    applied as Rz(yaw) * Ry(pitch) * Rx(roll)."""
    x, y, z = e
    cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return rz @ ry @ rx


def mat_to_euler(m):
    """QuaternionAngles -> MatrixAngles(matrix, RadianEuler&), incl. the gimbal-lock branch."""
    fwd, left, upz = m[:, 0], m[:, 1], m[2, 2]
    xy = math.hypot(fwd[0], fwd[1])
    if xy > 0.001:
        yaw = math.atan2(fwd[1], fwd[0])
        pitch = math.atan2(-fwd[2], xy)
        roll = math.atan2(left[2], upz)
    else:
        yaw = math.atan2(-left[0], left[1])
        pitch = math.atan2(-fwd[2], xy)
        roll = 0.0
    return np.array([roll, pitch, yaw])


def rigid(r, t):
    m = np.eye(4)
    m[:3, :3] = r
    m[:3, 3] = t
    return m


def inv_rigid(m):
    return rigid(m[:3, :3].T, -m[:3, :3].T @ m[:3, 3])


# ---------------------------------------------------------------- MDL / VVD access
def _i(b, o):
    return struct.unpack_from("<i", b, o)[0]


def _cstr(b, o):
    return b[o:b.find(b"\0", o)].decode("latin-1")


def read_bones(b):
    nb, bi = _i(b, 156), _i(b, 160)
    out = []
    for k in range(nb):
        o = bi + k * BONE_SIZE
        out.append(dict(off=o, name=_cstr(b, o + _i(b, o)), parent=_i(b, o + 4),
                        pos=np.array(struct.unpack_from("<3f", b, o + 32)),
                        quat=np.array(struct.unpack_from("<4f", b, o + 44)),
                        rot=np.array(struct.unpack_from("<3f", b, o + 60)),
                        p2b=rigid(np.eye(3), np.zeros(3)),
                        qalign=np.array(struct.unpack_from("<4f", b, o + 144))))
        out[-1]["p2b"][:3] = np.array(struct.unpack_from("<12f", b, o + 96)).reshape(3, 4)
    return out


def linear_bones(b):
    """(base offset, numbones, {field: absolute array offset}) of mstudiolinearbone_t or None."""
    h2 = _i(b, 400)
    if h2 <= 0 or h2 + 20 > len(b):
        return None
    lb = _i(b, h2 + 16)
    if lb <= 0:
        return None
    base = h2 + lb
    names = ("flags", "parent", "pos", "quat", "rot", "p2b", "posscale", "rotscale", "qalign")
    return base, _i(b, base), {n: base + _i(b, base + 4 + 4 * k) for k, n in enumerate(names)}


def animated_bones(b):
    """Set of bone indices that have a track in any local animation (sections included)."""
    na, ai = _i(b, 180), _i(b, 184)
    seen = set()
    for k in range(na):
        o = ai + k * ANIMDESC_SIZE
        nf, blk, idx, sidx, sfr = _i(b, o + 16), _i(b, o + 52), _i(b, o + 56), _i(b, o + 80), _i(b, o + 84)
        secs = [(blk, idx)]
        if sfr:
            secs = [(_i(b, o + sidx + s * 8), _i(b, o + sidx + s * 8 + 4)) for s in range(nf // sfr + 2)]
        for sb, sx in secs:
            if sb != 0:
                seen.add(-1)          # data in an external animblock: unknown, be safe
                continue
            p = o + sx
            for _ in range(10000):
                seen.add(b[p])
                nxt = struct.unpack_from("<h", b, p + 2)[0]
                if nxt == 0:
                    break
                p += nxt
    return seen


def read_vvd(path):
    v = open(path, "rb").read()
    if v[:4] != b"IDSV":
        raise ValueError("not a VVD: " + path)
    nv, vstart = _i(v, 16), _i(v, 56)
    raw = np.frombuffer(v, dtype=np.uint8, count=nv * 48, offset=vstart).reshape(nv, 48)
    w = raw[:, 0:12].copy().view("<f4").reshape(nv, 3)
    bones = raw[:, 12:15].astype(int)
    nb = raw[:, 15].astype(int)
    pos = raw[:, 16:28].copy().view("<f4").reshape(nv, 3).astype(float)
    return w, bones, nb, pos


def rest_world(B, local=None):
    """Bone-to-model matrices for the rest pose; local overrides {bone: 4x4 local}."""
    W = []
    for k, bo in enumerate(B):
        L = (local or {}).get(k)
        if L is None:
            L = rigid(quat_to_mat(bo["quat"]), bo["pos"])
        W.append(L if bo["parent"] < 0 else W[bo["parent"]] @ L)
    return W


def skin(B, W, vv, sel=None):
    """Skinned model-space vertex positions (boneToWorld * poseToBone, weighted)."""
    w, bones, nb, pos = vv
    if sel is not None:
        w, bones, nb, pos = w[sel], bones[sel], nb[sel], pos[sel]
    out = np.zeros_like(pos)
    ph = np.c_[pos, np.ones(len(pos))]
    for j in range(3):
        for k in np.unique(bones[:, j]):
            m = (bones[:, j] == k) & (nb > j)
            if not m.any():
                continue
            M = W[k] @ B[k]["p2b"]
            out[m] += w[m, j:j + 1] * (ph[m] @ M.T)[:, :3]
    return out


def rigid_mask(vv, k):
    w, bones, nb, _ = vv
    return (bones[:, 0] == k) & (w[:, 0] > 0.99)


# ---------------------------------------------------------------- mesh axis measurement
def barrel_geometry(B, vv, k):
    """Barrel long axis (unit, bone-local, pointing toward the muzzle half) and the point on
    that axis closest to the bone origin, from the vertices rigidly skinned to bone k."""
    pts = vv[3][rigid_mask(vv, k)]
    if len(pts) < 20:
        raise ValueError("bone %d has only %d rigid vertices" % (k, len(pts)))
    P = B[k]["p2b"]
    loc = pts @ P[:3, :3].T + P[:3, 3]
    c = loc.mean(0)
    ax = np.linalg.svd(loc - c)[2][0]
    if ax @ (c / (np.linalg.norm(c) + 1e-9)) < 0:
        ax = -ax
    snapped = None
    for j in range(3):
        for s in (1, -1):
            e = np.zeros(3)
            e[j] = s
            if math.degrees(math.acos(min(1.0, ax @ e))) < SNAP_DEG:
                snapped = e
    if snapped is not None:
        ax = snapped
    # centre: median of per-slice bounding-box centres in the plane normal to the axis
    u = np.cross(ax, [1, 0, 0] if abs(ax[0]) < 0.9 else [0, 1, 0])
    u /= np.linalg.norm(u)
    v = np.cross(ax, u)
    a, pu, pv = loc @ ax, loc @ u, loc @ v
    edges = np.linspace(a.min(), a.max(), 13)
    cents = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (a >= lo) & (a <= hi)
        if m.sum() >= 8:
            cents.append(((pu[m].max() + pu[m].min()) / 2, (pv[m].max() + pv[m].min()) / 2))
    cu, cv = np.median(np.array(cents), axis=0)
    centre = cu * u + cv * v
    return ax, centre, loc


# ---------------------------------------------------------------- code simulation
def spun_local(B, k, kind, theta):
    """Bone k's local matrix after TF2C's barrel code ran at angle theta (rest-pose input)."""
    bo = B[k]
    if kind == "vm":
        e = mat_to_euler(quat_to_mat(bo["quat"]))
        e[0] = theta
        r = euler_to_mat(e)
    else:
        r = euler_to_mat((0.0, 0.0, theta))
    return rigid(r, bo["pos"])


def spin_check(b, vv, kind, k):
    """Measure what TF2C's spin does to the barrel. Returns a dict of numbers."""
    B = read_bones(b)
    sel = rigid_mask(vv, k)
    ax, centre, _ = barrel_geometry(B, vv, k)
    W0 = rest_world(B)
    Fk = W0[k]
    mesh_axis = Fk[:3, :3] @ ax                       # model space
    mesh_pt = Fk[:3, :3] @ centre + Fk[:3, 3]
    base = skin(B, W0, vv, sel)
    angs, wob, dev = [], 0.0, 0.0
    for th in np.radians([30, 60, 90, 135, 180, 270]):
        W = rest_world(B, {k: spun_local(B, k, kind, th)})
        D = W[k] @ inv_rigid(W0[k])                 # model-space motion of the barrel
        rr = D[:3, :3]
        ang = math.acos(max(-1.0, min(1.0, (np.trace(rr) - 1) / 2)))
        w = np.array([rr[2, 1] - rr[1, 2], rr[0, 2] - rr[2, 0], rr[1, 0] - rr[0, 1]])
        if np.linalg.norm(w) > 1e-6:
            w /= np.linalg.norm(w)
            angs.append(math.degrees(math.acos(min(1.0, abs(w @ mesh_axis)))))
        moved = skin(B, W, vv, sel)
        # a spin about the barrel's own axis keeps every vertex at the same axial position
        # and radius; measure the worst deviation of that.
        rel0, rel1 = base - mesh_pt, moved - mesh_pt
        a0, a1 = rel0 @ mesh_axis, rel1 @ mesh_axis
        r0 = np.linalg.norm(rel0 - np.outer(a0, mesh_axis), axis=1)
        r1 = np.linalg.norm(rel1 - np.outer(a1, mesh_axis), axis=1)
        dev = max(dev, float(np.abs(a1 - a0).max()), float(np.abs(r1 - r0).max()))
        c0 = base.mean(0) - mesh_pt
        c1 = moved.mean(0) - mesh_pt
        wob = max(wob, float(np.linalg.norm((c1 - c0) - ((c1 - c0) @ mesh_axis) * mesh_axis)))
    off = Fk[:3, 3] - mesh_pt
    off_axis = float(np.linalg.norm(off - (off @ mesh_axis) * mesh_axis))
    return dict(axis_err_deg=max(angs) if angs else 0.0, max_vertex_dev=dev,
                centroid_wobble=wob, bone_origin_off_axis=off_axis,
                mesh_axis_model=np.round(mesh_axis, 4).tolist())


# ---------------------------------------------------------------- patching
def _put(b, off, fmt, vals):
    struct.pack_into(fmt, b, off, *[float(x) for x in vals])


def _write_bone(b, bo, lin, k, pos, quat, rot, p2b, qalign):
    o = bo["off"]
    _put(b, o + 32, "<3f", pos)
    _put(b, o + 44, "<4f", quat)
    _put(b, o + 60, "<3f", rot)
    _put(b, o + 96, "<12f", p2b[:3].reshape(-1))
    _put(b, o + 144, "<4f", qalign)
    if lin:
        _, n, f = lin
        if k < n:
            _put(b, f["pos"] + 12 * k, "<3f", pos)
            _put(b, f["quat"] + 16 * k, "<4f", quat)
            _put(b, f["rot"] + 12 * k, "<3f", rot)
            _put(b, f["p2b"] + 48 * k, "<12f", p2b[:3].reshape(-1))
            _put(b, f["qalign"] + 16 * k, "<4f", qalign)


def reframe_bone(b, B, k, X, report, tag):
    """New frame of bone k = old frame * X. Keeps the skinned mesh identical."""
    lin = linear_bones(b)
    Xi = inv_rigid(X)
    bo = B[k]
    L = rigid(quat_to_mat(bo["quat"]), bo["pos"]) @ X
    q = mat_to_quat(L[:3, :3])
    qa = mat_to_quat(quat_to_mat(bo["qalign"]) @ X[:3, :3])
    _write_bone(b, bo, lin, k, L[:3, 3], q, mat_to_euler(L[:3, :3]), Xi @ bo["p2b"], qa)
    for c, cb in enumerate(B):                      # children are expressed in bone k's frame
        if cb["parent"] == k:
            Lc = Xi @ rigid(quat_to_mat(cb["quat"]), cb["pos"])
            _write_bone(b, cb, lin, c, Lc[:3, 3], mat_to_quat(Lc[:3, :3]), mat_to_euler(Lc[:3, :3]),
                        cb["p2b"], cb["qalign"])
            report.append("  barrel %s: child bone %s re-expressed" % (tag, cb["name"]))
    for ho in _hitbox_offsets(b, k):               # only reached for a pure origin shift
        lo = np.array(struct.unpack_from("<3f", b, ho + 8)) - X[:3, 3]
        hi = np.array(struct.unpack_from("<3f", b, ho + 20)) - X[:3, 3]
        _put(b, ho + 8, "<6f", np.r_[lo, hi])
        report.append("  barrel %s: hitbox on %s shifted with the bone origin" % (tag, bo["name"]))
    na, ai = _i(b, 240), _i(b, 244)
    for a in range(na):                             # attachments on bone k
        o = ai + a * ATTACH_SIZE
        if _i(b, o + 8) == k:
            M = np.eye(4)
            M[:3] = np.array(struct.unpack_from("<12f", b, o + 12)).reshape(3, 4)
            _put(b, o + 12, "<12f", (Xi @ M)[:3].reshape(-1))
            report.append("  barrel %s: attachment %s re-expressed" % (tag, _cstr(b, o + _i(b, o))))


def _hitbox_offsets(b, k):
    """Offsets of the mstudiobbox_t records on bone k (all hitbox sets)."""
    out = []
    ns, si = _i(b, 172), _i(b, 176)
    for s in range(ns):
        o = si + s * 12
        for h in range(_i(b, o + 4)):
            ho = o + _i(b, o + 8) + h * 68
            if _i(b, ho) == k:
                out.append(ho)
    return out


def _hitboxes_on(b, k):
    return bool(_hitbox_offsets(b, k))


def _children_animated(B, k, anim):
    return any(cb["parent"] == k and c in anim for c, cb in enumerate(B))


def fix_minigun_barrel(mdl_path, report):
    """Patch a staged OF minigun .mdl in place (its .vvd is read, never written) so TF2C spins
    the barrel about the barrel's long axis. Appends lines to report (a list). Returns True if
    the .mdl was modified."""
    tag = os.path.basename(mdl_path)
    b = bytearray(open(mdl_path, "rb").read())
    if b[:4] != b"IDST":
        report.append("  !! barrel %s: not an MDL" % tag)
        return False
    vvd_path = os.path.splitext(mdl_path)[0] + ".vvd"
    if not os.path.exists(vvd_path):
        report.append("  !! barrel %s: no .vvd next to the model" % tag)
        return False
    B = read_bones(b)
    names = [bo["name"].lower() for bo in B]
    if VM_BONE in names:
        kind, k = "vm", names.index(VM_BONE)
    elif WM_BONE in names:
        kind, k = "wm", names.index(WM_BONE)
    else:
        report.append("  barrel %s: no %s/%s bone, nothing to do" % (tag, VM_BONE, WM_BONE))
        return False
    vv = read_vvd(vvd_path)
    ax, centre, _ = barrel_geometry(B, vv, k)
    before = spin_check(bytes(b), vv, kind, k)
    if kind == "vm":
        # spin axis = bone local X: rotate the frame so local X runs along the barrel
        want = np.array([1.0, 0.0, 0.0])
        cr = np.cross(want, ax)
        s, c = np.linalg.norm(cr), float(want @ ax)
        if s < 1e-9:
            C = np.eye(3) if c > 0 else np.diag([-1.0, -1.0, 1.0])
        else:
            kx = np.array([[0, -cr[2], cr[1]], [cr[2], 0, -cr[0]], [-cr[1], cr[0], 0]]) / s
            ang = math.atan2(s, c)
            C = np.eye(3) + math.sin(ang) * kx + (1 - math.cos(ang)) * kx @ kx
    else:
        # local rotation is REPLACED by Rz(theta): rest rotation must become identity, so the
        # barrel frame becomes the parent frame; that only works if the barrel runs along the
        # parent's Z axis.
        R = quat_to_mat(B[k]["quat"])
        parent_axis = R @ ax
        if abs(abs(parent_axis[2]) - 1) > 1e-3:
            report.append("  !! barrel %s: barrel axis %s is not the parent's Z axis; world-model "
                          "spin cannot be fixed by re-framing the barrel alone" % (tag, np.round(parent_axis, 3)))
            return False
        C = R.T
    t = centre if np.linalg.norm(centre) >= CENTRE_EPS else np.zeros(3)
    if np.allclose(C, np.eye(3), atol=1e-6) and not t.any():
        report.append("  barrel %s: %s already spins about its axis (err %.2f deg, wobble %.3f)"
                      % (tag, B[k]["name"], before["axis_err_deg"], before["centroid_wobble"]))
        return False
    anim = animated_bones(b)
    if k in anim or -1 in anim or _children_animated(B, k, anim):
        report.append("  !! barrel %s: bone %s (or a child) has animation tracks; not re-framed" % (tag, B[k]["name"]))
        return False
    if _hitboxes_on(b, k) and not np.allclose(C, np.eye(3), atol=1e-6):
        report.append("  !! barrel %s: bone %s has hitboxes and needs a rotation; not re-framed" % (tag, B[k]["name"]))
        return False
    X = rigid(C, t)
    rest_before = skin(B, rest_world(B), vv)
    reframe_bone(b, B, k, X, report, tag)
    B2 = read_bones(b)
    rest_after = skin(B2, rest_world(B2), vv)
    drift = float(np.abs(rest_after - rest_before).max())
    after = spin_check(bytes(b), vv, kind, k)
    ok = after["axis_err_deg"] < 0.5 and after["max_vertex_dev"] < 0.05 and drift < 0.01
    if not ok:
        report.append("  !! barrel %s: self-check failed (axis err %.3f deg, vertex dev %.4f, rest drift %.5f); "
                      "file left unchanged" % (tag, after["axis_err_deg"], after["max_vertex_dev"], drift))
        return False
    with open(mdl_path, "wb") as f:
        f.write(b)
    report.append("  barrel %s: %s re-framed (%s rule; rot %.1f deg, origin shift %.3f): spin axis error %.1f -> %.3f deg, "
                  "vertex dev %.3f -> %.4f, wobble %.3f -> %.4f, rest drift %.6f"
                  % (tag, B[k]["name"], "roll-about-X" if kind == "vm" else "replace-with-Rz",
                     math.degrees(math.acos(max(-1, min(1, (np.trace(C) - 1) / 2)))), float(np.linalg.norm(t)),
                     before["axis_err_deg"], after["axis_err_deg"], before["max_vertex_dev"], after["max_vertex_dev"],
                     before["centroid_wobble"], after["centroid_wobble"], drift))
    return True


def check(mdl_path):
    b = open(mdl_path, "rb").read()
    B = read_bones(b)
    names = [bo["name"].lower() for bo in B]
    kind, k = (("vm", names.index(VM_BONE)) if VM_BONE in names else
               ("wm", names.index(WM_BONE)) if WM_BONE in names else (None, None))
    if kind is None:
        return None
    vv = read_vvd(os.path.splitext(mdl_path)[0] + ".vvd")
    r = spin_check(b, vv, kind, k)
    r["bone"], r["rule"] = B[k]["name"], kind
    return r


def main(argv):
    only_check = "--check" in argv
    paths = [a for a in argv if a != "--check"]
    rc = 0
    for p in paths:
        if not only_check:
            rep = []
            fix_minigun_barrel(p, rep)
            print("\n".join(rep))
            rc |= any("!!" in line for line in rep)
        print(os.path.basename(p), check(p))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
