"""Prison 2 shipping steps inside Unreal (card id "Panopticon", menu name "Prison 2").

  P2S_MODE=inspect   prints the actors and streamed levels of the Prison wrappers and of Prison2_BP, saves nothing
  P2S_MODE=levelnav  Prison2_BP in place: removes its RecastNavMesh and NavMeshBoundsVolume (the mode wrappers own them)
  P2S_MODE=dup       duplicates GM_Maps/<Mode>/<Prefix>Prison into <Prefix>Panopticon for HP, TDM and DM and saves them
  P2S_MODE=wrappers  in a new process (loading a copy in the process that made it is a fatal error): streams Prison2_BP
                     instead of Prison_BP, removes the copied navmesh and sets the navmesh bounds over Prison 2
Start with /Engine/Maps/Entry, editor and game closed. The Prison files are only read.
"""
import os

import unreal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODE = os.environ.get('P2S_MODE', 'inspect')
CARD = os.environ.get('BCM_CARD', 'Panopticon')
LEVEL = os.environ.get('BCM_LEVEL', '/Game/Sandbox/Prison2/Prison2_BP')
UMAP = os.path.join(ROOT, *(LEVEL.replace('/Game/', 'Content/') + '.umap').split('/'))
MODES = (('Hardpoint', 'HP_'), ('TeamDeathmatch', 'TDM_'), ('DeathMatch', 'DM_'), ('Versus', 'VS_'), ('GunGame', 'GG_'), ('BodyBomb', 'BB_'), ('Wingman', 'WM_'))
_nav = [float(v) for v in os.environ.get('BCM_NAV', '0,0,1500,7200,7200,1900').split(',')]
NAV_CENTER, NAV_EXTENT = unreal.Vector(_nav[0], _nav[1], _nav[2]), unreal.Vector(_nav[3], _nav[4], _nav[5])
eal = unreal.EditorAssetLibrary
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def say(t):
    unreal.log_warning('[p2ship] ' + t)


def streamed(world):
    return [lvl.get_outer().get_path_name() for lvl in unreal.EditorLevelUtils.get_levels(world)]


def persistent_actors(world):
    lvl = world.get_editor_property('persistent_level') if hasattr(world, 'get_editor_property') else None
    acts = eas.get_all_level_actors()
    return [a for a in acts if a.get_level() == lvl] if lvl else acts


def describe(path):
    say('load_level %s: %s' % (path, les.load_level(path)))
    w = ues.get_editor_world()
    say('   world %s | streamed %s' % (w.get_path_name(), streamed(w)))
    ws = w.get_world_settings()
    for prop in ('default_game_mode', 'game_mode_override', 'navigation_system_config'):
        try:
            v = ws.get_editor_property(prop)
            say('   WorldSettings.%s = %s' % (prop, v.get_path_name() if hasattr(v, 'get_path_name') else v))
        except Exception as ex:
            say('   WorldSettings.%s: %s' % (prop, type(ex).__name__))
    counts = {}
    for a in eas.get_all_level_actors():
        lvl = a.get_level().get_outer().get_name()
        k = (lvl, a.get_class().get_name())
        counts[k] = counts.get(k, 0) + 1
    for (lvl, cls), n in sorted(counts.items()):
        if cls not in ('StaticMeshActor', 'SpotLight', 'PointLight', 'PlayerStart', 'GroupActor') or lvl.startswith(('HP_', 'TDM_', 'DM_')):
            say('   %-24s %-28s %d' % (lvl, cls, n))
    for a in eas.get_all_level_actors():
        if a.get_class().get_name() in ('NavMeshBoundsVolume', 'RecastNavMesh'):
            o, e = a.get_actor_bounds(False)
            say('   %s %s in %s center %s extent %s' % (a.get_class().get_name(), a.get_actor_label(), a.get_level().get_outer().get_name(), o, e))


if MODE == 'inspect':
    describe('/Game/GM_Maps/Hardpoint/HP_Prison')
    describe(LEVEL)
elif MODE == 'levelnav':
    say('load_level %s: %s' % (LEVEL, les.load_level(LEVEL)))
    w = ues.get_editor_world()
    acts = eas.get_all_level_actors()
    if w is None or 'Prison2_BP' not in w.get_path_name() or len(acts) < 800:
        say('ABORT: world %s with %d actors' % (w.get_path_name() if w else None, len(acts)))
        raise SystemExit
    doomed = [a for a in acts if a.get_class().get_name() in ('RecastNavMesh', 'NavMeshBoundsVolume')]
    say('removing %s' % [(a.get_class().get_name(), a.get_actor_label()) for a in doomed])
    for a in doomed:
        eas.destroy_actor(a)
    after = eas.get_all_level_actors()
    if len(after) != len(acts) - len(doomed):
        say('ABORT WITHOUT SAVING: actors %d -> %d' % (len(acts), len(after)))
        raise SystemExit
    mt0 = os.path.getmtime(UMAP)
    saved = les.save_current_level() and os.path.getmtime(UMAP) > mt0
    say('Prison2_BP actors %d -> %d | SAVED %s' % (len(acts), len(after), saved))
