"""The PlayStation entries, and the corrections the catalog audit asked for across the rest of the catalog.

The release listings under tests/fixtures/releases are trimmed copies of what the projects' own APIs returned on
2026-11-17: every file name, size and download address in them is real, the release notes are cut short. The archives
built here are made in the test, so nothing third-party is downloaded or run. What the real archives hold was read by
listing them on 2026-11-17 and is quoted where it matters:

    KytyPS5-2026-11-17-faec1f4-Linux-x86_64.tar.gz   kyty_launcher, kyty_emulator, kyty_updater, lib/, plugins/,
                                                    assets/, qt.conf   (kyty_launcher and kyty_emulator are -rwxr-xr-x)
    KytyPS5-2026-11-17-faec1f4-Windows-x64.zip       kyty_launcher.exe, kyty_emulator.exe, kyty_updater.exe
    shadps4-linux-sdl-0.21.0.zip                     Shadps4-sdl.AppImage (one file)
    shadPS4QtLauncher-linux-qt-2026-11-06-ecc8507.zip shadPS4QtLauncher-qt.AppImage (one file)
    mame0289lx.zip                                   mame0289.xml (326 MB of driver information, NOT a Linux build)
    Mesen_2.2.1_Linux_x64.zip                        Mesen (one file)
    dosbox-staging-linux-x86_64-v0.83.1.tar.xz       dosbox-staging-linux-x86_64-0.83.1-8888e/dosbox
    ymir-linux-x86_64-SSE2-v0.4.1.tar.xz             ymir-sdl3
    BigPEmu_Linux64_v1221.tar.gz                     bigpemu/bigpemu
    blastem64-1.0.0.tar.gz                           blastem64-1.0.0/blastem
    linux-sdl2-x86_64.zip                            fbneo
"""
from __future__ import annotations

import io
import json
import re
import tarfile
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path
from unittest import mock

from tests import helpers
from distill import emulators as em
from distill import recomps as rc

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "releases"


def asset(name: str, size: int = 10, digest: str = "", owner: str = "o") -> dict:
    return {"name": name, "url": f"https://github.com/{owner}/r/releases/download/t/{name}", "size": size, "digest": digest}


def rel(tag: str, *assets: dict, pre: bool = False, published: str = "2026-01-01") -> rc.Release:
    return rc.Release(tag, tag, "", published, pre, "https://example.invalid", tuple(assets))


