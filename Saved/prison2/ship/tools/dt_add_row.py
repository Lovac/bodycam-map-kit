"""Append one row to a cooked UE 5.5 DataTable whose row struct is {bool, object} (BP_MapDefinition /
S_MapWeatherConfig), adding the referenced data-asset imports when needed, and derive a new
PDA_LevelMetaData_C data asset from an existing one. Writes patched copies only (never in place).

usage:
  dt_add_row.py table <in_base> <out_base> <RowName> <ObjectPackagePath> <ObjectName> [--inactive]
      e.g. dt_add_row.py table .../DT_UI_HardpointMaps <out>/DT_UI_HardpointMaps Prison /Game/UI/MetaData/DA_Prison DA_Prison
      If an object import <ObjectName> in package <ObjectPackagePath> already exists it is reused,
      otherwise a Package import + an object import (class copied from the first object import whose
      class is a BlueprintGeneratedClass) are appended.
  dt_add_row.py da <in_base> <out_base> <OldLevelName> <NewLevelName> <NewDisplayName> [NewDescription]
      e.g. dt_add_row.py da .../DA_Paintball <out>/DA_Prison Paintball Prison "Prison"
      Renames the LevelName FName and the package/object names (Old -> New everywhere in the name table),
      rewrites Texts[0] (and Texts[1] if given) as culture-invariant Base texts, fixes SerialSize and
      BulkDataStartOffset.

Layout facts this relies on (measured on pakchunk24 DT_UI_HardpointMaps / DA_Paintball, see REPORT.md):
  * name entry = FString + uint16 NonCasePreservingHash (Strihash_DEPRECATED, low 16) + uint16 CasePreservingHash (StrCrc32, low 16)
  * import entry = 32 bytes: ClassPackage FName, ClassName FName, OuterIndex i32, ObjectName FName, bImportOptional i32
  * export entry = 96 bytes: ..., ObjectName FName @+16, SerialSize i64 @+28, SerialOffset i64 @+36,
    FirstExportDependency @+76, SerializationBeforeSerialization @+80, CreateBeforeSerialization @+84,
    SerializationBeforeCreate @+88, CreateBeforeCreate @+92 (counts into the PreloadDependencies list, in that order)
  * DataTable export = unversioned header 00 03 | RowStruct i32 | bHasGuid i32 (0) | RowCount i32 | rows | (uexp trailer C1 83 2A 9E)
  * row = FName(8) | fragment header (00 05 = bool+object present, 80 05 01 = bool is zero) | [bool byte] | object i32
"""
import os
import shutil
import struct
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from pak_patch_names import Summary, fstr, enc_name          # noqa: E402
from names_dump import Pkg                                    # noqa: E402

PACKAGE_FILE_TAG = b'\xc1\x83\x2a\x9e'

