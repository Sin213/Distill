# Catalog changes: the PlayStation entries and the auditor's corrections

**Date:** 2026-11-17 · **Branch:** `linux/upstream-pr-prep` · **Manifest:** `distill/assets/emulators.json` v1.2 → v1.3

**Scope.** Every entry in the bundled catalog either installs and launches what its project actually publishes on
Linux, or says in the UI why it cannot. The six Nintendo entries were finished by the previous card
(see `LINUX-EMULATORS.md` §2) and are not repeated here. This file is the per-entry record the card asked for: what
changed, on what evidence, and what could not be verified.

**How "verified" is used here.** A fact is *verified live* when it was read from the project's own release page, its
own release API, its own site, or its own archive **on 2026-11-17**. No archive was executed. Archives were downloaded
and **listed** (`tar -t`, `unzip -l`) to find what they really contain — that is how the launch targets below were
settled. Where a fact could not be established it says so rather than guessing.

**Kept and tested (no change needed):** `bluestacks` (notes only), `scummvm` (a launch pattern was missing; the Linux
route — Flathub — was already right), `ares` (source build was right; a Flathub alternative was added), `project64`
(the 2021 build is genuinely the newest; notes only).

---

## Part 1 — the PlayStation entries

### `anyps5` — AnyPS5: not an emulator, and no longer presented as one

