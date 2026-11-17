"""The AppImage-first install policy, the Nintendo entries wired to it, and the two projects that were retired.

The release listings under tests/fixtures/releases are trimmed copies of what the projects' own APIs returned on
2026-11-17: every file name, size and download address in them is real, the release notes are cut short. Nothing here
downloads a third-party binary: what a download would do is exercised with a stub HTTP response and small archives built
in the test, and the release listings are read from those fixtures.
"""
from __future__ import annotations

import io
import json
import re
import tarfile
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tests import helpers  # noqa: F401  (puts the project on sys.path)
from distill import emulators as em
from distill import hostenv
from distill import recomps as rc

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "releases"


def asset(name: str, size: int = 10, digest: str = "") -> dict:
    return {"name": name, "url": f"https://github.com/o/r/releases/download/t/{name}", "size": size, "digest": digest}


def rel(tag: str, *assets: dict, pre: bool = False, published: str = "2026-01-01") -> rc.Release:
    return rc.Release(tag, tag, "", published, pre, "https://example.invalid", tuple(assets))


def emu(**kw) -> em.Emulator:
    base = dict(id="pcsx2", name="PCSX2", system="PlayStation 2", group="Sony", repo="PCSX2/pcsx2",
                systems=("PlayStation 2",), platforms=("windows", "linux", "macos"))
    base.update(kw)
    return em.Emulator(**base)


