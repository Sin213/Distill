#!/bin/bash
# Package an existing amd64 PyInstaller one-folder build.
set -euo pipefail
unset CDPATH
umask 022
export LC_ALL=C
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-0}"
export DPKG_DEB_THREADS_MAX=1

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
bundle="$repo/dist/Distill"
output="${1:-$repo/dist}"
if [[ ! -x "$bundle/Distill" ]]; then
    echo "Distill: build dist/Distill with pyinstaller --noconfirm distill-linux.spec first." >&2
    exit 1
fi

version="$(awk -F '"' '
    /^\[project\]$/ { project = 1; next }
    /^\[/ { project = 0 }
    project && /^version[[:space:]]*=/ { print $2; exit }
' "$repo/pyproject.toml")"
if [[ ! $version =~ ^[0-9][0-9A-Za-z.+~-]*$ ]]; then
    echo "Distill: could not read a Debian-compatible project version from pyproject.toml." >&2
    exit 1
fi

stage="$(mktemp -d)"
trap 'rm -rf -- "$stage"' EXIT
install -d -m 0755 "$stage/DEBIAN" "$stage/opt/distill" "$stage/usr/bin" \
    "$stage/usr/share/applications" "$stage/usr/share/icons/hicolor/256x256/apps"
cp -a --no-preserve=ownership "$bundle/." "$stage/opt/distill/"
install -m 0755 "$repo/packaging/deb/distill" "$stage/usr/bin/distill"
sed 's/^Exec=Distill$/Exec=distill/' "$repo/packaging/distill.desktop" \
    > "$stage/usr/share/applications/distill.desktop"
install -m 0644 "$repo/distill.png" "$stage/usr/share/icons/hicolor/256x256/apps/distill.png"

libc6_min="$(python3 -I - "$stage/opt/distill" <<'PY'
import os
from pathlib import Path
import re
import stat
import sys


def raise_walk_error(error):
    raise error


glibc_version = re.compile(rb"\bGLIBC_([0-9]+)\.([0-9]+)(?:\.[0-9]+)?\b")
highest = None
try:
    for directory, _, filenames in os.walk(sys.argv[1], onerror=raise_walk_error):
        for name in filenames:
            path = Path(directory, name)
            if not stat.S_ISREG(path.lstat().st_mode):
                continue
            with path.open("rb") as stream:
                if stream.read(4) != b"\x7fELF":
                    continue
                contents = stream.read()
                if b"GLIBC_ABI_DT_RELR" in contents and (highest is None or highest < (2, 36)):
                    highest = (2, 36)
                for major, minor in glibc_version.findall(contents):
                    version = int(major), int(minor)
                    if highest is None or version > highest:
                        highest = version
except OSError as error:
    sys.exit(f"Distill: could not scan the staged bundle for GLIBC versions: {error}")

if highest is None:
    sys.exit("Distill: no GLIBC version strings found in the staged ELF files.")
print(f"{highest[0]}.{highest[1]}")
PY
)"
sed -e "s/@VERSION@/$version/" -e "s/@LIBC6_MIN@/$libc6_min/" \
    "$repo/packaging/deb/control" > "$stage/DEBIAN/control"

# Keep the bundle's executables and links, remove special mode bits, and fix archive timestamps.
find "$stage" -type d -exec chmod 00755 {} +
find "$stage" -type f \( -perm /0111 -exec chmod 0755 {} + -o ! -perm /0111 -exec chmod 0644 {} + \)
find "$stage" -exec touch -h -d "@$SOURCE_DATE_EPOCH" {} +

filename="distill_${version}_amd64.deb"
mkdir -p -- "$output"
dpkg-deb --root-owner-group -Zxz -z6 --build "$stage" "$output/$filename"
(cd -- "$output" && sha256sum "$filename" > "$filename.sha256")
