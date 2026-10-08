"""kit_game_files.py: copy the few game files the kit reads out of YOUR OWN Bodycam install (7 Oct 2026).

The public kit ships no file of the game. The packer and the Hardpoint check still need to read a handful of the
game's cooked packages (the hardpoint zone classes, a menu data asset and a menu texture to clone) and the list of
files in the game's paks. This script takes them from your installed game with Unreal's own UnrealPak, once.
newmap.sh runs it by itself when the files are missing; run it again after a big game update:
    python Scripts/kit_game_files.py [--force]
Environment: BCM_GAME = the Bodycam folder (the one holding Bodycam/Content/Paks), found through Steam if unset;
             BCM_UNREALPAK = UnrealPak.exe, default the UE 5.5 install."""
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

KIT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
UP = os.environ.get('BCM_UNREALPAK', r'C:\Program Files\Epic Games\UE_5.5\Engine\Binaries\Win64\UnrealPak.exe')
INDEX = os.path.join(KIT, 'Saved', 'menu_test', 'game_pak_index.tsv')
EXTRACT = os.path.join(KIT, 'Saved', 'hpgate', 'data', 'extract')
TEMPLATES = os.path.join(KIT, 'Saved', 'prison2', 'ship', 'templates')
# (pak, filter, where it goes: None = Saved/hpgate/data/extract/<pak name>/<path in the pak>, else a folder)
WANT = [('pakchunk26-Windows', '*GM/Gamemode/HardPoint/HardPointZone.*', None),
        ('pakchunk26-Windows', '*GM/Gamemode/HardPoint/BP_PointZonePreview.*', None),
        ('pakchunk26-Windows', '*GM/Gamemode/BodyBomb/BombZone.*', None),
        ('pakchunk26-Windows', '*STR_PlantZone.*', None),
        ('pakchunk18-Windows', '*DATA/STR/WEP/STR_RANGE.*', None),
        ('pakchunk24-Windows', '*UI/MetaData/DA_Paintball.*', TEMPLATES),
        ('pakchunk24-Windows', '*UI/Textures/Maps/HighresScreenshot00441.*', TEMPLATES)]
CHECK = [os.path.join(EXTRACT, 'pakchunk26-Windows', 'GM', 'Gamemode', 'HardPoint', 'HardPointZone.uasset'),
         os.path.join(TEMPLATES, 'DA_Paintball.uasset'), os.path.join(TEMPLATES, 'HighresScreenshot00441.uexp'), INDEX]


def die(msg):
    sys.exit('*** ' + msg)


def steam_libraries():
    roots = []
    try:
        import winreg
        for hive, key in ((winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam'),
                          (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam')):
            try:
                with winreg.OpenKey(hive, key) as k:
                    for name in ('SteamPath', 'InstallPath'):
                        try:
                            roots.append(winreg.QueryValueEx(k, name)[0])
                        except OSError:
                            pass
            except OSError:
                pass
    except ImportError:
        pass
    roots.append(r'C:\Program Files (x86)\Steam')
    libs = []
    for r in roots:
        vdf = os.path.join(r, 'steamapps', 'libraryfolders.vdf')
        libs.append(r)
        if os.path.exists(vdf):
            libs += [p.replace('\\\\', '\\') for p in re.findall(r'"path"\s+"([^"]+)"', open(vdf, encoding='utf-8', errors='replace').read())]
    seen, out = set(), []
    for p in libs:
        n = os.path.normcase(os.path.normpath(p))
        if n not in seen:
            seen.add(n)
            out.append(p)
    return out


def find_paks():
    cands = [os.environ['BCM_GAME']] if os.environ.get('BCM_GAME') else \
        [os.path.join(l, 'steamapps', 'common', 'Bodycam') for l in steam_libraries()]
    for c in cands:
        p = os.path.join(c, 'Bodycam', 'Content', 'Paks')
        if os.path.exists(os.path.join(p, 'pakchunk0-Windows.pak')):
            return p
    die('could not find Bodycam. Set BCM_GAME to the Bodycam game folder (the one holding Bodycam\\Content\\Paks), e.g.\n'
        '    BCM_GAME="D:/SteamLibrary/steamapps/common/Bodycam" bash Scripts/newmap.sh ...')


def unrealpak(*args):
    r = subprocess.run([UP] + list(args), capture_output=True, text=True, errors='replace')
    return r.returncode, r.stdout + r.stderr


def main():
    if '--force' not in sys.argv and all(os.path.exists(p) for p in CHECK):
        print('game files present (python Scripts/kit_game_files.py --force to take them again)')
        return
    if not os.path.exists(UP):
        die('UnrealPak not found at %s (install Unreal Engine 5.5, or set BCM_UNREALPAK)' % UP)
    paks = find_paks()
    print('game paks: %s' % paks)

    # 1. the list of every file in the game's own paks (mod paks *_P.pak are not the game)
    where = {}
    names = sorted(os.path.basename(p) for p in glob.glob(os.path.join(paks, 'pakchunk*-Windows.pak')))
    for name in names:
        rc, out = unrealpak(os.path.join(paks, name), '-List')
        m = re.search(r'with mount point "(?:\.\./)*([^"]*)"', out)
        if rc != 0 or not m:
            die('UnrealPak could not list %s:\n%s' % (name, out[-800:]))
        mount = m.group(1)
        for f in re.findall(r'Display: "([^"]+)" offset:', out):
            where.setdefault(mount + f, []).append(name)
    if not where:
        die('the game paks listed no files')
    os.makedirs(os.path.dirname(INDEX), exist_ok=True)
    with open(INDEX + '.tmp', 'w', encoding='utf-8', newline='\n') as f:
        for p in sorted(where):
            f.write('%s\t%s\n' % (p, ','.join(where[p])))
    os.replace(INDEX + '.tmp', INDEX)
    print('pak index: %d files in %d paks' % (len(where), len(names)))

    # 2. the packages the packer and the Hardpoint check read
    for pak, flt, dest in WANT:
        tmp = tempfile.mkdtemp(prefix='bcmkit_')
        try:
            rc, out = unrealpak(os.path.join(paks, pak + '.pak'), '-Extract', tmp, '-Filter=' + flt)
            got = [os.path.join(dp, f) for dp, _d, fs in os.walk(tmp) for f in fs]
            if rc != 0 or not got:
                die('could not take %s from %s.pak (did a game update move it?)\n%s' % (flt, pak, out[-800:]))
            for g in got:
                rel = os.path.relpath(g, tmp)
                d = os.path.join(dest, os.path.basename(rel)) if dest else os.path.join(EXTRACT, pak, rel)
                os.makedirs(os.path.dirname(d), exist_ok=True)
                shutil.copyfile(g, d)
            print('  %s: %d files' % (flt.strip('*'), len(got)))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    missing = [p for p in CHECK if not os.path.exists(p)]
    if missing:
        die('still missing after extraction: %s' % missing)
    print('game files ready')


if __name__ == '__main__':
    main()