def listing(name: str) -> list[dict]:
    """The recorded release listing, as the API returned it."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def catalog(plat: str = "linux") -> dict[str, em.Emulator]:
    return {e.id: e for e in em.load_catalog([em.bundled_manifest()], plat)}


class Isolated(unittest.TestCase):
    def setUp(self) -> None:
        td = tempfile.TemporaryDirectory(prefix="distill_policy_")
        self.addCleanup(td.cleanup)
        self.tmp = Path(td.name)
        (self.tmp / "state").mkdir()
        self.config = self.tmp / "config"
        for target, name, value in ((rc, "ROOT", self.tmp / "state"), (em.paths, "config_dir", lambda: self.config),
                                    (em.paths, "data_dir", lambda: self.tmp / "data")):
            patcher = mock.patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.store = rc.Store(self.tmp / "emulators_state.json")


class Linux(Isolated):
    """A Linux host: the platform the install policy is about."""

    def setUp(self) -> None:
        super().setUp()
        patcher = mock.patch.object(rc, "platform_key", return_value="linux")
        patcher.start()
        self.addCleanup(patcher.stop)


"""---- the preference order ------------------------------------------------------------------------------------"""


class InstallMethodOrderTests(Linux):
    def options(self, e, *rels, machine="x64", channel="stable"):
        with mock.patch.object(em, "fetch_releases", return_value=list(rels)), \
                mock.patch.object(rc, "machine_key", return_value=machine):
            return em.install_options(e, self.store, force=True)

    def test_an_appimage_is_installed_before_a_portable_archive(self):
        e = emu()
        got = self.options(e, rel("v2", asset("pcsx2-v2-linux-x86_64.tar.gz"), asset("pcsx2-v2-linux-x86_64.AppImage")))
        self.assertEqual([o.method for o in got], [em.APPIMAGE, em.PORTABLE])
        self.assertEqual(got[0].asset["name"], "pcsx2-v2-linux-x86_64.AppImage")

    def test_an_archive_holding_an_appimage_beats_a_plain_archive(self):
        e = emu()
        got = self.options(e, rel("v2", asset("pcsx2-v2-linux-x86_64.tar.gz"),
                                  asset("pcsx2-v2-appimage-x86_64.zip")))
        self.assertEqual(got[0].method, em.APPIMAGE_ARCHIVE)
        self.assertEqual(got[0].asset["name"], "pcsx2-v2-appimage-x86_64.zip")
        self.assertEqual(got[-1].method, em.PORTABLE)

    def test_flatpak_comes_after_an_appimage_and_before_a_portable_archive(self):
        # an entry that names both a download and a Flatpak id, so both are candidates
        e = emu(id="dolphin", name="Dolphin", flatpak="org.DolphinEmu.dolphin-emu", asset={"linux": r"\.(AppImage|tar\.gz)$"})
        flatpak = (rc.Release("2603", "Dolphin", "", "", False, "https://dolphin-emu.org/",
                             ({"name": "org.DolphinEmu.dolphin-emu (Flatpak)", "url": "", "size": 0,
                               "flatpak_commit": "a" * 64},)),
                   {"name": "org.DolphinEmu.dolphin-emu (Flatpak)", "url": "", "size": 0, "flatpak_commit": "a" * 64})
        with mock.patch.object(em, "_flatpak_latest", return_value=flatpak):
            got = self.options(e, rel("2603", asset("dolphin-2603-linux-x64.tar.gz"),
                                      asset("dolphin-2603-linux-x64.AppImage")))
        self.assertEqual([o.method for o in got], [em.APPIMAGE, em.FLATPAK, em.PORTABLE])
        # and the same entry without the AppImage still prefers Flatpak to a plain archive
        with mock.patch.object(em, "_flatpak_latest", return_value=flatpak):
            got = self.options(e, rel("2603", asset("dolphin-2603-linux-x64.tar.gz")))
        self.assertEqual([o.method for o in got], [em.FLATPAK, em.PORTABLE])

    def test_a_distribution_package_is_last_but_still_offered(self):
        e = emu(website="https://pcsx2.net/")
        got = self.options(e, rel("v2", asset("pcsx2_2.0_amd64.deb"), asset("pcsx2-v2-linux-x86_64.AppImage")))
        self.assertEqual([o.method for o in got], [em.APPIMAGE, em.PACKAGE])
        self.assertEqual(got[-1].asset["name"], "pcsx2_2.0_amd64.deb")
        self.assertTrue(got[-1].manual)  # named, but installing it is not something Distill does
        self.assertFalse(got[0].manual)

    def test_a_package_only_release_explains_that_distill_does_not_install_one(self):
        e = emu(website="https://pcsx2.net/")
        got = self.options(e, rel("v2", asset("pcsx2_2.0_amd64.deb")))
        self.assertEqual([o.method for o in got], [em.PACKAGE])
        with mock.patch.object(em, "fetch_releases", return_value=[rel("v2", asset("pcsx2_2.0_amd64.deb"))]):
            why = em.latest_for(e, self.store)
        self.assertIn("distribution package", str(why))
        self.assertIn("immutable host", str(why))
        self.assertIn("https://pcsx2.net/", str(why))

    def test_a_source_build_is_the_last_resort(self):
        e = emu(id="ares", name="ares", build="ares", repo="ares-emulator/ares")
        with mock.patch.object(em, "_build_latest", return_value=(rel("v140"), {"name": "ares-emulator/ares (built from source)"})):
            got = self.options(e, rel("v140", asset("ares-v140-windows-x64.zip")))
        self.assertEqual([o.method for o in got], [em.SOURCE])

    def test_every_alternative_is_offered_not_only_the_first(self):
        e = emu()
        got = self.options(e, rel("v2", asset("app-linux-x86_64.AppImage"), asset("app-linux-x86_64-pgo.AppImage"),
                                  asset("app-appimage-x86_64.zip"), asset("app-linux-x86_64.tar.gz"),
                                  asset("app_2_amd64.deb")))
        self.assertEqual([o.method for o in got], [em.APPIMAGE, em.APPIMAGE, em.APPIMAGE_ARCHIVE, em.PORTABLE, em.PACKAGE])
        self.assertEqual([o.manual for o in got], [False, False, False, False, True])
        self.assertEqual(len({o.text() for o in got}), 5)  # each one can be told apart in a chooser

    def test_the_newest_release_with_a_linux_build_wins_over_an_older_appimage(self):
        e = emu()
        got = self.options(e, rel("v3", asset("app-v3-linux-x86_64.tar.gz")), rel("v2", asset("app-v2-linux-x86_64.AppImage")))
        self.assertEqual(got[0].release.tag, "v3")
        self.assertEqual(got[0].method, em.PORTABLE)

    def test_a_prerelease_only_replaces_a_stable_build_when_nothing_stable_has_one(self):
        e = emu()
        got = self.options(e, rel("v3-rc1", asset("app-v3-rc1-linux-x86_64.AppImage"), pre=True),
                           rel("v3", asset("app-v3-windows-x64.zip")), rel("v2", asset("app-v2-appimage-x86_64.zip")))
        self.assertEqual(got[0].release.tag, "v2")  # the newest stable build that has a Linux file
        got = self.options(e, rel("v3-rc1", asset("app-v3-rc1-linux-x86_64.AppImage"), pre=True),
                           rel("v3", asset("app-v3-windows-x64.zip")), rel("v2", asset("app-v2-windows-x64.zip")))
        self.assertEqual(got[0].release.tag, "v3-rc1")  # nothing stable has one: the pre-release is better than nothing

    def test_the_plain_build_is_the_default_and_the_tuned_one_is_an_alternative(self):
        e = emu()
        got = self.options(e, rel("v2", asset("app-linux-x86_64-pgo.AppImage"), asset("app-linux-x86_64.AppImage")))
        self.assertEqual([o.asset["name"] for o in got], ["app-linux-x86_64.AppImage", "app-linux-x86_64-pgo.AppImage"])

    def test_a_catalog_pattern_narrows_the_files_and_the_rest_are_not_offered(self):
        e = emu(asset={"linux": r"Eden-Linux-v[0-9.]+-amd64-clang-pgo\.AppImage$"})
        got = self.options(e, rel("v1", asset("Eden-Linux-v1.2-amd64-clang-standard.AppImage"),
                                  asset("Eden-Linux-v1.2-amd64-clang-pgo.AppImage")))
        self.assertEqual([o.asset["name"] for o in got], ["Eden-Linux-v1.2-amd64-clang-pgo.AppImage"])

    def test_a_windows_only_release_list_is_explained_not_silently_empty(self):
        e = emu(website="https://pcsx2.net/")
        with mock.patch.object(em, "fetch_releases", return_value=[rel("v2", asset("app-v2-windows-x64.zip"))]):
            self.assertEqual(em.install_options(e, self.store, force=True), [])
            why = em.latest_for(e, self.store)
        self.assertIn("no Linux build", str(why))
        self.assertIn("https://pcsx2.net/", str(why))  # tells the person where to go next

    def test_windows_choice_is_unchanged(self):
        e = emu(exe=r"(^|/)pcsx2-qt\.exe$")
        rels = [rel("v3", asset("pcsx2-v3-linux.AppImage")), rel("v2", asset("pcsx2-v2-windows-x64.7z"))]
        with mock.patch.object(em, "fetch_releases", return_value=rels), \
                mock.patch.object(rc, "platform_key", return_value="windows"):
            latest = em.latest_for(e, self.store)
        self.assertEqual(latest, em.choose(e, rels, "stable", "windows", "x64"))

    def test_the_engine_never_asks_for_a_system_package(self):
        """An immutable host (Bazzite, Silverblue, SteamOS) cannot take one, so nothing here shells out to a package manager:
        an AppImage in the person's folder, a per-user Flatpak and a source build are the only routes."""
        source = Path(em.__file__).read_text(encoding="utf-8")
        for command in ("rpm-ostree", "dnf install", "apt-get", "zypper", "pacman", "sudo "):
            self.assertNotIn(command, source)

    def test_the_install_folder_comes_from_the_xdg_data_directory(self):
        """The paths module keeps runtime state in XDG directories: an install and the state that records it never land in
        the person's program folder or their configuration."""
        data = self.tmp / "xdg-data"
        with mock.patch.object(rc, "ROOT", None), mock.patch.object(em.paths, "data_dir", lambda: data), \
                mock.patch.object(em.paths, "layout", lambda: "xdg"):
            self.assertEqual(rc.root(), data / "recomps")
        self.assertFalse(data.exists())  # resolving a location never creates state

    def test_an_entry_that_names_a_windows_zip_for_linux_stays_installable(self):
        """Project64 on Linux runs the Windows build through Wine, and the catalog names that zip as its Linux file: an
        entry that says so is trusted over the file's own name, and the install still goes through Wine."""
        e = emu(id="project64", name="Project64", wine=True, exe=r"(^|/)Project64\.exe$", asset={"linux": r"\.zip$"})
        with mock.patch.object(em, "fetch_releases", return_value=[rel("v3", asset("Project64-3.0.1-x64.zip"))]):
            got = em.install_options(e, self.store, force=True)
        self.assertEqual([o.asset["name"] for o in got], ["Project64-3.0.1-x64.zip"])
        with mock.patch.object(em.EmulatorInstaller, "_need_wine") as wine, \
                mock.patch.object(em.EmulatorInstaller, "_wrap_in_wine", return_value="wrapped") as wrap, \
                mock.patch.object(rc.Installer, "install", return_value="installed"):
            self.assertEqual(em.EmulatorInstaller(self.store).install(e, rel("v3"), got[0].asset), "wrapped")
        wine.assert_called_once()
        wrap.assert_called_once()

    def test_a_badly_named_linux_tarball_is_still_a_portable_archive(self):
        """Xenia's Linux build is called "xenia_canary_linux.tar_.xz": a tar the extractor sniffs, and the policy still
        has to see it as the portable archive it is."""
        e = emu(id="xenia-canary", name="Xenia", asset={"linux": r"linux.*\.(tar[\w.]*|zip)$"})
        with mock.patch.object(em, "fetch_releases", return_value=[rel("v1", asset("xenia_canary_linux.tar_.xz"))]):
            got = em.install_options(e, self.store, force=True)
        self.assertEqual([o.method for o in got], [em.PORTABLE])


