"""Read-only sequence/animation decoder for compiled Source models (MDL v48, SDK 2013).

Decodes any frame of a local (in-file) animation, following bone_setup.cpp: mstudioanim_t tracks
RAWROT (Quaternion48), RAWROT2 (Quaternion64), RAWPOS (Vector48), ANIMROT/ANIMPOS (run-length
mstudioanimvalue_t, ExtractAnimValue), DELTA; animation sections (sectionframes, the last frame of a
long animation stored in its own section). Bones without a track keep their rest pose.

  sequences(m)            -> [dict(label, act, fps, frames, anim, events=[(cycle, event, options)])]
  local_pose(m, seq, f)   -> per-bone (pos, quat) local transforms at integer frame f
  world_pose(m, seq, f)   -> per-bone 4x4 bone-to-model matrices

m is a srcmodel.load() Model. CLI: python -I mdlanim.py <model.mdl> [sequence] prints the sequences
and, for a sequence, every bone that moves (largest translation/rotation from frame 0).
"""
import struct
import sys

import os

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import srcmodel as S  # noqa: E402

RAWPOS, RAWROT, ANIMPOS, ANIMROT, DELTA, RAWROT2 = 0x01, 0x02, 0x04, 0x08, 0x10, 0x20
SEQ_SIZE, ANIMDESC_SIZE, EVENT_SIZE = 212, 100, 80


def _i(b, o):
    return struct.unpack_from("<i", b, o)[0]


def euler_quat(x, y, z):
    """RadianEuler -> Quaternion (mathlib AngleQuaternion(RadianEuler))."""
    sr, cr = np.sin(x / 2), np.cos(x / 2)
    sp, cp = np.sin(y / 2), np.cos(y / 2)
    sy, cy = np.sin(z / 2), np.cos(z / 2)
    return np.array([sr * cp * cy - cr * sp * sy, cr * sp * cy + sr * cp * sy,
                     cr * cp * sy - sr * sp * cy, cr * cp * cy + sr * sp * sy])


def q48(b, o):
    x, y, zw = struct.unpack_from("<HHH", b, o)
    z, wneg = zw & 0x7FFF, zw >> 15
    qx, qy, qz = (x - 32768) / 32768.0, (y - 32768) / 32768.0, (z - 16384) / 16384.0
    w = np.sqrt(max(0.0, 1 - qx * qx - qy * qy - qz * qz))
    return np.array([qx, qy, qz, -w if wneg else w])


def q64(b, o):
    v = struct.unpack_from("<Q", b, o)[0]
    x, y, z, wneg = v & 0x1FFFFF, (v >> 21) & 0x1FFFFF, (v >> 42) & 0x1FFFFF, v >> 63
    qx, qy, qz = (x - 1048576) / 1048576.5, (y - 1048576) / 1048576.5, (z - 1048576) / 1048576.5
    w = np.sqrt(max(0.0, 1 - qx * qx - qy * qy - qz * qz))
    return np.array([qx, qy, qz, -w if wneg else w])


def v48(b, o):
    return np.array(struct.unpack_from("<3e", b, o), dtype=float)


def anim_value(b, p, frame, scale):
    """ExtractAnimValue (integer frame): p = absolute offset of the mstudioanimvalue_t run."""
    k = frame
    while True:
        valid, total = b[p], b[p + 1]
        if total == 0:
            return 0.0
        if total > k:
            break
        k -= total
        p += (valid + 1) * 2
    if valid > k:
        v = struct.unpack_from("<h", b, p + 2 + 2 * k)[0]
    else:
        v = struct.unpack_from("<h", b, p + 2 * valid)[0]
    return v * scale


def sequences(m):
    b = m.mdl
    out = []
    for so in m.seq_offsets:
        label = S.cstr(b, so + _i(b, so + 4))
        act = S.cstr(b, so + _i(b, so + 8))
        aidx = struct.unpack_from("<h", b, so + _i(b, so + 60))[0]
        ad = _i(b, 184) + aidx * ANIMDESC_SIZE
        fps = struct.unpack_from("<f", b, ad + 8)[0]
        frames = _i(b, ad + 16)
        nev, evi = _i(b, so + 24), _i(b, so + 28)
        ev = []
        for k in range(nev):
            eo = so + evi + k * EVENT_SIZE
            cyc = struct.unpack_from("<f", b, eo)[0]
            ev.append((round(cyc, 4), _i(b, eo + 4), b[eo + 12:eo + 76].split(b"\0")[0].decode("latin-1"),
                       S.cstr(b, eo + _i(b, eo + 76)) if _i(b, eo + 76) else ""))
        out.append(dict(label=label, act=act, fps=fps, frames=frames, anim=ad, off=so, events=ev,
                        flags=_i(b, so + 12)))
    return out


