"""Team icons for three old class weapons, recoloured from the icons already deployed (batch 16, user
2026-11-17: "just hue-shift the existing ones"; then "the orange parts of the rescue ranger colored
bright blue ... not accurate to the ingame blueteam rescue ranger": only what the skins recolour).

The deployed icon is the RED one, unchanged. BLU / GRN / YLW: each icon colour gets the change the
weapon's in-game skin textures make to that colour between RED and the team (transfer() below):
only the regions the team skins recolour change, to the colours those textures have.

ICONS: name -> (deployed icon VTF, the weapon's team skin textures (staged VMT names))
  team_rescueranger_skin        TF2's Rescue Ranger backpack icon (the item uses the stock
                               backpack/workshop/.../c_tele_shotgun icon; read from the TF2
                               client install's tf2_textures VPK, read-only), c_tele_shotgun_*
  team_overhealer_skin          TF2 Classic 2.2.3's w_overhealer_large, w_medigun01_*
  team_makeshiftmutilator_skin  TF2 Classic 2.2.3's w_chemthrower_large, c_chemthrower_*

Output: research/tf2cc-icons/<name>_red/_blue/_green/_yellow.png (512x512 RGBA, staged by
gen_schema's PNG_ICONS in the stock 512 DXT5 clamp format), <name>_samples.json and the review
sheet research/tf2cc-icons/batch16_team_icons.png (deployed | RED | BLU | GRN | YLW).

  python -B -I tools/tf2c/team_skin_icons.py      (needs a staged tf2c/staging for the skins, or TF2CC_STAGE)
"""
import json
import os
import re
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import dxt  # noqa: E402
import fix_vm_sounds as fvs  # noqa: E402

STAGE = os.environ.get("TF2CC_STAGE") or os.path.join(ROOT, "tf2c", "staging", "tf2classified")
OUT = os.path.join(ROOT, "research", "tf2cc-icons")
S223 = r"<STEAMCMD>/sdk2013/tf2classic-2/tf2classic/materials/backpack/weapons/w_models/"
TF2_TEXTURES = r"<STEAM_GAMES>/Team Fortress 2/tf/tf2_textures_dir.vpk"
TEAMS = ("red", "blue", "green", "yellow")
ICONS = {
    "team_rescueranger_skin": (
        ("vpk", TF2_TEXTURES, "materials/backpack/workshop/weapons/c_models/c_tele_shotgun/c_tele_shotgun_large.vtf"),
        ["models/tf2cc/oldclass/models/weapons/c_models/"],
        {"red": "c_tele_shotgun", "blue": "c_tele_shotgun_blue", "green": "c_tele_shotgun_green", "yellow": "c_tele_shotgun_yellow"}),
    "team_overhealer_skin": (
        ("file", S223 + "w_overhealer_large.vtf", None),
        ["models/tf2cc/oldclass/models/weapons/w_medigun_v2/", "models/weapons/w_medigun/"],
        {"red": "w_medigun01", "blue": "w_medigun01_Blue", "green": "w_medigun01_green", "yellow": "w_medigun01_yellow"}),
    "team_makeshiftmutilator_skin": (
        ("file", S223 + "w_chemthrower_large.vtf", None),
        ["models/tf2cc/oldclass/models/workshop/weapons/c_models/c_chemthrower_v2/"],
        {"red": "c_chemthrower", "blue": "c_chemthrower_blue", "green": "c_chemthrower_green", "yellow": "c_chemthrower_yellow"}),
}


def vtf_top(data):
    """Top mip of a single-frame VTF (DXT5 / RGBA8888 / BGRA8888) as RGBA."""
    w, h = struct.unpack_from("<HH", data, 16)
    fmt = struct.unpack_from("<i", data, 52)[0]
    bpp = {15: 1, 0: 4, 12: 4}[fmt]
    pix = data[len(data) - w * h * bpp:]
    if fmt == 12:
        pix = np.frombuffer(pix, np.uint8).reshape(h, w, 4)[..., [2, 1, 0, 3]].tobytes()
        fmt = 0
    return dxt.decode(pix, w, h, fmt)


def read_game(rel):
    p = os.path.join(STAGE, rel)
    if os.path.exists(p):
        return open(p, "rb").read()
    for v in (fvs.TF2C_VPK, fvs.TF2_VPK):
        b = fvs.vpk("cat", v, rel.lower())
        if b:
            return b
    try:        # stock TF2 textures (the BLU medigun): the client install's texture VPK, read-only
        return vpktool_cat(TF2_TEXTURES, rel.lower()) or None
    except Exception:
        return None