"""---- architecture --------------------------------------------------------------------------------------------"""


class ArchitectureTests(Linux):
    def options(self, *assets, machine):
        e = emu()
        with mock.patch.object(em, "fetch_releases", return_value=[rel("v2", *assets)]), \
                mock.patch.object(rc, "machine_key", return_value=machine):
            return em.install_options(e, self.store, force=True)

    def test_the_x86_64_build_is_chosen_on_an_x86_64_pc(self):
        got = self.options(asset("app-linux-aarch64.AppImage"), asset("app-linux-x86_64.AppImage"), machine="x64")
        self.assertEqual([o.asset["name"] for o in got], ["app-linux-x86_64.AppImage"])

    def test_the_aarch64_build_is_chosen_on_an_arm_pc(self):
        got = self.options(asset("app-linux-aarch64.AppImage"), asset("app-linux-x86_64.AppImage"), machine="arm64")
        self.assertEqual([o.asset["name"] for o in got], ["app-linux-aarch64.AppImage"])

    def test_every_way_projects_spell_a_cpu_is_read(self):
        names = ["app-linux-amd64.AppImage", "app-linux-x86_64.AppImage", "app-linux-x64.AppImage"]
        for name in names:
            with self.subTest(name=name):
                self.assertEqual([o.asset["name"] for o in self.options(asset(name), machine="x64")], [name])
        for name in ["app-linux-arm64.AppImage", "app-linux-aarch64.AppImage", "app-linux-aarch64-1.0.AppImage"]:
            with self.subTest(name=name):
                self.assertEqual([o.asset["name"] for o in self.options(asset(name), machine="arm64")], [name])

    def test_a_32_bit_build_is_never_chosen(self):
        self.assertEqual(self.options(asset("app-linux-i686.AppImage"), machine="x64"), [])

    def test_no_build_for_this_architecture_says_which_ones_there_are(self):
        e = emu(name="Azahar", website="https://azahar-emu.org/")
        with mock.patch.object(em, "fetch_releases", return_value=[rel("2126.2", asset("azahar.AppImage", 103684600))]), \
                mock.patch.object(rc, "machine_key", return_value="arm64"):
            why = em.latest_for(e, self.store)
        self.assertIn("no Linux build for arm64", str(why))
        self.assertIn("azahar.AppImage", str(why))  # names the file, so the person can see what it is for
        self.assertIn("azahar-emu.org", str(why))  # and where to go

    def test_a_file_that_names_no_cpu_is_taken_as_an_x86_64_build(self):
        self.assertEqual([o.asset["name"] for o in self.options(asset("azahar.AppImage"), machine="x64")], ["azahar.AppImage"])
        self.assertEqual(self.options(asset("azahar.AppImage"), machine="arm64"), [])