def listing(name: str) -> list[dict]:
    """The recorded release listing, as the API returned it."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def tar_bytes(files: dict[str, bytes], executable: tuple[str, ...] = ()) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755 if name in executable else 0o644
            t.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class Isolated(unittest.TestCase):
    def setUp(self) -> None:
        td = tempfile.TemporaryDirectory(prefix="distill_ps_")
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
    """A Linux host: what every entry here is judged on."""

    def setUp(self) -> None:
        super().setUp()
        patcher = mock.patch.object(rc, "platform_key", return_value="linux")
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(rc, "machine_key", return_value="x64")
        patcher.start()
        self.addCleanup(patcher.stop)

    def catalog(self, plat: str = "linux") -> dict[str, em.Emulator]:
        return {e.id: e for e in em.load_catalog([em.bundled_manifest()], plat)}

    def check(self, rid: str, fixture: str, cat: dict | None = None, plat: str = "linux"):
        """`em.check` against the recorded listing, with the API answered from the fixture."""
        cat = cat or self.catalog(plat)
        seen: list[str] = []

        def serve(url, *a, **k):
            seen.append(url)
            return json.dumps(listing(fixture)).encode()

        with mock.patch.object(rc, "_get", side_effect=serve):
            latest, options = em.check(cat[rid], self.store, force=True)
        return latest, options, seen

    def install(self, e, payload: bytes, name: str, tag: str = "v2", method: str = "", owner: str = "") -> rc.Installed:
        a = asset(name, len(payload), owner=owner or (e.repo.split("/")[0] if e.repo else "o"))
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


"""---- AnyPS5 is a porting tool, not an emulator ---------------------------------------------------------------"""


class AnyPS5Tests(Linux):
    def setUp(self) -> None:
        super().setUp()
        self.e = self.catalog()["anyps5"]

    def test_it_is_carried_as_a_tool_and_nothing_about_it_can_be_installed_as_an_emulator(self):
        self.assertEqual(self.e.kind, "tool")
        self.assertFalse(self.e.available)
        self.assertFalse(em.downloadable(self.e))
        self.assertFalse(em.launchable(self.e))
        self.assertEqual(em.install_options(self.e, self.store), [])
        self.assertEqual(em.status_text(self.e, None, None), ("unavailable", "Tool, not an emulator"))

    def test_its_page_explains_what_it_does_instead_of_showing_a_dead_install_button(self):
        self.assertIn("not an emulator", self.e.notes)
        self.assertIn("Settings > Tools", self.e.notes)
        self.assertIn("source/eboot.bin", self.e.notes)
        # the long form: what it is, what it is not, how Linux and Windows each get set up, what is needed, how it runs
        self.assertIn("relinker", self.e.details.lower())
        self.assertIn("differs from an emulator", self.e.details)
        self.assertEqual(set(self.e.setup), {"linux", "windows", "macos"})
        self.assertTrue(all("relinker" in text for text in self.e.setup.values()))
        self.assertTrue(any("AVX2" in d for d in self.e.dependencies))
        self.assertIn("relinker source/input.elf app.elf", self.e.usage)
        self.assertIn("relinker --windows source/input.elf app.exe", self.e.usage)
        self.assertEqual(self.e.tool_key, "relinker")

    def test_it_points_at_the_project_and_the_distill_tool_that_installs_it(self):
        self.assertEqual(self.e.repo, "boykopovar/AnyPS5")
        self.assertEqual(self.e.trusted_owner, "boykopovar")
        self.assertEqual(self.e.website, "https://boykopovar.github.io/AnyPS5/")
        from distill import tools
        self.assertIn(self.e.tool_key, {cls.KEY for cls in tools.managers() if getattr(cls, "KEY", "")})

    def test_it_is_never_linked_as_an_emulator_install(self):
        folder = self.tmp / "emus" / "AnyPS5"
        folder.mkdir(parents=True)
        (folder / "relinker").write_bytes(b"\x7fELF" + b"\0" * 8)
        self.assertEqual(em.scan_folder(self.tmp / "emus", [self.e], "linux"), {})

    def test_nothing_about_it_can_be_downloaded_through_the_installer(self):
        with mock.patch.object(rc.urllib.request, "urlopen", side_effect=AssertionError("must not download")):
            with self.assertRaises(rc.RecompError):
                em.EmulatorInstaller(self.store).install(self.e, rel("v0.1.5"), asset("relinker-v0.1.5"))

    def test_the_catalog_count_is_unchanged_by_the_extras_it_gained(self):
        # the self-test counts the manifest's own entries: shadPS4's Qt launcher is nested, so it is not a 37th emulator
        cat = self.catalog()
        self.assertEqual(len(cat), 36)
        self.assertEqual(len(em.all_entries(list(cat.values()))), 37)


"""---- KytyPS5: the graphical launcher is what runs ------------------------------------------------------------"""


class KytyPS5Tests(Linux):
    def test_the_launch_target_is_the_graphical_launcher_not_the_emulator_binary(self):
        e = self.catalog()["kytyps5"]
        folder = self.tmp / "emus" / "KytyPS5"
        folder.mkdir(parents=True)
        for name in ("kyty_launcher", "kyty_emulator", "kyty_updater"):
            (folder / name).write_bytes(b"\x7fELF" + b"\0" * 8)
        self.assertEqual(em.locate_exe(folder, e, "linux").name, "kyty_launcher")

    def test_the_windows_target_is_the_launcher_too(self):
        # the Windows zip holds kyty_launcher.exe beside kyty_emulator.exe and kyty_updater.exe
        e = self.catalog("windows")["kytyps5"]
        folder = self.tmp / "emus" / "KytyPS5"
        folder.mkdir(parents=True)
        for name in ("kyty_launcher.exe", "kyty_emulator.exe", "kyty_updater.exe"):
            (folder / name).write_bytes(b"MZ" + b"\0" * 8)
        self.assertEqual(em.locate_exe(folder, e, "windows").name, "kyty_launcher.exe")

    def test_the_recorded_release_gives_the_official_linux_archive(self):
        latest, options, _seen = self.check("kytyps5", "kytyps5.json")
        rel_, asset_ = latest
        self.assertEqual(rel_.tag, "KytyPS5-2026-11-17-faec1f4")
        self.assertEqual(asset_["name"], "KytyPS5-2026-11-17-faec1f4-Linux-x86_64.tar.gz")
        self.assertEqual([o.method for o in options], [em.PORTABLE])
        self.assertEqual(options[0].release.tag, rel_.tag)

    def test_an_install_from_that_layout_lands_on_the_launcher_and_is_made_executable(self):
        e = self.catalog()["kytyps5"]
        payload = tar_bytes({"kyty_emulator": b"\x7fELF" + b"\0" * 8, "lib/libQt6Core.so.6": b"\x7fELF",
                             "kyty_launcher": b"\x7fELF" + b"\0" * 8}, executable=())  # no mode bits: Distill sets them
        with mock.patch.object(rc, "sys", mock.Mock(platform="linux")), helpers.record_chmod() as chmod:
            inst = self.install(e, payload, "KytyPS5-2026-11-17-faec1f4-Linux-x86_64.tar.gz")
        self.assertEqual(inst.exe, "kyty_launcher")
        helpers.assert_executable(self, inst.exe_path(), chmod)

    def test_its_page_says_playstation_5_and_how_the_releases_are_named(self):
        e = self.catalog()["kytyps5"]
        self.assertIn("PlayStation 5", e.notes)
        self.assertNotIn("PlayStation 4", e.notes)
        self.assertEqual(e.channels, ("nightly",))
        self.assertEqual(set(e.platforms), {"windows", "linux", "macos"})


"""---- shadPS4 and its optional Qt launcher --------------------------------------------------------------------"""


class ShadPS4Tests(Linux):
    def setUp(self) -> None:
        super().setUp()
        self.cat = self.catalog()
        self.e = self.cat["shadps4"]
        self.launcher = self.e.extras[0]

    def test_the_emulator_installs_the_zip_of_its_stable_release(self):
        latest, options, _seen = self.check("shadps4", "shadps4.json")
        self.assertEqual(latest[0].tag, "v.0.21.0")  # the project's own odd tag format, leading dot and all
        self.assertFalse(latest[0].prerelease)  # the rolling Pre-release-shadPS4-* build is not taken as stable
        self.assertEqual(latest[1]["name"], "shadps4-linux-sdl-0.21.0.zip")
        self.assertEqual([o.method for o in options], [em.PORTABLE])

    def test_the_zip_holds_the_appimage_and_that_is_what_gets_registered(self):
        payload = zip_bytes({"Shadps4-sdl.AppImage": b"\x7fELF" + b"\0" * 8})
        with mock.patch.object(rc, "sys", mock.Mock(platform="linux")), helpers.record_chmod() as chmod:
            inst = self.install(self.e, payload, "shadps4-linux-sdl-0.21.0.zip")
        self.assertEqual(inst.exe, "Shadps4-sdl.AppImage")
        helpers.assert_executable(self, inst.exe_path(), chmod)

    def test_the_qt_launcher_is_an_optional_extra_of_the_emulator_not_a_second_entry(self):
        self.assertEqual([x.id for x in em.companions(self.e)], ["shadps4-qtlauncher"])
        self.assertNotIn("shadps4-qtlauncher", self.cat)  # no duplicate tile, no duplicate download
        self.assertTrue(self.launcher.preferred_launch)
        self.assertTrue(self.launcher.prerelease_only)
        self.assertEqual(self.launcher.status, "experimental")

    def test_the_real_launcher_archive_is_what_the_entry_asks_for(self):
        latest, options, _seen = self.check("shadps4-qtlauncher", "shadps4-qtlauncher.json", cat={"shadps4-qtlauncher": self.launcher})
        rel_, asset_ = latest
        self.assertEqual(rel_.tag, "shadPS4QtLauncher-2026-11-06-ecc85072dae45c05628934fdb6b3aa036e9f1d4b")
        self.assertEqual(asset_["name"], "shadPS4QtLauncher-linux-qt-2026-11-06-ecc8507.zip")
        self.assertEqual([o.method for o in options], [em.PORTABLE])

    def test_a_project_whose_only_release_is_a_prerelease_still_offers_a_build(self):
        # GitHub's /releases/latest answers 404 when every release is a pre-release: that is not "no releases"
        latest, options, _seen = self.check("shadps4-qtlauncher", "shadps4-qtlauncher.json", cat={"shadps4-qtlauncher": self.launcher})
        self.assertIsInstance(latest, tuple, latest)
        self.assertTrue(latest[0].prerelease)
        self.assertIn("pre-release", em.label_of(self.launcher, latest[0], latest[1]))
        self.assertTrue(options)

    def test_the_latest_lookup_answers_a_404_from_the_release_list(self):
        def serve(url, *a, **k):
            if url.endswith("/releases/latest"):
                raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)  # what GitHub answers, every time
            return json.dumps(listing("shadps4-qtlauncher.json")).encode()

        with mock.patch.object(rc, "_get", side_effect=serve):
            newest = rc.latest_release("shadps4-emu/shadps4-qtlauncher", self.store, force=True)
        self.assertIsNotNone(newest)
        self.assertEqual(newest.tag, "shadPS4QtLauncher-2026-11-06-ecc85072dae45c05628934fdb6b3aa036e9f1d4b")
        self.assertTrue(newest.prerelease)

    def test_a_repository_with_no_release_at_all_is_still_none(self):
        def serve(url, *a, **k):
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        with mock.patch.object(rc, "_get", side_effect=serve):
            self.assertIsNone(rc.latest_release("shadps4-emu/shadps4-qtlauncher", self.store, force=True))

    def test_the_launcher_is_preferred_as_the_launch_target_when_it_is_installed(self):
        emu_folder = self.tmp / "emus" / "shadPS4"
        emu_folder.mkdir(parents=True)
        (emu_folder / "Shadps4-sdl.AppImage").write_bytes(b"\x7fELF")
        cli = em.link(self.store, self.e, emu_folder, "linux")
        with mock.patch.object(rc, "launch") as launch:
            em.launch(self.e, self.store.installed("shadps4"), self.store)
        launch.assert_called_once()  # nothing installed for the launcher yet: the emulator itself runs
        (self.tmp / "emus" / "shadPS4 Qt launcher").mkdir(parents=True)
        (self.tmp / "emus" / "shadPS4 Qt launcher" / "shadPS4QtLauncher-qt.AppImage").write_bytes(b"\x7fELF")
        linked = em.link(self.store, self.launcher, self.tmp / "emus" / "shadPS4 Qt launcher", "linux")
        with mock.patch.object(rc, "launch") as launch:
            em.launch(self.e, self.store.installed("shadps4"), self.store)
        launch.assert_called_once()
        self.assertEqual(launch.call_args.args[0].exe, linked.exe)
        # and the command-line program is still one call away
        with mock.patch.object(rc, "launch") as launch:
            em.launch(self.e, self.store.installed("shadps4"), self.store, cli=True)
        self.assertEqual(launch.call_args.args[0].exe, cli.exe)

    def test_an_existing_launcher_install_is_found_by_a_scan(self):
        folder = self.tmp / "emus" / "shadPS4 Qt launcher"
        folder.mkdir(parents=True)
        (folder / "shadPS4QtLauncher-qt.AppImage").write_bytes(b"\x7fELF" + b"\0" * 8)
        found = em.scan_folder(self.tmp / "emus", [self.e], "linux")
        self.assertIn("shadps4-qtlauncher", found)
        self.assertNotIn("shadps4", found)

    def test_the_relationship_is_explained_in_the_page_text(self):
        self.assertIn("launcher", self.e.notes.lower())
        self.assertIn("pre-release", self.launcher.notes.lower())
        self.assertIn("experimental", self.launcher.notes.lower())


"""---- the audit's corrections across the rest of the catalog ---------------------------------------------------"""


