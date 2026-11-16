#!/usr/bin/env python3
"""Publish the TF2 Classified fork's staged files to the tf2classic FastDL repo, without cloning.

Uploads tf2c/staging/tf2classified/<path> as <repo>/tf2classified/<path>.bz2 in ONE
commit through the Git Data API (blobs -> tree with base_tree -> commit -> ref).

Safety (user rules for redchanitfastdl_tf2classic, used by the live April Fools server):
  * additive only: a path that already exists in the repo is never replaced, except the
    files in REPLACE (the merged item schema and sound scripts: clients delete
    download/scripts/items/* on disconnect and fetch them again). A tf2cc-owned path
    (OWN_PREFIXES) whose content changed is refused too: a client never downloads a path it
    already has, so changed assets get new paths (version_assets.py, run by stage_tf2c.py);
  * deploy/fastdl_first_published.json gains every path this tool adds;
  * dry run by default; --apply to publish; --revert <sha> --apply undoes a commit this
    tool made (only while it is still the branch head);
  * each publish is logged to deploy/fastdl_publish_log.tsv.

  python -I tools/tf2c/fastdl_publish_tf2c.py [--apply]
  python -I tools/tf2c/fastdl_publish_tf2c.py --revert <commit_sha> --apply
"""
import base64
import bz2
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
REPO = "AgitationSkeleton/redchanitfastdl_tf2classic"
PREFIX = "tf2classified/"
STAGE = os.path.join(ROOT, "tf2c", "staging", "tf2classified")
REPLACE = {"scripts/items/custom_items_game.txt",
           "scripts/items/custom_level_sounds.txt"}   # tf2cc-generated: only tf2cc.* sound scripts
# Paths only tf2cc ships (published by this tool): updated in place when their content changes.
OWN_PREFIXES = ("models/player/tf2cc/", "models/tf2cc/", "sound/tf2cc/", "sound/vo/tf2cc/",
                "materials/tf2cc/", "materials/models/tf2cc/", "materials/vgui/tf2cc/")
SKIP_EXT = (".nut",)
LOG = os.path.join(ROOT, "deploy", "fastdl_publish_log.tsv")


def gh(method, path, body=None):
    cmd = ["gh", "api", "-X", method, path]
    if body is not None:
        cmd += ["--input", "-"]
    r = subprocess.run(cmd, input=json.dumps(body).encode() if body is not None else None, capture_output=True)
    if r.returncode != 0:
        raise SystemExit("gh api %s %s failed: %s" % (method, path, r.stderr.decode()[:400]))
    return json.loads(r.stdout or b"{}")


def blob_exists(sha):
    r = subprocess.run(["gh", "api", "repos/%s/git/blobs/%s" % (REPO, sha), "--jq", ".sha"], capture_output=True)
    return r.returncode == 0


