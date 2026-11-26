"""Exercise CI's dependency shell without installing packages or using host state."""
from __future__ import annotations

import configparser
import json
import os
from email.parser import Parser
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import textwrap
import unittest

from tests.helpers import TempDirTest


ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(shutil.which("bash") and os.name != "nt", "Linux packaging uses Bash")
class AppImageDependenciesTests(TempDirTest):
    def install_packages(self, modern_glib):
        workflow = (ROOT / ".github/workflows/linux-appimage.yml").read_text(encoding="utf-8")
        step = workflow.split("      - name: Install dependencies\n", 1)[1].split("      - name:", 1)[0]
        script = textwrap.dedent(step.split("        run: |\n", 1)[1])
        commands = self.tmp / "bin"
        commands.mkdir()
        log = self.tmp / "commands.jsonl"
        # No forwarding: even sudo, apt and pip are disposable local recorders.
        stub = f"""#!{sys.executable}
import json, os, pathlib, sys
with open(os.environ['COMMAND_LOG'], 'a', encoding='utf-8') as stream:
    stream.write(json.dumps([pathlib.Path(sys.argv[0]).name, *sys.argv[1:]]) + '\\n')
if pathlib.Path(sys.argv[0]).name == 'apt-cache':
    raise SystemExit(0 if os.environ['MODERN_GLIB'] == '1' else 1)
"""
        for name in ("sudo", "apt-cache", "python", "pip"):
            path = commands / name
            path.write_text(stub, encoding="utf-8")
            path.chmod(0o700)
        env = dict(os.environ, PATH=str(commands), HOME=str(self.tmp / "home"),
                   COMMAND_LOG=str(log), MODERN_GLIB=str(int(modern_glib)))
        for category in ("CONFIG", "DATA", "STATE", "CACHE"):
            env[f"XDG_{category}_HOME"] = str(self.tmp / category.lower())
        result = subprocess.run([shutil.which("bash"), "-eo", "pipefail", "-c", script],
                                cwd=self.tmp, env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        installs = [args[3:] for args in calls if args[:3] == ["sudo", "apt-get", "install"]]
        self.assertEqual(len(installs), 1, calls)
        return {arg for arg in installs[0] if not arg.startswith("-")}

    def assert_docker_runtime_parity(self, packages, glib):
        docker = (ROOT / "packaging/build-in-docker.sh").read_text(encoding="utf-8")
        install = docker.split("apt-get install ", 1)[1].split(">/dev/null", 1)[0]
        expected = {word for word in shlex.split(install.replace("\\\n", " ")) if word.startswith("lib")}
        expected.add(glib)
        self.assertIn("libpulse0", packages)
        self.assertEqual({word for word in packages if word.startswith("lib")}, expected)
        self.assertTrue({"file", "curl", "ca-certificates"} <= packages)

    def test_ubuntu_24_runtime_dependencies_match_docker(self):
        packages = self.install_packages(True)
        self.assert_docker_runtime_parity(packages, "libglib2.0-0t64")
        control = Parser().parsestr((ROOT / "packaging/deb/control").read_text(encoding="utf-8"))
        dependencies = {item.split("|")[0].strip() for item in control["Depends"].split(",")}
        self.assertEqual(dependencies, (packages - {"file", "curl", "git"}) | {"libc6 (>= @LIBC6_MIN@)"})

    def test_older_glib_package_fallback_keeps_runtime_dependencies(self):
        self.assert_docker_runtime_parity(self.install_packages(False), "libglib2.0-0")


@unittest.skipUnless(shutil.which("bash") and sys.platform.startswith("linux"), "DEB staging uses Linux file tools")
class DebPackagingTests(TempDirTest):
    def test_control_desktop_and_launcher_match_the_staged_package(self):
        shutil.copytree(ROOT / "packaging", self.tmp / "packaging")
        shutil.copyfile(ROOT / "distill.png", self.tmp / "distill.png")
        self.write("pyproject.toml", '[project]\nversion = "2.3.4"\n')
        self.write("dist/Distill/Distill", b"\x7fELF\0GLIBC_2.34\0").chmod(0o755)
        helper = self.write("dist/Distill/_internal/helper.so", b"\x7fELF\0GLIBC_2.39.1\0GLIBC_2.9\0")
        self.write("dist/Distill/_internal/relr/marker.so", b"\x7fELF\0GLIBC_ABI_DT_RELR\0")
        self.write("dist/Distill/notes.txt", "GLIBC_99.0")
        outside = self.write("outside.so", b"\x7fELF\0GLIBC_99.0\0")
        (self.tmp / "dist/Distill/linked.so").symlink_to(outside)
        dpkg = self.write("bin/dpkg-deb", """#!/bin/bash
set -e
test "$1" = --root-owner-group
cp -a "${@: -2:1}" "$STAGED_DEB"
printf 'fixture package\\n' > "${@: -1}"
""")
        dpkg.chmod(0o755)
        env = dict(os.environ, PATH=f"{dpkg.parent}{os.pathsep}{os.environ['PATH']}", CDPATH=".",
                   SOURCE_DATE_EPOCH="1234567890")

        def build(minimum):
            stage = self.tmp / f"staged-{minimum}"
            result = subprocess.run([shutil.which("bash"), "packaging/build-deb.sh"],
                                    cwd=self.tmp, env=dict(env, STAGED_DEB=str(stage)), capture_output=True,
                                    text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            control = Parser().parsestr((stage / "DEBIAN/control").read_text(encoding="utf-8"))
            self.assertIn(f"libc6 (>= {minimum})", {item.strip() for item in control["Depends"].split(",")})
            return stage, control

        stage, control = build("2.39")
        self.assertEqual((control["Package"], control["Version"], control["Architecture"]), ("distill", "2.3.4", "amd64"))
        self.assertEqual(control["Maintainer"], "Sin213 <79215527+Sin213@users.noreply.github.com>")
        self.assertEqual(control["Recommends"], "curl, git")
        desktop = configparser.ConfigParser()
        desktop.read(stage / "usr/share/applications/distill.desktop", encoding="utf-8")
        entry = desktop["Desktop Entry"]
        launcher = stage / "usr/bin" / entry["Exec"]
        self.assertEqual(launcher.stat().st_mode & 0o7777, 0o755)
        launcher_text = launcher.read_text(encoding="utf-8")
        self.assertIn("unset DISTILL_PORTABLE", launcher_text.splitlines())
        self.assertIn('exec /opt/distill/Distill "$@"', launcher_text)
        self.assertTrue((stage / "opt/distill/Distill").is_file())
        self.assertTrue((stage / f"usr/share/icons/hicolor/256x256/apps/{entry['Icon']}.png").is_file())
        self.assertTrue((self.tmp / "dist/distill_2.3.4_amd64.deb.sha256").is_file())

        helper.unlink()
        build("2.36")
