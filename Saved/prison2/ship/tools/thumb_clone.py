"""OFFLINE feasibility check for a custom map-card thumbnail WITHOUT the editor/cook:
clone a game UI map texture package (2048x1024, 1 mip, inline DXT5/DXT1 at uexp 0x71) under a NEW same-length name,
swap the block payload for our own image encoded by Pillow, and prove the result round-trips.
Writes only into ./thumb_out. Nothing is installed.
usage: thumb_clone.py <template base> <new object name (same length)> <image or 'test'>"""
import io, os, struct, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'tools'))
from PIL import Image, ImageDraw
from names_dump import Pkg
from pak_patch_names import Summary, fstr
from dt_add_row import name_entry, strihash_deprecated, strcrc32

DDS_MAGIC = b'DDS '
tmpl, newname, src = sys.argv[1], sys.argv[2], sys.argv[3]
OUT = os.path.join(HERE, 'thumb_out'); os.makedirs(OUT, exist_ok=True)
d = bytearray(open(tmpl + '.uasset', 'rb').read()); u = bytearray(open(tmpl + '.uexp', 'rb').read())
S = Summary(bytes(d)); v = S.v
oldname = os.path.basename(tmpl)
assert len(newname) == len(oldname), 'same-length rename only (%d vs %d)' % (len(newname), len(oldname))
# -- pixel format / payload location from the cooked bytes
pf_len, = struct.unpack_from('<i', u, 0x59); pf = u[0x5d:0x5d + pf_len - 1].decode()
sx, sy, packed = struct.unpack_from('<iiI', u, 0x4d)
first, nmips, dataidx = struct.unpack_from('<iii', u, 0x65)
bpp = {'PF_DXT5': 1, 'PF_DXT1': 0.5}[pf]
payload = int(sx * sy * bpp)
dro = v['DataResourceOffset']; ver, cnt = struct.unpack_from('<Ii', d, dro)
flags, cooked_index, soff, dsoff, ssize, rsize, outer, legacy = struct.unpack_from('<IBqqqqiI', d, dro + 8)
print('template %s: %dx%d %s packed=%d FirstMip=%d NumMips=%d DataResourceIndex=%d' % (oldname, sx, sy, pf, packed, first, nmips, dataidx))
print('  DataResource @%d ver %d count %d (45-byte entry): flags 0x%x CookedIndex %d SerialOffset %d Dup %d SerialSize %d RawSize %d Outer %d LegacyFlags 0x%x' % (dro, ver, cnt, flags, cooked_index, soff, dsoff, ssize, rsize, outer, legacy))
assert soff == 0x71 and ssize == payload and len(u) == 0x71 + payload + 24 + 4
print('  mip trailer @%d: %s ; tag %s' % (0x71 + payload, u[0x71 + payload:0x71 + payload + 24].hex(' '), u[-4:].hex(' ')))

def dds_header(w, h, fourcc, size):
    pfmt = struct.pack('<II4sIIIII', 32, 0x4, fourcc, 0, 0, 0, 0, 0)
    return DDS_MAGIC + struct.pack('<IIIIIII', 124, 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000, h, w, size, 0, 1) + b'\0' * 44 + pfmt + struct.pack('<IIIII', 0x1000, 0, 0, 0, 0)

fourcc = b'DXT5' if pf == 'PF_DXT5' else b'DXT1'
# -- 1. decode the template's own payload (proves block layout/row order)
blocks = bytes(u[0x71:0x71 + payload])
img = Image.open(io.BytesIO(dds_header(sx, sy, fourcc, payload) + blocks)); img.load()
img.convert('RGB').resize((512, 256)).save(os.path.join(OUT, 'template_%s_preview.png' % oldname))
# -- 2. our image
if src == 'test':
    im = Image.new('RGBA', (sx, sy), (40, 44, 52, 255)); dr = ImageDraw.Draw(im)
    for k in range(0, sx, 128): dr.line([(k, 0), (k, sy)], fill=(90, 90, 90, 255), width=4)
    dr.rectangle([96, 96, sx - 96, sy - 96], outline=(230, 120, 30, 255), width=24)
    dr.ellipse([sx // 2 - 300, sy // 2 - 300, sx // 2 + 300, sy // 2 + 300], outline=(240, 240, 240, 255), width=40)
else:
    im = Image.open(src).convert('RGBA').resize((sx, sy), Image.LANCZOS)
buf = io.BytesIO(); im.save(buf, format='DDS', pixel_format=fourcc.decode())
dds = buf.getvalue(); hdr = 148 if dds[84:88] == b'DX10' else 128
newblocks = dds[hdr:]
print('  Pillow DDS %s: %d bytes, header %d, payload %d (need %d)' % (fourcc.decode(), len(dds), hdr, len(newblocks), payload))
assert len(newblocks) == payload
u2 = bytearray(u); u2[0x71:0x71 + payload] = newblocks
# -- 3. same-length renames: name table (+hashes) and summary PackageName
o = v['NameOffset']; renamed = []
for i in range(v['NameCount']):
    s, o2 = fstr(bytes(d), o)
    if oldname in s:
        s2 = s.replace(oldname, newname); e = name_entry(s2)
        assert len(e) == o2 + 4 - o
        d[o:o2 + 4] = e; renamed.append((i, s, s2))
    o = o2 + 4
pn, pe = fstr(bytes(d), 32)
d[32:pe] = struct.pack('<i', len(pn) + 1) + pn.replace(oldname, newname).encode() + b'\0'
base = os.path.join(OUT, newname)
open(base + '.uasset', 'wb').write(d); open(base + '.uexp', 'wb').write(u2)
for r in renamed: print('  name %d %r -> %r' % r)
# -- 4. verify
q = Pkg(base); S2 = Summary(open(base + '.uasset', 'rb').read())
diff = [i for i in range(len(d)) if d[i] != open(tmpl + '.uasset', 'rb').read()[i]]
print('  clone: pkg %s, export %s size %d, TotalHeaderSize %d == file %d, uasset bytes changed %d (range %d..%d), uexp changed only in [0x71,0x%x)' % (
    q.pkgname, q.exports[0]['name'], q.exports[0]['size'], S2.v['TotalHeaderSize'], len(d), len(diff), diff[0], diff[-1], 0x71 + payload))
back = Image.open(io.BytesIO(dds_header(sx, sy, fourcc, payload) + bytes(u2[0x71:0x71 + payload]))); back.load()
back.convert('RGB').resize((512, 256)).save(os.path.join(OUT, '%s_roundtrip_preview.png' % newname))
print('  round-trip decode ok: %s %s' % (back.size, back.mode))
