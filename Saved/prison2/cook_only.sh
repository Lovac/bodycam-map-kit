#!/usr/bin/env bash
# Prison 2: cook -> paks -> package -> install, i.e. steps U9..U12 of Saved/prison2/open_chain.sh, with the SAME gates
# and nothing else. No geometry regen, no mesh re-chunking, no relight, no spawn turning: the level on disk is shipped
# as it is (20 Sep 2026: spotlight shadows off, speakers re-seated, shaft cones 60/45, wing objectives moved in).
#
#   bash Saved/prison2/cook_only.sh cook       # U9  (long: the whole Prison2 mesh set)
#   bash Saved/prison2/cook_only.sh paks       # U10
#   bash Saved/prison2/cook_only.sh package    # U11 (VERSION=0.4.6 by default)
#   bash Saved/prison2/cook_only.sh install    # U12
set -u
export MSYS_NO_PATHCONV=1
SB=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
SBW="$(cygpath -m "$SB")"
UE="${BCM_UE:-/c/Program Files/Epic Games/UE_5.5/Engine/Binaries/Win64/UnrealEditor-Cmd.exe}"
PROJ="$(cygpath -w "$SB/BodycamSandbox.uproject")"
LOCK="$SB/Saved/torre_v3/tools/ue_lock.sh"
L="$SB/Saved/prison2/cook_only_logs"
APP=Saved/release/app/BodycamMapInstaller.exe
CARD=${BCM_CARD:-Panopticon}
LEVEL=${BCM_LEVEL:-/Game/Sandbox/Prison2/Prison2_BP}
COOKDIRS=${BCM_COOK_DIRS:-Prison2 Meshes/Prison2}
SHIPDIR=${BCM_SHIP_DIR:-$SB/Saved/prison2/ship}
CODEDIR=$SB/Saved/prison2/ship
export BCM_SHIP_DIR="$(cygpath -m "$SHIPDIR")"   # python on Windows cannot open a /c/... path
SHIPW=$(cygpath -m "$SHIPDIR")                      # the installer .exe needs a Windows path too
MODEMAPS=""
for fp in Hardpoint:HP TeamDeathmatch:TDM DeathMatch:DM Versus:VS GunGame:GG BodyBomb:BB Wingman:WM; do
  MODEMAPS="$MODEMAPS+/Game/GM_Maps/${fp%%:*}/${fp##*:}_$CARD"
done
VERSION=${VERSION:?VERSION=x.y.z required (22 Sep: a stale default installed 0.4.6 over 0.5.0; must exceed what --list shows)}
C=Saved/Cooked/Windows/BodycamSandbox/Content/Sandbox
mkdir -p "$L"
cd "$SB" || exit 2
say() { echo "== $(date +%H:%M:%S) $*"; }
die() { echo "*** FAILED: $*"; exit 1; }

case "${1:?stage: cook|paks|package|install}" in

cook)
  say "U9. cook (level + 7 wrappers)"
  B="Saved/snapshots/prison2_cookonly_$(date +%Y%m%d_%H%M%S)"
  mkdir -p "$B/stale_cook" || die backup
  cp -p "${LEVEL/\/Game\//Content\/}.umap" "$B/" || die backup
  for d in $COOKDIRS; do
    [ -d "$C/$d" ] && mkdir -p "$B/stale_cook/$(dirname $d)" && mv "$C/$d" "$B/stale_cook/$d"
  done
  echo "   stale cook moved to $B/stale_cook"
  bash "$LOCK" --max-wait-s 3600 "$UE" "$PROJ" -run=Cook -TargetPlatform=Windows \
    -Map=$LEVEL$MODEMAPS \
    -unattended -nopause -nosplash -stdout -FullStdOutLogOutput > "$L/cook.log" 2>&1 || die cook
  grep -a -q "Success - 0 error" "$L/cook.log" || die "cook errors"
  grep -a -E "Success - 0 error|Cooked packages|took" "$L/cook.log" | tail -3
  # 22 Sep 2026: Prison 2 has open basement hardpoints (z 26.5): its build passes BCM_HP_ZMIN=-50
  rm -f "$L/hp_gate.txt"
  python Saved/hpgate/gate_hardpoint_pattern.py --zmin "${BCM_HP_ZMIN:-420}" "Saved/Cooked/Windows/BodycamSandbox/Content/${LEVEL#/Game/}" | head -8 | tee "$L/hp_gate.txt"   # 24 Sep: the card's own level (was Prison 2's path)
  grep -q "^PASS" "$L/hp_gate.txt" || die "hardpoint gate"
  say "cook OK"
  ;;

paks)
  say "U10. paks (gates 1-5)"
  (cd "$CODEDIR" && python make_paks.py) > "$L/make_paks.txt" 2>&1 || { tail -30 "$L/make_paks.txt"; die make_paks; }
  tail -4 "$L/make_paks.txt"
  ls -la "$SHIPDIR"/paks/*.pak
  say "paks OK"
  ;;

package)
  say "U11. package $VERSION"
  INST=$("$APP" --list 2>/dev/null | grep -P "^$CARD	" | cut -f2)
  if [ -n "$INST" ] && [ "$(printf '%s
%s
' "$INST" "$VERSION" | sort -V | tail -1)" != "$VERSION" -o "$INST" = "$VERSION" ]; then
    die "VERSION $VERSION is not above the installed $INST"
  fi
  sed -i "s/^VERSION = '[0-9.]*'/VERSION = '$VERSION'/" "$CODEDIR/make_bcmap.py"
  grep -q "^VERSION = '$VERSION'" "$CODEDIR/make_bcmap.py" || die "version bump"
  (cd "$CODEDIR" && python make_bcmap.py) > "$L/make_bcmap.txt" 2>&1 || { tail -20 "$L/make_bcmap.txt"; die make_bcmap; }
  tail -3 "$L/make_bcmap.txt"
  "$APP" --validate "$SHIPW/out/$CARD.bcmap" > "$L/validate.txt" 2>&1 || { cat "$L/validate.txt"; die validate; }
  tail -1 "$L/validate.txt"
  say "package OK"
  ;;

install)
  say "U12. install $VERSION"
  bash "$LOCK" --max-wait-s 3600 "$APP" --install "$SHIPW/out/$CARD.bcmap" --yes > "$L/install.txt" 2>&1 || { cat "$L/install.txt"; die install; }
  tail -3 "$L/install.txt"
  "$APP" --list > "$L/list.txt"
  grep -q -P "^$CARD\t${VERSION//./\\.}\t" "$L/list.txt" || die "installed version is not $VERSION"
  grep -P "^$CARD" "$L/list.txt"
  say "OK $VERSION installed"
  ;;

*) die "unknown stage $1" ;;
esac