def skin_texture(cds, name):
    for cd in cds:
        t = read_game("materials/%s%s.vmt" % (cd, name))
        if not t:
            continue
        m = re.search(r'"?\$basetexture"?\s+"?([^"\s]+)"?', t.decode("latin-1"), re.I)
        v = read_game("materials/%s.vtf" % m.group(1).replace(chr(92), "/"))
        if v:
            return vtf_top(v)[..., :3].astype(np.float32) / 255.0
    raise SystemExit("hue_team_icons: no texture for %s" % name)


def hsv(rgb):
    """float RGB (..., 3) in 0..1 -> hue (degrees), saturation, value."""
    mx, mn = rgb.max(-1), rgb.min(-1)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    hue = np.degrees(np.arctan2(np.sqrt(3) * (g - b), 2 * r - g - b)) % 360
    return hue, (mx - mn) / np.maximum(mx, 1e-6), mx


def from_hsv(h, s, v):
    h = (h % 360) / 60.0
    i = np.floor(h).astype(int) % 6
    f = h - np.floor(h)
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    out = np.zeros(h.shape + (3,), np.float32)
    for k, (a, b, c) in enumerate(((v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q))):
        m = i == k
        out[m] = np.stack([a[m], b[m], c[m]], -1)
    return out


def reddish(rgb):
    h, s, v = hsv(rgb)
    d = np.minimum(h, 360 - h)
    return d, s, v


def circ_mean(h, w):
    a = np.radians(h)
    return float(np.degrees(np.arctan2((np.sin(a) * w).sum(), (np.cos(a) * w).sum())) % 360)


def sample(cds, names):
    red = skin_texture(cds, names["red"])
    d, s, v = reddish(red)
    out = {}
    for t in ("blue", "green", "yellow"):
        o = skin_texture(cds, names[t])
        if o.shape != red.shape:
            o = np.asarray(Image.fromarray((o * 255).astype(np.uint8)).resize(red.shape[1::-1], Image.LANCZOS), np.float32) / 255
        m = (np.abs(o - red).sum(-1) > 0.15) & (d < 40) & (s > 0.35) & (v > 0.12)
        hr, sr, vr = hsv(red[m])
        ht, st, vt = hsv(o[m])
        out[t] = dict(pixels=int(m.sum()), red_hue=round(circ_mean(hr, sr), 2), red_sat=round(float(np.median(sr)), 4),
                      red_val=round(float(np.median(vr)), 4), hue=round(circ_mean(ht, st), 2),
                      sat=round(float(np.median(st)), 4), val=round(float(np.median(vt)), 4))
    return out


# Region transfer (coordinator 2026-11-17: "only recolour the regions that actually differ between
# the team skins, to the colours those textures really have"): the RED skin texture's colours are
# binned by hue (10 degrees), saturation and value (4 x 3 bins); each bin records, over its texels,
# the median hue change, saturation ratio and value ratio to the same texels of the team skin. An
# icon pixel takes its bin's change (nearest populated bin in value, then saturation, then hue), so
# a colour the team skins keep (the Rescue Ranger's orange on BLU) stays, and one they recolour (its
# red wire and lamp) gets the team texture's colour. Greys (saturation < 0.12) never change.
HB, SB, VB = 36, 4, 3


