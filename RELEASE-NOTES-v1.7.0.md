# Distill v1.7.0 — Linux distribution (first Linux release)

This is our first Linux distribution of Distill, built and released from `Sin213/Distill` as an independent downstream release. The official upstream project is [QyuBurt/Distill](https://github.com/QyuBurt/Distill).
Report Linux-specific problems at [Sin213/Distill issues](https://github.com/Sin213/Distill/issues).

## Downloads and installation

Both packages are for x86_64 (amd64) Linux only.

| Package | SHA-256 checksum | Install or run |
| --- | --- | --- |
| `Distill-x86_64.AppImage` | `Distill-x86_64.AppImage.sha256` | `chmod +x Distill-x86_64.AppImage && ./Distill-x86_64.AppImage` |
| `distill_1.7.0_amd64.deb` | `distill_1.7.0_amd64.deb.sha256` | `sudo apt install ./distill_1.7.0_amd64.deb` |

Download the package and its checksum into the same directory. From there, verify your download with the matching command.

```bash
sha256sum -c Distill-x86_64.AppImage.sha256
sha256sum -c distill_1.7.0_amd64.deb.sha256
```

The DEB targets Debian and Ubuntu-family distributions. Its dependencies are
`libc6` (minimum version set at build time), `ca-certificates`, `libegl1`, `libopengl0`, `libxkbcommon0`, `libdbus-1-3`,
`libglib2.0-0t64` or `libglib2.0-0`, `libfontconfig1`, `libfreetype6`, `libpulse0`, `libgl1`, `libx11-6`, `libxkbcommon-x11-0`,
`libxcb-cursor0`, `libxcb-icccm4`, `libxcb-image0`, `libxcb-keysyms1`, `libxcb-randr0`, `libxcb-render-util0`,
`libxcb-shape0`, `libxcb-xkb1`, `libxcb-xinerama0`, `libwayland-client0`, `libwayland-cursor0`, and `libwayland-egl1`.

## Updates

When the in-app update check finds a newer release on Linux, **Open page** takes you to the `Sin213/Distill` release page in your browser. Download and install the update manually.

## Known limits

- Linux uses per-user XDG directories for runtime files. Tool and emulator support varies. Some tools require distribution packages or source builds, and emulators that use Flatpak or Wine require those to be installed first.
- On systems without FUSE, start the AppImage with `APPIMAGE_EXTRACT_AND_RUN=1 ./Distill-x86_64.AppImage`.

## Credits

- **QyuBurt** — original author of upstream Distill.
- **Nikoto28** — the original Linux port that this distribution builds on (native tool downloads, emulator install kinds, the AppImage packaging recipe), plus the Linux emulator install policy, AppImage-first emulator installs, and source-build support for ares and hactoolnet.
- **Zoltun Kulle** — emulator catalog corrections, tool pages, and catalog documentation. The commits list Zoltun Kulle as author and Nikoto28 as committer.
- **Sin213** — Linux distribution integration: XDG runtime directories, test baseline and portability, AppImage startup and child-environment fixes, amd64 DEB packaging, updater routing, and this release.
