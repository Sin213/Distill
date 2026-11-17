# Linux installs: the AppImage-first policy, and the Nintendo emulators

Two things changed here: the emulator engine now decides *how* to install a project by one catalog-wide rule instead of
entry by entry, and the six Nintendo-family entries that had no Linux plan were given real install and launch support
(or an honest statement of why they cannot have one).

Everything below was checked on **2026-11-17** against the projects' own release APIs. Where something could not be
verified on this machine it says so instead of claiming otherwise.

## 1. The install policy

`distill/emulators.py` picks an install method in this order:

| # | Method | What it means |
|---|--------|---------------|
| 1 | `appimage` | The project's own standalone `.AppImage` |
| 2 | `appimage-archive` | An official `.zip` / `.tar.gz` that holds an AppImage |
| 3 | `flatpak` | A per-user Flatpak from the entry's `flatpak` id |
| 4 | `portable` | A native portable Linux archive (`.tar.gz`, `.zip`, `.7z`, …) |
| 5 | `package` | A `.deb` / `.rpm` the project publishes — **named, never installed by Distill** |
| 6 | `source` | A source build / documented manual setup |

The choice is made per release: the newest release that has anything for this PC wins, and *within* that release the
order above decides. An older AppImage therefore never pins someone to a build the project has moved on from.

Why `package` is not an install method: an immutable host (Bazzite, Silverblue, SteamOS) cannot take a system package
without layering it over the OS, and Distill cannot unpack a `.deb`/`.rpm` anyway. The file is listed on the page
("Also published: … (install it with your package manager)") so the information isn't lost, but the Install button never
points at it. Nothing in the engine runs `dnf`, `rpm-ostree`, `apt` or `zypper`.

Other rules the engine follows:

- **Architecture is read from the file name, never assumed.** `x86_64`, `x86-64`, `amd64`, `x64`, `arm64`, `aarch64` and a
  bare `arm` are all recognised; a 32-bit build (`i686`, `armv7`, …) is never chosen. A file that names no CPU at all is
  taken as an x86_64 build, which is what an unnamed Linux binary almost always is, so an aarch64 machine is told there
  is no build instead of being handed a binary it cannot run.
- **AppImages are executable and are the launch target.** Downloads land in the app's own folder, are renamed into place
  by a merge (never a wholesale replace), get `chmod +x`, and are recorded as what Launch starts.
- **An AppImage inside an archive works.** `.zip`/`.tar.gz` downloads are unpacked, a lone top-level folder is peeled,
  and an `.AppImage` found anywhere in the result is preferred as the file to run — including when a plain binary sits
  beside it.
- **FUSE 2 is not required.** Fedora 41+ (and so Bazzite/Silverblue) no longer ships `libfuse.so.2`. When it is missing,
  the launch sets `APPIMAGE_EXTRACT_AND_RUN=1` — the AppImage runtime's own self-extract mode — so no package has to be
  layered. This is the one place the engine adds an environment variable, and it is handed to `subprocess.Popen`, so
  `hostenv.py` still strips the frozen bundle's `LD_LIBRARY_PATH`/`QT_PLUGIN_PATH` from the child exactly as before.
- **Updates never touch user data.** Install folders live under the XDG data directory (`paths.data_dir()/recomps/...`)
  or the person's chosen Emulators folder; the emulator's own settings and saves live in its own XDG directories and are
  never part of a download. An update merges new files over old ones of the same name and deletes only the previous
  AppImage it installed itself. A test asserts a save and a settings file survive an update and that nothing is written
  into `paths.config_dir()`.
- **Errors are sentences, not silence.** "No Linux build for arm64 in its recent releases. The Linux files it publishes
  are for another CPU (`azahar.AppImage`). …" or "… has no Linux build in its recent releases. Use <site> to install it by
  hand, or "I already have it..." if you already have it."
- **Alternatives are offered, not hidden.** `emulators.install_options()` returns every method the project offers for
  this PC, best first; `emulators.check()` returns the preferred one and the list from a single lookup. The emulator page
  shows a chooser when there is more than one (Eglantine and Lichii, for instance, offer a plain AppImage, a PGO
  AppImage and a `.tar.gz`), and the Install button uses whichever was picked.

### How an entry says all this

The existing nested `"linux": {...}` block is unchanged in shape; the fields it already had now feed the policy:

