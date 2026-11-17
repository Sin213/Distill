"""Building an emulator from source, for the projects that ship no Linux binary of their own.

Only ares needs this today. The idea is one button, one script: it works out which distribution family it is running
on, installs that family's build dependencies, checks out the newest release tag, compiles, and copies the finished
program into the emulator's folder so Distill's usual "find the executable" step picks it up.

The same machinery also builds *tools* that are no longer published as downloads (hactoolnet, see TOOL_RECIPES): those
need no distribution packages at all, so their script brings its own .NET SDK into the tool's folder.

The script runs in a terminal window of its own rather than inside Distill, for two reasons: installing packages asks
for the administrator password (nothing in Distill may own a password prompt), and a full build takes long enough that
it should not look like a frozen window.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

SCRIPT_NAME = "build-from-source.sh"

# How each distribution family installs packages, and the name it gives the pieces this build needs.
RECIPES: dict[str, dict] = {
    "ares": {
        "title": "ares",
        "repo": "https://github.com/ares-emulator/ares",
        "min_cmake": (3, 28),
        "deps": {
            # ares builds against GTK3 by default (Qt6 is experimental), plus X11/GL and the audio drivers.
            "debian": ("sudo apt update && sudo apt install -y build-essential cmake pkg-config curl git ninja-build "
                       "libgtk-3-dev libcanberra-gtk3-module libgl-dev libasound2-dev libao-dev libopenal-dev "
                       "libpulse-dev libudev-dev"),
            "fedora": ("sudo dnf install -y cmake pkg-config curl git gcc gcc-c++ ninja-build gtk3-devel libX11-devel "
                       "libXrandr-devel mesa-libGL-devel openal-soft-devel alsa-lib-devel pulseaudio-libs-devel "
                       "libao-devel"),
            "arch": ("sudo pacman -S --needed --noconfirm base-devel cmake ninja pkgconf git curl gtk3 libcanberra "
                     "libx11 libxrandr mesa openal alsa-lib libpulse libao"),
            # Verified against the Tumbleweed OSS x86_64 repository: gcc/gcc-c++, make, cmake (4.4.4), pkg-config,
            # curl, git, ninja, gtk3-devel, libcanberra-gtk3-module, Mesa-libGL-devel, alsa-devel, libao-devel,
            # openal-soft-devel, libpulse-devel, libX11-devel, libXrandr-devel, systemd-devel (libudev.h) all exist
            # there under these names.
            "opensuse": ("sudo zypper install -y gcc gcc-c++ make cmake pkg-config curl git ninja gtk3-devel "
                         "libcanberra-gtk3-module Mesa-libGL-devel libX11-devel libXrandr-devel alsa-devel libao-devel "
                         "openal-soft-devel libpulse-devel systemd-devel"),
        },
        # SDL3 is optional and not packaged on older releases; trying it must not sink the whole install.
        "optional": {
            "debian": "sudo apt install -y libsdl3-dev || true",
            "fedora": "sudo dnf install -y SDL3-devel || true",
            "arch": "sudo pacman -S --needed --noconfirm sdl3 || true",
            "opensuse": "sudo zypper install -y SDL3-devel || true",
        },
        # The same package set once more, for systems whose root is read-only: layering needs a reboot, so the script
        # prints this line instead of running it. Fedora Atomic/Bazzite layer with rpm-ostree, MicroOS/Aeon (and any
        # transactional-update openSUSE) with `transactional-update pkg install` (SUSE documentation for SLE Micro).
        "atomic": {
            "fedora": "sudo rpm-ostree install cmake ninja-build gcc gcc-c++ pkg-config git curl gtk3-devel "
                      "libX11-devel libXrandr-devel mesa-libGL-devel openal-soft-devel alsa-lib-devel "
                      "pulseaudio-libs-devel libao-devel",
            "opensuse": "sudo transactional-update pkg install gcc gcc-c++ make cmake pkg-config curl git ninja "
                        "gtk3-devel libcanberra-gtk3-module Mesa-libGL-devel libX11-devel libXrandr-devel alsa-devel "
                        "libao-devel openal-soft-devel libpulse-devel systemd-devel",
        },
        "cmake_args": ("-G Ninja -DCMAKE_BUILD_TYPE=Release -DARES_BUILD_OFFICIAL=ON -DENABLE_IPO=OFF "
                       "-DARES_BUILD_LOCAL=OFF"),
        "output": "rundir",
        "binary": "bin/ares",
        "commands": ("cmake", "ninja", "gcc", "g++", "pkg-config", "git", "curl"),
        "pkg_config": ("gtk+-3.0", "x11", "xrandr", "gl", "openal", "alsa", "libpulse", "ao"),
        "notes": "GTK3 is required. If CMake is older than 3.28 the script stops and says so.",
    },
}


def family_of(os_release: str) -> str:
    """'debian', 'fedora', 'arch', 'opensuse' or '' from the text of /etc/os-release."""
    text = os_release.lower()
    ids = re.findall(r"^(?:id|id_like)=(.*)$", text, re.MULTILINE)  # text is lowercased above
    words = {w.strip().strip('"') for chunk in ids for w in chunk.split()}
    for family, members in (("arch", {"arch", "archlinux", "manjaro", "endeavouros", "cachyos"}),
                            ("debian", {"debian", "ubuntu", "linuxmint", "pop", "zorin", "elementary", "kali"}),
                            ("fedora", {"fedora", "rhel", "centos", "rocky", "almalinux", "bazzite", "nobara"}),
                            # MicroOS and Aeon report ID_LIKE="opensuse suse" too; they are openSUSE, and the script's
                            # atomic branch is what keeps them from trying a live install on a read-only root.
                            ("opensuse", {"opensuse", "opensuse-tumbleweed", "opensuse-leap", "opensuse-slowroll",
                                          "suse", "sles", "sled"})):
        if words & members:
            return family
    return ""


def this_family() -> str:
    try:
        return family_of(Path("/etc/os-release").read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return ""


def script_for(key: str, target: Path, version: str = "") -> str:
    """The shell script that builds this project into `target`, for the distribution it is run on."""
    recipe = RECIPES[key]
    version = "" if version == "source" else version
    return f"""#!/bin/bash