def main():
    apply = "--apply" in sys.argv
    branch = gh("GET", "repos/%s" % REPO)["default_branch"]
    head = gh("GET", "repos/%s/git/ref/heads/%s" % (REPO, branch))["object"]["sha"]
    if "--revert" in sys.argv:
        target = sys.argv[sys.argv.index("--revert") + 1]
        if head != target:
            raise SystemExit("branch head %s is not %s; refusing to revert over newer commits" % (head, target))
        parent = gh("GET", "repos/%s/git/commits/%s" % (REPO, target))["parents"][0]["sha"]
        print("revert %s: %s -> %s" % (REPO, head, parent))
        if apply:
            gh("PATCH", "repos/%s/git/refs/heads/%s" % (REPO, branch), {"sha": parent, "force": True})
        return

    base_tree = gh("GET", "repos/%s/git/commits/%s" % (REPO, head))["tree"]["sha"]
    listing = gh("GET", "repos/%s/git/trees/%s?recursive=1" % (REPO, base_tree))
    if listing.get("truncated"):
        raise SystemExit("repo tree listing truncated; cannot prove additivity")
    existing = {e["path"].lower(): e["sha"] for e in listing["tree"] if e["type"] == "blob"}

    todo, skipped, refused = [], [], []
    for dp, _, names in os.walk(STAGE):
        for n in names:
            rel = os.path.relpath(os.path.join(dp, n), STAGE).replace(os.sep, "/")
            if rel.endswith(SKIP_EXT):
                continue
            dst = PREFIX + rel + ".bz2"
            if dst.lower() in existing:
                if rel not in REPLACE and not rel.lower().startswith(OWN_PREFIXES):
                    skipped.append(dst)
                    continue
                data = bz2.compress(open(os.path.join(STAGE, rel), "rb").read(), 9)
                if hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest() == existing[dst.lower()]:
                    continue      # unchanged
                if rel not in REPLACE:
                    refused.append(dst)
                    continue
            todo.append((rel, dst, dst.lower() in existing))
    if refused:
        raise SystemExit("refusing to replace %d tf2cc-owned file(s) in place (clients keep their old copy; "
                         "run tools/tf2c/stage_tf2c.py, whose version_assets.py gives them new paths):\n  %s"
                         % (len(refused), "\n  ".join(refused[:40])))
    todo.sort()
    print("%s@%s: %d file(s) to publish, %d already present (left untouched)" % (REPO, branch, len(todo), len(skipped)))
    for rel, dst, replace in todo:
        if replace:
            print("  REPLACE %s" % dst)
    for d in skipped[:40]:
        print("  skip    %s" % d)
    if not apply or not todo:
        print("(dry run)" if not apply else "nothing to do")
        return

    entries = []
    reused = 0
    for i, (rel, dst, _) in enumerate(todo):
        data = bz2.compress(open(os.path.join(STAGE, rel), "rb").read(), 9)
        sha = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
        if blob_exists(sha):
            reused += 1     # left over from an earlier attempt
        else:
            sha = gh("POST", "repos/%s/git/blobs" % REPO, {"content": base64.b64encode(data).decode(), "encoding": "base64"})["sha"]
        entries.append({"path": dst, "mode": "100644", "type": "blob", "sha": sha})
        if i % 50 == 0:
            print("  blobs %d/%d (reused %d)" % (i + 1, len(todo), reused), flush=True)
    # One big tree request times out against this repo's ~3k-entry tree: build it in chunks.
    tree_sha = base_tree
    for k in range(0, len(entries), 60):
        tree_sha = gh("POST", "repos/%s/git/trees" % REPO, {"base_tree": tree_sha, "tree": entries[k:k + 60]})["sha"]
        print("  tree %d/%d" % (min(k + 60, len(entries)), len(entries)), flush=True)
    tree = {"sha": tree_sha}
    msg = ("tf2cc (TF2 Classified): Mercenary assets + merged April Fools/Merc item schema\n\n"
           "%d file(s): new files, files under tf2cc-owned paths (%s)\n"
           "and scripts/items/custom_items_game.txt (April Fools pack unchanged; only the hidden\n"
           "tf2cc Merc items differ). No other existing file is touched.\n"
           "Generated by tf2cc-rework tools/tf2c/fastdl_publish_tf2c.py." % (len(entries), ", ".join(OWN_PREFIXES)))
    commit = gh("POST", "repos/%s/git/commits" % REPO, {"message": msg, "tree": tree["sha"], "parents": [head]})
    gh("PATCH", "repos/%s/git/refs/heads/%s" % (REPO, branch), {"sha": commit["sha"]})
    print("published commit %s (revert: --revert %s --apply)" % (commit["sha"], commit["sha"]))
    with open(LOG, "a", encoding="utf-8", newline="\n") as f:
        f.write("%s\t%s\t%s\t%d\n" % (REPO, head, commit["sha"], len(entries)))
    hist_path = os.path.join(ROOT, "deploy", "fastdl_first_published.json")
    hist = json.load(open(hist_path)) if os.path.exists(hist_path) else {"first": {}, "modified_in_place": []}
    for (rel, dst, replace), e in zip(todo, entries):
        if not replace:
            hist["first"].setdefault(rel.lower(), e["sha"])
    json.dump(hist, open(hist_path, "w", encoding="utf-8", newline="\n"), indent=0, sort_keys=True)


if __name__ == "__main__":
    main()
