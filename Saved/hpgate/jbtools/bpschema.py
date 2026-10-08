"""Parse FField ChildProperties of cooked UStruct exports (UserDefinedStruct / BlueprintGeneratedClass / Function)
to recover Blueprint property schemas, then decode unversioned property blobs (CDOs, DataTable rows) with them.

Layout (validated on STR_ZombieMapInfo):
  UObject: unversioned header (+ values) for the struct object's own UPROPERTYs, int32 bHasGuid(+guid)
  UField:  int32 Next
  UStruct: int32 SuperStruct, TArray<int32> Children, int32 NumProps, NumProps x SingleField,
           int32 BytecodeBufferSize, int32 SerializedScriptSize, script
  SingleField: FName Type; FField: FName Name, u32 Flags; FProperty: i32 ArrayDim, u64 PropertyFlags, u16 RepIndex,
           FName RepNotifyFunc, u8 BlueprintReplicationCondition; then per-type payload.
"""
import os, struct, sys
from names_dump import Pkg, fstr
from usmap import Usmap

USMAP = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'Bodycam-5.5.4-0+UE5-c838a8ac.usmap')


def read_fname(p, b, o):
    i, n = struct.unpack_from('<ii', b, o)
    s = p.nm(i)
    if n: s += '_%d' % (n - 1)
    return s, o + 8


def short(name):
    """strip the _N_GUID suffix Blueprint user structs put on member names"""
    parts = name.split('_')
    if len(parts) >= 3 and len(parts[-1]) == 32 and parts[-2].isdigit():
        return '_'.join(parts[:-2])
    return name


class FieldParser:
    def __init__(self, p):
        self.p = p

    def single(self, b, o):
        t, o = read_fname(self.p, b, o)
        if t == 'None':
            return None, o
        name, o = read_fname(self.p, b, o)
        flags, = struct.unpack_from('<I', b, o); o += 4
        dim, pflags = struct.unpack_from('<iQ', b, o); o += 12
        rep, = struct.unpack_from('<H', b, o); o += 2
        repfn, o = read_fname(self.p, b, o)
        cond = b[o]; o += 1
        o += 4                                  # measured: 4 extra bytes after BlueprintReplicationCondition in this 5.5.4 build
        typ, o = self.payload(t, b, o)
        return dict(name=name, type=typ, dim=dim, pflags=pflags, ftype=t), o

    def refname(self, idx):
        if idx == 0: return 'None'
        return self.p.ref(idx)

    def payload(self, t, b, o):
        p = self.p
        if t == 'ArrayProperty':
            inner, o = self.single(b, o); return ('Array', inner['type']), o
        if t == 'SetProperty':
            inner, o = self.single(b, o); return ('Set', inner['type']), o
        if t == 'MapProperty':
            k, o = self.single(b, o); v, o = self.single(b, o); return ('Map', k['type'], v['type']), o
        if t == 'OptionalProperty':
            inner, o = self.single(b, o); return ('Optional', inner['type']), o
        if t == 'BoolProperty':
            o += 6; return ('BoolProperty',), o   # measured: FieldSize,ByteOffset,ByteMask,FieldMask,BoolSize,NativeBool
        if t == 'ByteProperty':
            e, = struct.unpack_from('<i', b, o); o += 4
            return (('Enum', self.refname(e), ('ByteProperty',)) if e else ('ByteProperty',)), o
        if t == 'EnumProperty':
            e, = struct.unpack_from('<i', b, o); o += 4
            inner, o = self.single(b, o)
            return ('Enum', self.refname(e), inner['type']), o
        if t in ('ObjectProperty', 'WeakObjectProperty', 'LazyObjectProperty', 'SoftObjectProperty', 'InterfaceProperty'):
            c, = struct.unpack_from('<i', b, o); o += 4
            return (t, self.refname(c)), o
        if t in ('ClassProperty', 'SoftClassProperty'):
            c, m = struct.unpack_from('<ii', b, o); o += 8
            return (t, self.refname(c), self.refname(m)), o
        if t == 'StructProperty':
            s, = struct.unpack_from('<i', b, o); o += 4
            return ('Struct', self.refname(s)), o
        if t in ('DelegateProperty', 'MulticastDelegateProperty', 'MulticastInlineDelegateProperty', 'MulticastSparseDelegateProperty'):
            o += 4; return (t,), o
        if t == 'FieldPathProperty':
            _, o = read_fname(p, b, o); return (t,), o
        return (t,), o

    def struct_fields(self, e, skip_uobject=True):
        """fields of a UStruct-derived export (UserDefinedStruct/BlueprintGeneratedClass/Function)."""
        b = self.p.data(e); o = 0
        # UObject part: unversioned header for the object's own class props. Walk fragments to skip values we cannot size:
        # UserDefinedStruct: Guid (16 bytes) present; BlueprintGeneratedClass: many props -> we search for the field list instead.
        cls = self.p.ref(e['cls'])
        if cls == 'UserDefinedStruct':
            fr, o = self._frags(b, 0)
            nvals = sum(f[1] for f in fr)
            if nvals: o += 16 * nvals          # Guid only
            o += 4                              # bHasGuid
            o += 4                              # Next
            sup, = struct.unpack_from('<i', b, o); o += 4   # SuperStruct (Children array is NOT serialized in this build: measured)
            nprops, = struct.unpack_from('<i', b, o); o += 4
            fields = []
            for _ in range(nprops):
                f, o = self.single(b, o); fields.append(f)
            return sup, fields, o
        # generic: scan for a plausible (Next=0 or import, SuperStruct, Children, NumProps) tuple where every field parses
        best = None
        for start in range(0, min(len(b), 4000)):
            try:
                sup, = struct.unpack_from('<i', b, start)
                o2 = start + 4
                nprops, = struct.unpack_from('<i', b, o2); o2 += 4
                nchild = 0
                if not (0 <= nprops < 2000): continue
                fields = []
                ok = True
                for _ in range(nprops):
                    f, o2 = self.single(b, o2)
                    if f is None or f['ftype'] not in KNOWN or f['name'] == 'None': ok = False; break
                    fields.append(f)
                if not ok: continue
                if nprops == 0 and nchild == 0: continue
                return sup, fields, o2
            except Exception:
                continue
        return None, [], 0

    def _frags(self, b, o):
        fr = []
        while o + 2 <= len(b):
            f = struct.unpack_from('<H', b, o)[0]; o += 2
            fr.append((f & 0x7F, (f >> 9) & 0x7F, bool(f & 0x80), bool(f & 0x100)))
            if f & 0x100: break
        return fr, o