```json
"linux": {
  "trusted_owner": "azahar-emu",              // downloads only from this owner's GitHub releases
  "download_hosts": ["git.ryujinx.app"],     // …or only from these hosts, for a project that isn't on GitHub
  "asset": {"linux-x64": "^azahar\\.AppImage$"},  // optional: narrow the files considered (per CPU or for all Linux)
  "exe": "(^|/)azahar[^/]*\\.AppImage$",     // what to run once it is unpacked
  "notes": "…"                               // what the page tells the person about Linux
}
```

`asset` is a *filter* when present, not the whole decision: within it the preference order still applies, which is why
Lichii and Eglantine need no patterns at all and only Azahar (whose AppImage has no version or CPU in its name) pins one.

New top-level fields for projects that are no longer maintained:

```json
"status": "superseded" | "discontinued" | "experimental",
"replaced_by": "azahar"
```

A `superseded`/`discontinued` entry is never downloadable and never fetches a release listing, but **a copy the person
already has still launches**, and the page's main button becomes "Open Azahar" when there is a replacement. An
`experimental` entry installs and updates normally; the status is there so the page can say the builds are not stable.

## 2. The Nintendo entries

### Azahar — 3DS — `azahar-emu/azahar`

- **Verified live (2026-11-17):** `GET /repos/azahar-emu/azahar/releases/latest` → `2126.2` (published 2026-10-08) with
  `azahar.AppImage`, **103,684,600 B**. The newest releases are `2127.0-rc3`, `-rc2`, `-rc1`, `alpha4`… and every one of
  them is flagged `prerelease: true`, which is why the stable line is still `2126.2`. The only Linux assets are
  `azahar.AppImage` (x86_64 — no aarch64 Linux build is published) and `azahar-libretro-linux-x86_64-<tag>.zip`.
- **Implemented:** `linux` block with `trusted_owner: azahar-emu` and `asset: {"linux-x64": "^azahar\\.AppImage$"}`, so the
  libretro core zip and the Windows/macOS files can never be picked. Version discovery is dynamic — the entry contains no
  version string at all, and a test changes the recorded listing's tag to prove the entry follows the API rather than a
  constant. `exe` matches `azahar.AppImage`.
- **Verified by test:** against the recorded listing, `2126.2` is chosen over the newer 2127.0-rc3 (stable beats
  pre-release) and the asset resolves to `azahar.AppImage` at exactly 103,684,600 B; the real file name is what
  `locate_exe` returns; on an arm64 machine the message names the file and the site.
- **Not verified:** no download or execution of the real 135 MB AppImage (forbidden on this host, and it would be running
  a third-party binary). Install mechanics are proven with archives built in the test.

### Lime3DS — 3DS — superseded by Azahar

- **Verified live (2026-11-17):** `https://github.com/Lime3DS/Lime3DS` answers **301 → https://github.com/azahar-emu/azahar**,
  and the API redirect lands on repository id 767183985, which is Azahar's. There is no Lime3DS repository left.
  `https://lime3ds.github.io/` still returns 200 with the old marketing text (no discontinuation notice), so it is a
  stale page, not a source of builds.