"""---- unpacking an AppImage that arrives inside an archive -----------------------------------------------------"""


def zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def tar_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            t.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class AppImageInstallTests(Linux):
    def install(self, e, payload: bytes, name: str, tag: str = "v2", method: str = ""):
        a = asset(name, len(payload))
        if method:
            a["method"] = method
        r = rel(tag, a)

        class Resp(io.BytesIO):
            headers = {"Content-Length": str(len(payload))}

            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False
        with mock.patch.object(rc.urllib.request, "urlopen", lambda *a, **k: Resp(payload)):
            return em.EmulatorInstaller(self.store).install(e, r, a)

    def test_an_appimage_inside_a_zip_is_unpacked_made_executable_and_registered(self):
        root = self.tmp / "emus"
        em.set_emulators_root(self.store, root)
        e = emu(id="azahar", name="Azahar", exe=r"(^|/)Azahar[^/]*\.AppImage$")
        payload = zip_bytes({"Azahar-2126.2/Azahar.AppImage": b"\x7fELF" + b"\0" * 32,
                             "Azahar-2126.2/README.txt": b"notes"})
        inst = self.install(e, payload, "Azahar-2126.2-linux-appimage-x86_64.zip", method=em.APPIMAGE_ARCHIVE)
        self.assertEqual(Path(inst.folder), root / "Azahar")
        target = inst.exe_path()
        self.assertEqual(target.name, "Azahar.AppImage")  # the AppImage in the archive runs, not something beside it
        self.assertTrue(target.stat().st_mode & 0o111)
        self.assertEqual(inst.exe, "Azahar.AppImage")

    def test_an_appimage_inside_a_tar_gz_is_unpacked_and_registered(self):
        e = emu(id="ryujinx", name="Ryujinx", exe=r"(^|/)Ryujinx[^/]*\.AppImage$")
        payload = tar_bytes({"Ryujinx-1.3.3/Ryujinx.AppImage": b"\x7fELF" + b"\0" * 32})
        inst = self.install(e, payload, "ryujinx-1.3.3-linux_x64-appimage.tar.gz", method=em.APPIMAGE_ARCHIVE)
        self.assertEqual(inst.exe, "Ryujinx.AppImage")
        self.assertTrue(inst.exe_path().stat().st_mode & 0o111)

    def test_an_appimage_beside_a_plain_binary_is_the_one_that_runs(self):
        e = emu(id="lichii", name="Lichii")  # no exe pattern: the guess has to prefer the AppImage
        payload = tar_bytes({"lichii/lichii": b"\x7fELF" + b"\0" * 32, "lichii/lichii-linux-x86_64.AppImage": b"\x7fELF" + b"\0" * 32})
        inst = self.install(e, payload, "lichii-linux-x86_64.tar.gz")
        self.assertEqual(inst.exe, "lichii-linux-x86_64.AppImage")

    def test_updating_an_appimage_keeps_saves_and_settings_and_drops_the_old_file(self):
        root = self.tmp / "emus"
        em.set_emulators_root(self.store, root)
        e = emu(id="azahar", name="Azahar", exe=r"(^|/)Azahar[^/]*\.AppImage$")
        first = self.install(e, b"\x7fELF-old", "Azahar-2126.2.AppImage")
        folder = Path(first.folder)
        (folder / "saves").mkdir()
        (folder / "saves" / "game.sav").write_bytes(b"my save")
        (folder / "qt-config.ini").write_bytes(b"my settings")
        second = self.install(e, b"\x7fELF-new", "Azahar-2127.0.AppImage", tag="2127.0")
        self.assertEqual(second.exe, "Azahar-2127.0.AppImage")
        self.assertEqual((folder / "saves" / "game.sav").read_bytes(), b"my save")
        self.assertEqual((folder / "qt-config.ini").read_bytes(), b"my settings")
        self.assertFalse((folder / "Azahar-2126.2.AppImage").exists())  # the old build is not left piling up
        self.assertEqual(second.version, "2127.0")

    def test_an_install_lands_in_its_own_folder_and_never_in_the_persons_config(self):
        e = emu(id="azahar", name="Azahar", exe=r"(^|/)Azahar[^/]*\.AppImage$")
        inst = self.install(e, b"\x7fELF", "Azahar-2126.2.AppImage")
        self.assertIn("emulators", Path(inst.folder).parts)  # Distill's own data folder, which is not the program's settings
        self.assertNotIn(str(self.config), inst.folder)
        self.assertFalse(self.config.exists() and any(self.config.rglob("*")))
        self.assertEqual(self.store.installed("azahar").folder, inst.folder)