# Builds {recipe['title']} from source for this distribution, then puts it where Distill looks for it.
# Written by Distill. Safe to read; nothing here is hidden.
set -u

TARGET={shell_quote(str(target))}
REPO={shell_quote(recipe['repo'])}
WANT={shell_quote(version)}
SRC="$TARGET/src"
BUILD="$TARGET/build"

say() {{ printf '\\n== %s\\n' "$*"; }}
die() {{ printf '\\n!! %s\\n' "$*"; printf '\\nPress Enter to close.\\n'; read -r _; exit 1; }}

# ---- which distribution is this? -------------------------------------------------------------
FAMILY=""
. /etc/os-release 2>/dev/null || true
for word in ${{ID:-}} ${{ID_LIKE:-}}; do
  case "$word" in
    arch|archlinux|manjaro|endeavouros|cachyos) FAMILY=arch ;;
    debian|ubuntu|linuxmint|pop|zorin|elementary|kali) FAMILY=debian ;;
    fedora|rhel|centos|rocky|almalinux|bazzite|nobara) FAMILY=fedora ;;
    opensuse|opensuse-tumbleweed|opensuse-leap|opensuse-slowroll|suse|sles|sled) FAMILY=opensuse ;;
  esac
  [ -n "$FAMILY" ] && break
done
[ -n "$FAMILY" ] || die "This doesn't look like a Debian, Fedora, Arch or openSUSE system, so the package names are unknown."
say "{recipe['title']}: building on ${{PRETTY_NAME:-$FAMILY}}"