class SharedRegexDefectTests(Linux):
    """`|\\.AppImage$` (no path anchor) made five entries report 'installed' for any AppImage on the machine."""

    def test_no_entry_takes_an_unrelated_appimage_for_its_own_program(self):
        cat = self.catalog("windows")
        foreign = ["/opt/emulators/Firefox.AppImage", "/home/someone/Downloads/GIMP.AppImage", "Other.AppImage"]
        for e in cat.values():
            if not e.exe:
                continue
            with self.subTest(entry=e.id):
                for path in foreign:
                    self.assertIsNone(re.search(e.exe, path, re.IGNORECASE), f"{e.id} claims {path}")

    def test_the_five_entries_that_had_it_now_name_their_own_build(self):
        for rid, owns in (("retroarch", "retroarch"), ("duckstation", "DuckStation-x64.AppImage"),
                          ("pcsx2", "pcsx2-v2.8.2-linux-appimage-x64-Qt.AppImage"), ("rpcs3", "rpcs3-v0.0.43_linux64.AppImage"),
                          ("cemu", "Cemu-2.6-x86_64.AppImage")):
            e = self.catalog("windows")[rid]
            with self.subTest(entry=rid):
                self.assertIsNotNone(re.search(e.exe, owns, re.IGNORECASE))
                self.assertIsNone(re.search(e.exe, "/opt/emulators/Firefox.AppImage", re.IGNORECASE))


