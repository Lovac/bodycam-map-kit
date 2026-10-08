"""OFFLINE GATE (read-only): does a cooked _BP level carry the Hardpoint objective the way the game's own maps do?

usage:
  python gate_hardpoint_pattern.py [--zmin 420] [--min-previews 2] <pkg base> [<pkg base> ...]
      pkg base = cooked level path without .umap/.uexp (game extract or Saved/Cooked/.../Prison_BP)
  python gate_hardpoint_pattern.py --selftest
      runs on the 7 game Hardpoint _BP levels (must PASS) and on the installed Prison_BP (currently must FAIL)

Prints one PASS/FAIL line per package plus every failed rule; exit code 0 only if every package passes.
Decoding: Saved/hardpoint/level-diff/zoneleveldump.py (tagged + unversioned, usmap + BP schemas). Writes nothing.

Rules (each one is what the game's 7 Hardpoint _BP levels have, see FIX_PLAN.md section 3):
  R1  exactly 1 HardPointZone_C actor
  R2  the zone has exactly these 8 subobjects (name:class):
        Audio:AudioComponent Box:BoxComponent Decal:DecalComponent DefaultSceneRoot:SceneComponent
        HMSInterfaceComponent:HMS_InterfaceComponent WidgetActual:BodycamWidgetComponent
        WidgetNext:BodycamWidgetComponent ZoneCountdown:CountdownComponent
  R3  templates: SCS ones = HardPointZone_C.<Name>_GEN_VARIABLE, native ones = Default__HardPointZone_C.<Name>
  R4  the actor's own properties point at all 8 (+ RootComponent = DefaultSceneRoot)
  R5  serialized bindings on the zone itself: Box.OnComponentBeginOverlap/_0_, Box.OnComponentEndOverlap/_1_,
      ZoneCountdown.OnTick/_2_  (the names in HardPointZone_C's ComponentDelegateBinding_0)
  R6  zone Box carries no BoxExtent/RelativeScale3D/RelativeLocation override (the capture box is the class template's)
  R7  min-previews <= BP_PointZonePreview_C count <= 32 (VisitedMask is uint32), unique FNames
  R8  each preview has exactly BombZoneDecalActual:DecalComponent + DefaultSceneRoot:SceneComponent, templates
      BP_PointZonePreview_C.<Name>_GEN_VARIABLE
  R9  decal scale = the Blueprint construction script's X/Z swap already applied (a cooked game never reruns it):
      decal RelativeScale3D == (0.01*sz/sx, 0.2, 0.2*sx/sz) for root scale (sx,sy,sz); zone Decal the same
  R10 every zone/preview actor is in a PersistentLevel Actors array, bNotForClient = bNotForServer = 0
  R11 (only with --zmin) every preview root z >= zmin (the closed underground is not a valid objective)
  R12 the package imports /Script/Bodycam.BodycamWidgetComponent, /Script/Bodycam.CountdownComponent and
      /Script/HostMigrationSystem.HMS_InterfaceComponent, and every import directly under /Script/Bodycam or
      /Script/HostMigrationSystem is a name the game's usmap knows (analysis/asset_origin_audit.py passes any /Script/*,
      so a misspelled native placeholder would otherwise go through)
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'level-diff'))
import zoneleveldump as zld  # noqa: E402

ZONE_COMPS = {'Audio': 'AudioComponent', 'Box': 'BoxComponent', 'Decal': 'DecalComponent',
              'DefaultSceneRoot': 'SceneComponent', 'HMSInterfaceComponent': 'HMS_InterfaceComponent',
              'WidgetActual': 'BodycamWidgetComponent', 'WidgetNext': 'BodycamWidgetComponent',
              'ZoneCountdown': 'CountdownComponent'}
NATIVE = {'ZoneCountdown', 'HMSInterfaceComponent'}
PREV_COMPS = {'BombZoneDecalActual': 'DecalComponent', 'DefaultSceneRoot': 'SceneComponent'}
HPZ = '/Game/GM/Gamemode/HardPoint/HardPointZone.'
PZP = '/Game/GM/Gamemode/HardPoint/BP_PointZonePreview.'
BIND = {('Box', 'OnComponentBeginOverlap'): 'BndEvt__HardPointZone_Box_K2Node_ComponentBoundEvent_0_ComponentBeginOverlapSignature__DelegateSignature',
        ('Box', 'OnComponentEndOverlap'): 'BndEvt__HardPointZone_Box_K2Node_ComponentBoundEvent_1_ComponentEndOverlapSignature__DelegateSignature',
        ('ZoneCountdown', 'OnTick'): 'BndEvt__HardPointZone_ZoneCountdown_K2Node_ComponentBoundEvent_2_OnCountdownTick__DelegateSignature'}
EX = os.path.join(HERE, 'level-diff', 'extract')
GAME_MAPS = [r'pakchunk14-Windows\Map\Paintball\Paintball_BP']
SELFTEST_PRISON = os.path.join(EX, r'PanopticonPrison_P\Sandbox\Trenches\Prison_BP')


def find_game_maps():
    out = []
    for n in ('Paintball_BP', 'Hospital_BP', 'Rome_BP', 'AirSoft_BP', 'WornHouse_BP', 'PublicPool_BP', 'RussianBuilding_BP'):
        for root, _d, files in os.walk(EX):
            if 'PanopticonPrison' in root or 'zCabins' in root:
                continue
            if n + '.umap' in files:
                out.append(os.path.join(root, n)); break
    return out


def comp_map(actor):
    return {c['fullname']: c for c in actor['components']}


def vec(v, default):
    return tuple(float(x) for x in v) if isinstance(v, (list, tuple)) and len(v) == 3 else default


def decal_expected(root_scale):
    sx, sy, sz = root_scale
    return (0.01 * sz / sx, 0.2, 0.2 * sx / sz)


def close(a, b, tol=2e-3):
    return all(abs(x - y) <= tol * max(1.0, abs(y)) for x, y in zip(a, b))


def check(rec, zmin=None, min_prev=2):
    fails = []
    acts = rec['actors']
    zones = [a for a in acts if a['cls'] == 'HardPointZone_C']
    prevs = [a for a in acts if a['cls'] == 'BP_PointZonePreview_C']
    if len(zones) != 1:
        fails.append('R1 HardPointZone_C count = %d (game: 1)' % len(zones))
    for z in zones:
        tag = 'zone %s' % z['fullname']
        cm = comp_map(z)
        got = {k: v['cls'] for k, v in cm.items()}
        if got != ZONE_COMPS:
            miss = sorted(set(ZONE_COMPS) - set(got)); extra = sorted(set(got) - set(ZONE_COMPS))
            wrong = sorted(k for k in set(got) & set(ZONE_COMPS) if got[k] != ZONE_COMPS[k])
            fails.append('R2 %s subobjects: missing %s extra %s wrong-class %s' % (tag, miss, extra, wrong))
        for n, c in cm.items():
            want = 'import:' + HPZ + ('Default__HardPointZone_C.%s' % n if n in NATIVE else 'HardPointZone_C.%s_GEN_VARIABLE' % n)
            if n in ZONE_COMPS and c['template'] != want:
                fails.append('R3 %s.%s template %s (want %s)' % (tag, n, c['template'], want))
        for n in ZONE_COMPS:
            v = z['props'].get(n)
            if not (isinstance(v, str) and v.endswith(':' + n)):
                fails.append('R4 %s actor property %s = %r' % (tag, n, v))
        rc = z['props'].get('RootComponent')
        if not (isinstance(rc, str) and rc.endswith(':DefaultSceneRoot')):
            fails.append('R4 %s RootComponent = %r' % (tag, rc))
        for (cn, dn), fn in BIND.items():
            c = cm.get(cn)
            vals = (c or {}).get('props', {}).get(dn) or []
            want = 'export%d:%s::%s' % (z['export'], z['fullname'], fn)
            if want not in vals:
                fails.append('R5 %s %s.%s binding missing (have %s)' % (tag, cn, dn, vals))
        box = cm.get('Box')
        if box:
            ov = sorted(k for k in ('BoxExtent', 'RelativeScale3D', 'RelativeLocation') if k in box['props'])
            if ov:
                fails.append('R6 %s Box overrides %s = %s' % (tag, ov, [box['props'][k] for k in ov]))
        dec = cm.get('Decal'); root = cm.get('DefaultSceneRoot')
        if dec and root:
            exp = decal_expected(vec(root['props'].get('RelativeScale3D'), (1.0, 1.0, 1.0)))
            have = vec(dec['props'].get('RelativeScale3D'), (0.2, 0.2, 0.01))
            if not close(have, exp):
                fails.append('R9 %s Decal RelativeScale3D %s (want %s)' % (tag, have, tuple(round(x, 4) for x in exp)))
    if not (min_prev <= len(prevs) <= 32):
        fails.append('R7 BP_PointZonePreview_C count = %d (want %d..32)' % (len(prevs), min_prev))
    names = [p['fullname'] for p in prevs]
    if len(set(names)) != len(names):
        fails.append('R7 duplicate preview FNames')
    for p in prevs:
        tag = 'preview %s' % p['fullname']
        cm = comp_map(p)
        got = {k: v['cls'] for k, v in cm.items()}
        if got != PREV_COMPS:
            fails.append('R8 %s subobjects %s (want %s)' % (tag, got, PREV_COMPS))
        for n, c in cm.items():
            want = 'import:' + PZP + 'BP_PointZonePreview_C.%s_GEN_VARIABLE' % n
            if n in PREV_COMPS and c['template'] != want:
                fails.append('R8 %s.%s template %s' % (tag, n, c['template']))
        root = cm.get('DefaultSceneRoot'); dec = cm.get('BombZoneDecalActual')
        if root and dec:
            exp = decal_expected(vec(root['props'].get('RelativeScale3D'), (1.0, 1.0, 1.0)))
            have = vec(dec['props'].get('RelativeScale3D'), (0.2, 0.2, 0.01))
            if not close(have, exp):
                fails.append('R9 %s BombZoneDecalActual RelativeScale3D %s (want %s)' % (tag, have, tuple(round(x, 4) for x in exp)))
        if zmin is not None and root:
            loc = vec(root['props'].get('RelativeLocation'), (0.0, 0.0, 0.0))
            if loc[2] < zmin:
                fails.append('R11 %s root z %.1f < %.1f' % (tag, loc[2], zmin))
    for a in zones + prevs:
        if a['outer'] != 'PersistentLevel' or not a['level_actor_slot']:
            fails.append('R10 %s %s not in a PersistentLevel Actors array (outer %s)' % (a['cls'], a['fullname'], a['outer']))
        if a['notforclient'] or a['notforserver']:
            fails.append('R10 %s %s NotForClient/Server set' % (a['cls'], a['fullname']))
    return fails, len(zones), len(prevs)


REQ_IMPORTS = ('/Script/Bodycam.BodycamWidgetComponent', '/Script/Bodycam.CountdownComponent',
               '/Script/HostMigrationSystem.HMS_InterfaceComponent')


def check_imports(q, usmap):
    fails = []
    full = set(q.full_import(-(i + 1)) for i in range(len(q.imports)))
    for r in REQ_IMPORTS:
        if r not in full:
            fails.append('R12 import %s missing' % r)
    known = set(usmap.structs)
    for p in sorted(full):
        for pre in ('/Script/Bodycam.', '/Script/HostMigrationSystem.'):
            if p.startswith(pre):
                n = p[len(pre):]
                if '.' not in n and ':' not in n and n not in known and not n.startswith('Default__'):
                    fails.append('R12 import %s is not a class/struct in the game usmap' % p)
    return fails


def run(bases, zmin, min_prev):
    reg = zld.build_registry()
    ok_all = True
    for b in bases:
        rec, q, _d = zld.dump_pkg(reg, b)
        fails, nz, npv = check(rec, zmin, min_prev)
        fails += check_imports(q, reg.u)
        ok = not fails
        ok_all &= ok
        print('%s  %s  (%s, tagged=%s, zones=%d previews=%d)' % ('PASS' if ok else 'FAIL', rec['pkgname'], os.path.relpath(b, HERE), rec['tagged'], nz, npv))
        seen = {}
        for f in fails:   # collapse repeats of the same rule
            key = f.split(' ')[0] + ' ' + f.split(' ', 2)[1]
            seen[key] = seen.get(key, 0) + 1
            if seen[key] <= 3:
                print('    ' + f)
        for k, n in seen.items():
            if n > 3:
                print('    ... %s repeated %d times' % (k, n))
    return ok_all


if __name__ == '__main__':
    a = sys.argv[1:]
    zmin = None; min_prev = 2
    if '--zmin' in a:
        i = a.index('--zmin'); zmin = float(a[i + 1]); del a[i:i + 2]
    if '--min-previews' in a:
        i = a.index('--min-previews'); min_prev = int(a[i + 1]); del a[i:i + 2]
    if a == ['--selftest']:
        games = find_game_maps()
        print('== game Hardpoint _BP levels (must PASS)')
        g = run(games, None, min_prev)
        print('== installed Prison_BP (PanopticonPrison_P.pak extract; with the stub-cooked zones it must FAIL)')
        p = run([SELFTEST_PRISON], 420.0, min_prev)
        print('SELFTEST %s: game maps %s, Prison %s' % ('OK' if (g and not p) else 'BROKEN', 'pass' if g else 'FAIL', 'pass' if p else 'fail'))
        sys.exit(0 if (g and not p) else 1)
    sys.exit(0 if run(a, zmin, min_prev) else 1)
