#!/bin/sh
# Builds dist/cellstat.oxt from libreoffice/src, the Python core and the web panel.
set -e
here=$(cd "$(dirname "$0")" && pwd)
root=$(dirname "$here")
out="$here/dist"
stage="$out/stage"
rm -rf "$stage" "$out/cellstat.oxt"
mkdir -p "$stage"
cp -r "$here/src/." "$stage/"
cp -r "$root/core/cellstat" "$stage/python/pythonpath/"
find "$stage" -name __pycache__ -prune -exec rm -rf {} +
mkdir -p "$stage/web"
cp -r "$root/web/dist/libreoffice/." "$stage/web/"
cp "$root/web/public/icon-64.png" "$stage/web/"
cp "$root/LICENSE" "$stage/LICENSE.txt"
(cd "$stage" && zip -qr "$out/cellstat.oxt" . -x '.*')
rm -rf "$stage"
echo "Built $out/cellstat.oxt"