class CatalogCorrectionTests(Linux):
    def setUp(self) -> None:
        super().setUp()
        self.cat = self.catalog()

    def test_mames_windows_pattern_matches_the_real_files(self):
        e = self.cat["mame"]
        for name in ("mame0289b_x64.exe", "mame0289b_arm64.exe"):
            with self.subTest(file=name):
                self.assertIsNotNone(re.search(e.asset["windows"], name))
        self.assertIsNone(re.search(e.asset["windows"], "mame0289s.exe"))  # that one is the source archive

    def test_mame_promises_no_linux_download_the_audit_wrongly_thought_existed(self):
        # mame0289lx.zip is the driver information in XML, not a Linux build (listing it shows one mame0289.xml)
        e = self.cat["mame"]
        self.assertFalse(em.hosts_linux_download(e))
        with mock.patch.object(em, "fetch_releases", return_value=[
                rel("mame0289", asset("mame0289lx.zip"), asset("mame0289b_x64.exe"))]):
            with mock.patch.object(em, "_flatpak_latest", return_value="mame comes from Flathub here"):
                options = em.install_options(e, self.store)
        self.assertEqual(options, [])  # nothing on Linux is offered as a download, and the page says why
        self.assertIn("XML", e.notes)

    def test_xenia_follows_the_live_channel_not_the_frozen_mirror(self):
        e = self.cat["xenia-canary"]
        self.assertEqual(e.repo, "xenia-canary/xenia-canary")
        self.assertNotIn("xenia-canary-releases", e.repo)
        self.assertIn("linux", e.platforms)
        self.assertIsNotNone(re.search(e.asset["linux"], "xenia_canary_linux.AppImage"))

    def test_mesen_follows_the_repository_the_project_moved_to(self):
        e = self.cat["mesen2"]
        self.assertEqual(e.repo, "nesdev-org/MesenCE")
        self.assertEqual(e.name, "Mesen CE")
        self.assertIsNotNone(re.search(e.asset["linux"], "Mesen_2.2.1_Linux_x64.zip"))
        self.assertEqual([m for m in ("mesen2", "mesen") if m in e.aliases], ["mesen2", "mesen"])
        # Mesen_2.2.1_Windows.zip holds Mesen.exe; Mesen_2.2.1_Linux_x64.zip holds Mesen
        win = self.catalog("windows")["mesen2"]
        self.assertIsNotNone(re.search(win.exe, "Mesen.exe", re.IGNORECASE))
        self.assertIsNotNone(re.search(e.exe, "Mesen", re.IGNORECASE))

    def test_ymirs_launch_target_is_the_program_its_tarball_holds(self):
        e = self.cat["ymir"]
        self.assertEqual(e.repo, "ymir-emu/Ymir")
        self.assertIsNotNone(re.search(e.exe, "ymir-sdl3", re.IGNORECASE))
        self.assertIsNone(re.search(e.exe, "ymir.txt", re.IGNORECASE))

    def test_a_dead_website_is_replaced_by_the_repository_never_by_an_invented_domain(self):
        e = self.cat["flycast"]
        self.assertEqual(e.website, "https://github.com/flyinghead/flycast")
        self.assertNotIn("colorgames", e.website)
        self.assertIn("no longer resolves", e.notes)

    def test_a_corrected_entry_names_the_real_stream_it_installs(self):
        for rid, pattern, real in (
                ("retroarch", "linux", "RetroArch-linux-x86_64.7z"),
                ("duckstation", "linux", "DuckStation-x64.AppImage"),
                ("pcsx2", "linux", "pcsx2-v2.8.2-linux-appimage-x64-Qt.AppImage"),
                ("rpcs3", "linux", "rpcs3-v0.0.43-20607-fb6737b1_linux64.AppImage"),
                ("ppsspp", "linux", "PPSSPP-v1.20.4-anylinux-x86_64.AppImage"),
                ("vita3k", "linux", "Vita3K-x86_64.AppImage"),
                ("dolphin", "linux", "dolphin-2609b-linux-x64.AppImage"),
                ("cemu", "linux", "Cemu-2.6-x86_64.AppImage"),
                ("melonds", "linux", "melonDS-1.1-appimage-x86_64.zip"),
                ("mgba", "linux", "mGBA-0.10.5-appimage-x64.appimage"),
                ("rmg", "linux", "RMG-Portable-Linux64-v0.9.1.AppImage"),
                ("xemu", "linux", "xemu-0.8.139-x86_64.AppImage"),
                ("flycast", "linux", "flycast-x86_64-2.7.AppImage"),
                ("ymir", "linux", "ymir-linux-x86_64-SSE2-v0.4.1.tar.xz"),
                ("snes9x", "linux", "Snes9x-1.63-x86_64.AppImage"),
                ("fbneo", "linux", "linux-sdl2-x86_64.zip"),
                ("dosbox-staging", "linux", "dosbox-staging-linux-x86_64-v0.83.1.tar.xz"),
                ("blastem", "linux", "blastem-linux-x64-1.0.0.tar.gz"),
                ("bigpemu", "linux", "BigPEmu-linux-x64-1.221.tar.gz"),
                ("shadps4", "linux", "shadps4-linux-sdl-0.21.0.zip"),
                ("kytyps5", "linux", "KytyPS5-2026-11-17-faec1f4-Linux-x86_64.tar.gz"),
        ):
            e = self.cat[rid]
            with self.subTest(entry=rid):
                self.assertIsNotNone(re.search(e.asset[pattern], real, re.IGNORECASE), f"{rid} must match {real}")

    def test_every_entry_says_how_linux_gets_it_or_says_honestly_that_it_cannot(self):
        for e in self.cat.values():
            with self.subTest(entry=e.id):
                if e.kind == "tool":
                    self.assertTrue(e.notes)
                    continue
                if "linux" not in e.platforms:
                    # nothing exists for Linux at all, and the entry says so rather than offering a dead button
                    self.assertEqual(e.id, "bluestacks")
                    self.assertIn("Linux", e.notes)
                    continue
                if e.status in em.LEGACY_STATUSES:
                    self.assertFalse(e.repo or e.asset.get("linux") or e.flatpak)  # nothing is offered for it
                else:
                    self.assertTrue(em.downloadable(e), f"{e.id} says Linux but cannot be installed there")
                    # and something real has to carry it: a release feed, a Flatpak, a build, or Wine
                    self.assertTrue(e.repo or e.adapter or e.flatpak or e.build or e.wine, f"{e.id} has no route")
                self.assertTrue(e.notes)

    def test_a_retired_project_is_never_replaced_by_another_program(self):
        self.assertFalse(self.cat["sudachi"].repo)
        self.assertFalse(self.cat["sudachi"].website)
        self.assertEqual(self.cat["lime3ds"].replaced_by, "azahar")
        self.assertEqual(self.cat["sudachi"].status, "discontinued")
        self.assertEqual(self.cat["lime3ds"].status, "superseded")

    def test_plain_dosbox_is_not_taken_for_dosbox_staging(self):
        folder = self.tmp / "emus" / "DOSBox"
        folder.mkdir(parents=True)
        (folder / "dosbox.exe").write_bytes(b"MZ")
        found = em.scan_folder(self.tmp / "emus", [self.cat["dosbox-staging"]], "windows")
        self.assertEqual(found, {})

    def test_a_status_change_never_uninstalls_anything_on_disk(self):
        e = self.cat["lime3ds"]
        folder = self.tmp / "emus" / "Lime3DS"
        folder.mkdir(parents=True)
        (folder / "lime3ds.x86_64.AppImage").write_bytes(b"\x7fELF")
        with mock.patch.object(rc, "launch"):
            em.link(self.store, e, folder, "linux")
        self.assertEqual(em.install_options(e, self.store), [])
        self.assertTrue((folder / "lime3ds.x86_64.AppImage").exists())


if __name__ == "__main__":
    unittest.main()