def find(m, want):
    for s in sequences(m):
        if s["label"].lower() == want.lower() or s["act"].upper() == want.upper():
            return s
    raise KeyError(want)


def local_pose(m, seq, frame):
    b = m.mdl
    nb, bi = _i(b, 156), _i(b, 160)
    pos = [bo["pos"].copy() for bo in m.bones]
    quat = [bo["quat"].copy() for bo in m.bones]
    if isinstance(seq, str):
        seq = find(m, seq)
    ad = seq["anim"]
    nframes = _i(b, ad + 16)
    frame = max(0, min(int(frame), nframes - 1))
    animblock, animindex = _i(b, ad + 52), _i(b, ad + 56)
    sidx, sframes = _i(b, ad + 80), _i(b, ad + 84)
    f = frame
    if sframes:
        if nframes > sframes and f == nframes - 1:
            section, f = nframes // sframes + 1, 0
        else:
            section = f // sframes
            f -= section * sframes
        animblock, animindex = _i(b, ad + sidx + 8 * section), _i(b, ad + sidx + 8 * section + 4)
    if animblock != 0:
        raise ValueError("animation in an external .ani block")
    if animindex:
        p = ad + animindex
        while True:
            bone, flags = b[p], b[p + 1]
            nxt = struct.unpack_from("<h", b, p + 2)[0]
            bo = bi + bone * S.BONE_SIZE
            rest_rot = np.array(struct.unpack_from("<3f", b, bo + 60))
            posscale = np.array(struct.unpack_from("<3f", b, bo + 72))
            rotscale = np.array(struct.unpack_from("<3f", b, bo + 84))
            o = p + 4
            if flags & RAWROT:
                quat[bone] = q48(b, o)
                o += 6
            elif flags & RAWROT2:
                quat[bone] = q64(b, o)
                o += 8
            elif flags & ANIMROT:
                offs = struct.unpack_from("<3h", b, o)
                e = np.array([anim_value(b, o + offs[k], f, rotscale[k]) if offs[k] else 0.0 for k in range(3)])
                if not flags & DELTA:
                    e = e + rest_rot
                quat[bone] = euler_quat(*e)
                o += 6
            elif flags & DELTA:
                quat[bone] = np.array([0.0, 0.0, 0.0, 1.0])
            if flags & RAWPOS:
                pos[bone] = v48(b, o)
            elif flags & ANIMPOS:
                offs = struct.unpack_from("<3h", b, o)
                d = np.array([anim_value(b, o + offs[k], f, posscale[k]) if offs[k] else 0.0 for k in range(3)])
                pos[bone] = d if flags & DELTA else d + m.bones[bone]["pos"]
            elif flags & DELTA:
                pos[bone] = np.zeros(3)
            if nxt == 0:
                break
            p += nxt
    return list(zip(pos, quat))


def world_pose(m, seq, frame):
    W = []
    for k, (p, q) in enumerate(local_pose(m, seq, frame)):
        L = np.eye(4)
        L[:3, :3] = S.quat_to_mat(q / (np.linalg.norm(q) or 1))
        L[:3, 3] = p
        par = m.bones[k]["parent"]
        W.append(L if par < 0 else W[par] @ L)
    return W


def bone_motion(m, seq, names=None, rel_parent=True):
    """Per bone: max translation (units) and rotation (deg) of its parent-relative transform
    from frame 0 over the sequence."""
    if isinstance(seq, str):
        seq = find(m, seq)
    p0 = local_pose(m, seq, 0)
    out = {}
    for f in range(seq["frames"]):
        pf = local_pose(m, seq, f)
        for k, bo in enumerate(m.bones):
            if names and bo["name"] not in names:
                continue
            dt = float(np.linalg.norm(pf[k][0] - p0[k][0]))
            q0, q1 = p0[k][1] / np.linalg.norm(p0[k][1]), pf[k][1] / np.linalg.norm(pf[k][1])
            da = float(np.degrees(2 * np.arccos(min(1.0, abs(float(q0 @ q1))))))
            t, a, ft, fa = out.get(bo["name"], (0.0, 0.0, 0, 0))
            out[bo["name"]] = (max(t, dt), max(a, da), f if dt > t else ft, f if da > a else fa)
    return out


if __name__ == "__main__":
    mm = S.load(sys.argv[1])
    for s in sequences(mm):
        print("%-14s %-26s %3d frames @ %g fps flags %x events %s" % (s["label"], s["act"], s["frames"], s["fps"],
                                                                    s["flags"], s["events"]))
    if len(sys.argv) > 2:
        for name, (t, a, ft, fa) in sorted(bone_motion(mm, sys.argv[2]).items(), key=lambda kv: -kv[1][0]):
            if t > 0.01 or a > 0.1:
                print("  %-26s move %6.2f u (frame %3d)  turn %6.1f deg (frame %3d)" % (name, t, ft, a, fa))