# Atomic systems (Fedora Atomic/Bazzite, openSUSE MicroOS/Aeon) keep their root read-only: build dependencies are
# layered and arrive only after a reboot, so the script explains instead of running a package manager that would fail.
ATOMIC=0
if [ -e /run/ostree-booted ]; then
  ATOMIC=1
  missing=""
  for tool in {' '.join(recipe['commands'])}; do
    command -v "$tool" >/dev/null 2>&1 || missing="$missing $tool"
  done
  if command -v pkg-config >/dev/null 2>&1; then
    for module in {' '.join(recipe['pkg_config'])}; do
      pkg-config --exists "$module" || missing="$missing $module"
    done
  fi
  if [ -n "$missing" ]; then
    say "This atomic system needs more layered build dependencies:$missing"
    echo "Run this, reboot, then press the button again:"
    echo
    case "$FAMILY" in
      fedora) echo "  {recipe['atomic']['fedora']}" ;;
      opensuse) echo "  {recipe['atomic']['opensuse']}" ;;
    esac
    die "Missing dependencies; nothing was changed."
  fi
  say "Using the build dependencies already layered on this atomic system."
fi

# ---- dependencies ---------------------------------------------------------------------------
if [ "$ATOMIC" = 0 ]; then
say "Installing build dependencies (this asks for your password)"
case "$FAMILY" in
  debian) {recipe['deps']['debian']} ;;
  fedora) {recipe['deps']['fedora']} ;;
  arch)   {recipe['deps']['arch']} ;;
  opensuse) {recipe['deps']['opensuse']} ;;
esac || die "Installing the build dependencies failed."

# Optional pieces are tried and forgotten: SDL3 is missing from older releases, and ares works without it.
case "$FAMILY" in
  debian) {recipe['optional']['debian']} ;;
  fedora) {recipe['optional']['fedora']} ;;
  arch)   {recipe['optional']['arch']} ;;
  opensuse) {recipe['optional']['opensuse']} ;;
esac
fi

need=$(cmake --version 2>/dev/null | head -n1 | awk '{{print $3}}')
[ -n "$need" ] || die "CMake is not installed."
if [ "$(printf '%s\\n' {recipe['min_cmake'][0]}.{recipe['min_cmake'][1]} "$need" | sort -V | head -n1)" != \\
     "{recipe['min_cmake'][0]}.{recipe['min_cmake'][1]}" ]; then
  die "CMake $need is too old: {recipe['title']} needs {recipe['min_cmake'][0]}.{recipe['min_cmake'][1]} or newer. \\
Install a newer CMake from cmake.org, then press the button again."
fi

# ---- source ---------------------------------------------------------------------------------
mkdir -p "$TARGET" || die "Could not create $TARGET"
if [ -d "$SRC/.git" ]; then
  say "Updating the source"
else
  say "Fetching the source"
  git clone --depth 1 "$REPO" "$SRC" || die "Could not clone $REPO."
fi
cd "$SRC" || die "Could not enter $SRC"
git fetch --tags --depth 1 origin '+refs/heads/*:refs/remotes/origin/*' || die "Could not fetch the source."
if [ -n "$WANT" ]; then
  REF="refs/tags/$WANT"
else
  git remote set-head origin --auto || die "Could not determine the remote default branch."
  REF=$(git symbolic-ref --quiet refs/remotes/origin/HEAD) || die "Could not resolve the remote default branch."
fi
COMMIT=$(git rev-parse --verify "$REF^{{commit}}") || die "Could not resolve source target $REF."
[ -n "$COMMIT" ] || die "Source target $REF has no commit."
git checkout --detach "$COMMIT" || die "Could not check out source target $REF."
HEAD_COMMIT=$(git rev-parse --verify HEAD) || die "Could not verify the source checkout."
[ "$HEAD_COMMIT" = "$COMMIT" ] || die "Source HEAD does not match the resolved target $REF."
say "Building $REF ($COMMIT)"

# ---- build ----------------------------------------------------------------------------------
say "Configuring"
cmake -S "$SRC" -B "$BUILD" {recipe['cmake_args']} || die "CMake could not configure the build."
say "Compiling (this is the slow part; a fast machine takes a few minutes)"
cmake --build "$BUILD" -j "$(nproc)" || die "The build failed. The output above says why."

