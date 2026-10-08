"""Probe a level before shipping it as a Bodycam card (22 Sep 2026, for Scripts/newmap.sh).

Prints one KEY=VALUE per line so bash can read it, and refuses with a plain sentence when the level cannot ship:
no PlayerStart, tilted PlayerStarts (the Prison 2 generator bug: a spawn with pitch looks at the floor), no lighting.

  BCM_LEVEL=/Game/Sandbox/Alpine/Alpine_BP
Start with /Engine/Maps/Entry, editor and game closed.
"""
import os

import unreal

LEVEL = os.environ['BCM_LEVEL']
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def say(t):
    unreal.log_warning('[bcmprobe] ' + t)


if not unreal.EditorAssetLibrary.does_asset_exist(LEVEL):
    raise SystemExit('[bcmprobe] ABORT: there is no level at %s' % LEVEL)
say('load_level %s: %s' % (LEVEL, les.load_level(LEVEL)))
w = ues.get_editor_world()
short = LEVEL.rsplit('/', 1)[1]
if w is None or short not in w.get_path_name():
    raise SystemExit('[bcmprobe] ABORT: wrong world %s' % (w.get_path_name() if w else None))

acts = eas.get_all_level_actors()
starts = [a for a in acts if a.get_class().get_name() == 'PlayerStart']
tilted = [a for a in starts if abs(a.get_actor_rotation().pitch) > 0.5 or abs(a.get_actor_rotation().roll) > 0.5]
suns = [a for a in acts if isinstance(a, unreal.DirectionalLight)]
skies = [a for a in acts if isinstance(a, unreal.SkyLight)]
lands = [a for a in acts if 'Landscape' == a.get_class().get_name()]
meshes = [a for a in acts if isinstance(a, unreal.StaticMeshActor)]

lo = [1e18, 1e18, 1e18]
hi = [-1e18, -1e18, -1e18]
for a in acts:
    if not (isinstance(a, unreal.StaticMeshActor) or a.get_class().get_name() == 'Landscape'):
        continue
    try:
        o, e = a.get_actor_bounds(False)
    except Exception:
        continue
    if e.x <= 0 and e.y <= 0 and e.z <= 0:
        continue
    for i, (c, ex) in enumerate(((o.x, e.x), (o.y, e.y), (o.z, e.z))):
        lo[i] = min(lo[i], c - ex)
        hi[i] = max(hi[i], c + ex)
if lo[0] > hi[0]:                                   # nothing with bounds: fall back to the spawns
    for a in starts:
        p = a.get_actor_location()
        for i, c in enumerate((p.x, p.y, p.z)):
            lo[i] = min(lo[i], c - 5000.0)
            hi[i] = max(hi[i], c + 5000.0)

say('actors %d | PlayerStart %d (tilted %d) | StaticMeshActor %d | Landscape %d | sun %d sky %d'
    % (len(acts), len(starts), len(tilted), len(meshes), len(lands), len(suns), len(skies)))

problems = []
if len(starts) < 4:
    problems.append('the level has %d PlayerStart actors; it needs at least 4 (8+ is better). '
                    'Place Actors > PlayerStart, drop them on open ground.' % len(starts))
if tilted:
    problems.append('%d PlayerStart actors are tilted (pitch or roll not 0), so players spawn looking at the floor '
                    'or the ceiling. Set their Rotation X and Y to 0.' % len(tilted))
if not suns or not skies:
    problems.append('the level has %d DirectionalLight and %d SkyLight; it needs one of each or the map is black.'
                    % (len(suns), len(skies)))
for t in problems:
    say('PROBLEM: ' + t)
if problems:
    raise SystemExit('[bcmprobe] ABORT: the level is not ready to ship (%d problem(s) above)' % len(problems))

cx, cy, cz = [(lo[i] + hi[i]) / 2.0 for i in range(3)]
ex, ey, ez = [max(1000.0, (hi[i] - lo[i]) / 2.0 * 1.05) for i in range(3)]
say('BOUNDS=%.0f,%.0f,%.0f,%.0f,%.0f,%.0f' % (cx, cy, cz, ex, ey, ez))
say('SPAWNS=%d' % len(starts))
say('size %.0f x %.0f m, height %.0f m' % (2 * ex / 100, 2 * ey / 100, 2 * ez / 100))
say('done')