"""---- starting an AppImage on a host without FUSE 2 ------------------------------------------------------------"""


class AppImageLaunchTests(Linux):
    def test_an_appimage_without_fuse2_is_started_with_the_runtime_fallback(self):
        exe = self.tmp / "Azahar.AppImage"
        exe.write_bytes(b"\x7fELF")
        with mock.patch.object(em, "appimage_fuse2", return_value=False):
            env = em.appimage_env(exe)
        self.assertEqual(env["APPIMAGE_EXTRACT_AND_RUN"], "1")

    def test_with_fuse2_nothing_is_added(self):
        exe = self.tmp / "Azahar.AppImage"
        exe.write_bytes(b"\x7fELF")
        with mock.patch.object(em, "appimage_fuse2", return_value=True):
            self.assertIsNone(em.appimage_env(exe))

    def test_a_plain_program_gets_no_extra_environment(self):
        exe = self.tmp / "pcsx2-qt"
        exe.write_bytes(b"\x7fELF")
        with mock.patch.object(em, "appimage_fuse2", return_value=False):
            self.assertIsNone(em.appimage_env(exe))

    def test_the_extra_variable_is_added_and_hostenv_still_cleans_the_environment(self):
        """The AppImage is started through subprocess like any other child, so hostenv still strips the bundle's paths: an
        environment built here is handed over as it is and cleaned there."""
        exe = self.tmp / "Azahar.AppImage"
        exe.write_bytes(b"\x7fELF")
        bundle = "/opt/Distill/_internal"
        with mock.patch.object(em, "appimage_fuse2", return_value=False):
            env = em.appimage_env(exe, {"LD_LIBRARY_PATH": bundle, "LD_LIBRARY_PATH_ORIG": "/usr/lib", "HOME": "/home/someone"})
        with mock.patch.object(hostenv.sys, "frozen", True, create=True), \
                mock.patch.object(hostenv.sys, "_MEIPASS", bundle, create=True):
            cleaned = hostenv.host_env(env)
        self.assertEqual(cleaned["LD_LIBRARY_PATH"], "/usr/lib")  # the frozen bundle's own libraries are gone again
        self.assertEqual(cleaned["APPIMAGE_EXTRACT_AND_RUN"], "1")  # and what the AppImage needs survives

    def test_a_launch_of_an_appimage_passes_the_environment_through_subprocess(self):
        folder = self.tmp / "Azahar"
        folder.mkdir()
        exe = folder / "Azahar.AppImage"
        exe.write_bytes(b"\x7fELF")
        self.store.set_installed(rc.Installed("azahar", "2126.2", str(folder), "Azahar.AppImage"))
        e = emu(id="azahar", name="Azahar")
        with mock.patch.object(em, "appimage_fuse2", return_value=False), \
                mock.patch.object(rc, "launch") as launch:
            em.launch(e, self.store.installed("azahar"))
        self.assertEqual(launch.call_args.kwargs["env"]["APPIMAGE_EXTRACT_AND_RUN"], "1")

    def test_an_ordinary_launch_passes_no_environment_at_all(self):
        folder = self.tmp / "PCSX2"
        folder.mkdir()
        (folder / "pcsx2-qt").write_bytes(b"\x7fELF")
        self.store.set_installed(rc.Installed("pcsx2", "v2", str(folder), "pcsx2-qt"))
        with mock.patch.object(rc, "launch") as launch:
            em.launch(emu(), self.store.installed("pcsx2"))
        launch.assert_called_once_with(mock.ANY)