# ---- put it where Distill looks -------------------------------------------------------------
OUT="$TARGET/build/{recipe['output']}"
[ -d "$OUT" ] || die "The build finished but {recipe['output']} is missing."
say "Copying the built program into $TARGET"
cp -a "$OUT"/. "$TARGET"/ || die "Could not copy the build."
[ -x "$TARGET/{recipe['binary']}" ] || die "The built program is not where it was expected ({recipe['binary']})."
say "Done. {recipe['title']} is at $TARGET/{recipe['binary']} - go back to Distill and click 'Find installed'."
printf '\\nPress Enter to close.\\n'
read -r _
"""


def shell_quote(text: str) -> str:
    return "'" + str(text).replace("'", "'\\''") + "'"


# ---- tools that have to be built rather than downloaded ------------------------------------------------------
# hactoolnet's original home (Thealexbarney/LibHac) is gone from GitHub, taking the release zips with it. The
# maintained fork still has the source, so the app builds it once instead. Note the branch: the v0.19.0 tag no longer
# compiles (26 ref-safety errors under .NET 8 and 10), while master moved to net8.0 and builds cleanly. Do not "pin a
# tag" here without testing it.
TOOL_RECIPES: dict[str, dict] = {
    "hactoolnet": {
        "title": "hactoolnet",
        "repo": "https://git.ryujinx.app/projects/LibHac.git",
        "branch": "master",
        "project": "src/hactoolnet/hactoolnet.csproj",
        "binary": "hactoolnet",
        "sdk_channel": "10.0",  # the .NET SDK version this build was verified with
        "rids": {"x86_64": "linux-x64", "amd64": "linux-x64", "aarch64": "linux-arm64", "arm64": "linux-arm64"},
    },
}

TOOL_SCRIPT_NAME = "build-from-source.sh"


def tool_script_for(key: str, root: Path) -> str:
    """A script that installs a private .NET SDK, builds the tool from source and files it where Distill looks.

    No root and no packages: the SDK goes into the tool's own folder with Microsoft's install script, so this works
    on an atomic system (Bazzite, Silverblue) where nothing can be installed the usual way."""
    recipe = TOOL_RECIPES[key]
    return f"""#!/bin/bash
# Builds {recipe['title']} from source into Distill's tools folder. Written by Distill; nothing here is hidden.
set -u

ROOT={shell_quote(str(root))}
REPO={shell_quote(recipe['repo'])}
BRANCH={shell_quote(recipe['branch'])}
PROJECT={shell_quote(recipe['project'])}
BINARY={shell_quote(recipe['binary'])}
SDK={shell_quote(recipe['sdk_channel'])}

say() {{ printf '\\n== %s\\n' "$*"; }}
die() {{ printf '\\n!! %s\\n' "$*"; printf '\\nPress Enter to close.\\n'; read -r _; exit 1; }}

case "$(uname -m)" in
  x86_64|amd64) RID=linux-x64 ;;
  aarch64|arm64) RID=linux-arm64 ;;
  *) die "Unknown processor: $(uname -m)." ;;
esac

mkdir -p "$ROOT" || die "Could not create $ROOT"
DOTNET="$ROOT/.dotnet/dotnet"

if [ ! -x "$DOTNET" ]; then
  say "Fetching the .NET SDK ($SDK) into $ROOT/.dotnet (about 200 MB, no root needed)"
  command -v curl >/dev/null || die "curl is needed to fetch the SDK."
  curl -sSL https://dot.net/v1/dotnet-install.sh -o "$ROOT/dotnet-install.sh" || die "Could not download the installer."
  bash "$ROOT/dotnet-install.sh" --channel "$SDK" --install-dir "$ROOT/.dotnet" --no-path \\
      || die "The .NET SDK could not be installed."
fi
[ -x "$DOTNET" ] || die "The .NET SDK is not usable at $DOTNET"

say "Fetching the source"
if [ -d "$ROOT/src/.git" ]; then
  git -C "$ROOT/src" fetch --depth 1 origin "$BRANCH" || die "Could not fetch the source."
  git -C "$ROOT/src" checkout -q FETCH_HEAD || die "Could not check out $BRANCH."
