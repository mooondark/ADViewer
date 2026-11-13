#!/bin/sh
# Couverture (pytest) puis scores CRAP. Usage : scripts/metrics.sh [options crapper, ex. --changed]
# crapper est attendu a cote du depot (../crapper, ou CRAPPER_DIR) avec son .venv installe.
# Son lanceur et son choix d'interpreteur supposent Unix et unittest : on mesure la couverture
# nous-memes avec pytest et on la lui fait relire.
# QT_QPA_PLATFORM=windows (ou autre) pour inclure les tests qui creent la fenetre principale (VTK exige OpenGL).
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd)
CRAPPER=${CRAPPER_DIR:-$ROOT/../crapper}
PY_CRAPPER="$CRAPPER/.venv/Scripts/python.exe"
[ -x "$PY_CRAPPER" ] || PY_CRAPPER="$CRAPPER/.venv/bin/python"
if [ ! -x "$PY_CRAPPER" ]; then
  echo "crapper introuvable : cloner https://github.com/unclebob/crapper dans $CRAPPER puis" >&2
  echo "  python -m venv $CRAPPER/.venv && $CRAPPER/.venv/Scripts/python -m pip install -e $CRAPPER" >&2
  exit 1
fi
OUT="$ROOT/target/coverage/python"
cd "$ROOT"
mkdir -p "$OUT"
QT_QPA_PLATFORM=${QT_QPA_PLATFORM:-offscreen} python -m coverage run --data-file="$OUT/.coverage" --source=. \
  --omit="tests/*,graphify-out/*" -m pytest -q
python -m coverage lcov -i --data-file="$OUT/.coverage" -o "$OUT/lcov.info"
PYTHONIOENCODING=utf-8 "$PY_CRAPPER" -m crapper --use-existing-coverage "$@"
