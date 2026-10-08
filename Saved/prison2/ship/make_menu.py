"""Menu files of the Prison 2 card (id Panopticon), no Unreal. BCMAP_FORMAT.md section 4.

    python make_menu.py <photo 2048x1024 png>      -> menu/UI/MetaData/DA_Panopticon_{HP,TDM,DM}.{uasset,uexp}
                                                      menu/UI/Textures/Maps/T_UI_Map_Panopticon000.{uasset,uexp}

Each DA is the game's DA_Paintball rewritten by dt_add_row.make_da: object DA_Panopticon_<Mode>, LevelName
/Game/GM_Maps/<Folder>/<Prefix>Panopticon?PrisonLobbyBypass, Texts = display name and description with fixed uuid5 keys
(the same export always gives the same bytes), thumbnail and loading screen pointing at the card texture. The texture is
the game's HighresScreenshot00441 cloned under the 22-letter name T_UI_Map_Panopticon000 with the photo as its DXT5 payload.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
SHIP = os.environ.get('BCM_SHIP_DIR', HERE)   # per-card output dir; HERE stays the code dir (tools/, templates/)
sys.path.insert(0, os.path.join(HERE, 'tools'))
sys.dont_write_bytecode = True
import dt_add_row as T  # noqa: E402

CARD = os.environ.get('BCM_CARD', 'Panopticon')
DISPLAY = os.environ.get('BCM_DISPLAY', 'Prison 2')
DESCRIPTION = os.environ.get('BCM_DESCRIPTION', 'Custom map: a panopticon prison with cell rings, office wings, parking and a roof fight')
MODES = (('HP', 'Hardpoint', 'HP_'), ('TDM', 'TeamDeathmatch', 'TDM_'), ('DM', 'DeathMatch', 'DM_'), ('VS', 'Versus', 'VS_'), ('GG', 'GunGame', 'GG_'), ('BB', 'BodyBomb', 'BB_'), ('WM', 'Wingman', 'WM_'))
TEMPLATE_DA = os.path.join(HERE, 'templates', 'DA_Paintball')
TEMPLATE_TEX = os.path.join(HERE, 'templates', 'HighresScreenshot00441')
TEXTURE = ('T_UI_Map_%s' % CARD).ljust(22, '0')   # 22 = the length proven in game (BCMAP_FORMAT 4.2);
assert len(CARD) <= 13, 'the card id must be 13 characters or fewer so T_UI_Map_<Id> pads to 22'
TEX_PATH = '/Game/UI/Textures/Maps/' + TEXTURE
OUT = os.path.join(SHIP, 'menu', 'UI')
assert len(TEXTURE) == len('HighresScreenshot00441')


def md5(p):
    return hashlib.md5(open(p, 'rb').read()).hexdigest()


def main(photo):
    shutil.rmtree(os.path.join(SHIP, 'menu'), ignore_errors=True)
    ok = True
    for mode, folder, prefix in MODES:
        keys = iter([uuid.uuid5(uuid.NAMESPACE_URL, 'bcmap/%s/%s/%d' % (CARD, mode, i)).hex.upper() for i in (0, 1)])

        def fixed_text(src, keys=keys):
            return T.struct.pack('<Ib', 0, 0) + T.fstring_bytes('') + T.fstring_bytes(next(keys)) + T.fstring_bytes(src)

        T.base_text = fixed_text
        base = os.path.join(OUT, 'MetaData', 'DA_%s_%s' % (CARD, mode))
        level = '/Game/GM_Maps/%s/%s%s?PrisonLobbyBypass' % (folder, prefix, CARD)
        T.make_da(TEMPLATE_DA, base, 'Paintball', '%s_%s' % (CARD, mode), DISPLAY, DESCRIPTION, level_name=level)
        # point the thumbnail and loading screen at the card texture (same-length names)
        d = open(base + '.uasset', 'rb').read()
        u = open(base + '.uexp', 'rb').read()
        H = T.Header(d)
        n = 0
        for i, (s, h) in enumerate(H.names):
            if 'HighresScreenshot00441' in s:
                s2 = s.replace('/Game/UI/Textures/Maps/HighresScreenshot00441', TEX_PATH).replace('HighresScreenshot00441', TEXTURE)
                H.names[i] = (s2, T.name_entry(s2)[-4:])
                n += 1
        assert n == 2, 'thumbnail names found: %d' % n
        data = u[:-4]
        open(base + '.uasset', 'wb').write(H.build(len(data)))
        ok = T.verify(base) and ok
        names = T.Pkg(base).names
        assert level in names and TEX_PATH in names and not any('Paintball' in s or 'Highres' in s for s in names), names
        print('DA_%s_%s: LevelName %s, texture %s, md5 %s / %s' % (CARD, mode, level, TEX_PATH, md5(base + '.uasset')[:8], md5(base + '.uexp')[:8]))
    tex_out = os.path.join(OUT, 'Textures', 'Maps')
    os.makedirs(tex_out, exist_ok=True)
    tools = os.path.join(HERE, 'tools')
    r = subprocess.run([sys.executable, '-X', 'utf8', os.path.join(tools, 'thumb_clone.py'), TEMPLATE_TEX, TEXTURE, photo],
                       capture_output=True, text=True)
    print(r.stdout[-1500:], r.stderr[-1500:])
    if r.returncode != 0:
        print('FAIL: thumb_clone.py exit %d' % r.returncode)
        sys.exit(1)
    for ext in ('uasset', 'uexp'):
        shutil.copy2(os.path.join(tools, 'thumb_out', '%s.%s' % (TEXTURE, ext)), tex_out)
    q = T.Pkg(os.path.join(tex_out, TEXTURE))
    assert q.pkgname == TEX_PATH, q.pkgname
    print('%s: package %s, uexp %d bytes, md5 %s' % (TEXTURE, q.pkgname, os.path.getsize(os.path.join(tex_out, TEXTURE + '.uexp')),
                                                   md5(os.path.join(tex_out, TEXTURE + '.uexp'))[:8]))
    print('menu files %s' % ('OK' if ok else 'FAILED verify'))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main(sys.argv[1])
