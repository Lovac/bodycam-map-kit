#!/usr/bin/env bash
# newmap.sh: take ANY level in BodycamSandbox and put it in Bodycam as its own card (22 Sep 2026).
#
#   bash Scripts/newmap.sh <Id> "<Display name>" <photo.png> [VERSION]
#
#   Id            letters and digits only, 2-23 characters, no underscore (BCMAP_FORMAT.md 3.1).
#                 The level must be at Content/Sandbox/<Id>/<Id>_BP.umap  (override with BCM_LEVEL=...)
#   Display name  what the card says in the game's menu.
#   photo.png     any .png/.jpg screenshot; it is centre-cropped to 2:1 and resized to the sizes needed.
#   VERSION       x.y.z, default 0.1.0. Must be above the installed one if the card already exists.
#
# It does, refusing with one plain sentence at the first thing that is wrong:
#   1 checks the Id, the photo and that the level exists
#   2 probes the level in the editor: spawns present and level, lighting present, and measures its bounds
#   3 duplicates the 7 game-mode wrappers and points them at your level, with a navmesh box over its bounds
#   4 builds the menu data assets and the menu texture from the photo
#   5 cooks, packs the two paks, packages the .bcmap and installs it
# Everything of this card lives in Saved/maps/<Id>/ ; Prison 2 is untouched.
set -u
export MSYS_NO_PATHCONV=1
SB=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
UE="${BCM_UE:-/c/Program Files/Epic Games/UE_5.5/Engine/Binaries/Win64/UnrealEditor-Cmd.exe}"
# 25 Sep 2026 (Lovac: the editor windows are "very distracting while I do other stuff"): the editor script steps run
# with no renderer and no window; UE_HIDE= (empty) brings the window back.
UE_HIDE=${UE_HIDE--NullRHI}
PROJ="$(cygpath -w "$SB/BodycamSandbox.uproject")"
LOCK="$SB/Saved/torre_v3/tools/ue_lock.sh"
APP=$SB/Saved/release/app/BodycamMapInstaller.exe
cd "$SB" || exit 2

die() { echo; echo "*** $*"; exit 1; }
say() { echo "== $(date +%H:%M:%S) $*"; }

