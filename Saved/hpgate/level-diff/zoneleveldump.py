"""Read-only, unversioned-aware dump of every hardpoint/bomb zone actor in cooked level packages.

usage: zoneleveldump.py <out.json> <pkg base> [<pkg base> ...]      (pkg base = path without .umap/.uexp)

For each HardPointZone_C / BP_PointZonePreview_C / BombZone_C export (plus anything whose class name contains
Zone/Hardpoint) it records: export index, FULL FName (index+number), class, outer level, template, object flags,
bNotForClient/bNotForServer, position in the owning Level's serialized Actors array, every serialized property of the
actor and of each subobject (components), decoded against the usmap (natives) + Blueprint FField schemas parsed from
the class packages (HardPointZone_C, BP_PointZonePreview_C, BombZone_C, STR_RANGE). Unversioned property data holds only
values that DIFFER from the archetype; missing properties = archetype default (also dumped: the BP _GEN_VARIABLE
templates). Offsets printed are relative to the .uexp file.
"""
import json, os, struct, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'jbtools'))   # 18 Sep: copied into the project
from names_dump import Pkg
from bpschema import Registry

HERE = os.path.dirname(os.path.abspath(__file__))
EX = os.path.join(HERE, '..', 'data', 'extract')
CLASS_PKGS = [os.path.join(EX, r'pakchunk26-Windows\GM\Gamemode\HardPoint\HardPointZone'),
              os.path.join(EX, r'pakchunk26-Windows\GM\Gamemode\HardPoint\BP_PointZonePreview'),
              os.path.join(EX, r'pakchunk26-Windows\GM\Gamemode\BodyBomb\BombZone'),
              os.path.join(EX, r'pakchunk18-Windows\BodycamWeapons\Core\DATA\STR\WEP\STR_RANGE')]
import glob as _g
CLASS_PKGS += [f[:-7] for f in _g.glob(os.path.join(EX, '*', '**', 'STR_PlantZone.uasset'), recursive=True)]

BINARY_STRUCTS = {
    'Vector': '<3d', 'Rotator': '<3d', 'Vector2D': '<2d', 'Vector4': '<4d', 'Quat': '<4d', 'Plane': '<4d',
    'LinearColor': '<4f', 'IntPoint': '<2i', 'IntVector': '<3i', 'Vector3f': '<3f', 'Rotator3f': '<3f',
    'Box': '<3d3dB', 'Box2D': '<2d2dB', 'FrameNumber': '<i', 'DateTime': '<q', 'Timespan': '<q',
}