- **What changed.** The entry is now `"kind": "tool"`: it can never be installed as an emulator, never launched, never
  scanned for, and it no longer carries a fake or empty install button. Its page instead carries real links
  (`https://github.com/boykopovar/AnyPS5`, `https://boykopovar.github.io/AnyPS5/`) and the content a person needs:
  what the tool does, how that differs from an emulator, setup notes per system (`setup.linux`, `setup.windows`,
  `setup.macos`), its dependencies (an already extracted and decrypted ELF; AVX2/FMA/F16C/BMI1/BMI2/LZCNT/MOVBE on
  the host CPU), the command lines it is run with (`usage`), and its relationship to the relinker Distill already
  ships (`tool_key: "relinker"` → `distill/tools.py` `AnyPS5Manager`). The wrong `notes` ("A conceptual repository
  targeting native-port layering"), the stale `active: false` and the unconfirmed-source `verify` flag are gone.
- **Evidence (2026-11-17).** `github.com/boykopovar/AnyPS5` README: *"Tool for automatic executables porting to Linux
  and Windows. The relinker-only build runs on macOS, including Apple silicon."* … *"Includes a relinker (core/relinker)
  that converts executable to the target system's native format and implementations of system prx libraries … No
  emulation or separate runtime process."* `docs/user/USAGE.md`: `relinker [options] <input.elf> <output>`,
  `relinker --windows source/input.elf app.exe`, `--dry-run`, the CPU-extension requirement and the security note.
  `releases.atom` newest tag `v0.1.5` (2026-11-11); `releases/expanded_assets/v0.1.5` lists `relinker-v0.1.5`,
  `relinker-v0.1.5.exe`, `prx-linux-v0.1.5.*`, `prx-windows-v0.1.5.*`, `prx-headers-v0.1.5.*`, `web-v0.1.5.zip` — a
  porting toolchain, no emulator payload. `distill/tools.py:1052` `AnyPS5Manager` already installs `relinker` +
  `prx-linux`/`prx-windows` from one release on both Linux and Windows.
- **Automatic install.** Genuinely supported, by the official project, and already implemented — under
  **Settings → Tools → AnyPS5 relinker**, which the page links to (`Open Settings > Tools`) rather than duplicating.
  Nothing is installed from the emulator page, and no button there pretends otherwise.
- **Verified by test.**
  `tests/test_playstation_and_audit.py::AnyPS5Tests` (6 tests) and
  `tests/test_ui_smoke.py::test_the_anyps5_page_explains_a_tool_and_offers_no_emulator_install`: no install options, no
  launch, `status_text` = "Tool, not an emulator", the installer refuses before any download, a scan never links it, the
  page renders the setup/needs/usage text and hides the install and release-notes cards.
- **Could not verify.** That the Linux `relinker-v0.1.5` binary actually runs (it would be executing a third-party
  binary, which this card forbids); which distribution libraries, if any, the Linux relinker needs beyond glibc (the
  release page does not say). Distill's own tool manager downloads and runs it with `--help` as its probe, which is the
  project's supported path.

### `kytyps5` — KytyPS5: the graphical launcher is the launch target

- **What changed.** `exe` is now `kyty_launcher` (`(^|/)kyty_launcher(\.exe)?$`; `(^|/)kyty_launcher$` on Linux), not
  the emulator binary and not a name that does not exist. A Linux route was added
  (`KytyPS5-.*-Linux-x86_64\.tar\.gz$`), `platforms` and `channels: ["nightly"]`, notes rewritten to PlayStation 5 only
  (the old text claimed PS4 and PS5), and the unconfirmed-source `verify` flag dropped.
- **Evidence (2026-11-17).** Release `KytyPS5-2026-11-17-faec1f4`. Listing
  `KytyPS5-2026-11-17-faec1f4-Linux-x86_64.tar.gz` (42,251,463 B) shows `./kyty_launcher` (5,407,056 B, mode
  `-rwxr-xr-x`), `./kyty_emulator` (23,111,800 B), `./kyty_updater`, `./lib/` (the Qt 6 libraries), `./plugins/`
  (`platforms/libqxcb.so`, `libqwayland.so`, …), `./assets/` and `./qt.conf` — a Qt GUI launcher. Listing
  `KytyPS5-2026-11-17-faec1f4-Windows-x64.zip` (26,982,913 B) shows `kyty_launcher.exe` (5,588,480 B) beside
  `kyty_emulator.exe` (27,414,528 B) and `kyty_updater.exe`. **No file called `kytyps5` exists in either archive**, and
  the previous entry had no exe pattern at all, so the generic picker chose the largest matching file — the emulator
  binary. That is the "installs, launch fails" symptom.
- **Executable permissions.** Verified in behaviour, not assumed: Python's `tarfile` extraction with the `data` filter
  keeps `kyty_launcher` at `-rwxr-xr-x`, and `recomps.Installer.install` additionally chmods the registered executable
  (`exe.chmod(mode | 0o111)`) — proved by a test that unpacks a tar whose members carry no execute bit at all.
- **Which of the two is the window.** Read statically from the binaries (not executed): `file` reports both as
  `ELF 64-bit LSB pie executable, x86-64`; `readelf -d` shows `kyty_launcher` linking **`libQt6Widgets.so.6`,
  `libQt6Gui.so.6`, `libQt6Core.so.6`, `libQt6DBus.so.6`, `libGLX.so.0`, `libOpenGL.so.0`** with `RPATH [$ORIGIN/lib]`,
  and the archive ships the platform plugins that make a window possible (`plugins/platforms/libqxcb.so`,
  `libqwayland.so`, `libqoffscreen.so`, `qt.conf`). `kyty_emulator` links **no GUI toolkit at all** — only
  `libm`, `libstdc++`, `libgcc_s` and `libc` — so starting it can never open the launcher window, which is exactly the
  symptom the card describes.
- **Verified by test.** `KytyPS5Tests` (5 tests): the launch target is `kyty_launcher` and not `kyty_emulator` or
  `kyty_updater` on Linux; the Windows target is `kyty_launcher.exe`; the recorded release resolves to the official
  Linux tarball as a portable archive; an install from that layout lands on `kyty_launcher` and is made executable.
- **Windows.** Reviewed: the Windows archive contains `kyty_launcher.exe`, and the catalog now names it. **Could not be
  verified on a Windows host** — there is none here, and running the binary is forbidden — so "the Windows launcher
  opens" is *not* claimed. What is verified is that the file exists in the published archive with that exact name.
- **Could not verify.** That `kyty_launcher` opens a window on this host: launching a downloaded third-party binary is
  forbidden by the card. What is established is that it is a Qt 6 Widgets GUI program (see above), that the archive
  carries the Qt platform plugins and libraries it needs, and that Distill's launch path passes it to the system
  unchanged. The project's runtime dependencies beyond what it bundles were not audited.

### `shadps4` — shadPS4: the CLI emulator, plus an optional Qt launcher

- **What changed.** The emulator entry gained its Linux route (`shadps4-linux-sdl-[0-9.]+\.zip$`), a launch pattern
  (`(^|/)Shadps4[^/]*\.AppImage$|(^|/)shadps4(\.exe)?$`), and notes explaining the launcher relationship. A new
  **nested** `extras` entry `shadps4-qtlauncher` carries the launcher: `repo: shadps4-emu/shadps4-qtlauncher`,
  `prerelease_only: true`, `preferred_launch: true`, `status: "experimental"`, and its own `.zip` patterns per OS.
- **Why nested, not a 37th entry.** The manifest still holds 36 emulators (the self-test counts them), an extra can
  never appear as its own tile, and it can never be downloaded twice under two names — the `lime3ds`/`azahar`
  duplicate-entry bug the audit found is exactly what a second top-level row would have reintroduced.
- **Evidence (2026-11-17).** `releases?per_page=15` for `shadps4-emu/shadPS4`: the newest entry is
  `Pre-release-shadPS4-2026-11-17-9ac8b23…` (`prerelease: true`), the newest stable is `v.0.21.0` — the leading dot is
  the project's own. Listing `shadps4-linux-sdl-0.21.0.zip` (33,362,189 B) shows **one file**,
  `Shadps4-sdl.AppImage` (33,851,896 B): the Linux zip *is* an AppImage payload, there is no separate `.AppImage`
  asset, and none is promised. `shadps4-emu/shadps4-qtlauncher`: exactly one release, tag
  `shadPS4QtLauncher-2026-11-06-ecc85072dae45c05628934fdb6b3aa036e9f1d4b`, **`prerelease: true`**, assets
  `shadPS4QtLauncher-linux-qt-2026-11-06-ecc8507.zip`, `…-macos-qt-…zip`, `…-win64-qt-…zip` — **no `.AppImage` asset**.
  Listing the Linux zip (58,611,977 B) shows one file, `shadPS4QtLauncher-qt.AppImage` (59,243,000 B): a zip whose
  payload is an AppImage. README: *"QtLauncher is the official launcher for shadPS4. It was separated from the main
  repository and is now in development here."*
- **Pre-release-only release API.** `GET /repos/shadps4-emu/shadps4-qtlauncher/releases/latest` answers **404** (GitHub
  only calls a release "latest" when it is not a pre-release); `https://github.com/.../releases/latest` redirects to
  `/releases`, not to a tag. `recomps.latest_release()` now asks that endpoint and, on 404, answers from the release
  list, so a pre-release-only project is never reported as "no releases"; a repository with genuinely no release still
  returns `None`. The entry is looked up through the release list as well (`em.prerelease_only` puts the newest release,
  pre-release included, first), and its version label ends in "(pre-release)".
- **Behaviour.** The extra installs on its own into a folder of its own (`Emulators/shadPS4 Qt launcher`), whether or
  not shadPS4 is installed; a scan finds an existing launcher install; **Launch starts the launcher when it is
  installed**; `Launch shadPS4 without the launcher` still starts the emulator's own program, and `em.launch(..., cli=True)`
  is the engine-side equivalent. The page labels it "PRE-RELEASE · EXPERIMENTAL" and explains the relationship.
- **Verified by test.** `ShadPS4Tests` (9 tests) and
  `tests/test_ui_smoke.py::test_the_shadps4_page_offers_its_qt_launcher_as_an_optional_extra`: the stable `v.0.21.0` zip
  is chosen over the rolling pre-release; the zip's AppImage is what gets registered and made executable; the launcher
  is an extra, not a tile; the real launcher archive is what the entry asks for; a pre-release-only listing still
  offers a build; a 404 from `/releases/latest` is answered from the list; a repository with no releases is still
  `None`; the launcher is preferred at launch and `cli=True` bypasses it; a scan finds an existing launcher.
- **Could not verify.** Whether the launcher actually opens against an installed shadPS4, and how it locates the
  emulator (its README and build docs do not say; it is a separate project). Not executed — third-party binary.

---

## Part 2 — the corrections across the rest of the catalog

Ordered as the audit ordered them. "Verified live" facts were re-checked on 2026-11-17 where the audit's wording
mattered; the rest is the audit's own evidence (`audit/CATALOG-AUDIT.md`, `audit/raw/`), which is dated the same day.

### Entries that were factually wrong (9)

| Entry | What changed | Evidence |
| --- | --- | --- |
| `retroarch` | `exe` was `(^|/)retroarch\.exe$\|\.AppImage$`, whose second alternative matched **every** AppImage on the machine. Now `(^|/)retroarch(\.exe)?$`. A Linux block was added: Flathub `org.libretro.RetroArch` (200) plus the official buildbot archive `RetroArch-linux-x86_64.7z`, and notes saying there is no Linux AppImage and no arm64 stable build. | `buildbot.libretro.com/stable/1.22.2/linux/x86_64/`; `flathub.org/api/v2/appstream/org.libretro.RetroArch` = 200; the adapter's own file names (`_libretro()` names them `RetroArch-linux-x86_64.7z`). |
| `anyps5` | See Part 1. |  |
| `sudachi` | Nothing to change: the previous card already made it `discontinued` with no repository and no website. **Not** replaced by any fork — the audit found no official successor, and a mirror is exactly what must not be used. | `api.github.com/repos/emuplace/sudachi.emuplace.app` 404, `sudachi.emuplace.app` TLS failure. |
| `lichii` | Already split from Eglantine by the previous card (`exe` no longer claims `eglantine`). Nothing further this card. | `tests/test_install_policy.py::CrossIdentificationTests`. |
| `mesen2` | `repo` → `nesdev-org/MesenCE`; `name` → **Mesen CE**; aliases keep `mesen2`/`mesen` so an existing folder is still found; Linux block `Mesen_[0-9.]+_Linux_(x64|ARM64)\.zip$`; `exe` `(^|/)Mesen$`. | `api.github.com/repos/SourMesen/Mesen2` → `archived: true`, `pushed_at` 2026-06-04; `api.github.com/repos/nesdev-org/MesenCE` → not archived, pushed 2026-11-15; `mesen.ca` links its downloads to MesenCE; listing `Mesen_2.2.1_Linux_x64.zip` shows the single program **`Mesen`**. |
| `xenia-canary` | `repo` → `xenia-canary/xenia-canary` (the `-releases` repo is a frozen mirror); `platforms` gains linux; Linux asset `xenia_canary_linux(\.tar\.xz\|\.AppImage)$`; `exe` gains the AppImage. | `xenia-canary-releases/releases.atom` newest 2026-02-13 (`9369464`); `xenia-canary/releases.atom` newest 2026-11-17 (`f9431eb`, `5d8f3ec`); the live asset listing has `xenia_canary_linux.AppImage`. |
| `flycast` | `website` → `https://github.com/flyinghead/flycast` (the project has no site of its own; none invented); Linux asset `flycast-x86_64-[0-9.]+\.AppImage$`, Flathub `org.flycast.Flycast` (200), `exe` gains the AppImage. | `getent hosts flycast.colorgames.de` → **NXDOMAIN**; `flycast/releases/tag/v2.7` assets. |
| `mame` | `asset.windows` `64bit\.exe$` matched none of the four real files → `(x64|arm64)\.exe$`. **Linux has no MAME binary**: the audit's `mame0289lx.zip` is *not* one (below), so the Linux route is the Flathub app only and the entry says so. | `mamedev.org/release.html`: the table labels `mame0289lx.zip` "MAME 0.289 full driver information in XML format"; `flathub.org/api/v2/appstream/org.mamedev.MAME` = 200. |
| `lime3ds` | Nothing further: `superseded`/`replaced_by: azahar`/no repo was done by the previous card. | `api.github.com/repos/Lime3DS/Lime3DS` → `full_name: azahar-emu/azahar`. |

### Entries that were stale (5)

| Entry | What changed | Evidence |
| --- | --- | --- |
| `dolphin` | `platforms` gains linux; Linux asset `dolphin-.*-linux-(x64|arm64)\.AppImage$`; `exe` gains `dolphin-emu` and anchors the macOS bundle to `Dolphin.app`. | `dolphin-emu.org/update/latest/beta` lists an artifact `"Linux x64 (AppImage)"` → `dolphin-2609b-x64.AppImage`, which `_dolphin_name()` renames `dolphin-2609b-linux-x64.AppImage`; Flathub `org.DolphinEmu.dolphin-emu` = 200. |
| `ryujinx` | Left to the previous card. |  |
| `eden` | Left to the previous card. |  |
| `eglantine` | Left to the previous card. |  |
| `ymir` | `repo` and `website` → `ymir-emu/Ymir` (the old owner redirects); Linux asset `ymir-linux-.*\.tar\.xz$`; `exe` → `ymir-sdl3` (see the audit corrections below). | `github.com/StrikerX3/ymir` → **301** `https://github.com/ymir-emu/Ymir`; listing `ymir-linux-x86_64-SSE2-v0.4.1.tar.xz` shows the program **`ymir-sdl3`**. |

### Entries missing their Linux data (18)

Each gained a `linux.asset` pattern taken from the file names the project itself publishes, a launch pattern, and a
note stating what Linux gets and what it does not. Patterns are anchored to the real names — a test re-runs every one
against the real file name it was written for.

| Entry | Linux route wired in | Evidence (asset listing) |
| --- | --- | --- |
| `duckstation` | `DuckStation-(x64\|x64-SSE2\|arm64)\.AppImage$`; `exe` fixed (see below). `version_from: published_at` kept, with a note that its tags roll. | `DuckStation-x64.AppImage`, `-x64-SSE2`, `-arm64`, `-armhf` |
| `pcsx2` | `pcsx2-v[0-9.]+-linux-appimage-x64-Qt\.AppImage$` + Flathub `net.pcsx2.PCSX2` (200) | `pcsx2-v2.8.2-linux-appimage-x64-Qt.AppImage` |
| `rpcs3` | `rpcs3-.*_linux64\.AppImage$`; `repo_by_platform` gains the two arm64 repositories the project publishes | `rpcs3-v0.0.43-20607-fb6737b1_linux64.AppImage` |
| `shadps4` | See Part 1 | `shadps4-linux-sdl-0.21.0.zip` |
| `kytyps5` | See Part 1 | `KytyPS5-…-Linux-x86_64.tar.gz` |
| `ppsspp` | `PPSSPP-v[0-9.]+-anylinux-(x86_64\|aarch64)\.AppImage$`; `exe` gains `PPSSPPSDL` and the AppImage | `PPSSPP-v1.20.4-anylinux-x86_64.AppImage` |
| `vita3k` | `Vita3K-(x86_64\|aarch64)\.AppImage$`; `version_from: published_at` kept (the tag is literally `continuous`) | `Vita3K-x86_64.AppImage` |
| `cemu` | `Cemu-[0-9.]+-x86_64\.AppImage$`; notes set the expectation that v2.6 (2025-02-06) is genuinely the newest | `Cemu-2.6-x86_64.AppImage` |
| `azahar`, `eglantine`, `lichii`, `ryujinx` | Previous card |  |
| `melonds` | `melonDS-[0-9.]+-appimage-x86_64\.zip$` (the AppImage is inside a zip) + Flathub `net.kuribo64.melonDS` (200) | `melonDS-1.1-appimage-x86_64.zip` |
| `mgba` | `mGBA-[0-9.]+-appimage-(x64\|arm64)\.appimage$` (lower-case extension) + Flathub `io.mgba.mGBA` (200) | `mGBA-0.10.5-appimage-x64.appimage` |
| `rmg` | `RMG-Portable-Linux64-v[0-9.]+\.AppImage$`; `exe` `RMG` | `RMG-Portable-Linux64-v0.9.1.AppImage` |
| `xemu` | `xemu-[0-9.]+-(x86_64\|aarch64)\.AppImage$` | `xemu-0.8.139-x86_64.AppImage` |
| `bigpemu` | `BigPEmu-linux-(x64\|arm64)-.*\.tar\.gz$` (the adapter's own names); `exe` → `bigpemu` | `BigPEmu_Linux64_v1221.tar.gz` → `bigpemu/bigpemu` |
| `snes9x` | `Snes9x-[0-9.]+-x86_64\.AppImage$`; `website` → `http://www.snes9x.com/` | `Snes9x-1.63-x86_64.AppImage` |
| `fbneo` | `linux-sdl2-x86_64\.zip$`; `version_from: published_at` (the tag is literally `latest`); `channels: ["nightly"]` | `linux-sdl2-x86_64.zip` → `fbneo` |
| `dosbox-staging` | `dosbox-staging-linux-x86_64-v[0-9.]+\.tar\.xz$`; the `dosbox` alias was removed (plain DOSBox is a different program); `website` → `https://www.dosbox-staging.org/`; **no** Flatpak claimed (both plausible ids 404) | `dosbox-staging-linux-x86_64-v0.83.1.tar.xz` → `…/dosbox` |
| `blastem` | `blastem-linux-x64-.*\.tar\.gz$` (the adapter's own names) + Flathub `com.retrodev.blastem` (200); `platforms` gains linux | `blastem64-1.0.0.tar.gz` → `blastem64-1.0.0/blastem` |

`ares` also gained Flathub `dev.ares.ares` as an alternative to compiling (app id 200, homepage `ares-emu.net`,
developer "ares team", licence ISC — the project's own). The source build stays the first route, because the project
publishes no Linux binary.

### The shared regex defect (5 entries, one line each)

`|\\.AppImage$` has no path anchor, so `retroarch`, `duckstation`, `pcsx2`, `rpcs3` and `cemu` each claimed **any**
AppImage on the machine as their own — including `/opt/emulators/Firefox.AppImage`. All five now name their own build.
`tests/test_playstation_and_audit.py::SharedRegexDefectTests` compiles every entry's `exe` from the shipped manifest and
matches three foreign AppImage paths against it, so the defect cannot come back through another entry.

---

## Where the audit itself turned out to be wrong

1. **MAME publishes no Linux binary.** The audit lists `mame0289lx.zip` under "Linux assets" and says *"the Linux
   binary is `mame`"*, and its checklist tells the developer to add `mame[0-9]+lx\.zip$` to a Linux block.
   `mamedev.org/release.html` describes that file as *"MAME 0.289 full driver information in XML format"*, and listing
   it (2026-11-17) shows **one file, `mame0289.xml`, 326,688,140 B** — the driver database, not a program. Adding a
   Linux download on that basis would have given every Linux user a 19.7 MB XML file and an install that fails on the
   first run. The entry now offers Flathub only and says why.
2. **Ymir's program is `ymir-sdl3`, not `ymir`.** The audit's proposed `exe` `(^|/)ymir$` would never have matched the
   installed program. Listing `ymir-linux-x86_64-SSE2-v0.4.1.tar.xz` shows `ymir-sdl3`. The entry matches both names.
3. **BigPEmu's Linux program is `bigpemu`, not `BigPEmu`.** Harmless in practice because the matcher is
   case-insensitive, but the catalog now says what the archive holds (`bigpemu/bigpemu`).
4. **"shadPS4 has no AppImage" needs a qualifier.** True of the *release assets* (there is no `.AppImage` file to
   download), false of the *payload*: `shadps4-linux-sdl-0.21.0.zip` contains exactly one file,
   `Shadps4-sdl.AppImage`. The same is true of the Qt launcher's Linux zip. So the AppImage-first policy still applies
   in substance — Distill unpacks the zip and registers the AppImage inside it — which is why the entries keep the zip
   pattern and no separate AppImage is invented.
5. **KytyPS5's launch target.** The audit proposed `exe` `(^|/)kytyps5$`; no such file exists in either published
   archive (see Part 1). The launcher is `kyty_launcher`.
6. **DuckStation's `version_from` advice was not followed, deliberately.** The audit asks to point the version at the
   newest dated `v0.1-*` tag instead of the rolling `latest`. Verified: `latest`, `preview` and each `v0.1-*` tag carry
   the *identical* asset set, and the rolling tag is the fresher of them (`latest` was re-uploaded after the newest
   dated tag, 2026-10-25). Following the advice would mean shipping month-old builds and never seeing a rolling update.
   Because applying the same rule mechanically would break `fbneo` (whose dated tag is from 2021 while `latest` ships
   nightly), the entry keeps `version_from: published_at` and its `notes` now say that its tags roll and that the date
   is what names a build.

Also noted, not changed: `org.duckstation.DuckStation` resolves 200 on Flathub but the audit could not establish
whether the project publishes it, so it was not added as a route (the audit's own instruction).

---

## Behavioural fixes and where their tests are

| Behaviour | Test |
| --- | --- |
| A tool entry is never installed, launched or scanned for as an emulator | `AnyPS5Tests.test_it_is_carried_as_a_tool_…`, `…_never_linked_as_an_emulator_install`, `…_nothing_about_it_can_be_downloaded_through_the_installer` |
| An entry's optional extra installs on its own, is found by a scan, and is preferred at launch | `ShadPS4Tests.test_an_existing_launcher_install_is_found_by_a_scan`, `…_preferred_as_the_launch_target_when_it_is_installed` |
| A pre-release-only project still offers its build; `/releases/latest` 404 is not "no releases" | `ShadPS4Tests.test_a_project_whose_only_release_is_a_prerelease_still_offers_a_build`, `…_the_latest_lookup_answers_a_404_from_the_release_list`, `…_a_repository_with_no_release_at_all_is_still_none` |
| A launch target matches the real program in the real archive | `KytyPS5Tests` (5), `CatalogCorrectionTests.test_a_corrected_entry_names_the_real_stream_it_installs` |
| No entry claims an unrelated AppImage | `SharedRegexDefectTests` (2) |
| Superseded/discontinued entries keep what is on disk and download nothing | `CatalogCorrectionTests.test_a_status_change_never_uninstalls_anything_on_disk`, `tests/test_install_policy.py::NintendoCatalogTests` |
| MAME offers no Linux download that is not a program | `CatalogCorrectionTests.test_mame_promises_no_linux_download_the_audit_wrongly_thought_existed` |
| Plain DOSBox is not mistaken for DOSBox Staging | `CatalogCorrectionTests.test_plain_dosbox_is_not_taken_for_dosbox_staging` |

## Test counts

| | Tests | Result |
| --- | --- | --- |
| Before this card | 1920 | `OK (skipped=1)` |
| After | 1956 | `OK (skipped=1)` — 36 added: 34 in `tests/test_playstation_and_audit.py`, 2 in `tests/test_ui_smoke.py` |

Command (unchanged from the previous cards):

```
QT_QPA_PLATFORM=offscreen ../.venv-1.5.0/bin/python tests/ci_unittest.py --timeout 1200 -- \
    ../.venv-1.5.0/bin/python -m unittest discover -s tests -t .
```

Two existing tests were updated because the catalog moved, not to make them pass: the list of entries that install on
Linux through Flatpak/a build/Wine gained the six entries that received a Flathub app, and the emurelation test now
exercises the mapping with an entry that has no launch pattern (the catalog names RMG's program `RMG.exe`, so a folder
holding an unrelated `app.exe` is no longer RMG — which is the intended behaviour).

## What could not be verified here

- **No third-party binary was run.** Archives were downloaded and listed only. Every install/launch behaviour is
  proved with archives built inside the tests and with recorded release listings, never by executing a project's file.
- **Windows.** No Windows host exists here. The Windows launch targets that were reviewed are *file names inside the
  published archives* (`kyty_launcher.exe`, `shadps4.exe`, `Mesen.exe`, `RMG.exe`, …), not observed launches. Windows
  code paths are unchanged apart from the catalog's own `exe`/`asset` strings, and the pre-existing Windows tests pass.
- **Two audit entries were re-verified live and are as the audit says:** `xenia-canary` (mirror frozen, live channel
  shipping daily) and `mesen2` (archived, MesenCE active). Everything else here rests on the audit's own cached
  evidence of the same date plus the live checks named in the table above.
- **Flathub provenance** beyond the app id resolving, the app's own homepage and licence: not established for the six
  Flathub ids added here (`org.pcsx2`, `org.libretro`, `net.kuribo64`, `io.mgba`, `org.flycast`, `com.retrodev`,
  `dev.ares`, `org.mamedev`).
- **RMG's portable marker.** The project publishes an explicit "Portable" Linux build; which file or folder makes it
  keep its settings beside the program was not verified, so no `portable` field was invented.
