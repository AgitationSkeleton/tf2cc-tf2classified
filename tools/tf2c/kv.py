"""Small Valve KeyValues reader/writer for the TF2 Classified tools.

Handles quoted and unquoted tokens, // comments, [$CONDITION] tags (dropped) and
#base/#include lines (returned separately). Keys are case-preserving; lookups
via get() are case-insensitive. Duplicate keys keep every value in order
(KV.items_all) and get() returns the first.
"""
import re

_TOK = re.compile(r'\s+|//[^\n]*|"((?:[^"\\]|\\.)*)"|([{}])|\[[^\]\n]*\]|([^\s{}"]+)')


class KV:
    __slots__ = ("pairs",)

    def __init__(self, pairs=None):
        self.pairs = pairs if pairs is not None else []

    def get(self, key, default=None):
        k = key.lower()
        for a, b in self.pairs:
            if a.lower() == k:
                return b
        return default

    def all(self, key):
        k = key.lower()
        return [b for a, b in self.pairs if a.lower() == k]

    def keys(self):
        return [a for a, _ in self.pairs]

    def items(self):
        return list(self.pairs)

    def blocks(self):
        return [(a, b) for a, b in self.pairs if isinstance(b, KV)]

    def __contains__(self, key):
        return self.get(key) is not None

    def __getitem__(self, key):
        v = self.get(key)
        if v is None:
            raise KeyError(key)
        return v

    def set(self, key, value):
        k = key.lower()
        for i, (a, _) in enumerate(self.pairs):
            if a.lower() == k:
                self.pairs[i] = (a, value)
                return
        self.pairs.append((key, value))

    def add(self, key, value):
        self.pairs.append((key, value))


def tokens(text):
    for m in _TOK.finditer(text):
        if m.group(1) is not None:
            yield m.group(1)
        elif m.group(2):
            yield m.group(2)
        elif m.group(3):
            yield m.group(3)


def parse(text):
    """Returns (root KV, [base/include file names])."""
    bases = re.findall(r'^\s*#(?:base|include)\s+"?([^"\s]+)"?', text, re.M)
    text = re.sub(r'^\s*#(?:base|include)[^\n]*', "", text, flags=re.M)
    toks = list(tokens(text))
    pos = 0

    def block():
        nonlocal pos
        kv = KV()
        while pos < len(toks):
            k = toks[pos]
            pos += 1
            if k == "}":
                return kv
            if pos >= len(toks):
                break
            v = toks[pos]
            pos += 1
            if v == "{":
                kv.add(k, block())
            else:
                kv.add(k, v)
        return kv

    return block(), bases


def load(path, encoding="utf-8"):
    return parse(open(path, encoding=encoding, errors="replace").read())


def dump(kv, indent=0):
    out = []
    pad = "\t" * indent
    for k, v in kv.pairs:
        if isinstance(v, KV):
            out.append('%s"%s"\n%s{\n%s%s}' % (pad, k, pad, dump(v, indent + 1), pad))
        else:
            out.append('%s"%s"\t"%s"' % (pad, k, str(v).replace('"', "'")))
    return "\n".join(out) + ("\n" if out else "")