KNOWN = {'ArrayProperty', 'SetProperty', 'MapProperty', 'BoolProperty', 'ByteProperty', 'EnumProperty', 'ObjectProperty', 'WeakObjectProperty',
         'SoftObjectProperty', 'InterfaceProperty', 'ClassProperty', 'SoftClassProperty', 'StructProperty', 'DelegateProperty',
         'MulticastDelegateProperty', 'MulticastInlineDelegateProperty', 'MulticastSparseDelegateProperty', 'IntProperty', 'FloatProperty',
         'DoubleProperty', 'NameProperty', 'StrProperty', 'TextProperty', 'Int64Property', 'UInt32Property', 'UInt64Property', 'Int8Property',
         'Int16Property', 'UInt16Property', 'FieldPathProperty', 'LazyObjectProperty', 'OptionalProperty'}


class Registry:
    """schemas for BP structs/classes (by export name) collected from a set of extracted packages + usmap for natives."""
    def __init__(self, usmap_path=USMAP):
        self.u = Usmap(usmap_path)
        self.bp = {}       # name -> (super_name, [fields])
        self.pkgs = {}

    def add_pkg(self, base):
        p = Pkg(base); self.pkgs[base] = p
        fp = FieldParser(p)
        for e in p.exports:
            cls = p.ref(e['cls'])
            if cls in ('UserDefinedStruct', 'BlueprintGeneratedClass', 'WidgetBlueprintGeneratedClass', 'AnimBlueprintGeneratedClass'):
                sup, fields, _ = fp.struct_fields(e)
                supname = p.ref(sup) if (sup and cls == 'UserDefinedStruct') else (p.ref(e['sup']) if e['sup'] else None)
                self.bp[e['name']] = (supname, fields, p)
        return p

    def schema(self, cls):
        """[(owner, idx, name, type, dim)] own props first then supers (matches usmap.schema)."""
        out = []
        cur = cls
        while cur:
            if cur in self.bp:
                sup, fields, _ = self.bp[cur]
                for i, f in enumerate(fields):
                    out.append((cur, i, f['name'], f['type'], f['dim']))
                cur = sup
            else:
                try:
                    out.extend(self.u.schema(cur))
                except Exception:
                    out.append((cur, 0, '<unknown class %s>' % cur, ('?',), 1))
                break
        return out


def dump_fields(reg, name):
    sup, fields, p = reg.bp[name]
    print('== %s : %s' % (name, sup))
    for f in fields:
        print('   %-60s dim=%d %s' % (f['name'], f['dim'], f['type']))


if __name__ == '__main__':
    reg = Registry()
    for b in sys.argv[1:]:
        p = reg.add_pkg(b)
        for n, (sup, fields, pp) in reg.bp.items():
            if pp is p: dump_fields(reg, n)