class Dec:
    def __init__(self, reg, q):
        self.r = reg; self.q = q; self.u = reg.u

    # -------- names / refs
    def fname(self, b, o):
        i, n = struct.unpack_from('<ii', b, o)
        return self.q.nm(i) + ('_%d' % (n - 1) if n else ''), o + 8

    def objref(self, idx):
        if idx == 0: return 'None'
        if idx < 0: return 'import:' + self.q.full_import(idx)
        return 'export%d:%s' % (idx, full_export_name(self.q, idx - 1))

    def fstring(self, b, o):
        n, = struct.unpack_from('<i', b, o); o += 4
        if n == 0: return '', o
        if n > 0: return b[o:o + n - 1].decode('utf-8', 'replace'), o + n
        return b[o:o - 2 * n - 2].decode('utf-16-le', 'replace'), o - 2 * n

    # -------- schema
    def schema(self, cls):
        out = []
        for owner, idx, name, t, dim in self.r.schema(cls):
            for k in range(max(1, dim)):
                out.append((owner, name if dim <= 1 else '%s[%d]' % (name, k), t))
        return out

    def is_struct_known(self, s):
        return s in self.r.bp or s in self.u.structs

    # -------- values
    def value(self, b, o, t):
        k = t[0]
        if k == 'Enum':
            inner = t[2] if len(t) > 2 else ('ByteProperty',)
            v, o = self.value(b, o, inner)
            names = self.u.enums.get(t[1])
            if names and isinstance(v, int) and 0 <= v < len(names):
                return '%s(%d)' % (names[v], v), o
            return v, o
        if k == 'BoolProperty': return bool(b[o]), o + 1
        fmt = {'ByteProperty': '<B', 'Int8Property': '<b', 'Int16Property': '<h', 'UInt16Property': '<H', 'IntProperty': '<i',
               'UInt32Property': '<I', 'FloatProperty': '<f', 'Int64Property': '<q', 'UInt64Property': '<Q', 'DoubleProperty': '<d'}.get(k)
        if fmt:
            v, = struct.unpack_from(fmt, b, o); return v, o + struct.calcsize(fmt)
        if k == 'NameProperty': return self.fname(b, o)
        if k in ('ObjectProperty', 'WeakObjectProperty', 'InterfaceProperty', 'ClassProperty'):
            idx, = struct.unpack_from('<i', b, o); return self.objref(idx), o + 4
        if k == 'LazyObjectProperty': return b[o:o + 16].hex(), o + 16
        if k in ('SoftObjectProperty', 'SoftClassProperty', 'AssetObjectProperty'):
            if getattr(self.q, 'sopc', 0):
                idx, = struct.unpack_from('<i', b, o); return 'softpath#%d' % idx, o + 4
            p, o = self.fname(b, o); a, o = self.fname(b, o); s, o = self.fstring(b, o)
            return '%s.%s%s' % (p, a, (':' + s) if s else ''), o
        if k in ('StrProperty', 'Utf8StrProperty', 'AnsiStrProperty'): return self.fstring(b, o)
        if k == 'TextProperty': return self.text(b, o)
        if k == 'Array':
            n, = struct.unpack_from('<i', b, o); o += 4
            if not (0 <= n < 100000): raise ValueError('bad array count %d' % n)
            out = []
            for _ in range(n):
                v, o = self.value(b, o, t[1]); out.append(v)
            return out, o
        if k == 'Set':
            nr, = struct.unpack_from('<i', b, o); o += 4
            for _ in range(nr): _, o = self.value(b, o, t[1])
            n, = struct.unpack_from('<i', b, o); o += 4
            out = []
            for _ in range(n):
                v, o = self.value(b, o, t[1]); out.append(v)
            return out, o
        if k == 'Map':
            nr, = struct.unpack_from('<i', b, o); o += 4
            for _ in range(nr): _, o = self.value(b, o, t[1])
            n, = struct.unpack_from('<i', b, o); o += 4
            out = []
            for _ in range(n):
                kv, o = self.value(b, o, t[1]); vv, o = self.value(b, o, t[2]); out.append([kv, vv])
            return out, o
        if k == 'Optional':
            has = b[o]; o += 1
            if not has: return None, o
            return self.value(b, o, t[1])
        if k in ('DelegateProperty',):
            idx, = struct.unpack_from('<i', b, o); fn, o2 = self.fname(b, o + 4); return '%s::%s' % (self.objref(idx), fn), o2
        if k in ('MulticastDelegateProperty', 'MulticastInlineDelegateProperty', 'MulticastSparseDelegateProperty'):
            n, = struct.unpack_from('<i', b, o); o += 4; out = []
            for _ in range(n):
                idx, = struct.unpack_from('<i', b, o); fn, o = self.fname(b, o + 4); out.append('%s::%s' % (self.objref(idx), fn))
            return out, o
        if k == 'FieldPathProperty':
            n, = struct.unpack_from('<i', b, o); o += 4; parts = []
            for _ in range(n):
                s, o = self.fname(b, o); parts.append(s)
            owner, = struct.unpack_from('<i', b, o); o += 4
            return '.'.join(parts) + '@' + self.objref(owner), o
        if k == 'Struct':
            return self.struct(b, o, t[1])
        raise ValueError('unsized type %s' % (t,))

    def text(self, b, o):
        flags, = struct.unpack_from('<I', b, o); o += 4
        ht = struct.unpack_from('<b', b, o)[0]; o += 1
        if ht == -1:
            has = struct.unpack_from('<i', b, o)[0]; o += 4
            if has:
                s, o = self.fstring(b, o); return 'Text(invariant %r)' % s, o
            return 'Text(empty)', o
        if ht == 0:
            ns, o = self.fstring(b, o); key, o = self.fstring(b, o); src, o = self.fstring(b, o)
            return 'Text(ns=%r key=%r src=%r)' % (ns, key, src), o
        if ht == 11:
            tab, o = self.fname(b, o); key, o = self.fstring(b, o); return 'Text(table=%s key=%r)' % (tab, key), o
        raise ValueError('text history %d' % ht)

    def struct(self, b, o, sname):
        if sname in BINARY_STRUCTS:
            fmt = BINARY_STRUCTS[sname]; v = struct.unpack_from(fmt, b, o)
            return [round(x, 4) if isinstance(x, float) else x for x in v], o + struct.calcsize(fmt)
        if sname == 'Color': return list(b[o:o + 4]), o + 4
        if sname == 'Guid': return b[o:o + 16].hex(), o + 16
        if sname in ('SoftObjectPath', 'SoftClassPath'):
            return self.value(b, o, ('SoftObjectProperty',))
        if sname == 'GameplayTagContainer':
            n, = struct.unpack_from('<i', b, o); o += 4; out = []
            for _ in range(n):
                s, o = self.fname(b, o); out.append(s)
            return out, o
        if sname in ('PerPlatformFloat', 'PerPlatformInt', 'PerPlatformBool', 'PerQualityLevelInt', 'PerQualityLevelFloat'):
            cooked = struct.unpack_from('<i', b, o)[0]; o += 4
            if sname == 'PerPlatformBool': v = bool(b[o]); o += 1
            else:
                v, = struct.unpack_from('<f' if 'Float' in sname else '<i', b, o); o += 4
            if 'Quality' in sname:
                n, = struct.unpack_from('<i', b, o); o += 4 + n * 8
            return {'Default': v, 'cooked': cooked}, o
        if sname == 'PointerToUberGraphFrame': return '<ubergraphframe>', o
        if not self.is_struct_known(sname):
            raise ValueError('unknown struct ' + sname)
        return self.props(b, o, sname)

    # ---------------- tagged (versioned) packages: UE5 >= PROPERTY_TAG_COMPLETE_TYPE_NAME (1012)
    def ttree(self, b, o):
        n, o = self.fname(b, o); c, = struct.unpack_from('<i', b, o); o += 4
        kids = []
        for _ in range(c):
            k, o = self.ttree(b, o); kids.append(k)
        return (n, kids), o

    def tvalue(self, b, o, tt, size, flags):
        name, kids = tt
        if name == 'BoolProperty':
            return bool(flags & 0x10), o
        if name == 'StructProperty':
            sname = kids[0][0] if kids else '?'
            if sname in BINARY_STRUCTS or sname in ('Color', 'Guid', 'SoftObjectPath', 'SoftClassPath', 'GameplayTagContainer') or sname.startswith('PerPlatform') or sname.startswith('PerQuality'):
                return self.struct(b, o, sname)
            return self.tprops(b, o, top=False)
        if name == 'ByteProperty':
            if size == 8:
                return self.fname(b, o)
            return b[o], o + 1
        if name == 'EnumProperty':
            return self.fname(b, o)
        if name in ('ArrayProperty', 'SetProperty'):
            inner = kids[0]
            if name == 'SetProperty':
                nr, = struct.unpack_from('<i', b, o); o += 4
            n, = struct.unpack_from('<i', b, o); o += 4
            out = []
            for _ in range(n):
                v, o = self.tinner(b, o, inner); out.append(v)
            return out, o
        if name == 'MapProperty':
            nr, = struct.unpack_from('<i', b, o); o += 4
            n, = struct.unpack_from('<i', b, o); o += 4
            out = []
            for _ in range(n):
                kv, o = self.tinner(b, o, kids[0]); vv, o = self.tinner(b, o, kids[1]); out.append([kv, vv])
            return out, o
        return self.value(b, o, (name,))

    def tinner(self, b, o, tt):
        name, kids = tt
        if name == 'BoolProperty': return bool(b[o]), o + 1
        if name == 'StructProperty':
            sname = kids[0][0] if kids else '?'
            if sname in BINARY_STRUCTS or sname in ('Color', 'Guid', 'SoftObjectPath', 'GameplayTagContainer'):
                return self.struct(b, o, sname)
            return self.tprops(b, o, top=False)
        if name == 'ByteProperty':
            if kids: return self.fname(b, o)
            return b[o], o + 1
        if name == 'EnumProperty': return self.fname(b, o)
        return self.value(b, o, (name,))

    def tprops(self, b, o, top=True, start_off=0):
        if top:
            o += 1                                           # EClassSerializationControlExtension byte (measured 00)
        vals = {}
        while True:
            name, o = self.fname(b, o)
            if name == 'None': break
            tt, o = self.ttree(b, o)
            size, flags = struct.unpack_from('<iB', b, o); o += 5
            idx = 0
            if flags & 1:
                idx, = struct.unpack_from('<i', b, o); o += 4
            if flags & 2: o += 16
            if flags & 4:
                ext = b[o]; o += 1
                if ext & 2: o += 2
            key = name if not idx else '%s[%d]' % (name, idx)
            at = o
            try:
                v, end = self.tvalue(b, o, tt, size, flags)
                if tt[0] != 'BoolProperty' and end != at + size:
                    v = '%s  <size mismatch: decoded %d of %d>' % (v, end - at, size)
            except Exception as ex:
                v = '<undecoded %s %dB @uexp+0x%x: %s  hex=%s>' % (tt, size, start_off + at, ex, b[at:at + min(size, 48)].hex())
            vals[key] = v
            o = at + (0 if tt[0] == 'BoolProperty' else size)
        return vals, o

    def props(self, b, o, cls, start_off=0):
        """unversioned property block for class/struct `cls` at b[o:]; returns ({name: value}, end offset)."""
        if getattr(self, 'tagged', False):
            return self.tprops(b, o, top=(o == 0), start_off=start_off)
        slots = self.schema(cls)
        fr = []
        while True:
            f, = struct.unpack_from('<H', b, o); o += 2
            fr.append((f & 0x7F, (f >> 9) & 0x7F, bool(f & 0x80), bool(f & 0x100)))
            if f & 0x100: break
        present = []; slot = 0
        for skip, num, hz, last in fr:
            slot += skip
            for _ in range(num):
                present.append((slot, hz)); slot += 1
        nz = sum(1 for s, hz in present if hz)
        zbits = []
        if nz:
            nb = 1 if nz <= 8 else 2 if nz <= 16 else ((nz + 31) // 32) * 4
            bits = int.from_bytes(b[o:o + nb], 'little'); o += nb
            zbits = [(bits >> i) & 1 for i in range(nz)]
        vals = {}; zi = 0
        for s, hz in present:
            owner, name, t = slots[s] if s < len(slots) else ('?', '?slot%d' % s, ('?',))
            key = name if name not in vals else '%s#%d' % (name, s)
            if hz:
                z = zbits[zi]; zi += 1
                if z:
                    vals[key] = '<zero>'; continue
            at = o
            try:
                v, o = self.value(b, o, t)
            except Exception as ex:
                vals[key] = '<STOP @uexp+0x%x: %s type=%s>' % (start_off + at, ex, t)
                vals['__stopped__'] = True
                return vals, o
            vals[key] = v
        return vals, o


def full_export_name(q, i):
    """export i (0-based) FName with number, read straight from the export table."""
    d = q.d
    p = q.eo + i * q.export_size
    ni, nn = struct.unpack_from('<ii', d, p + 16)
    return q.nm(ni) + ('_%d' % (nn - 1) if nn else '')


def open_pkg(base):
    q = Pkg(base)
    d = q.d
    o = 24; ncv, = struct.unpack_from('<i', d, o); o += 4 + ncv * 20
    o += 4
    ln, = struct.unpack_from('<i', d, o); o += 4 + (ln if ln >= 0 else -ln * 2)
    flags, nc, no = struct.unpack_from('<Iii', d, o); o += 12
    q.sopc, q.sopo = struct.unpack_from('<ii', d, o); o += 8
    o += 8
    ec, eo, ic, io_, dep = struct.unpack_from('<iiiii', d, o)
    q.eo = eo
    # export extra fields: bForcedExport(+44) bNotForClient(+48) bNotForServer(+52) (UE5.5 96-byte FObjectExport)
    for i, e in enumerate(q.exports):
        p = eo + i * q.export_size
        e['forced'], e['notforclient'], e['notforserver'] = struct.unpack_from('<iii', d, p + 44)
        e['fullname'] = full_export_name(q, i)
    return q


def parse_actor_tail(dec, b, o):
    """after the property block: int32 bHasGuid(+guid); AActor cooked extra = int32 flag, FString ActorLabel, FGuid ActorGuid, FGuid ActorInstanceGuid (measured on Paintball_BP)."""
    try:
        t = {}
        hg, = struct.unpack_from('<i', b, o); o += 4
        if hg: t['objguid'] = b[o:o + 16].hex(); o += 16
        t['flag'], = struct.unpack_from('<i', b, o); o += 4
        t['label'], o = dec.fstring(b, o)
        t['guid1'] = b[o:o + 16].hex(); t['guid2'] = b[o + 16:o + 32].hex(); o += 32
        t['left'] = len(b) - o
        return t
    except Exception as ex:
        return {'error': str(ex)}


def parse_component_tail(dec, b, o):
    """int32 bHasGuid(+guid); UActorComponent: TArray<FSimpleMemberReference> UCSModifiedProperties (int32 parent, FName, FGuid)."""
    try:
        t = {}
        hg, = struct.unpack_from('<i', b, o); o += 4
        if hg: t['objguid'] = b[o:o + 16].hex(); o += 16
        if o + 4 <= len(b):
            n, = struct.unpack_from('<i', b, o); o += 4
            lst = []
            for _ in range(n):
                par, = struct.unpack_from('<i', b, o); nm, _o = dec.fname(b, o + 4); lst.append(nm); o += 28
            t['UCSModifiedProperties'] = lst
        t['left'] = len(b) - o
        return t
    except Exception as ex:
        return {'error': str(ex)}


ZONE_CLASSES = ('HardPointZone_C', 'BP_PointZonePreview_C', 'BombZone_C')


def level_actor_lists(q, dec):
    """Level export -> list of actor export indices from ULevel::Serialize (props block, then TArray<AActor*> Actors)."""
    out = {}
    for i, e in enumerate(q.exports):
        if q.ref(e['cls']) != 'Level': continue
        b = q.data(e)
        try:
            vals, o = dec.props(b, 0, 'Level')
            hasguid, = struct.unpack_from('<i', b, o); o += 4 + (16 if hasguid else 0)
            n, = struct.unpack_from('<i', b, o)
            acts = list(struct.unpack_from('<%di' % n, b, o + 4))
            out[i + 1] = dict(name=e['fullname'], props=vals, actors=acts, actors_off=o)
        except Exception as ex:
            out[i + 1] = dict(name=e['fullname'], error=str(ex), actors=[])
    return out


def dump_pkg(reg, base):
    q = open_pkg(base); dec = Dec(reg, q)
    dec.tagged = not (q.flags & 0x2000)
    lv = level_actor_lists(q, dec)
    rec = dict(pkg=base, pkgname=q.pkgname, package_flags='0x%x' % q.flags, tagged=dec.tagged, export_entry_size=q.export_size, exports=len(q.exports), soft_object_paths=q.sopc,
               levels={str(k): dict(name=v['name'], nactors=len(v['actors']), props=v.get('props'), error=v.get('error')) for k, v in lv.items()},
               actors=[])
    for i, e in enumerate(q.exports):
        cls = q.ref(e['cls'])
        if cls not in ZONE_CLASSES: continue
        idx = i + 1
        pos = [(k, v['actors'].index(idx)) for k, v in lv.items() if idx in v['actors']]
        b = q.data(e); start = e['off'] - q.total_hdr
        vals, end = dec.props(b, 0, cls, start)
        tail = parse_actor_tail(dec, b, end)
        a = dict(export=idx, tail=tail, fullname=e['fullname'], cls=cls, outer=q.ref(e['outer']), outer_idx=e['outer'],
                 template=dec.objref(e['tmpl']), flags='0x%x' % e['flags'], notforclient=e['notforclient'], notforserver=e['notforserver'],
                 forced=e['forced'], uexp_off=start, size=e['size'], props_end=end, tail_hex=b[end:end + 64].hex(),
                 level_actor_slot=[('export%d' % k, p) for k, p in pos], props=vals, components=[])
        for j, c in enumerate(q.exports):
            if c['outer'] != idx: continue
            ccls = q.ref(c['cls']); cb = q.data(c); cstart = c['off'] - q.total_hdr
            try:
                cv, cend = dec.props(cb, 0, ccls, cstart)
            except Exception as ex:
                cv, cend = {'__error__': str(ex)}, 0
            ctail = parse_component_tail(dec, cb, cend) if cend else None
            a['components'].append(dict(export=j + 1, tail=ctail, fullname=c['fullname'], cls=ccls, template=dec.objref(c['tmpl']), flags='0x%x' % c['flags'],
                                        notforclient=c['notforclient'], notforserver=c['notforserver'], uexp_off=cstart, size=c['size'],
                                        props_end=cend, tail_hex=cb[cend:cend + 48].hex(), props=cv))
        # who references this actor (int32 == idx inside other exports' bytes, aligned scan limited to small exports)
        rec['actors'].append(a)
    return rec, q, dec


def build_registry():
    reg = Registry()
    for b in CLASS_PKGS:
        reg.add_pkg(b)
    return reg


if __name__ == '__main__':
    out = sys.argv[1]
    reg = build_registry()
    allrec = []
    for base in sys.argv[2:]:
        rec, q, dec = dump_pkg(reg, base)
        allrec.append(rec)
        print('==', base, 'exports', rec['exports'], 'softpaths', rec['soft_object_paths'], 'pkgflags', rec['package_flags'], 'tagged', rec['tagged'])
        for k, v in rec['levels'].items():
            print('   level export%s %s actors=%d %s' % (k, v['name'], v['nactors'], v.get('error') or ''))
        for a in rec['actors']:
            print('  export%-5d %-22s %-45s outer=%s slot=%s nfc=%d nfs=%d flags=%s @uexp+0x%x size=%d end=%d' % (
                a['export'], a['cls'], a['fullname'], a['outer'], a['level_actor_slot'], a['notforclient'], a['notforserver'], a['flags'], a['uexp_off'], a['size'], a['props_end']))
            print('        [tail] %s' % a['tail'])
            for k, v in a['props'].items(): print('        %-34s %s' % (k, v))
            for c in a['components']:
                print('     .export%-5d %-24s %-28s tmpl=%s @uexp+0x%x size=%d end=%d nfc=%d nfs=%d' % (c['export'], c['cls'], c['fullname'], c['template'], c['uexp_off'], c['size'], c['props_end'], c['notforclient'], c['notforserver']))
                for k, v in c['props'].items(): print('            %-30s %s' % (k, v))
                print('            [tail] %s' % c['tail'])
    json.dump(allrec, open(out, 'w'), indent=1, default=str)
