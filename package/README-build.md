# Building Kord.app

One command, once the interpreter is in place:

```bash
./package/build-mac-app.sh          # → build/Kord-mac.zip
```

## Why the bundle looks the way it does

**A vendored CPython, not the system one.** A Mac may have no Python, or the
wrong one, and a virtualenv is not relocatable — its scripts hardcode absolute
paths, so copying `.venv` to another machine produces something that cannot
start. `python-build-standalone` is built to be moved, and was checked by
moving it and running it from the new path.

```bash
mkdir -p build && cd build
curl -L -o python.tar.gz \
  https://github.com/astral-sh/python-build-standalone/releases/download/20250818/cpython-3.11.13+20250818-aarch64-apple-darwin-install_only.tar.gz
tar xzf python.tar.gz
./python/bin/python3 -m pip install ".[btc,stems]" imageio-ffmpeg
```

**A static ffmpeg.** Homebrew's is linked against `/opt/homebrew/Cellar/...`,
which will not exist on anyone else's Mac, so copying that binary produces one
that cannot run. `imageio-ffmpeg` ships a static arm64 build with no Homebrew
links; the launcher puts it first on `PATH`.

**The separation weights, shipped.** Demucs pulls `htdemucs_6s` from the
HuggingFace hub rather than torch's cache — 52MB — so the bundle carries that
cache and the launcher points `HF_HOME` at it. Without this the first
separation needs a download.

**The backend serves the UI.** There is no Vite in a bundle, so `KORD_UI_DIR`
points the API at the built frontend and everything runs on one port.

**Data lives outside the app**, under `~/Library/Application Support/Kord`, so
replacing the app never deletes someone's library.

## Apple silicon only

The vendored interpreter and ffmpeg are both `aarch64`. An Intel Mac needs the
`x86_64` equivalents of both; nothing else changes.

## Signing

Ad-hoc (`codesign --sign -`), not notarised. Notarising needs a paid Apple
Developer ID. Without it macOS quarantines a downloaded or AirDropped app;
`Install.command` clears that flag, and the README covers the right-click →
Open fallback if someone opens the app directly instead.
