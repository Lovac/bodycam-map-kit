"""Bodycam Map Kit, step 2b (runs inside the editor, after the probe). Two things every Hardpoint map needs, checked
BEFORE the long cook instead of after it:
  1. exactly 1 HardPointZone and 2-32 BP_PointZonePreview placed from /Game/GM/Gamemode/HardPoint (the packer's
     hardpoint gate refuses anything else, but only after cooking);
  2. the HardPointZone's marker widgets (WidgetNext, WidgetActual) get NO collision. They are 19 x 11 m invisible
     world-space panels that block the Visibility channel; in Prison V2P one stood across the tower and players
     reported "an invisible wall" (Nexus, 2 Oct 2026). The marker still draws; only its collision goes.
Saves the level only when it changed something. Env BCM_LEVEL = the level path (/Game/Sandbox/<Id>/<Id>_BP)."""
import os

import unreal

LEVEL = os.environ['BCM_LEVEL']
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def say(t):
    unreal.log_warning('[bcmfix] ' + t)


if not les.load_level(LEVEL):
    say('PROBLEM: could not open %s' % LEVEL)
    raise SystemExit(1)
acts = eas.get_all_level_actors()
zones = [a for a in acts if a.get_class().get_name() == 'HardPointZone_C']
previews = [a for a in acts if a.get_class().get_name() == 'BP_PointZonePreview_C']
ok = True
if len(zones) != 1:
    say('PROBLEM: %d HardPointZone in the level; place exactly 1 (Content/GM/Gamemode/HardPoint/HardPointZone)' % len(zones))
    ok = False
if not 2 <= len(previews) <= 32:
    say('PROBLEM: %d BP_PointZonePreview in the level; place 2 to 32 (Content/GM/Gamemode/HardPoint/BP_PointZonePreview), '
        'one per spot the point can move to' % len(previews))
    ok = False
if not ok:
    raise SystemExit(1)
changed = 0
for z in zones:
    for c in z.get_components_by_class(unreal.WidgetComponent):
        if str(c.get_collision_profile_name()) != 'NoCollision':
            c.set_collision_profile_name('NoCollision')
            c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
            changed += 1
say('hardpoints OK: 1 zone, %d previews; marker widgets set to no collision: %d' % (len(previews), changed))
if changed:
    z.modify()
    say('saved %s' % les.save_current_level())
say('done')