elif MODE == 'dup':
    for folder, prefix in MODES:
        # the game's own Prison has wrappers for HP/TDM/DM only (measured 22 Sep). For the four modes it lacks,
        # copy THIS card's TDM wrapper, which the same pass made two lines up: a wrapper is the same shell in every
        # mode, and copying a game wrapper of another map (Paintball) would leave that map's name in the name table,
        # which make_paks.py forbids.
        src = '/Game/GM_Maps/%s/%sPrison' % (folder, prefix)
        if not eal.does_asset_exist(src):
            src = '/Game/GM_Maps/TeamDeathmatch/TDM_%s' % CARD
        dst = '/Game/GM_Maps/%s/%s%s' % (folder, prefix, CARD)
        if eal.does_asset_exist(dst):
            say('kept %s' % dst)
            continue
        if not eal.does_asset_exist(src):
            say('ABORT: no source wrapper for %s (looked for %sPrison and TDM_%s)' % (folder, prefix, CARD))
            raise SystemExit
        if not eal.duplicate_asset(src, dst) or not eal.save_asset(dst, only_if_is_dirty=False):
            say('ABORT: could not duplicate and save %s' % dst)
            raise SystemExit
        say('duplicated %s -> %s' % (src, dst))
elif MODE == 'wrappers':
    for folder, prefix in MODES:
        dst = '/Game/GM_Maps/%s/%s%s' % (folder, prefix, CARD)
        if not eal.does_asset_exist(dst):
            say('ABORT: %s missing (run dup first)' % dst)
            raise SystemExit
        say('load_level %s: %s' % (dst, les.load_level(dst)))
        w = ues.get_editor_world()
        if w is None or not w.get_path_name().startswith(dst):
            say('ABORT: unexpected world %s' % (w.get_path_name() if w else None))
            raise SystemExit
        before = streamed(w)
        for lvl in unreal.EditorLevelUtils.get_levels(w):
            name = lvl.get_outer().get_path_name()
            if 'Prison_BP' in name:
                unreal.EditorLevelUtils.remove_level_from_world(lvl)
        added = unreal.EditorLevelUtils.add_level_to_world(w, LEVEL, unreal.LevelStreamingAlwaysLoaded)
        for a in eas.get_all_level_actors():
            owner = a.get_level().get_outer().get_path_name()
            if not owner.startswith(dst):
                continue
            if a.get_class().get_name() == 'RecastNavMesh':
                eas.destroy_actor(a)
        vols = [a for a in eas.get_all_level_actors() if a.get_class().get_name() == 'NavMeshBoundsVolume' and a.get_level().get_outer().get_path_name().startswith(dst)]
        for i, v in enumerate(vols):
            if i == 0:
                v.set_actor_location(NAV_CENTER, False, False)
                v.set_actor_scale3d(unreal.Vector(NAV_EXTENT.x / 100.0, NAV_EXTENT.y / 100.0, NAV_EXTENT.z / 100.0))
            else:
                eas.destroy_actor(v)
        if not vols:
            v = eas.spawn_actor_from_class(unreal.NavMeshBoundsVolume, NAV_CENTER)
            v.set_actor_scale3d(unreal.Vector(NAV_EXTENT.x / 100.0, NAV_EXTENT.y / 100.0, NAV_EXTENT.z / 100.0))
        # adding a streamed level makes it the current level: make the wrapper current again, or the save writes the
        # sublevel instead of the wrapper (measured 16 Sep: the wrappers kept streaming Prison_BP)
        short = dst.rsplit('/', 1)[1]
        if not les.set_current_level_by_name(short) or not les.get_current_level().get_outer().get_path_name().startswith(dst):
            say('ABORT WITHOUT SAVING: could not make %s current' % dst)
            raise SystemExit
        saved = les.save_current_level()
        w = ues.get_editor_world()
        bounds = [(a.get_actor_bounds(False)) for a in eas.get_all_level_actors() if a.get_class().get_name() == 'NavMeshBoundsVolume'
                  and a.get_level().get_outer().get_path_name().startswith(dst)]
        say('%s: streamed before %s | after %s | added %s | nav bounds %s | SAVED %s' % (
            dst, before, streamed(w), added is not None, [(str(o), str(e)) for o, e in bounds], saved))
say('done')
