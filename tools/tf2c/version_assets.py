#!/usr/bin/env python3
"""Give every tf2cc-owned asset whose content changed since it was first published a new path.

Why: a Source client never downloads a file again once it has one at that path, so an asset
replaced in place on FastDL stays stale for every player who already downloaded it (playtest
2026-11-16: crowbar team skins and the round-5 viewmodels never reached the user). The rule
is therefore: a published path never changes content.

How: deploy/fastdl_first_published.json records, per FastDL path, the blob first published
there (built from the FastDL repo history by --refresh, and extended by every publish). After
the generators ran, each staged file under a tf2cc-owned prefix whose bz2 blob differs from
the first published one is moved, with its whole group, to "<stem>_<hash8><rest>":

  * models: <stem>.mdl/.vvd/.dx90.vtx/.dx80.vtx/.sw.vtx/.phy/.ani move together;
  * bucket icons: <stem>, <stem>_large, <stem>_red/_blue/_green/_yellow (.vmt/.vtf) move
    together, so the client's "<image>_<team>" lookup keeps working.

References are rewritten in the staged text files (schema, sound scripts, VMTs), the plugin
configs (configs/tf2cc_tf2c/*.cfg) and in MDL include tables. A VMT referenced by a model's
texture table cannot be renamed this way and stops the build. The pass repeats until no
staged file differs (a rewritten VMT/schema reference can make another file differ).

Files outside the tf2cc-owned prefixes (4dm paths such as materials/models/player/
merc_deathmatch, which FastDL never replaces) and the REPLACE files (re-downloaded every
connection: the client deletes download/scripts/items/* on disconnect) are left alone.

  python -I tools/tf2c/version_assets.py [--refresh]     (stage_tf2c.py runs it)
"""
import bz2
import hashlib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gen_merc_variants as gmv  # noqa: E402  (Mdl include editor)

STAGE = os.path.join(ROOT, "tf2c", "staging", "tf2classified")
CFG_DIR = os.path.join(ROOT, "config", "sourcemod", "configs", "tf2cc_tf2c")
HISTORY = os.path.join(ROOT, "deploy", "fastdl_first_published.json")
REPO = "AgitationSkeleton/redchanitfastdl_tf2classic"
PREFIX = "tf2classified/"
REPLACE = {"scripts/items/custom_items_game.txt", "scripts/items/custom_level_sounds.txt"}
OWN_PREFIXES = ("models/player/tf2cc/", "models/tf2cc/", "sound/tf2cc/", "sound/vo/tf2cc/",
                "materials/tf2cc/", "materials/models/tf2cc/", "materials/vgui/tf2cc/")
MODEL_EXT = (".dx90.vtx", ".dx80.vtx", ".sw.vtx", ".vtx", ".vvd", ".phy", ".ani", ".mdl")
ICON_DIRS = ("materials/tf2cc/of/bucket/", "materials/tf2cc/of/bucket_team/", "materials/tf2cc/oldmerc/bucket/",
             "materials/tf2cc/oldclass/bucket/", "materials/tf2cc/oldclass/bucket_team/",
             "materials/tf2cc/oldmerc/bucket_team/", "materials/vgui/tf2cc/")
ICON_SUFFIX = re.compile(r"_(large|red|blue|green|yellow)$")
TEXT_EXT = (".txt", ".vmt", ".res", ".cfg")


def blob_sha(data):
    d = bz2.compress(data, 9)
    return hashlib.sha1(b"blob %d\0" % len(d) + d).hexdigest()


def gh(path):
    r = subprocess.run(["gh", "api", path], capture_output=True)
    if r.returncode != 0:
        raise SystemExit("gh api %s failed: %s" % (path, r.stderr.decode()[:300]))
    return json.loads(r.stdout)


def refresh():
    """First published blob per path, from every tf2cc publish commit (oldest first)."""
    shas = []
    page = 1
    while True:
        lst = gh("repos/%s/commits?per_page=100&page=%d" % (REPO, page))
        if not lst:
            break
        shas += [c["sha"] for c in lst if c["commit"]["message"].startswith("tf2cc (TF2 Classified)")]
        page += 1
    first, modified = {}, set()
    for sha in reversed(shas):
        page = 1
        while True:
            files = gh("repos/%s/commits/%s?per_page=300&page=%d" % (REPO, sha, page)).get("files") or []
            if not files:
                break
            for f in files:
                p = f["filename"]
                if not (p.startswith(PREFIX) and p.endswith(".bz2")):
                    continue
                rel = p[len(PREFIX):-4].lower()
                if f["status"] == "added":
                    first.setdefault(rel, f["sha"])
                elif f["status"] == "modified":
                    modified.add(rel)
            page += 1
    hist = {"first": first, "modified_in_place": sorted(modified)}
    os.makedirs(os.path.dirname(HISTORY), exist_ok=True)
    json.dump(hist, open(HISTORY, "w", encoding="utf-8", newline="\n"), indent=0, sort_keys=True)
    print("fastdl history: %d paths, %d were modified in place" % (len(first), len(modified)))
    return hist


