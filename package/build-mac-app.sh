#!/usr/bin/env bash
# Build Kord.app — a double-clickable macOS app with nothing to install.
#
# Everything Kord needs is inside the bundle: a relocatable CPython (the
# system one cannot be assumed), every Python dependency including torch and
# demucs, a static ffmpeg (Homebrew's is linked against /opt/homebrew and
# would not exist on another Mac), the separation weights, and the built UI.
# The result runs on a Mac that has never seen Python.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
BUILD="$ROOT/build"
APP="$BUILD/Kord.app"
RES="$APP/Contents/Resources"

[ -d "$BUILD/python" ] || { echo "Missing $BUILD/python — see package/README-build.md" >&2; exit 1; }
command -v swiftc >/dev/null || { echo "Missing swiftc — install Xcode Command Line Tools (xcode-select --install)" >&2; exit 1; }

echo "==> building the frontend"
(cd frontend && npm run build >/dev/null)

echo "==> laying out the bundle"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$RES/bin" "$RES/ui" "$RES/models" "$RES/hf"

# The interpreter and every dependency. Copied rather than linked so the
# bundle is self-contained on a machine that has none of this.
cp -R "$BUILD/python" "$RES/python"
cp -R "$ROOT/frontend/dist/." "$RES/ui/"

# ffmpeg: imageio-ffmpeg ships a static arm64 build with no Homebrew links.
FF=$("$RES/python/bin/python3" -c 'import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())')
cp "$FF" "$RES/bin/ffmpeg"
chmod +x "$RES/bin/ffmpeg"

# Chord weights, and the separation weights demucs pulls from HuggingFace.
[ -f "$HOME/.kord/models/btc_model_large_voca.pt" ] \
  && cp "$HOME/.kord/models/btc_model_large_voca.pt" "$RES/models/" \
  || echo "    (no BTC weights found — chords will fall back to the chroma engine)"
[ -d "$HOME/.cache/huggingface/hub" ] \
  && cp -R "$HOME/.cache/huggingface/hub" "$RES/hf/hub" \
  || echo "    (no demucs weights cached — first separation will download them)"

cp "$ROOT/package/Info.plist" "$APP/Contents/Info.plist"

echo "==> compiling the app shell"
# Kord's executable is a real Cocoa app that owns a window, not a script that
# shells out to `open`. Compiled here rather than shipped as a binary in the
# repo, and targeted at the oldest macOS the bundle claims to support so it
# runs on a Mac older than this build machine.
swiftc -O -target arm64-apple-macosx12.0 \
  -o "$APP/Contents/MacOS/Kord" "$ROOT/package/Kord.swift"
[ -f "$ROOT/package/kord.icns" ] && cp "$ROOT/package/kord.icns" "$RES/kord.icns" || true

echo "==> signing (ad-hoc)"
# Ad-hoc, not notarised: notarising needs a paid Apple Developer ID. Without
# it macOS still quarantines a downloaded app, which is what the README's
# right-click-Open instruction is for. Ad-hoc signing at least stops the
# harsher "is damaged" refusal on Apple silicon.
codesign --force --deep --sign - "$APP" 2>/dev/null || echo "    (codesign unavailable, continuing)"

echo "==> zipping"
# The zip holds a folder, not a bare app: the person unzipping needs the
# installer and the instructions sitting next to it, not just an app icon
# they are then expected to know what to do with.
OUT="$BUILD/Kord"
rm -rf "$OUT" "$BUILD/Kord-mac.zip"
mkdir -p "$OUT"
mv "$APP" "$OUT/Kord.app"
cp "$ROOT/package/Install.command" "$OUT/Install.command"
cp "$ROOT/package/README.txt" "$OUT/README.txt"
chmod +x "$OUT/Install.command"
(cd "$BUILD" && ditto -c -k --sequesterRsrc --keepParent Kord Kord-mac.zip)
echo "built: $BUILD/Kord-mac.zip  ($(du -h "$BUILD/Kord-mac.zip" | cut -f1))"
echo "contains: Kord.app, Install.command, README.txt"
