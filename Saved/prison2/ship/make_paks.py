"""Prison 2 content paks (card id Panopticon) from the cook, with the gates of BCMAP_FORMAT.md sections 3 and 8.

    python make_paks.py      -> paks/zPanopticon_9_P.pak, paks/zPanopticon_Modes_9_P.pak, paks/make_paks_report.json

Gates (any failure = exit 1 and no pak is kept):
  1. content = the cooked level and every cooked file under Sandbox/Prison2/ and Sandbox/Meshes/Prison2/; modes = exactly
     the 6 wrapper files; no path of either pak exists in the game's paks
  2. every /Game and /Engine package the packed files import is either packed or present in the game's paks
     (placeholders at game paths such as the jukebox, the hardpoint zone or the game materials stay out: the game has them)
  3. each wrapper names its own path, the level and /Game/Map/PPV/GlobalPostProcess, and nothing of another map or a game mode
  4. no path or name contains a word the Nexus rules forbid (S2Town, Stalker, ZoneKit, Cabins, MatTest, _probe, EDITOR_ONLY_)
  5. UnrealPak lists exactly the expected files and an extraction is byte-identical to the cook
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SHIP = os.environ.get('BCM_SHIP_DIR', HERE)   # per-card output dir; HERE stays the code dir (tools/, templates/)
sys.path.insert(0, os.path.join(HERE, 'tools'))
sys.dont_write_bytecode = True
from names_dump import Pkg  # noqa: E402

SB = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
COOKED = os.path.join(SB, r'Saved\Cooked\Windows\BodycamSandbox\Content')
UP = os.environ.get('BCM_UNREALPAK', r'C:\Program Files\Epic Games\UE_5.5\Engine\Binaries\Win64\UnrealPak.exe')
INDEX = os.path.join(SB, r'Saved\menu_test\game_pak_index.tsv')
CARD = os.environ.get('BCM_CARD', 'Panopticon')
LEVEL = os.environ.get('BCM_LEVEL', '/Game/Sandbox/Prison2/Prison2_BP')
CONTENT_ROOTS = tuple(os.environ.get('BCM_CONTENT_ROOTS', 'Sandbox/Prison2/,Sandbox/Meshes/Prison2/').split(','))
MODES = (('Hardpoint', 'HP_'), ('TeamDeathmatch', 'TDM_'), ('DeathMatch', 'DM_'), ('Versus', 'VS_'), ('GunGame', 'GG_'), ('BodyBomb', 'BB_'), ('Wingman', 'WM_'))
FORBIDDEN = ('s2town', 'stalker', 's2assets', 'zonekit', 'cabins', 'mattest', 'modular_rural_cabin', '_probe', 'editor_only_')
OUT = os.path.join(SHIP, 'paks')
fails = []


def fail(msg):
    fails.append(msg)
    print('  FAIL', msg)


def md5(p):
    return hashlib.md5(open(p, 'rb').read()).hexdigest()


def cooked_files(prefix):
    root = os.path.join(COOKED, prefix.replace('/', os.sep))
    out = []
    for d, _, fs in os.walk(root):
        for f in fs:
            out.append(os.path.relpath(os.path.join(d, f), COOKED).replace(os.sep, '/'))
    return sorted(out)


def game_paths():
    have = set()
    for line in open(INDEX, encoding='utf-8'):
        p, _, where = line.rstrip('\n').partition('\t')
        # 24 Sep 2026: only files a GAME pak holds (pakchunkN-Windows.pak); the 13 Sep snapshot also lists mod paks
        # (*_P.pak, e.g. the old V1's pakchunk99-Windows_P.pak, long gone), which are not the game
        if where and all(w.strip().endswith('_P.pak') for w in where.split(',')):
            continue
        if p.startswith('Bodycam/Content/'):
            have.add('/Game/' + p[len('Bodycam/Content/'):].rsplit('.', 1)[0])
        elif p.startswith('Engine/Content/'):
            have.add('/Engine/' + p[len('Engine/Content/'):].rsplit('.', 1)[0])
    return have


print('== 1. file lists')
content = []
for r in CONTENT_ROOTS:
    content += cooked_files(r)
modes = []
for folder, prefix in MODES:
    for ext in ('umap', 'uexp'):
        modes.append('GM_Maps/%s/%s%s.%s' % (folder, prefix, CARD, ext))
for p in modes:
    if not os.path.exists(os.path.join(COOKED, p)):
        fail('wrapper file missing in the cook: %s' % p)
if LEVEL[len('/Game/'):] + '.umap' not in content:      # 24 Sep 2026: the card's own level (was Prison 2's path)
    fail('level not cooked')
game = game_paths()
for p in content + modes:
    if ('/Game/' + p.rsplit('.', 1)[0]) in game:
        fail('%s is a path of the game' % p)
print('  content %d files, modes %d files, game packages known %d' % (len(content), len(modes), len(game)))

print('== 2. imports resolve to the pak or the game')
packed = {'/Game/' + p.rsplit('.', 1)[0] for p in content + modes}
missing = {}
for p in content + modes:
    if not p.endswith(('.umap', '.uasset')):
        continue
    q = Pkg(os.path.join(COOKED, p.replace('/', os.sep)).rsplit('.', 1)[0])
    for i in range(len(q.imports)):
        im = q.imports[i]
        if im['outer'] != 0:
            continue
        pkg = im['name']
        if pkg.startswith('/Script/') or not pkg.startswith(('/Game/', '/Engine/')):
            continue
        if pkg not in packed and pkg not in game:
            missing.setdefault(pkg, []).append(p)
for pkg, users in sorted(missing.items()):
    fail('%s is imported by %s but is neither packed nor in the game' % (pkg, users[:2]))
print('  unresolved imports: %d' % len(missing))

print('== 3. wrappers')
for folder, prefix in MODES:
    base = os.path.join(COOKED, 'GM_Maps', folder, prefix + CARD)
    q = Pkg(base)
    names = set(q.names)
    own = '/Game/GM_Maps/%s/%s%s' % (folder, prefix, CARD)
    games = sorted(n for n in names if n.startswith('/Game/'))
    ok = own in names and LEVEL in names and '/Game/Map/PPV/GlobalPostProcess' in names
    extra = [n for n in games if n not in (own, LEVEL, '/Game/Map/PPV/GlobalPostProcess')]
    bad = [n for n in names if 'Paintball' in n or ('Prison_BP' in n and not LEVEL.endswith('/Prison_BP')) or 'GameMode' in n]   # V1's own card names Prison_BP
    if not ok or extra or bad:
        fail('%s names %s (extra %s, forbidden %s)' % (own, games, extra, bad))
    else:
        print('  ok %s -> %s' % (own, games))

print('== 4. forbidden words')
for p in content + modes:
    if any(w in p.lower() for w in FORBIDDEN):
        fail('forbidden word in %s' % p)

if fails:
    print('FAILED %d gates, no pak written' % len(fails))
    sys.exit(1)

print('== 5. paks')
os.makedirs(OUT, exist_ok=True)
report = {}
for name, files in (('z%s_9_P.pak' % CARD, content), ('z%s_Modes_9_P.pak' % CARD, modes)):
    pak = os.path.join(OUT, name)
    if os.path.exists(pak):
        os.remove(pak)
    rsp = os.path.join(OUT, name + '.txt')
    with open(rsp, 'w', encoding='utf-8', newline='\n') as f:
        for p in files:
            f.write('"%s" "../../../Bodycam/Content/%s"\n' % (os.path.join(COOKED, p.replace('/', os.sep)), p))
    r = subprocess.run([UP, pak, '-create=' + rsp, '-compress'], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if r.returncode != 0 or not os.path.exists(pak):
        print(r.stdout[-2000:])
        fail('UnrealPak -create failed for %s' % name)
        break
    lst = subprocess.run([UP, pak, '-List'], capture_output=True, text=True, stdin=subprocess.DEVNULL).stdout
    # UnrealPak mounts at the files' common folder and lists and extracts paths relative to it
    mount = next((l.split('mount point "', 1)[1].split('"', 1)[0] for l in lst.splitlines() if 'mount point "' in l), '')
    rel_listed = sorted(set(l.split('"')[1] for l in lst.splitlines() if 'Display: "' in l and l.count('"') >= 2))
    listed = sorted(mount + r for r in rel_listed)
    want = sorted('../../../Bodycam/Content/' + p for p in files)
    if not mount.startswith('../../../Bodycam/Content/'):
        fail('%s mount point %r is not under ../../../Bodycam/Content/' % (name, mount))
    below = mount[len('../../../Bodycam/Content/'):]
    if listed != want:
        fail('%s lists %d files, expected %d' % (name, len(listed), len(want)))
    tmp = tempfile.mkdtemp(prefix='p2pak_')
    subprocess.run([UP, pak, '-Extract', tmp], capture_output=True, stdin=subprocess.DEVNULL)
    diff = []
    for p in files:
        rel = p[len(below):] if p.startswith(below) else None
        got = os.path.join(tmp, rel.replace('/', os.sep)) if rel is not None else None
        if got is not None and not os.path.exists(got):
            got = None
        if got is None or md5(got) != md5(os.path.join(COOKED, p.replace('/', os.sep))):
            diff.append(p)
    shutil.rmtree(tmp, ignore_errors=True)
    if diff:
        fail('%s: %d files differ after extraction, e.g. %s' % (name, len(diff), diff[:3]))
    report[name] = dict(files=len(files), bytes=os.path.getsize(pak), md5=md5(pak), mount=mount)
    print('  %s: %d files, %d bytes, md5 %s, mount %s, listed = expected %s, extraction identical %s' % (
        name, len(files), os.path.getsize(pak), md5(pak), mount, listed == want, not diff))
json.dump(dict(report=report, fails=fails), open(os.path.join(OUT, 'make_paks_report.json'), 'w', newline='\n'), indent=1)
if fails:
    for name in report:
        os.remove(os.path.join(OUT, name))
    print('FAILED, paks removed')
    sys.exit(1)
print('PAKS OK')