def staged():
    out = []
    for dp, _, names in os.walk(STAGE):
        for n in names:
            out.append(os.path.relpath(os.path.join(dp, n), STAGE).replace(os.sep, "/"))
    return out


def group_key(rel):
    low = rel.lower()
    for ext in MODEL_EXT:
        if low.startswith("models/") and low.endswith(ext):
            return rel[:-len(ext)]
    stem, ext = os.path.splitext(rel)
    if low.startswith(ICON_DIRS) and ext.lower() in (".vmt", ".vtf"):
        key = ICON_SUFFIX.sub("", stem)
        # the materials/vgui/ copy of an icon belongs to the icon: same new name (the client
        # looks up "vgui/<image_inventory>" too)
        if key.lower().startswith("materials/vgui/"):
            key = "materials/" + key[len("materials/vgui/"):]
        return key
    return stem


def own_stem(rel):
    """The part of rel the version tag follows (its group key spelled as rel spells it)."""
    low = rel.lower()
    for ext in MODEL_EXT:
        if low.startswith("models/") and low.endswith(ext):
            return rel[:-len(ext)]
    stem, ext = os.path.splitext(rel)
    if low.startswith(ICON_DIRS) and ext.lower() in (".vmt", ".vtf"):
        return ICON_SUFFIX.sub("", stem)
    return stem


def refs_of(rel):
    """Strings other files use for rel (longest first)."""
    low = rel.lower()
    out = [rel]
    if low.startswith("materials/"):
        out += [rel[len("materials/"):], os.path.splitext(rel[len("materials/"):])[0]]
    elif low.startswith("sound/"):
        out += [rel[len("sound/"):]]
    return out


def text_files():
    for rel in staged():
        if rel.lower().endswith(TEXT_EXT):
            yield os.path.join(STAGE, rel)
    for n in os.listdir(CFG_DIR):
        if n.lower().endswith(TEXT_EXT) and n.lower() != "downloads.txt":
            yield os.path.join(CFG_DIR, n)


def rewrite(mapping):
    """mapping: old rel -> new rel. Text references and MDL include tables."""
    pairs = []
    for old, new in mapping.items():
        for a, b in zip(refs_of(old), refs_of(new)):
            pairs.append((a, b))
    pairs.sort(key=lambda p: -len(p[0]))
    rx = re.compile("|".join(re.escape(a).replace(r"/", r"[/\\\\]") for a, _ in pairs) + r"(?![A-Za-z0-9_])", re.I) if pairs else None
    lut = {a.lower(): b for a, b in pairs}
    touched = 0
    for path in text_files():
        t = open(path, encoding="latin-1").read()
        n = rx.sub(lambda m: lut[m.group(0).replace("\\", "/").lower()], t)
        if n != t:
            open(path, "w", encoding="latin-1", newline="").write(n)
            touched += 1
    mdl_map = {o.lower(): n for o, n in mapping.items() if o.lower().endswith(".mdl")}
    for rel in staged():
        if not rel.lower().endswith(".mdl"):
            continue
        path = os.path.join(STAGE, rel)
        m = gmv.Mdl(open(path, "rb").read())
        inc = m.includes()
        new = [mdl_map.get(i.replace("\\", "/").lower(), i) for i in inc]
        if new != inc:
            m.set_includes(new)
            open(path, "wb").write(m.finish())
            touched += 1
    return touched


def main():
    hist = refresh() if ("--refresh" in sys.argv or not os.path.exists(HISTORY)) else json.load(open(HISTORY))
    first = hist["first"]
    moved = {}
    for rnd in range(8):
        files = staged()
        changed = set()
        for rel in files:
            low = rel.lower()
            if low in REPLACE or not low.startswith(OWN_PREFIXES) or low not in first:
                continue
            if blob_sha(open(os.path.join(STAGE, rel), "rb").read()) != first[low]:
                changed.add(group_key(rel))
        if not changed:
            break
        mapping = {}
        for key in sorted(changed):
            members = sorted(r for r in files if group_key(r) == key)
            h = hashlib.sha1()
            for r in members:
                h.update(open(os.path.join(STAGE, r), "rb").read())
            tag = "_" + h.hexdigest()[:8]
            for r in members:
                st = own_stem(r)
                new = st + tag + r[len(st):]
                os.makedirs(os.path.dirname(os.path.join(STAGE, new)), exist_ok=True)
                os.replace(os.path.join(STAGE, r), os.path.join(STAGE, new))
                mapping[r] = new
        # A VMT used by a model's texture table cannot be renamed by a text rewrite.
        for r in mapping:
            if r.lower().endswith(".vmt") and not r.lower().startswith(ICON_DIRS):
                raise SystemExit("version_assets: %s changed but models reference it by name; "
                                 "give it a new name in its generator" % r)
        n = rewrite(mapping)
        moved.update(mapping)
        print("version_assets: round %d: %d group(s) changed since first publish, %d file(s) moved, "
              "%d referencing file(s) rewritten" % (rnd + 1, len(changed), len(mapping), n))
        for key in sorted(changed):
            print("  %s -> %s" % (key, next(v for k, v in mapping.items() if group_key(k) == key)))
    else:
        raise SystemExit("version_assets: references did not settle")
    return moved


if __name__ == "__main__":
    main()