"""---- the Nintendo entries, against the release listings they really publish ----------------------------------"""


class NintendoCatalogTests(Linux):
    def setUp(self) -> None:
        super().setUp()
        self.cat = catalog()

    def check(self, rid: str, fixture: str, machine: str = "x64", host: str = "api.github.com"):
        seen = []

        def serve(url, *a, **k):
            seen.append(url)
            self.assertIn(host, url)
            return json.dumps(listing(fixture)).encode()

        with mock.patch.object(rc, "_get", side_effect=serve), \
                mock.patch.object(rc, "machine_key", return_value=machine):
            latest, options = em.check(self.cat[rid], self.store, force=True)
        return latest, options, seen

    def test_azahar_installs_the_appimage_of_its_newest_stable_release(self):
        latest, options, _seen = self.check("azahar", "azahar.json")
        rel_, asset_ = latest
        self.assertEqual(rel_.tag, "2126.2")  # the newest release that is not a pre-release
        self.assertFalse(rel_.prerelease)
        self.assertEqual(asset_["name"], "azahar.AppImage")  # the file has no version in its name
        self.assertEqual(asset_["size"], 103684600)  # the size the project publishes for it
        self.assertEqual([o.method for o in options], [em.APPIMAGE])
        self.assertTrue(all(o.release.tag == "2126.2" for o in options))

    def test_azahars_version_is_looked_up_never_written_into_the_catalog(self):
        entry = next(e for e in json.loads(em.bundled_manifest().read_text())["emulators"] if e["id"] == "azahar")
        text = json.dumps(entry)
        for tag in ("2126.2", "2127.0", "2127.0-rc3"):
            self.assertNotIn(tag, text)  # a hardcoded version would go stale the day the project ships a new one
        patched = listing("azahar.json")
        patched[1]["tag_name"] = "2128.1"  # the stable release in the listing; only the fixture changes, and the entry follows it
        with mock.patch.object(rc, "_get", return_value=json.dumps(patched).encode()), \
                mock.patch.object(rc, "machine_key", return_value="x64"):
            latest, _options = em.check(self.cat["azahar"], self.store, force=True)
        self.assertEqual(latest[0].tag, "2128.1")

    def test_azahar_has_no_arm_build_and_says_so(self):
        latest, _options, _seen = self.check("azahar", "azahar.json", machine="arm64")
        self.assertIsInstance(latest, str)
        self.assertIn("arm64", latest)

    def test_ryubing_is_read_through_the_forgejo_adapter_and_installs_its_appimage(self):
        latest, options, seen = self.check("ryujinx", "ryubing.json", host="git.ryujinx.app")
        self.assertTrue(any("/api/v1/repos/projects/Ryubing/releases" in url for url in seen))
        rel_, asset_ = latest
        self.assertEqual((rel_.tag, asset_["name"]), ("1.3.3", "ryujinx-1.3.3-x64.AppImage"))
        self.assertTrue(asset_["url"].startswith("https://git.ryujinx.app/"))
        self.assertEqual([o.method for o in options], [em.APPIMAGE, em.PORTABLE])
        self.assertEqual(options[1].asset["name"], "ryujinx-1.3.3-linux_x64.tar.gz")

    def test_ryubing_picks_the_arm_build_on_an_arm_pc(self):
        latest, options, _seen = self.check("ryujinx", "ryubing.json", machine="arm64", host="git.ryujinx.app")
        self.assertEqual(latest[1]["name"], "ryujinx-1.3.3-arm64.AppImage")
        self.assertEqual(options[1].asset["name"], "ryujinx-1.3.3-linux_arm64.tar.gz")

    def test_eglantine_resolves_its_own_appimage_and_is_labelled_experimental(self):
        e = self.cat["eglantine"]
        self.assertEqual(e.status, "experimental")
        latest, options, _seen = self.check("eglantine", "eglantine.json")
        self.assertEqual(latest[1]["name"], "eglantine-linux-x86_64.AppImage")
        self.assertEqual(options[1].asset["name"], "eglantine-linux-x86_64-pgo.AppImage")
        self.assertEqual(latest[0].tag, "v0.1.0-rc4")  # the daily build is a pre-release, so it is not taken as stable
        self.assertIn("experimental", e.notes.lower())
        self.assertIn("release candidate", e.notes.lower())

    def test_lichii_resolves_its_own_appimage(self):
        latest, options, _seen = self.check("lichii", "lichii.json")
        self.assertEqual(latest[0].tag, "build-316")
        self.assertEqual(latest[1]["name"], "lichii-linux-x86_64.AppImage")
        self.assertEqual(options[1].asset["name"], "lichii-linux-x86_64-pgo.AppImage")

    def test_the_real_file_name_of_each_entry_is_the_one_it_would_launch(self):
        for rid, fixture, host in (("azahar", "azahar.json", "api.github.com"), ("eglantine", "eglantine.json", "api.github.com"),
                                   ("lichii", "lichii.json", "api.github.com"), ("ryujinx", "ryubing.json", "git.ryujinx.app")):
            with self.subTest(entry=rid):
                latest, _options, _seen = self.check(rid, fixture, host=host)
                folder = self.tmp / f"install-{rid}"
                folder.mkdir()
                (folder / latest[1]["name"]).write_bytes(b"\x7fELF")
                found = em.locate_exe(folder, self.cat[rid], "linux")
                self.assertIsNotNone(found, rid)
                self.assertEqual(found.name, latest[1]["name"])

    def test_lime3ds_is_superseded_and_never_downloads_azahars_build(self):
        e = self.cat["lime3ds"]
        self.assertEqual((e.status, e.replaced_by), ("superseded", "azahar"))
        self.assertFalse(e.available)
        self.assertEqual(e.repo, "")  # its repository redirects to Azahar: pointing at it would download the wrong project
        self.assertEqual(em.install_options(e, self.store), [])
        self.assertIn("Azahar", em.latest_for(e, self.store))
        with mock.patch.object(rc.urllib.request, "urlopen", side_effect=AssertionError("must not download")):
            with self.assertRaises(rc.RecompError):
                em.EmulatorInstaller(self.store).install(e, rel("v1"), asset("azahar.AppImage"))

    def test_sudachi_is_discontinued_with_nothing_to_download(self):
        e = self.cat["sudachi"]
        self.assertEqual(e.status, "discontinued")
        self.assertFalse(e.available)
        self.assertEqual((e.repo, e.website), ("", ""))  # no repository and no site to point at: there is no official one
        self.assertEqual(em.install_options(e, self.store), [])
        why = em.latest_for(e, self.store)
        self.assertIn("discontinued", str(why).lower())
        self.assertIn("mirror", str(why).lower())  # and it says it will not fall back to a copy of it

    def test_the_six_entries_carry_linux_data_or_an_honest_status(self):
        for rid in ("azahar", "eglantine", "lichii", "ryujinx"):
            with self.subTest(entry=rid):
                e = self.cat[rid]
                self.assertTrue(em.downloadable(e), rid)
                self.assertTrue(e.exe, f"{rid} needs a launch pattern")
                self.assertTrue(e.trusted_owner or e.source in ("forgejo", "gitlab"), rid)
        for rid, status in (("lime3ds", "superseded"), ("sudachi", "discontinued")):
            with self.subTest(entry=rid):
                self.assertEqual(self.cat[rid].status, status)
                self.assertFalse(em.downloadable(self.cat[rid]))
                self.assertGreater(len(self.cat[rid].notes), 80)

    def test_a_retired_entry_still_launches_a_copy_the_person_has(self):
        for rid in ("lime3ds", "sudachi"):
            with self.subTest(entry=rid):
                e = self.cat[rid]
                self.assertTrue(em.launchable(e))
                folder = self.tmp / rid
                folder.mkdir(exist_ok=True)
                (folder / f"{rid}.AppImage").write_bytes(b"\x7fELF")
                inst = rc.Installed(rid, "1.0", str(folder), f"{rid}.AppImage")
                with mock.patch.object(rc, "launch") as launch:
                    em.launch(e, inst)
                launch.assert_called_once_with(inst)

    def test_a_refused_entry_is_still_never_launched(self):
        refused = emu(available=False, notes="Refused: untrusted install kind.", flatpak="org.unrelated.App")
        self.assertFalse(em.launchable(refused))
        installed = rc.Installed("pcsx2", "v1", str(self.tmp), em.LAUNCHER)
        with self.assertRaisesRegex(rc.RecompError, "Refused"):
            em.launch(refused, installed)


