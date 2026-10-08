"""Rename entries of a cooked package's name table (UE 5.5 split .uasset/.umap + .uexp), fixing every
header offset the length change moves. Used to turn the Trenches border walls (BlockingVolume) into
TriggerVolumes (same property schema, no collision) inside the game's own Tranches_BP, which is
otherwise kept byte-for-byte (sky, weather, fog, post-processing as shipped).

usage: pak_patch_names.py <in_base> <out_base> Old=New [Old=New ...]
  in_base / out_base without extension; .uexp (and .ubulk) are copied unchanged.
"""
import os
import shutil
import struct
import sys

PKG_FILTER_EDITOR_ONLY = 0x80000000


def fstr(b, o):
    n, = struct.unpack_from('<i', b, o)
    o += 4
    if n < 0:
        return b[o:o + (-n) * 2].decode('utf-16-le')[:-1], o + (-n) * 2
    return (b[o:o + n].decode('latin-1')[:-1] if n else ''), o + n


def enc_name(s):
    if all(ord(c) < 128 for c in s):
        raw = s.encode('latin-1') + b'\0'
        return struct.pack('<i', len(raw)) + raw
    raw = s.encode('utf-16-le') + b'\0\0'
    return struct.pack('<i', -(len(raw) // 2)) + raw


class Summary:
    """Every field with its byte position, so offsets can be rewritten in place."""

    def __init__(self, d):
        self.d = d
        self.pos = {}
        o = 24
        ncv, = struct.unpack_from('<i', d, o)
        o += 4 + ncv * 20
        o = self.i32('TotalHeaderSize', o)
        self.package_name, o = fstr(d, o)
        o = self.u32('PackageFlags', o)
        o = self.i32('NameCount', o)
        o = self.i32('NameOffset', o)
        o = self.i32('SoftObjectPathsCount', o)
        o = self.i32('SoftObjectPathsOffset', o)
        if not (self.v['PackageFlags'] & PKG_FILTER_EDITOR_ONLY):
            _, o = fstr(d, o)                                   # LocalizationId
        o = self.i32('GatherableTextDataCount', o)
        o = self.i32('GatherableTextDataOffset', o)
        o = self.i32('ExportCount', o)
        o = self.i32('ExportOffset', o)
        o = self.i32('ImportCount', o)
        o = self.i32('ImportOffset', o)
        o = self.i32('DependsOffset', o)
        o = self.i32('SoftPackageReferencesCount', o)
        o = self.i32('SoftPackageReferencesOffset', o)
        o = self.i32('SearchableNamesOffset', o)
        o = self.i32('ThumbnailTableOffset', o)
        o += 16                                                 # Guid
        if not (self.v['PackageFlags'] & PKG_FILTER_EDITOR_ONLY):
            o += 16                                             # PersistentGuid
        gen, = struct.unpack_from('<i', d, o)
        o += 4 + gen * 8
        for _ in range(2):                                      # SavedBy / CompatibleWith engine versions
            o += 2 + 2 + 2 + 4
            _, o = fstr(d, o)
        o += 4                                                  # CompressionFlags
        n, = struct.unpack_from('<i', d, o)
        o += 4                                                  # CompressedChunks (count, must be 0)
        assert n == 0, 'compressed chunks'
        o += 4                                                  # PackageSource
        n, = struct.unpack_from('<i', d, o)
        o += 4                                                  # AdditionalPackagesToCook
        for _ in range(n):
            _, o = fstr(d, o)
        # NumTextureAllocations (legacy block): present as a 0 before AssetRegistryDataOffset
        nta, = struct.unpack_from('<i', d, o)
        if nta == 0:
            o += 4
        o = self.i32('AssetRegistryDataOffset', o)
        o = self.i64('BulkDataStartOffset', o)
        o = self.i32('WorldTileInfoDataOffset', o)
        n, = struct.unpack_from('<i', d, o)
        o += 4 + 4 * n                                          # ChunkIDs
        o = self.i32('PreloadDependencyCount', o)
        o = self.i32('PreloadDependencyOffset', o)
        o = self.i32('NamesReferencedFromExportDataCount', o)
        o = self.i64('PayloadTocOffset', o)
        o = self.i32('DataResourceOffset', o)
        self.end = o

    v = property(lambda self: self._v)

    def _rd(self, name, o, fmt, size):
        if not hasattr(self, '_v'):
            self._v = {}
        self._v[name] = struct.unpack_from(fmt, self.d, o)[0]
        self.pos[name] = (o, fmt)
        return o + size

    def i32(self, name, o):
        return self._rd(name, o, '<i', 4)

    def u32(self, name, o):
        return self._rd(name, o, '<I', 4)

    def i64(self, name, o):
        return self._rd(name, o, '<q', 8)


def patch(in_base, out_base, renames):
    ext = '.umap' if os.path.exists(in_base + '.umap') else '.uasset'
    d = bytearray(open(in_base + ext, 'rb').read())
    S = Summary(d)
    v = S.v
    assert v['SoftObjectPathsOffset'] == 0 or v['SoftObjectPathsOffset'] > v['NameOffset'] or v['SoftObjectPathsCount'] == 0
    # name table
    o = v['NameOffset']
    names = []
    for _ in range(v['NameCount']):
        s, o2 = fstr(d, o)
        names.append((s, d[o2:o2 + 4]))                       # + the two uint16 hashes
        o = o2 + 4
    name_end = o
    new_tab = bytearray()
    hit = 0
    for s, h in names:
        if s in renames:
            s = renames[s]
            hit += 1
        new_tab += enc_name(s) + h
    delta = len(new_tab) - (name_end - v['NameOffset'])
    print('renamed %d entries, name table delta %d bytes' % (hit, delta))
    # rebuild: summary + new names + rest of header, then fix offsets
    out = bytearray(d[:v['NameOffset']]) + new_tab + d[name_end:v['TotalHeaderSize']]
    for key in ('TotalHeaderSize', 'SoftObjectPathsOffset', 'GatherableTextDataOffset', 'ExportOffset', 'ImportOffset', 'DependsOffset',
                'SoftPackageReferencesOffset', 'SearchableNamesOffset', 'ThumbnailTableOffset', 'AssetRegistryDataOffset', 'BulkDataStartOffset',
                'WorldTileInfoDataOffset', 'PreloadDependencyOffset', 'PayloadTocOffset'):
        pos, fmt = S.pos[key]
        val = v[key]
        if val > v['NameOffset'] or (key == 'TotalHeaderSize'):
            struct.pack_into(fmt, out, pos, val + delta)
    # exports: SerialOffset (int64 at +36 of each entry) are absolute (uasset header + uexp)
    esz = (v['DependsOffset'] - v['ExportOffset']) // v['ExportCount']
    eo = v['ExportOffset'] + delta
    for k in range(v['ExportCount']):
        p = eo + k * esz + 36
        so, = struct.unpack_from('<q', out, p)
        struct.pack_into('<q', out, p, so + delta)
    # data resources (bulk data records): Version, Count, then 45-byte entries with absolute SerialOffsets
    if v['DataResourceOffset'] > 0:
        o = v['DataResourceOffset'] + delta
        ver, cnt = struct.unpack_from('<Ii', out, o)
        o += 8
        esize = 45 if ver >= 2 else 44
        for k in range(cnt):
            so_pos = o + k * esize + (5 if ver >= 2 else 4)
            so, dso = struct.unpack_from('<qq', out, so_pos)
            if so > v['NameOffset']:
                struct.pack_into('<q', out, so_pos, so + delta)
            if dso > v['NameOffset']:
                struct.pack_into('<q', out, so_pos + 8, dso + delta)
        print('data resources: %d records shifted' % cnt)
    open(out_base + ext, 'wb').write(out)
    for e in ('.uexp', '.ubulk', '.uptnl'):
        if os.path.exists(in_base + e):
            shutil.copyfile(in_base + e, out_base + e)
    print('written %s%s (%d -> %d bytes)' % (out_base, ext, len(d), len(out)))
    return out_base + ext


if __name__ == '__main__':
    ren = dict(a.split('=', 1) for a in sys.argv[3:])
    patch(sys.argv[1], sys.argv[2], ren)
