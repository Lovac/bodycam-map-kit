"""Dump name table / imports / exports / literals of cooked UE5 packages (.uasset|.umap + .uexp).

usage: python names_dump.py <pkg base path without ext> [...]  -> writes names_<Name>.txt next to this script
Also usable as a module: Pkg(base).
"""
import struct, sys, os, re

HERE = os.path.dirname(os.path.abspath(__file__))

def fstr(b, o):
    n, = struct.unpack_from("<i", b, o); o += 4
    if n < 0:
        s = b[o:o + (-n) * 2].decode("utf-16-le", "replace")[:-1]; o += (-n) * 2
    else:
        s = b[o:o + n].decode("latin-1")[:-1] if n else ""; o += n
    return s, o

class Pkg:
    def __init__(self, base):
        for ext in (".uasset", ".umap"):
            if os.path.exists(base + ext):
                self.hdr_path = base + ext; break
        else:
            raise FileNotFoundError(base)
        d = open(self.hdr_path, "rb").read(); self.d = d
        self.uexp = open(base + ".uexp", "rb").read() if os.path.exists(base + ".uexp") else b""
        self.base = base
        o = 24; ncv, = struct.unpack_from("<i", d, o); o += 4 + ncv * 20
        self.total_hdr, = struct.unpack_from("<i", d, o); o += 4
        self.pkgname, o = fstr(d, o)
        self.flags, nc, no = struct.unpack_from("<Iii", d, o); o += 12
        sopc, sopo = struct.unpack_from("<ii", d, o); o += 8
        gtc, gto = struct.unpack_from("<ii", d, o); o += 8
        ec, eo, ic, io, dep_o = struct.unpack_from("<iiiii", d, o); o += 20
        sprc, spro, sno, tho = struct.unpack_from("<iiii", d, o); o += 16
        self.counts = dict(names=nc, imports=ic, exports=ec)
        # names
        self.names = []; p = no
        for _ in range(nc):
            s, p = fstr(d, p); p += 4; self.names.append(s)
        # imports (size auto-detected from table spacing)
        isz = (eo - io) // ic if ic else 40
        self.import_size = isz
        self.imports = []; p = io
        for _ in range(ic):
            cp, cn, outer, on = (struct.unpack_from("<i", d, p)[0], struct.unpack_from("<i", d, p + 8)[0],
                                 struct.unpack_from("<i", d, p + 16)[0], struct.unpack_from("<i", d, p + 20)[0])
            onum = struct.unpack_from("<i", d, p + 24)[0]   # FName number: 'X_0_1' is stored as 'X_0' + number 2
            pn = struct.unpack_from("<i", d, p + 28)[0] if isz >= 36 else 0
            self.imports.append(dict(clspkg=self.nm(cp), cls=self.nm(cn), outer=outer, name=self.nm(on, onum), pkg=self.nm(pn)))
            p += isz
        # exports
        esz = (dep_o - eo) // ec if ec else 0
        self.export_size = esz
        self.exports = []; p = eo
        for _ in range(ec):
            cls, sup, tmpl, outer = struct.unpack_from("<iiii", d, p)
            on, onum = struct.unpack_from("<ii", d, p + 16)
            oflags, = struct.unpack_from("<I", d, p + 24)
            ssize, soff = struct.unpack_from("<qq", d, p + 28)
            self.exports.append(dict(cls=cls, sup=sup, tmpl=tmpl, outer=outer, name=self.nm(on, onum), flags=oflags, size=ssize, off=soff))
            p += esz
        # soft object paths / soft package refs (asset dependencies by name)
        self.soft_pkgs = []
        p = spro
        for _ in range(sprc):
            idx, = struct.unpack_from("<i", d, p); p += 8
            self.soft_pkgs.append(self.nm(idx))

    def nm(self, i, number=0):
        s = self.names[i] if 0 <= i < len(self.names) else "<bad %d>" % i
        return s + '_%d' % (number - 1) if number > 0 else s

    def ref(self, idx):
        if idx > 0 and idx - 1 < len(self.exports): return self.exports[idx - 1]["name"]
        if idx < 0 and -idx - 1 < len(self.imports): return self.imports[-idx - 1]["name"]
        return "None"

    def full_import(self, idx):
        """dotted outer chain for an import index (negative)."""
        parts = []
        while idx < 0 and -idx - 1 < len(self.imports):
            im = self.imports[-idx - 1]; parts.append(im["name"]); idx = im["outer"]
        return ".".join(reversed(parts))

    def data(self, e):
        s = e["off"] - self.total_hdr
        if s < 0 or not self.uexp: return b""
        return self.uexp[s:s + e["size"]]

    # ---- heuristics over serialized export bytes ----
    def name_refs(self, blob):
        """FName pairs (idx<nc, number small) found at any 4-byte aligned-or-not offset."""
        found = {}
        nc = len(self.names)
        for o in range(0, len(blob) - 7):
            idx, num = struct.unpack_from("<ii", blob, o)
            if 0 <= idx < nc and 0 <= num < 64:
                found[idx] = found.get(idx, 0) + 1
        return found

    def import_refs(self, blob):
        """negative int32 package indices that resolve to imports."""
        found = {}
        ni = len(self.imports)
        for o in range(0, len(blob) - 3):
            v, = struct.unpack_from("<i", blob, o)
            if v < 0 and -v - 1 < ni:
                found[v] = found.get(v, 0) + 1
        return found

