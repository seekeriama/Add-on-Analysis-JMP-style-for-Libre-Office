#!/bin/sh
# Installs the built extension into a headless LibreOffice and drives the panel with Playwright.
# Needs: soffice, unopkg, Node with playwright, and NumPy/SciPy for LibreOffice's Python.
set -e
here=$(cd "$(dirname "$0")" && pwd)
out=${1:-$here/out}
mkdir -p "$out"
export CELLSTAT_NO_BROWSER=1  # the component prints the panel URL instead of opening a browser
unopkg remove --shared org.cellstat.calc >/dev/null 2>&1 || true
unopkg add --shared -s "$here/../dist/cellstat.oxt"
log="$out/soffice.log"
soffice --headless --invisible --norestore --accept="socket,host=127.0.0.1,port=2002;urp;" >"$log" 2>&1 &
pid=$!
trap 'kill $pid 2>/dev/null' EXIT
python3 "$here/lo_session.py" setup
sleep 2
url=$(grep -o 'http://127.0.0.1[^ ]*' "$log" | tail -1)
node "$here/panel_e2e.js" "$url" "$out"
python3 "$here/lo_session.py" check