# ---- FName hashes (verified against every entry of the game's own name tables) --------------------------------
_CRC_NONREFL = []
for _i in range(256):
    _c = _i << 24
    for _ in range(8):
        _c = ((_c << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if _c & 0x80000000 else (_c << 1) & 0xFFFFFFFF
    _CRC_NONREFL.append(_c)
_CRC_REFL = []
for _i in range(256):
    _c = _i
    for _ in range(8):
        _c = (_c >> 1) ^ 0xEDB88320 if _c & 1 else _c >> 1
    _CRC_REFL.append(_c)


def strihash_deprecated(s):
    h = 0
    for ch in s:
        c = ord(ch.upper())
        h = ((h >> 8) & 0x00FFFFFF) ^ _CRC_NONREFL[(h ^ c) & 0xFF]
    return h


def strcrc32(s):
    crc = 0xFFFFFFFF
    for ch in s:
        c = ord(ch)
        for _ in range(4):
            crc = (crc >> 8) ^ _CRC_REFL[(crc ^ c) & 0xFF]
            c >>= 8
    return (~crc) & 0xFFFFFFFF


def name_entry(s):
    return enc_name(s) + struct.pack('<HH', strihash_deprecated(s) & 0xFFFF, strcrc32(s) & 0xFFFF)


def check_hashes(names_with_hash):
    bad = [s for s, h in names_with_hash if name_entry(s)[-4:] != h]
    return bad


# ---- header model ------------------------------------------------------------------------------------------------
class Header:
    """Split a cooked package header into editable pieces."""

    def __init__(self, d):
        self.S = Summary(d)
        v = self.S.v
        self.d = d
        self.v = dict(v)
        # FPackageFileSummary.PackageName (FString right after TotalHeaderSize @28)
        self.package_name, self.pkgname_end = fstr(d, 32)
        self.new_package_name = None
        o = v['NameOffset']
        self.names = []
        for _ in range(v['NameCount']):
            s, o2 = fstr(d, o)
            self.names.append((s, d[o2:o2 + 4]))
            o = o2 + 4
        self.names_end = o
        assert o == v['ImportOffset'], ('gap between names and imports', o, v['ImportOffset'])
        assert v['SoftObjectPathsCount'] == 0 and v['GatherableTextDataCount'] == 0, 'unexpected header tables'
        self.imports = [bytearray(d[v['ImportOffset'] + 32 * k: v['ImportOffset'] + 32 * (k + 1)]) for k in range(v['ImportCount'])]
        assert v['ImportOffset'] + 32 * v['ImportCount'] == v['ExportOffset'], 'imports are not 32 bytes / not followed by exports'
        self.exports = [bytearray(d[v['ExportOffset'] + 96 * k: v['ExportOffset'] + 96 * (k + 1)]) for k in range(v['ExportCount'])]
        assert v['ExportOffset'] + 96 * v['ExportCount'] == v['DependsOffset'], 'exports are not 96 bytes / not followed by depends'
        self.depends = d[v['DependsOffset']:v['AssetRegistryDataOffset']]
        self.assetreg = d[v['AssetRegistryDataOffset']:v['PreloadDependencyOffset']]
        pdo = v['PreloadDependencyOffset']
        self.preload = list(struct.unpack_from('<%di' % v['PreloadDependencyCount'], d, pdo))
        assert pdo + 4 * v['PreloadDependencyCount'] == v['TotalHeaderSize'], 'preload dependencies do not end the header'
        assert v['DataResourceOffset'] == -1 and v['PayloadTocOffset'] == -1

    def import_name(self, k):
        i, = struct.unpack_from('<i', self.imports[k], 20)
        return self.names[i][0]

    def import_fields(self, k):
        cp, _, cn, _, outer, on, _, opt = struct.unpack_from('<iiiiiiii', self.imports[k])
        return dict(clspkg=self.names[cp][0], cls=self.names[cn][0], outer=outer, name=self.names[on][0], optional=opt)

    def find_name(self, s):
        for i, (n, h) in enumerate(self.names):
            if n == s:
                return i
        return -1

    def remap_names(self, remap):
        """remap: old index -> new index, applied to every FName index stored in imports and exports."""
        for im in self.imports:
            for off in (0, 8, 20):
                i, = struct.unpack_from('<i', im, off)
                struct.pack_into('<i', im, off, remap[i])
        for ex in self.exports:
            i, = struct.unpack_from('<i', ex, 16)
            struct.pack_into('<i', ex, 16, remap[i])

    def build(self, uexp_data_len):
        v = self.v
        S = self.S
        out = bytearray(self.d[:v['NameOffset']])
        pkg_delta = 0
        if self.new_package_name is not None:
            new_str = enc_name(self.new_package_name)
            pkg_delta = len(new_str) - (self.pkgname_end - 32)
            out = bytearray(self.d[:32]) + new_str + bytearray(self.d[self.pkgname_end:v['NameOffset']])
            # every summary field position after the string moves with it
            S.pos = {k: (p + pkg_delta if p > 32 else p, fmt) for k, (p, fmt) in S.pos.items()}
        pos = {}
        pos['NameOffset'] = len(out)
        for s, h in self.names:
            out += enc_name(s) + h
        pos['ImportOffset'] = len(out)
        for im in self.imports:
            out += im
        pos['ExportOffset'] = len(out)
        export_pos = [len(out) + 96 * k for k in range(len(self.exports))]
        for ex in self.exports:
            out += ex
        pos['DependsOffset'] = len(out)
        out += self.depends
        pos['AssetRegistryDataOffset'] = len(out)
        out += self.assetreg
        pos['PreloadDependencyOffset'] = len(out)
        out += struct.pack('<%di' % len(self.preload), *self.preload)
        total = len(out)
        # summary fields
        def put(key, val):
            p, fmt = S.pos[key]
            struct.pack_into(fmt, out, p, val)
        put('TotalHeaderSize', total)
        put('NameCount', len(self.names))
        put('NameOffset', pos['NameOffset'])
        put('SoftObjectPathsOffset', pos['ImportOffset'] if v['SoftObjectPathsOffset'] else 0)
        put('ImportCount', len(self.imports))
        put('ImportOffset', pos['ImportOffset'])
        put('ExportCount', len(self.exports))
        put('ExportOffset', pos['ExportOffset'])
        put('DependsOffset', pos['DependsOffset'])
        put('AssetRegistryDataOffset', pos['AssetRegistryDataOffset'])
        put('PreloadDependencyCount', len(self.preload))
        put('PreloadDependencyOffset', pos['PreloadDependencyOffset'])
        put('NamesReferencedFromExportDataCount', v['NamesReferencedFromExportDataCount'])
        put('BulkDataStartOffset', total + uexp_data_len)
        # export serial offsets: first export starts right after the header, next ones follow
        off = total
        for k, ex in enumerate(self.exports):
            size, = struct.unpack_from('<q', ex, 28)
            struct.pack_into('<q', out, export_pos[k] + 36, off)
            off += size
        return bytes(out)


# ---- DataTable: append a row ------------------------------------------------------------------------------------
def add_row(in_base, out_base, row_name, obj_pkg, obj_name, active=True, log=print):
    d = open(in_base + '.uasset', 'rb').read()
    uexp = open(in_base + '.uexp', 'rb').read()
    H = Header(d)
    v = H.v
    assert v['ExportCount'] == 1, 'expected a single DataTable export'
    bad = check_hashes(H.names)
    assert not bad, ('hash formula mismatch on', bad)
    # --- names: the row name must sit inside the "referenced from export data" block (first N names) ---
    n_exp = v['NamesReferencedFromExportDataCount']
    remap = {}
    if H.find_name(row_name) < 0:
        ins = n_exp
        H.names.insert(ins, (row_name, name_entry(row_name)[-4:]))
        for i in range(len(H.names)):
            remap[i] = i if i < ins else i + 1
        remap.pop(ins + 0, None)
        # imports/exports indices >= ins move by one
        remap = {i: (i if i < ins else i + 1) for i in range(len(H.names) - 1)}
        H.remap_names(remap)
        H.v['NamesReferencedFromExportDataCount'] = n_exp + 1
        row_name_idx = ins
        log('  name %r inserted at index %d (NamesReferencedFromExportDataCount %d -> %d)' % (row_name, ins, n_exp, n_exp + 1))
    else:
        row_name_idx = H.find_name(row_name)
        log('  name %r already present at index %d' % (row_name, row_name_idx))
    # --- imports: reuse or append Package + object ---
    obj_import = None
    for k in range(len(H.imports)):
        f = H.import_fields(k)
        if f['name'] == obj_name and f['outer'] < 0 and H.import_fields(-f['outer'] - 1)['name'] == obj_pkg:
            obj_import = -(k + 1)
    if obj_import is None:
        # class of the object import = same class as the first object import whose outer is a /Game package (the DAs)
        proto = None
        proto_pkg = None
        for k in range(len(H.imports)):
            f = H.import_fields(k)
            if f['outer'] < 0 and f['clspkg'].startswith('/Game/'):
                proto = k
                proto_pkg = -f['outer'] - 1
                break
        assert proto is not None, 'no prototype object import found'
        fp = H.import_fields(proto_pkg)
        fo = H.import_fields(proto)
        log('  prototype imports: package %s (class %s.%s), object %s (class %s.%s)' % (fp['name'], fp['clspkg'], fp['cls'], fo['name'], fo['clspkg'], fo['cls']))
        def name_idx(s):
            i = H.find_name(s)
            if i < 0:
                H.names.append((s, name_entry(s)[-4:]))
                i = len(H.names) - 1
                log('  name %r appended at index %d' % (s, i))
            return i
        pkg_entry = bytearray(H.imports[proto_pkg])
        struct.pack_into('<ii', pkg_entry, 20, name_idx(obj_pkg), 0)
        H.imports.append(pkg_entry)
        pkg_import = -len(H.imports)
        obj_entry = bytearray(H.imports[proto])
        struct.pack_into('<i', obj_entry, 16, pkg_import)
        struct.pack_into('<ii', obj_entry, 20, name_idx(obj_name), 0)
        H.imports.append(obj_entry)
        obj_import = -len(H.imports)
        log('  imports appended: %d = Package %s, %d = %s %s (outer %d)' % (pkg_import, obj_pkg, obj_import, fo['cls'], obj_name, pkg_import))
        # preload dependencies: the object goes into the CreateBeforeSerialization group of export 1
        ex = H.exports[0]
        sbs, cbs, sbc, cbc = struct.unpack_from('<iiii', ex, 80)
        first, = struct.unpack_from('<i', ex, 76)
        insert_at = first + sbs + cbs
        H.preload.insert(insert_at, obj_import)
        struct.pack_into('<i', ex, 84, cbs + 1)
        log('  preload dependency %d inserted at position %d (CreateBeforeSerialization %d -> %d)' % (obj_import, insert_at, cbs, cbs + 1))
    else:
        log('  object import already present: %d' % obj_import)
    # --- uexp: append the row ---
    ex = H.exports[0]
    size, off = struct.unpack_from('<qq', ex, 28)
    assert off == v['TotalHeaderSize'] and size + 4 == len(uexp) and uexp[-4:] == PACKAGE_FILE_TAG, 'unexpected uexp layout'
    data = bytearray(uexp[:-4])
    hdr = struct.unpack_from('<H', data, 0)[0]
    assert hdr == 0x0300, 'DataTable header not 00 03'
    count_pos = 2 + 4 + 4
    count, = struct.unpack_from('<i', data, count_pos)
    row = struct.pack('<ii', row_name_idx, 0)
    if active:
        row += b'\x00\x05\x01' + struct.pack('<i', obj_import)
    else:
        row += b'\x80\x05\x01' + struct.pack('<i', obj_import)
    data += row
    struct.pack_into('<i', data, count_pos, count + 1)
    struct.pack_into('<q', ex, 28, len(data))
    log('  row %d appended: %s (%d bytes), row count %d -> %d, SerialSize %d -> %d' % (count, row.hex(' '), len(row), count, count + 1, size, len(data)))
    new_hdr = H.build(len(data))
    os.makedirs(os.path.dirname(out_base) or '.', exist_ok=True)
    open(out_base + '.uasset', 'wb').write(new_hdr)
    open(out_base + '.uexp', 'wb').write(bytes(data) + PACKAGE_FILE_TAG)
    log('  written %s.uasset (%d -> %d bytes) and .uexp (%d -> %d bytes)' % (out_base, len(d), len(new_hdr), len(uexp), len(data) + 4))
    return out_base


# ---- Data asset: derive DA_<New> from DA_<Old> ------------------------------------------------------------------
def fstring_bytes(s):
    raw = s.encode('latin-1') + b'\0'
    return struct.pack('<i', len(raw)) + raw


def base_text(src):
    """FText, Base history: flags u32 0, history i8 0, Namespace '' (len 1 + NUL, as the game serializes it),
    Key = new 32-hex GUID, SourceString."""
    key = uuid.uuid4().hex.upper()
    return struct.pack('<Ib', 0, 0) + fstring_bytes('') + fstring_bytes(key) + fstring_bytes(src)


def read_text(b, o):
    flags, ht = struct.unpack_from('<Ib', b, o); o += 5
    if ht == -1:
        has, = struct.unpack_from('<i', b, o); o += 4
        if has:
            n, = struct.unpack_from('<i', b, o); o += 4 + (n if n >= 0 else -2 * n)
        return o
    if ht == 0:
        for _ in range(3):
            n, = struct.unpack_from('<i', b, o); o += 4 + (n if n >= 0 else -2 * n)
        return o
    if ht == 11:
        o += 8
        n, = struct.unpack_from('<i', b, o); o += 4 + (n if n >= 0 else -2 * n)
        return o
    raise ValueError('text history %d' % ht)


def make_da(in_base, out_base, old, new, display, description=None, log=print, level_name=None):
    """level_name (13 sep): if given, the name entry that is EXACTLY <old> (the LevelName FName) becomes
    level_name, while the package/object names still get old -> new. Needed for per-mode DAs whose LevelName
    is a long travel path, e.g. DA_Prison_HP with LevelName '/Game/GM_Maps/Hardpoint/HP_Prison?PrisonLobbyBypass'
    (BodycamGI.TravelToMap only sends a long path when the name contains 'Lobby'; see PLAN Q2)."""
    d = open(in_base + '.uasset', 'rb').read()
    uexp = open(in_base + '.uexp', 'rb').read()
    H = Header(d)
    bad = check_hashes(H.names)
    assert not bad, ('hash formula mismatch on', bad)
    hits = 0
    for i, (s, h) in enumerate(H.names):
        if level_name is not None and s == old:
            H.names[i] = (level_name, name_entry(level_name)[-4:])
            hits += 1
            log('  name %d: LevelName %r -> %r' % (i, s, level_name))
            continue
        if old in s:
            s2 = s.replace(old, new)
            H.names[i] = (s2, name_entry(s2)[-4:])
            hits += 1
            log('  name %d: %r -> %r' % (i, s, s2))
    assert hits, 'old name not found'
    if old in H.package_name:
        H.new_package_name = H.package_name.replace(old, new)
        log('  summary PackageName: %r -> %r' % (H.package_name, H.new_package_name))
    ex = H.exports[0]
    size, off = struct.unpack_from('<qq', ex, 28)
    assert off == H.v['TotalHeaderSize'] and size + 4 == len(uexp) and uexp[-4:] == PACKAGE_FILE_TAG
    data = bytearray(uexp[:-4])
    # walk: header 00 08 02 05 (slots 0-3, 6-7), LevelName 8, two soft paths 20 each, Texts array
    assert data[:4] == b'\x00\x08\x02\x05', 'unexpected unversioned header %s' % data[:4].hex()
    o = 4 + 8 + 20 + 20
    n, = struct.unpack_from('<i', data, o)
    assert n == 2, 'expected 2 Texts'
    t0 = o + 4
    t1 = read_text(data, t0)
    t2 = read_text(data, t1)
    new0 = base_text(display)
    new1 = base_text(description) if description is not None else data[t1:t2]
    log('  Texts[0] %d bytes at %d -> Base text %r (%d bytes); Texts[1] %d -> %d bytes' % (t1 - t0, t0, display, len(new0), t2 - t1, len(new1)))
    data = data[:t0] + new0 + new1 + data[t2:]
    struct.pack_into('<q', ex, 28, len(data))
    new_hdr = H.build(len(data))
    os.makedirs(os.path.dirname(out_base) or '.', exist_ok=True)
    open(out_base + '.uasset', 'wb').write(new_hdr)
    open(out_base + '.uexp', 'wb').write(bytes(data) + PACKAGE_FILE_TAG)
    log('  written %s.uasset (%d -> %d bytes) and .uexp (%d -> %d bytes)' % (out_base, len(d), len(new_hdr), len(uexp), len(data) + 4))
    return out_base


# ---- verification -----------------------------------------------------------------------------------------------
def verify(base, log=print):
    d = open(base + '.uasset', 'rb').read()
    uexp = open(base + '.uexp', 'rb').read()
    H = Header(d)
    v = H.v
    q = Pkg(base)
    ok = True
    def chk(cond, msg):
        nonlocal ok
        log('  %s %s' % ('ok ' if cond else 'BAD', msg))
        ok = ok and cond
    chk(v['TotalHeaderSize'] == len(d), 'TotalHeaderSize %d == file size %d' % (v['TotalHeaderSize'], len(d)))
    chk(not check_hashes(H.names), 'all %d name hashes match the FName formulas' % len(H.names))
    for k in range(len(H.imports)):
        f = H.import_fields(k)
        chk(-len(H.imports) <= f['outer'] <= 0, 'import %d %s.%s outer=%d name=%s' % (-(k + 1), f['clspkg'], f['cls'], f['outer'], f['name']))
    size, off = struct.unpack_from('<qq', H.exports[0], 28)
    chk(off == v['TotalHeaderSize'], 'export SerialOffset %d == TotalHeaderSize' % off)
    chk(size + 4 == len(uexp) and uexp[-4:] == PACKAGE_FILE_TAG, 'export SerialSize %d + tag == uexp %d bytes' % (size, len(uexp)))
    chk(v['BulkDataStartOffset'] == v['TotalHeaderSize'] + size, 'BulkDataStartOffset %d == header + export data' % v['BulkDataStartOffset'])
    first, sbs, cbs, sbc, cbc = struct.unpack_from('<iiiii', H.exports[0], 76)
    chk(first + sbs + cbs + sbc + cbc == len(H.preload), 'preload groups %d+%d+%d+%d == PreloadDependencyCount %d' % (sbs, cbs, sbc, cbc, len(H.preload)))
    chk(all(-len(H.imports) <= p < 0 or 0 < p <= len(H.exports) for p in H.preload), 'preload dependency indices resolve: %s' % H.preload)
    chk(q.names == [s for s, h in H.names], 'names_dump.Pkg reads the same %d names' % len(q.names))
    chk(q.pkgname == H.package_name, 'summary PackageName %r' % H.package_name)
    return ok


if __name__ == '__main__':
    # 13 sep: exit code 1 when verify() prints BAD (before, a BAD table still returned 0 to the pipeline).
    # Positional /Game arguments: call with MSYS_NO_PATHCONV=1 from Git Bash, or they arrive as C:/Program Files/Git/Game/...
    for a in sys.argv[2:]:
        if 'Program Files/Git/' in a.replace('\\', '/'):
            print('argument %r was rewritten by Git Bash (set MSYS_NO_PATHCONV=1)' % a)
            sys.exit(2)
    mode = sys.argv[1]
    opts = [a for a in sys.argv[2:] if a.startswith('--')]
    args = [a for a in sys.argv[2:] if not a.startswith('--')]
    level = next((o.split('=', 1)[1] for o in opts if o.startswith('--level=')), None)
    if mode == 'table':
        add_row(args[0], args[1], args[2], args[3], args[4], active='--inactive' not in opts)
        sys.exit(0 if verify(args[1]) else 1)
    elif mode == 'da':
        make_da(args[0], args[1], args[2], args[3], args[4], args[5] if len(args) > 5 else None, level_name=level)
        sys.exit(0 if verify(args[1]) else 1)
    elif mode == 'verify':
        sys.exit(0 if verify(args[0]) else 1)
    else:
        print(__doc__)