[ $# -ge 3 ] || die "usage: bash Scripts/newmap.sh <Id> \"<Display name>\" <photo 2048x1024.png> [VERSION]
       example: bash Scripts/newmap.sh Alpine \"Alpine Valley\" ~/Desktop/alpine.png 0.1.0"
ID=$1; DISPLAY=$2; PHOTO=$3; VERSION=${4:-0.1.0}

# ---------------------------------------------------------------------------------------------------- 1. the basics
echo "$ID" | grep -qE '^[A-Za-z][A-Za-z0-9]{1,12}$' || die "the Id \"$ID\" is not allowed: letters and digits only, 2 to 13 characters, no underscore or space."
echo "$ID" | grep -qiE 'prison$|gamemode|paintball' && die "the Id \"$ID\" ends in Prison or contains GameMode/Paintball; the packer would refuse it. Pick another Id."
echo "$ID" | grep -qiE 'lobby' && die "the Id \"$ID\" contains \"lobby\", which the game uses for its own levels."
for g in Trenches Russian WornHouse Airsoft Hospital BombHouse Pool Rome Paintball Logistics CQB Tumblewood Backrooms Airport OilRig Pit Assylum Village ShootingRange RussianBuilding PublicPool; do
  echo "$ID" | grep -qiE "$g" && die "the Id \"$ID\" contains the game's own map name \"$g\"; the game's menu matches names by substring, so that Id would break \"$g\"."
done
[ -f "$PHOTO" ] || die "there is no photo at $PHOTO"
PHOTO=$(cd "$(dirname "$PHOTO")" && pwd)/$(basename "$PHOTO")   # absolute: the menu step runs from another folder
python -c "from PIL import Image;Image.open(r'$(cygpath -m "$PHOTO")')" 2>/dev/null || die "could not read $PHOTO as a picture. Use a .png or .jpg screenshot."

LEVEL=${BCM_LEVEL:-/Game/Sandbox/$ID/${ID}_BP}
UMAP="Content/${LEVEL#/Game/}.umap"
[ -f "$UMAP" ] || die "there is no level at $UMAP
       Make one in the editor: File > Save Current Level As > Content/Sandbox/$ID/${ID}_BP
       (or point this script at an existing one with BCM_LEVEL=/Game/Sandbox/Foo/Foo_BP)"

SHIPDIR=$SB/Saved/maps/$ID
COOKDIR=$(dirname "${LEVEL#/Game/}")            # /Game/Sandbox/Alpine/Alpine_BP -> Sandbox/Alpine
LEAF=$(basename "$COOKDIR")
ROOTS="$COOKDIR/"
COOKDIRS="$LEAF"
if [ -d "Content/Sandbox/Meshes/$LEAF" ]; then  # a level whose meshes were chunked out (as Prison 2's are)
  ROOTS="$ROOTS,Sandbox/Meshes/$LEAF/"
  COOKDIRS="$COOKDIRS Meshes/$LEAF"
fi
COOKDIRS=${BCM_COOK_DIRS:-$COOKDIRS}
mkdir -p "$SHIPDIR/thumb" || die "could not make $SHIPDIR"
say "card $ID (\"$DISPLAY\") v$VERSION | level $LEVEL | output $SHIPDIR"

INST=$("$APP" --list 2>/dev/null | grep -P "^$ID\t" | cut -f2 || true)
if [ -n "$INST" ]; then
  [ "$(printf '%s\n%s\n' "$INST" "$VERSION" | sort -V | tail -1)" = "$VERSION" ] && [ "$INST" != "$VERSION" ] \
    || die "version $VERSION is not above the installed $INST. Pass a higher one, e.g. bash Scripts/newmap.sh $ID \"$DISPLAY\" \"$PHOTO\" $(echo "$INST" | awk -F. '{printf "%d.%d.%d",$1,$2,$3+1}')"
fi

# Any picture -> the two sizes needed: 2048x1024 for the game's menu card, 1024x512 for the installer window.
# Centre-cropped to 2:1 first, so a 16:9 screenshot or a phone photo both work without the player thinking about it.
python "$(cygpath -m "$SB/Scripts/bcm_make_pictures.py")" "$(cygpath -m "$PHOTO")" "$(cygpath -m "$SHIPDIR")/thumb" || die "could not prepare the picture"
PHOTO="$SHIPDIR/thumb/card_2048x1024.png"

# 1b. (public kit) the few game files the build reads, taken once from YOUR Bodycam install with UnrealPak
python "$(cygpath -m "$SB/Scripts/kit_game_files.py")" || die "could not take the game files the build needs from your Bodycam install (see the line above)"

# ------------------------------------------------------------------------------------------- 2. probe in the editor
say "2. probing the level (spawns, lighting, bounds)"
rm -rf "$SB/Saved/torre_v3/tools/.ue_lock"
BCM_LEVEL="$LEVEL" bash "$LOCK" --max-wait-s 3600 "$UE" "$PROJ" -dx11 /Engine/Maps/Entry \
  -ExecutePythonScript="$(cygpath -m "$SB")/Scripts/bcm_level_probe.py" \
  -unattended -nopause -nosplash -stdout $UE_HIDE > "$SHIPDIR/probe.log" 2>&1
grep -a "\[bcmprobe\]" "$SHIPDIR/probe.log" | sed 's/.*Warning: //;s/^\[bcmprobe\] //' | grep -vE '^(load_level|done)' | sed 's/^/   /'
grep -aq "\[bcmprobe\] done" "$SHIPDIR/probe.log" || die "the level cannot ship yet (see the problems above, and $SHIPDIR/probe.log)"
# 2b. (kit) hardpoints present + the marker widgets' invisible collision off, before the long cook
say "2b. checking the hardpoints, switching off the marker's invisible collision"
rm -rf "$SB/Saved/torre_v3/tools/.ue_lock"
BCM_LEVEL="$LEVEL" bash "$LOCK" --max-wait-s 3600 "$UE" "$PROJ" -dx11 /Engine/Maps/Entry \
  -ExecutePythonScript="$(cygpath -m "$SB")/Scripts/bcm_level_fix.py" \
  -unattended -nopause -nosplash -stdout $UE_HIDE > "$SHIPDIR/fix.log" 2>&1
grep -a "\[bcmfix\]" "$SHIPDIR/fix.log" | sed 's/.*Warning: //;s/^\[bcmfix\] //' | grep -v '^done' | sed 's/^/   /'
grep -aq "\[bcmfix\] done" "$SHIPDIR/fix.log" || die "the level cannot ship yet (see the problems above, and $SHIPDIR/fix.log)"
NAV=${BCM_NAV_OVERRIDE:-$(grep -a -o "BOUNDS=[-0-9.,]*" "$SHIPDIR/probe.log" | tail -1 | cut -d= -f2)}   # 24 Sep: override when far scenery (V1's island ground) would blow up the box
[ -n "$NAV" ] || die "could not measure the level's bounds"
say "   navmesh box $NAV"

# 29 Sep 2026 (release check on a fresh map): the Hardpoint gate's R11 minimum height defaulted to Prison 2's 420 cm
# (its closed underground), so any other level failed. For a new map: 1 m below the bottom of its measured bounds
# (still catches a hardpoint under the world). BCM_HP_ZMIN set by the caller wins.
export BCM_HP_ZMIN="${BCM_HP_ZMIN:-$(echo "$NAV" | awk -F, '{printf "%.0f", $3 - $6 - 100}')}"
say "   hardpoint minimum height $BCM_HP_ZMIN cm"
export BCM_CARD="$ID" BCM_LEVEL="$LEVEL" BCM_DISPLAY="$DISPLAY" BCM_NAV="$NAV"
export BCM_SHIP_DIR="$(cygpath -m "$SHIPDIR")"
export BCM_COOK_DIRS="$COOKDIRS"
export BCM_CONTENT_ROOTS="${BCM_CONTENT_ROOTS:-$ROOTS}"
export BCM_DESCRIPTION="${BCM_DESCRIPTION:-Custom map: $DISPLAY}"

# ------------------------------------------------------------------------------------------------- 3. the wrappers
say "3. game-mode wrappers (7)"
for MODE in dup wrappers; do
  rm -rf "$SB/Saved/torre_v3/tools/.ue_lock"
  P2S_MODE=$MODE bash "$LOCK" --max-wait-s 3600 "$UE" "$PROJ" -dx11 /Engine/Maps/Entry \
    -ExecutePythonScript="$(cygpath -m "$SB")/Scripts/prison2_ship.py" \
    -unattended -nopause -nosplash -stdout $UE_HIDE > "$SHIPDIR/wrappers_$MODE.log" 2>&1
  grep -a "\[p2ship\]" "$SHIPDIR/wrappers_$MODE.log" | sed 's/.*Warning: //' | tail -3 | sed 's/^/   /'
  grep -aq "ABORT" "$SHIPDIR/wrappers_$MODE.log" && die "the $MODE step failed (see $SHIPDIR/wrappers_$MODE.log)"
done

# The wrappers step removes the copied navmesh and resizes the bounds volume; without a bake the bots have no
# navmesh and never move (22 Sep 2026: shipped that way in Prison 2 0.5.3). Same bake as open_chain.sh U7.
say "3b. navmesh bake of the 7 wrappers"
for W in HP TDM DM VS GG BB WM; do
  rm -rf "$SB/Saved/torre_v3/tools/.ue_lock"
  bash "$LOCK" --max-wait-s 3600 "$UE" "$PROJ" -dx11 -run=ResavePackages -Map=${W}_$ID -BuildNavigationData \
    -unattended -nopause -nosplash -stdout -FullStdOutLogOutput > "$SHIPDIR/nav_${W}.log" 2>&1 || die "the navmesh bake of ${W}_$ID failed (see $SHIPDIR/nav_${W}.log)"
  grep -aq "agent radius 15.0" "$SHIPDIR/nav_${W}.log" || die "the navmesh of ${W}_$ID was not baked with the game's agent radius 15 (see $SHIPDIR/nav_${W}.log)"
done
echo "   baked, agent radius 15"

# ----------------------------------------------------------------------------------------------------- 4. the menu
say "4. menu data assets and texture"
(cd "$SB/Saved/prison2/ship" && python make_menu.py "$(cygpath -m "$PHOTO")") > "$SHIPDIR/make_menu.log" 2>&1 \
  || { tail -20 "$SHIPDIR/make_menu.log"; die "make_menu failed"; }
ls "$SHIPDIR/menu/UI/MetaData" | wc -l | xargs printf "   %s menu files\n"

# --------------------------------------------------------------------------------------- 5. cook, pak, package, install
for STAGE in ${BCM_STAGES:-cook paks package install}; do
  say "5. $STAGE"
  VERSION=$VERSION bash "$SB/Saved/prison2/cook_only.sh" $STAGE 2>&1 | sed 's/^/   /' | tail -6
  [ "${PIPESTATUS[0]}" -eq 0 ] || die "the $STAGE step failed (logs in Saved/prison2/cook_only_logs/)"
  if [ "$STAGE" = cook ]; then
    for W in Hardpoint:HP TeamDeathmatch:TDM DeathMatch:DM Versus:VS GunGame:GG BodyBomb:BB Wingman:WM; do
      F="Saved/Cooked/Windows/BodycamSandbox/Content/GM_Maps/${W%%:*}/${W##*:}_$ID.umap"
      grep -aq "RecastNavMesh" "$F" 2>/dev/null || die "the cooked ${W##*:}_$ID has no navmesh; bots would not move. Nothing was installed."
    done
    echo "   navmesh present in all 7 cooked wrappers"
  fi
done

echo
case " ${BCM_STAGES:-cook paks package install} " in
  *" install "*) say "DONE: $DISPLAY $VERSION is installed. Start Bodycam and look in Play > Custom." ;;
  *)             say "DONE: $DISPLAY $VERSION built at $SHIPDIR/out/$ID.bcmap (install was not in BCM_STAGES)." ;;
esac