"""---- Lichii and Eglantine are not each other ---------------------------------------------------------------"""


class CrossIdentificationTests(Linux):
    def setUp(self) -> None:
        super().setUp()
        self.cat = catalog()

    def folder(self, name: str, *files: str) -> Path:
        folder = self.tmp / "emus" / name
        folder.mkdir(parents=True)
        for file in files:
            (folder / file).write_bytes(b"\x7fELF" + b"\0" * 16)
        return folder

    def test_an_eglantine_install_is_not_taken_for_lichii(self):
        self.folder("Eglantine", "eglantine-linux-x86_64.AppImage")
        found = em.scan_folder(self.tmp / "emus", [self.cat["eglantine"], self.cat["lichii"]], "linux")
        self.assertIn("eglantine", found)
        self.assertNotIn("lichii", found)

    def test_a_lichii_install_is_not_taken_for_eglantine(self):
        self.folder("Lichii", "lichii-linux-x86_64.AppImage")
        found = em.scan_folder(self.tmp / "emus", [self.cat["eglantine"], self.cat["lichii"]], "linux")
        self.assertIn("lichii", found)
        self.assertNotIn("eglantine", found)

    def test_lichiis_launch_pattern_never_matches_an_eglantine_file(self):
        folder = self.folder("mixed", "eglantine", "eglantine-linux-x86_64.AppImage")
        self.assertIsNone(em.locate_exe(folder, self.cat["lichii"], "linux"))
        self.assertEqual(em.locate_exe(folder, self.cat["eglantine"], "linux").name, "eglantine-linux-x86_64.AppImage")

    def test_each_project_keeps_its_own_launch_pattern(self):
        self.assertNotIn("eglantine", self.cat["lichii"].exe.replace("eglantine-nx2", ""))
        self.assertIn("lichii", self.cat["lichii"].exe)
        self.assertIn("eglantine", self.cat["eglantine"].exe)


if __name__ == "__main__":
    unittest.main()