def literals(blob, minlen=3):
    """FString-shaped literals (int32 len + chars + NUL), ASCII and UTF-16."""
    out = []
    n = len(blob)
    o = 0
    while o < n - 4:
        ln, = struct.unpack_from("<i", blob, o)
        if minlen + 1 <= ln <= 2000 and o + 4 + ln <= n:
            s = blob[o + 4:o + 4 + ln]
            if s[-1] == 0 and all(32 <= c < 127 for c in s[:-1]):
                out.append((o, s[:-1].decode("latin-1"))); o += 4 + ln; continue
        if -2000 <= ln <= -(minlen + 1) and o + 4 + (-ln) * 2 <= n:
            s = blob[o + 4:o + 4 + (-ln) * 2]
            try:
                t = s.decode("utf-16-le")
            except Exception:
                t = None
            if t and t[-1] == "\0" and all(32 <= ord(c) < 0x3000 for c in t[:-1]):
                out.append((o, t[:-1])); o += 4 + (-ln) * 2; continue
        o += 1
    return out

def raw_strings(blob, minlen=5):
    return [m.group().decode("latin-1") for m in re.finditer(rb"[\x20-\x7e]{%d,}" % minlen, blob)]

def dump(base, outdir=HERE):
    p = Pkg(base)
    name = os.path.basename(base)
    lines = []
    w = lines.append
    w("PACKAGE %s  (%s)" % (p.pkgname, p.hdr_path))
    w("names=%d imports=%d exports=%d import_size=%d export_size=%d total_hdr=%d uexp=%d" % (
        p.counts["names"], p.counts["imports"], p.counts["exports"], p.import_size, p.export_size, p.total_hdr, len(p.uexp)))
    w("")
    w("== NAMES (%d) ==" % len(p.names))
    for i, s in enumerate(p.names): w("%5d  %s" % (i, s))
    w("")
    w("== IMPORTS (%d) ==" % len(p.imports))
    for i, im in enumerate(p.imports):
        w("%5d  %-24s %-40s  outer=%s  pkg=%s" % (-(i + 1), im["cls"], im["name"], p.ref(im["outer"]), im["pkg"]))
    w("")
    w("== SOFT PACKAGE REFS (%d) ==" % len(p.soft_pkgs))
    for s in p.soft_pkgs: w("       %s" % s)
    w("")
    w("== EXPORTS (%d) ==" % len(p.exports))
    for i, e in enumerate(p.exports):
        w("%5d  %-24s %-48s outer=%-24s super=%-20s size=%d" % (i + 1, p.ref(e["cls"]), e["name"], p.ref(e["outer"]), p.ref(e["sup"]), e["size"]))
    w("")
    # per-function reference scan
    funcs = [e for e in p.exports if p.ref(e["cls"]) in ("Function",)]
    if funcs:
        w("== FUNCTION EXPORTS: referenced names / imports (heuristic scan of serialized bytes) ==")
        for e in funcs:
            blob = p.data(e)
            nr = p.name_refs(blob); ir = p.import_refs(blob)
            w("")
            w("-- %s  (%d bytes)" % (e["name"], len(blob)))
            w("   names: " + ", ".join(p.names[i] for i, _ in sorted(nr.items(), key=lambda kv: -kv[1])))
            w("   imports: " + ", ".join(p.full_import(v) for v, _ in sorted(ir.items(), key=lambda kv: -kv[1])))
            lits = literals(blob)
            if lits: w("   literals: " + " | ".join(repr(s) for _, s in lits))
        w("")
    # whole-uexp literals
    w("== UEXP LITERALS (FString-shaped) ==")
    for o, s in literals(p.uexp):
        w("  @%-8d %r" % (o, s))
    w("")
    w("== UEXP RAW PRINTABLE RUNS (>=6) ==")
    seen = set()
    for s in raw_strings(p.uexp, 6):
        if s not in seen:
            seen.add(s); w("  %s" % s)
    out = os.path.join(outdir, "names_%s.txt" % name)
    open(out, "w", encoding="utf-8").write("\n".join(lines))
    return p, out

if __name__ == "__main__":
    for b in sys.argv[1:]:
        b = re.sub(r"\.(uasset|umap|uexp)$", "", b)
        p, out = dump(b)
        print("%-40s names=%d imports=%d exports=%d -> %s" % (os.path.basename(b), len(p.names), len(p.imports), len(p.exports), out))