def bin_index(h, s, v):
    return ((h // 10).astype(int) % HB, np.clip((s * SB).astype(int), 0, SB - 1), np.clip((v * VB).astype(int), 0, VB - 1))


def transfer_table(red, team):
    hr, sr, vr = hsv(red.reshape(-1, 3))
    ht, st, vt = hsv(team.reshape(-1, 3))
    keep = sr >= 0.12
    hr, sr, vr, ht, st, vt = hr[keep], sr[keep], vr[keep], ht[keep], st[keep], vt[keep]
    dh = (ht - hr + 180) % 360 - 180
    dh = np.where(st < 0.05, 0, dh)                 # a texel that turned grey: no hue to follow
    rs = st / np.maximum(sr, 1e-3)
    rv = vt / np.maximum(vr, 1e-3)
    bi = bin_index(hr, sr, vr)
    flat = (bi[0] * SB + bi[1]) * VB + bi[2]
    table = np.full((HB * SB * VB, 4), np.nan)     # dh, sat ratio, val ratio, texel count
    for k in np.unique(flat):
        m = flat == k
        table[k] = (np.median(dh[m]), np.median(rs[m]), np.median(rv[m]), m.sum())
    return table


def lookup(table, h, s, v):
    hb, sb, vb = bin_index(h, s, v)
    out = np.full(h.shape + (3,), np.nan)
    order = [(dh, ds, dv) for dh in (0, -1, 1, -2, 2) for ds in (0, -1, 1, -2, 2, 3, -3) for dv in (0, -1, 1, -2, 2)]
    for dh_, ds_, dv_ in order:
        todo = np.isnan(out[..., 0])
        if not todo.any():
            break
        hh = (hb + dh_) % HB
        ss = sb + ds_
        vv = vb + dv_
        ok = todo & (ss >= 0) & (ss < SB) & (vv >= 0) & (vv < VB)
        k = (hh * SB + np.clip(ss, 0, SB - 1)) * VB + np.clip(vv, 0, VB - 1)
        row = table[k]
        hit = ok & (row[..., 3] >= 20)
        out[hit] = row[hit][:, :3]
    out[np.isnan(out[..., 0])] = (0, 1, 1)
    return out


def transfer(icon, table):
    rgb = icon[..., :3].astype(np.float32) / 255.0
    h, s, v = hsv(rgb)
    d = lookup(table, h, s, v)
    grey = s < 0.12
    nh = h + np.where(grey, 0, d[..., 0])
    ns = np.clip(s * np.where(grey, 1, d[..., 1]), 0, 1)
    nv = np.clip(v * np.where(grey, 1, d[..., 2]), 0, 1)
    out = icon.copy()
    out[..., :3] = np.clip(np.round(from_hsv(nh, ns, nv) * 255), 0, 255).astype(np.uint8)
    return out


def deployed(src):
    kind, path, inner = src
    data = open(path, "rb").read() if kind == "file" else vpktool_cat(path, inner)
    rgba = vtf_top(data)
    if rgba.shape[:2] != (512, 512):
        rgba = np.asarray(Image.fromarray(rgba, "RGBA").resize((512, 512), Image.LANCZOS))
    return rgba


def vpktool_cat(vpk, rel):
    import subprocess
    return subprocess.run([sys.executable, "-I", os.path.join(os.path.dirname(HERE), "vpktool.py"), "cat", vpk, rel],
                          check=True, capture_output=True).stdout


def main():
    rows = []
    for name, (src, cds, names) in ICONS.items():
        base = deployed(src)
        smp = sample(cds, names)
        json.dump(smp, open(os.path.join(OUT, name + "_samples.json"), "w"), indent=1)
        skins = {t: skin_texture(cds, names[t]) for t in TEAMS}
        imgs = {"red": base}
        for t in ("blue", "green", "yellow"):
            team = skins[t]
            if team.shape != skins["red"].shape:
                team = np.asarray(Image.fromarray((team * 255).astype(np.uint8)).resize(skins["red"].shape[1::-1], Image.LANCZOS), np.float32) / 255
            imgs[t] = transfer(base, transfer_table(skins["red"], team))
        for t in TEAMS:
            Image.fromarray(imgs[t], "RGBA").save(os.path.join(OUT, "%s_%s.png" % (name, t)))
        rows.append((name, base, imgs, skins))
        print(name, json.dumps(smp))
    # review sheet: per item, the icons (deployed | RED | BLU | GRN | YLW) over the HUD grey and
    # under each team icon that team's in-game skin texture (the model's $basetexture)
    cell = 256
    sheet = Image.new("RGBA", (cell * 5, (cell * 2 + 8) * len(rows) + 24), (46, 43, 40, 255))
    dr = ImageDraw.Draw(sheet)
    for c, label in enumerate(("deployed", "RED", "BLU", "GRN", "YLW")):
        dr.text((c * cell + 8, 6), label, fill=(235, 226, 202, 255))
    for r, (name, base, imgs, skins) in enumerate(rows):
        y = 24 + r * (cell * 2 + 8)
        for c, img in enumerate((base, imgs["red"], imgs["blue"], imgs["green"], imgs["yellow"])):
            sheet.alpha_composite(Image.fromarray(img, "RGBA").resize((cell, cell), Image.LANCZOS), (c * cell, y))
        dr.text((8, y + cell + 6), name + ": in-game skin textures", fill=(235, 226, 202, 255))
        for c, t in enumerate(TEAMS):
            tex = Image.fromarray((skins[t] * 255).astype(np.uint8)).convert("RGBA").resize((cell - 8, cell - 8), Image.LANCZOS)
            sheet.alpha_composite(tex, ((c + 1) * cell + 4, y + cell + 4))
    sheet.save(os.path.join(OUT, "batch16_team_icons.png"))


if __name__ == "__main__":
    main()
