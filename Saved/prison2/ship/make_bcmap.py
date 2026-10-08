"""Prison 2 map package for the Bodycam Map Installer (BCMAP_FORMAT.md sections 1 and 2).

    python make_bcmap.py      -> out/Panopticon-<version>.zip, out/Panopticon.bcmap (same bytes), out/Panopticon.export.json

Takes paks/ (make_paks.py), menu/ (make_menu.py) and thumb/thumb.png. Paks are stored, everything else deflated.
"""
import hashlib
import json
import os
import shutil
import sys
import zipfile
import re


def steam_build(default='25228199'):
    """30 Sep (ported from the V2P packager, 29 Sep): the card says which Bodycam build it was made on; read it from
    the installed game (the installer warns players whose build differs, so a stale constant warned everyone)"""
    acf = os.environ.get('BCM_STEAM_ACF', 'C:/Program Files (x86)/Steam/steamapps/appmanifest_2406770.acf')
    try:
        m = re.search(r'"buildid"\s*"(\d+)"', open(acf, encoding='utf-8', errors='replace').read())
        return m.group(1) if m else default
    except OSError:
        return default

HERE = os.path.dirname(os.path.abspath(__file__))
SHIP = os.environ.get('BCM_SHIP_DIR', HERE)   # per-card output dir; HERE stays the code dir (tools/, templates/)
CARD = os.environ.get('BCM_CARD', 'Panopticon')
VERSION = '0.1.6'
sys.path.insert(0, HERE)
DESCRIPTION = os.environ.get('BCM_DESCRIPTION', 'Custom map: a panopticon prison with cell rings, office wings, parking and a roof fight')
CARD_JSON = {
    'format': 1,
    'id': CARD,
    'display_name': os.environ.get('BCM_DISPLAY', 'Prison 2'),
    'description': DESCRIPTION,
    'version': VERSION,
    'author': os.environ.get('BCM_AUTHOR', 'Unknown'),
    'modes': ['HP', 'TDM', 'DM', 'VS', 'GG', 'BB', 'WM'],   # 22 Sep: every hostable mode
    'level_package': os.environ.get('BCM_LEVEL', '/Game/Sandbox/Prison2/Prison2_BP'),
    'thumbnail': 'thumb.png',
    'menu_texture': '/Game/UI/Textures/Maps/' + ('T_UI_Map_%s' % CARD).ljust(22, '0'),
    'weather_da': os.environ.get('BCM_WEATHER', '/Game/GM/WeatherManaer/DataAssets/DA_DebugBadWeatherWeatherConfig'),   # 21 Sep: storm (Rain_Thunderstorm is in this set)
    'replaces': [],
    'game_build': steam_build(),
    'credits': ['Bodycam by Reissad Studio (base game assets)'],
}


def md5(p):
    return hashlib.md5(open(p, 'rb').read()).hexdigest()


def main():
    entries = [('card.json', None), ('thumb.png', os.path.join(SHIP, 'thumb', 'thumb.png'))]
    for name in ('z%s_9_P.pak' % CARD, 'z%s_Modes_9_P.pak' % CARD):
        entries.append(('paks/' + name, os.path.join(SHIP, 'paks', name)))
    menu = os.path.join(SHIP, 'menu')
    for d, _, fs in os.walk(menu):
        for f in sorted(fs):
            full = os.path.join(d, f)
            entries.append(('menu/' + os.path.relpath(full, menu).replace(os.sep, '/'), full))
    out = os.path.join(SHIP, 'out')
    os.makedirs(out, exist_ok=True)
    zpath = os.path.join(out, '%s-%s.zip' % (CARD, VERSION))
    card_bytes = (json.dumps(CARD_JSON, indent=2, ensure_ascii=True) + '\n').encode('utf-8')
    with zipfile.ZipFile(zpath, 'w') as z:
        for name, src in entries:
            data = card_bytes if src is None else open(src, 'rb').read()
            info = zipfile.ZipInfo(name, date_time=(2026, 9, 16, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED if name.startswith('paks/') else zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    shutil.copyfile(zpath, os.path.join(out, '%s.bcmap' % CARD))
    report = dict(zip=os.path.basename(zpath), md5=md5(zpath), bytes=os.path.getsize(zpath),
                  files={name: (md5(src) if src else hashlib.md5(card_bytes).hexdigest()) for name, src in entries}, card=CARD_JSON)
    json.dump(report, open(os.path.join(out, '%s.export.json' % CARD), 'w', newline='\n'), indent=1)
    print('%s: %d entries, %d bytes, md5 %s' % (zpath, len(entries), os.path.getsize(zpath), report['md5']))
    for name, _ in entries:
        print('  ', name)


if __name__ == '__main__':
    main()
