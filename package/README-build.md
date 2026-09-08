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
links; the app puts it first on `PATH`.

**The separation weights, shipped.** Demucs pulls `htdemucs_6s` from the
HuggingFace hub rather than torch's cache — 52MB — so the bundle carries that
cache and the app points `HF_HOME` at it. Without this the first
separation needs a download.

**The backend serves the UI.** There is no Vite in a bundle, so `KORD_UI_DIR`
points the API at the built frontend and everything runs on one port.

**A Cocoa shell, not a shell script.** `package/Kord.swift` compiles to the
bundle's executable: it starts uvicorn and the worker as its own children,
waits for `/api/health`, and hosts the UI in a `WKWebView`. This replaced a
script that called `open` on a URL — which gave the user a browser tab rather
than an app, and left the server running after that tab was closed. Building
it needs the Xcode Command Line Tools (`xcode-select --install`) on the build
machine only; the compiled binary has no such dependency.

**A port chosen at launch.** The old script hardcoded 8000, so anything else
already on that port produced an app that opened to nothing. The shell binds
port 0 to find a free one and passes it to uvicorn.

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
