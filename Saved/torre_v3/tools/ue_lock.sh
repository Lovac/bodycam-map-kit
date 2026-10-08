#!/bin/bash
# Torre v3 (13 sep 2026, noche). Candado para TODO lo que abre Unreal (editor headless, ResavePackages, Cook) o toca Paks.
# uso: bash Saved/torre_v3/tools/ue_lock.sh [--max-wait-s N] <comando...>
#  - Espera a que Bodycam-Win64-Shipping.exe y todo UnrealEditor*.exe esten cerrados (Lovac puede estar jugando).
#  - Toma un candado atomico (mkdir) para que dos agentes nunca corran el editor a la vez; candado viejo (pid muerto) se limpia.
#  - Codigo 98 = sigue ocupado tras --max-wait-s (por defecto 540 s, cabe en una llamada Bash de 10 min): volver a llamar.
set -u
L="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.ue_lock"
MAX=540
if [ "${1:-}" = "--max-wait-s" ]; then MAX=$2; shift 2; fi
[ $# -ge 1 ] || { echo "uso: ue_lock.sh [--max-wait-s N] <comando...>" >&2; exit 2; }
start=$(date +%s)
busy() { tasklist 2>/dev/null | grep -i -E "Bodycam-Win64|UnrealEditor" | head -3; }
while :; do
  b=$(busy)
  if [ -z "$b" ]; then
    if mkdir "$L" 2>/dev/null; then
      echo "$$ $(date +%H:%M:%S) $*" > "$L/owner"
      break
    fi
    opid=$(cut -d' ' -f1 "$L/owner" 2>/dev/null)
    if [ -n "$opid" ] && ! kill -0 "$opid" 2>/dev/null; then
      echo "[ue_lock] candado viejo de pid $opid limpiado" >&2
      rm -rf "$L"
      continue
    fi
    b="candado tomado por: $(cat "$L/owner" 2>/dev/null)"
  fi
  now=$(date +%s)
  if [ $((now - start)) -ge "$MAX" ]; then
    echo "[ue_lock] OCUPADO tras ${MAX}s: $b" >&2
    exit 98
  fi
  echo "[ue_lock] esperando ($(date +%H:%M:%S)): $b" >&2
  ping -n 31 127.0.0.1 > /dev/null 2>&1
done
trap 'rm -rf "$L"' EXIT
export MSYS_NO_PATHCONV=1
"$@"