else
  git clone --depth 1 --branch "$BRANCH" "$REPO" "$ROOT/src" || die "Could not clone $REPO."
fi

say "Building {recipe['title']} (this takes a few minutes)"
rm -rf "$ROOT/staging"
"$DOTNET" publish "$ROOT/src/$PROJECT" -c Release -r "$RID" --self-contained true -o "$ROOT/staging" \\
    || die "The build failed. The output above says why."

[ -x "$ROOT/staging/$BINARY" ] || die "The build finished but $BINARY is not in it."
VERSION=$("$ROOT/staging/$BINARY" --version 2>/dev/null | grep -oE '[0-9]+(\\.[0-9]+)+' | head -n1)
[ -n "$VERSION" ] || die "The built program did not report a version."

say "Filing $BINARY $VERSION where Distill looks for it"
rm -rf "$ROOT/$VERSION"
mv "$ROOT/staging" "$ROOT/$VERSION" || die "Could not move the build into place."
echo "$VERSION" > "$ROOT/current.txt"

say "Done: {recipe['title']} $VERSION is installed. Go back to Distill - the tool box now finds it."
printf '\\nPress Enter to close.\\n'
read -r _ || true   # no terminal to read from: that is not a failure
exit 0
"""


def write_tool_script(key: str, root: Path) -> Path:
    """Write the build script into the tool's own folder and make it runnable."""
    root.mkdir(parents=True, exist_ok=True)
    path = root / TOOL_SCRIPT_NAME
    path.write_text(tool_script_for(key, root), encoding="utf-8")
    path.chmod(0o755)
    return path


def start_tool(key: str, root: Path) -> Path:
    """Write the build script for a tool and open it in a terminal. Returns the script."""
    script = write_tool_script(key, root)
    argv = terminal_command(script)
    if argv is None:
        raise RuntimeError(f"No terminal program was found to run the build in. The script is saved at:\n\n{script}")
    subprocess.Popen(argv, cwd=str(root), close_fds=True, start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return script


TERMINALS = (
    ("konsole", ["konsole", "-e", "bash", "-c"]),
    ("gnome-terminal", ["gnome-terminal", "--", "bash", "-c"]),
    ("kgx", ["kgx", "--", "bash", "-c"]),
    ("xfce4-terminal", ["xfce4-terminal", "-x", "bash", "-c"]),
    ("mate-terminal", ["mate-terminal", "-x", "bash", "-c"]),
    ("tilix", ["tilix", "-e", "bash", "-c"]),
    ("kitty", ["kitty", "bash", "-c"]),
    ("alacritty", ["alacritty", "-e", "bash", "-c"]),
    ("wezterm", ["wezterm", "start", "--", "bash", "-c"]),
    ("foot", ["foot", "bash", "-c"]),
    ("xterm", ["xterm", "-e", "bash", "-c"]),
)


def terminal_command(script: Path) -> list[str] | None:
    """A command that opens `script` in whatever terminal this desktop has, or None when there isn't one."""
    inner = f"bash {shell_quote(script)}"
    for name, argv in TERMINALS:
        if shutil.which(name):
            return [*argv, inner]
    return None


def write_script(key: str, target: Path, version: str = "") -> Path:
    """Write the build script into the emulator's folder and make it runnable."""
    target.mkdir(parents=True, exist_ok=True)
    path = target / SCRIPT_NAME
    path.write_text(script_for(key, target, version), encoding="utf-8")
    path.chmod(0o755)
    return path


def start(key: str, target: Path, version: str = "") -> Path:
    """Write the script and open it in a terminal. Returns the script; raises RuntimeError with a readable reason."""
    script = write_script(key, target, version)
    argv = terminal_command(script)
    if argv is None:
        raise RuntimeError(f"No terminal program was found to run the build in. The script is saved at:\\n\\n{script}")
    subprocess.Popen(argv, cwd=str(target), close_fds=True, start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return script