- **Implemented:** `status: "superseded"`, `replaced_by: "azahar"`, the `repo` removed entirely (pointing at it would
  download **Azahar's** binary under the Lime3DS name — the one thing that must never happen), and an `exe` pattern that
  still finds an existing Lime3DS install. The page shows "Superseded", explains what happened, and its main button opens
  Azahar.
- **Verified by test:** no install options, no release lookup, `latest_for` explains the status, an installer call refuses
  with nothing downloaded (a download attempt would raise), and a linked `lime3ds.AppImage` still launches.
- **Not verified:** nothing about a Lime3DS build itself — there is none to check.

### Eglantine — Switch / Switch 2 — `Eglantine-Community/Eglantine`

- **Verified live (2026-11-17):** repository description "VERY experimental Nintendo Switch 2 emulator", default branch
  `nx2`. `v0.1.0-rc4` is the newest release with `prerelease: false` — an **rc whose GitHub flag says stable** — while
  `daily-20261117` is a proper pre-release. Assets: `eglantine-linux-x86_64.AppImage` (72,649,208 B),
  `…-pgo.AppImage`, `…aarch64.AppImage`, `…aarch64-pgo.AppImage`, and the four `.tar.gz` counterparts. The catalog pointed
  at `Djihads80/Eglantine`, which now redirects to `Eglantine-Community/Eglantine`; the entry names the canonical one.
- **Implemented:** `status: "experimental"`, `trusted_owner: Eglantine-Community`, a `linux` block with the launch
  pattern and Linux notes that say plainly it is a VERY experimental emulator whose newest tag is a release candidate.
  No `asset` pattern is needed: the file names say their CPU, so the policy picks x86_64 or aarch64 correctly and offers
  the PGO build and the `.tar.gz` as alternatives.
- **Verified by test:** against the recorded listing the preferred choice is `v0.1.0-rc4` /
  `eglantine-linux-x86_64.AppImage`, alternatives are the PGO AppImage then the archives, the aarch64 listing yields the
  aarch64 files on an arm64 machine, and the entry is marked experimental.
- **Not verified:** the build itself (see Azahar).

### Lichii — Switch / Switch 2 — `zortos293/Lichii`

- **Verified live (2026-11-17):** `build-316` (published 2026-11-16, `prerelease: false`) with
  `lichii-linux-x86_64.AppImage` (128,543,224 B), `…-pgo.AppImage`, `aarch64` variants and the `.tar.gz` set. The
  repository is **not** a GitHub fork of Eglantine (`fork: false`, no parent) and its description is identical:
  "VERY experimental Nintendo Switch 2 emulator". Two separate projects, two separate sets of `lichii-*` / `eglantine-*`
  builds.
- **Implemented:** `status: "experimental"`, a `linux` block with the Lichii launch pattern, and Linux notes that name the
  relationship to Eglantine without conflating them.
- **Bug fixed:** the entry's `exe` was `(^|/)(lichii|eglantine)(\\.exe)?$`, which matched an *Eglantine* file and could
  register an Eglantine install as Lichii. It is now `(^|/)lichii(\\.exe)?$` (and the Linux block adds the `.AppImage`
  form). Eglantine got its own pattern in the same change.
- **Verified by test (regression):** an `Eglantine/` folder holding `eglantine-linux-x86_64.AppImage` is found as
  Eglantine and not as Lichii, and the other way round; `locate_exe` with Lichii's entry returns nothing for a folder that
  only holds `eglantine` / `eglantine-…AppImage`; and each entry's pattern mentions only its own name.
- **Not verified:** the build itself.

### Ryujinx / Ryubing — Switch — `projects/Ryubing` on `git.ryujinx.app`

- **Verified live (2026-11-17):** the Forgejo API `https://git.ryujinx.app/api/v1/repos/projects/Ryubing/releases` returns
  `1.3.3` with `ryujinx-1.3.3-x64.AppImage` (31,894,008 B), `ryujinx-1.3.3-arm64.AppImage`,
  `ryujinx-1.3.3-linux_x64.tar.gz`, `ryujinx-1.3.3-linux_arm64.tar.gz`, plus macOS and Windows assets. The original
  `Ryujinx/Ryujinx` on GitHub answers **404** — the maintained project is this fork, and Windows/macOS/Linux all come
  from the Forgejo host, not GitHub.
- **Implemented:** a `linux` block with `download_hosts: ["git.ryujinx.app"]` and a launch pattern that matches both the
  AppImage and the `Ryujinx` binary inside the `.tar.gz`. The release path goes through the existing Forgejo adapter
  (`source: forgejo`), and the older `exe` (`…|\\.app$`) could not have matched `ryujinx-1.3.3-x64.AppImage`, so the Linux
  entry needed its own.
- **Verified by test:** with the recorded Forgejo answer, `fetch_releases` is driven through the `/api/v1/...` endpoint on
  `git.ryujinx.app`, the preferred asset is `ryujinx-1.3.3-x64.AppImage` (arm64 on an arm64 machine) with the matching
  `.tar.gz` as the alternative, and the AppImage name is what `locate_exe` returns.
- **Not verified / worth knowing:** Forgejo publishes no digest for these assets, so a Ryubing download is checked by size
  only (`sha256_of` finds nothing to compare). That is the project's own metadata, not a Distill setting; the entry's
  Linux notes say so.
- **Nightly channel:** `channel_repos` still points at `Ryubing/Canary` on the same host; it was not re-verified beyond the
  stable listing.

### Sudachi — Switch — discontinued

- **Verified live (2026-11-17):** `api.github.com/repos/sudachi-emu/sudachi` → **404**, and the old site
  `https://sudachi.emuplace.app/` fails TLS (`unable to get local issuer certificate`). There is no official repository or
  site left.
- **Implemented:** `status: "discontinued"`, `repo` and `website` removed (no fork, mirror or re-upload is named anywhere),
  notes that explain the status and say an existing install keeps working, and a launch pattern for an existing copy.
  Automatic download is off: no options, no release lookup, and the installer refuses.
- **Verified by test:** nothing installs, `latest_for` explains it, and a linked `sudachi.AppImage` still launches.
- **Not verified:** there is nothing left to verify.

### The PlayStation entries and the rest of the catalog

The same policy and the same entry shape carry three further cases, and the auditor's corrections to the other 30
entries:

- **AnyPS5** is not an emulator but a porting toolchain. Its entry is `"kind": "tool"`: nothing is installed or started
  from its page, which instead explains the relinker, its per-system setup, its dependencies and its command lines, and
  points at Settings > Tools where Distill already installs it.
- **KytyPS5** launches `kyty_launcher` (the graphical launcher), which is what the published archive actually contains —
  not `kyty_emulator`, and not a `kytyps5` file that does not exist.
- **shadPS4** takes a nested `"extras": [...]` entry for its optional Qt launcher: an extra installs into its own folder,
  is found by a scan, and is preferred as the launch target when installed, while the emulator's own command-line
  program stays one call away. The extra is marked `prerelease_only`, because GitHub calls no release "latest" in a
  repository whose releases are all pre-releases (`/releases/latest` answers 404) — `recomps.latest_release()` answers
  that from the release list instead of reporting "no releases".

`CATALOG-CHANGES.md` (repository root) is the per-entry record: what changed, the URL and date behind each change, the
three places the audit itself was wrong (MAME has no Linux binary — `mame0289lx.zip` is XML; Ymir's program is
`ymir-sdl3`; BigPEmu's is `bigpemu`), and what could not be verified.

## 3. Tests

- Before this change: **1867 tests, OK (skipped=1)** — command:
  `QT_QPA_PLATFORM=offscreen ../.venv-1.5.0/bin/python tests/ci_unittest.py --timeout 900 -- ../.venv-1.5.0/bin/python -m unittest discover -s tests -t .`
- After: **1920 tests, OK (skipped=1)** with the same command — 53 added (51 in `tests/test_install_policy.py`, 2 in
  `tests/test_ui_smoke.py`).
- After the PlayStation and catalog-correction card: **1956 tests, OK (skipped=1)** with the same command — 36 more (34
  in `tests/test_playstation_and_audit.py`, 2 in `tests/test_ui_smoke.py`). See `CATALOG-CHANGES.md`.

New coverage lives in `tests/test_install_policy.py` (the order, architecture, AppImage-in-archive installs, the FUSE
fallback, the six entries against the recorded API answers, the Lichii/Eglantine regression) and in `tests/test_ui_smoke.py`
(the install-method chooser actually drives the Install button; a superseded entry sends the person to its replacement).

`tests/fixtures/releases/*.json` are trimmed copies of the real API answers fetched on 2026-11-17: file names, sizes,
addresses and digests are exactly what the projects publish; only the release-note bodies are shortened. No test downloads
or runs a third-party binary — install mechanics use archives built inside the test with a stub HTTP response.

## 4. What a reviewer should look at

1. `_plan`/`_release_options` in `distill/emulators.py` — the newest release with a usable file wins, then the order.
2. `_method_here` — OS and CPU filtering, and the rule that an unnamed binary counts as x86_64.
3. `EmulatorInstaller.install` — routing now comes from the chosen asset's `method`, and an asset with no method keeps the
   old behaviour (cached listings from before this change still install).
4. `appimage_env` + `recomps.launch(env=…)` — the only new environment variable, still funnelled through `subprocess.Popen`
   so `hostenv.py` keeps working. `hostenv.py` and `paths.py` are unchanged.
5. The two `status` values in the catalog — nothing is downloaded for them, and nothing on disk is deleted.
