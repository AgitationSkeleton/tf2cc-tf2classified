#!/usr/bin/env python3
"""Merge tf2cc's items (schema/tf2cc_items.txt) into a TF2 Classified custom_items_game.txt.

  python -I tools/tf2c/merge_schema.py <tf2cc_items.txt> <out custom_items_game.txt> [<existing custom_items_game.txt>]

Without an existing file the output holds only the tf2cc items. With one, every one of its
sections and items is kept as it is and the tf2cc items (ids 30099+) are added or replaced.
TF2 Classified build 5205 reads custom/<folder>/scripts/items/custom_items_game.txt; a VPK in
custom/ that carries its own copy wins over loose files (see README).
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kv  # noqa: E402


def main():
    frag, out = sys.argv[1], sys.argv[2]
    base = sys.argv[3] if len(sys.argv) > 3 else None
    froot, _ = kv.load(frag, "latin-1")
    fitems = froot["items_game"]["items"]
    if base:
        broot, _ = kv.load(base, "latin-1")
        game = broot["items_game"]
        items = game.get("items")
        if items is None:
            items = kv.KV()
            game.add("items", items)
        ids = set(k for k, _ in fitems.items())
        items.pairs = [(k, v) for k, v in items.pairs if k not in ids]
        for k, v in fitems.items():
            items.add(k, v)
        root = broot
    else:
        root = froot
    with open(out, "w", encoding="latin-1", newline="\n") as f:
        f.write(kv.dump(root, 0))
    print("wrote %s (%d tf2cc items)" % (out, len(fitems.pairs)))


if __name__ == "__main__":
    main()
