"""Reader for Unreal .usmap mapping files (UnrealMappingsDumper format, versions 0-3, oodle/brotli/zstd/none),
plus the unversioned-property schema order for a class: usmap.py <file.usmap> <ClassName> [ClassName...]
Schema order (UE FUnversionedStructSchema): the struct's own properties first, then each super's, i.e. TFieldRange
with IncludeSuper. A property with ArrayDim N occupies N schema slots."""
import ctypes, os, struct, sys, zlib

OODLE = r"C:\Program Files\Epic Games\UE_5.7\Engine\Binaries\DotNET\AutomationTool\AutomationScripts\BuildGraph\oo2core_9_win64.dll"


def decompress(method, data, want):
    if method == 0:
        return data
    if method == 1:                                              # oodle
        dll = ctypes.CDLL(OODLE); out = ctypes.create_string_buffer(want)
        n = dll.OodleLZ_Decompress(data, len(data), out, want, 1, 0, 0, None, 0, None, None, None, 0, 3)
        assert n == want, ('oodle', n, want); return out.raw
    if method == 2:
        import brotli; return brotli.decompress(data)
    if method == 3:
        import zstandard; return zstandard.ZstdDecompressor().decompress(data, max_output_size=want)
    raise ValueError(method)


class Usmap:
    def __init__(self, path):
        d = open(path, 'rb').read()
        magic, ver = struct.unpack_from('<HB', d, 0); assert magic == 0x30C4, hex(magic)
        o = 3
        if ver >= 1:
            has_versioning = struct.unpack_from('<i', d, o)[0]; o += 4
            if has_versioning:
                o += 4 + 4 + 4                                      # FileVersionUE4, FileVersionUE5, NetCL
                # custom versions: count + (guid 16 + int32) each
                n = struct.unpack_from('<i', d, o)[0]; o += 4 + n * 20
        method = d[o]; o += 1
        csize, dsize = struct.unpack_from('<II', d, o); o += 8
        b = decompress(method, d[o:o + csize], dsize)
        self.version = ver
        p = 0
        n, = struct.unpack_from('<I', b, p); p += 4
        self.names = []
        for _ in range(n):
            if ver >= 2:
                ln = struct.unpack_from('<H', b, p)[0]; p += 2
            else:
                ln = b[p]; p += 1
            self.names.append(b[p:p + ln].decode('utf-8', 'replace')); p += ln
        n, = struct.unpack_from('<I', b, p); p += 4
        self.enums = {}
        for _ in range(n):
            ni, = struct.unpack_from('<I', b, p); p += 4
            if ver >= 3:                                            # v3+: u16 count; v4 entries = int64 value + u32 name
                cnt, = struct.unpack_from('<H', b, p); p += 2
            else:
                cnt = b[p]; p += 1
            vals = []
            for _ in range(cnt):
                if ver >= 4:
                    val, = struct.unpack_from('<q', b, p); p += 8
                vi, = struct.unpack_from('<I', b, p); p += 4; vals.append(self.names[vi])
            self.enums[self.names[ni]] = vals
        n, = struct.unpack_from('<I', b, p); p += 4
        self.structs = {}
        for _ in range(n):
            ni, si = struct.unpack_from('<II', b, p); p += 8
            pc, sc = struct.unpack_from('<HH', b, p); p += 4
            props = []
            for _ in range(sc):
                idx, dim = struct.unpack_from('<HB', b, p); p += 3
                pni, = struct.unpack_from('<I', b, p); p += 4
                t, p = self.read_type(b, p)
                props.append((idx, dim, self.names[pni], t))
            props.sort()
            self.structs[self.names[ni]] = {'super': self.names[si] if si != 0xFFFFFFFF else None, 'count': pc, 'props': props}

    TYPES = ['ByteProperty', 'BoolProperty', 'IntProperty', 'FloatProperty', 'ObjectProperty', 'NameProperty', 'DelegateProperty', 'DoubleProperty', 'ArrayProperty', 'StructProperty', 'StrProperty', 'TextProperty', 'InterfaceProperty', 'MulticastDelegateProperty', 'WeakObjectProperty', 'LazyObjectProperty', 'AssetObjectProperty', 'SoftObjectProperty', 'UInt64Property', 'UInt32Property', 'UInt16Property', 'Int64Property', 'Int16Property', 'Int8Property', 'MapProperty', 'SetProperty', 'EnumProperty', 'FieldPathProperty', 'OptionalProperty', 'Utf8StrProperty', 'AnsiStrProperty']

    def read_type(self, b, p):
        t = b[p]; p += 1; name = self.TYPES[t] if t < len(self.TYPES) else 'T%d' % t
        if name == 'EnumProperty':
            inner, p = self.read_type(b, p); ni, = struct.unpack_from('<I', b, p); p += 4
            return ('Enum', self.names[ni], inner), p
        if name == 'StructProperty':
            ni, = struct.unpack_from('<I', b, p); p += 4; return ('Struct', self.names[ni]), p
        if name in ('ArrayProperty', 'SetProperty', 'OptionalProperty'):
            inner, p = self.read_type(b, p); return (name[:-8], inner), p
        if name == 'MapProperty':
            k, p = self.read_type(b, p); v, p = self.read_type(b, p); return ('Map', k, v), p
        return (name,), p

    def schema(self, cls):
        """[(slot, name, type, dim)] in unversioned order: own props, then super chain."""
        out = []; c = cls
        while c and c in self.structs:
            s = self.structs[c]
            for idx, dim, name, t in s['props']:
                out.append((c, idx, name, t, dim))
            c = s['super']
        return out


if __name__ == '__main__':
    u = Usmap(sys.argv[1])
    print('usmap v%d: %d names, %d enums, %d structs' % (u.version, len(u.names), len(u.enums), len(u.structs)))
    for cls in sys.argv[2:]:
        print('==', cls, 'super chain:', end=' ')
        c = cls; chain = []
        while c and c in u.structs:
            chain.append(c); c = u.structs[c]['super']
        print(' > '.join(chain))
        for owner, idx, name, t, dim in u.schema(cls):
            print('   %-28s %3d  %-40s %s%s' % (owner, idx, name, t, ' x%d' % dim if dim > 1 else ''))
