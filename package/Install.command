#!/bin/bash
# Double-click this to install Kord.
cd "$(dirname "$0")"
clear
echo "Installing Kord..."
echo

if [ ! -d "Kord.app" ]; then
  echo "Kord.app isn't next to this file."
  echo "Unzip the whole download first, then double-click Install again."
  echo; read -p "Press return to close."; exit 1
fi

# macOS quarantines anything downloaded or AirDropped and refuses to open it.
# Clearing that flag here is what turns "Kord is damaged" into an app that
# just opens. It only ever touches this folder.
echo "  Clearing the download quarantine..."
xattr -dr com.apple.quarantine Kord.app 2>/dev/null || true

echo "  Moving Kord to your Applications folder..."
rm -rf "/Applications/Kord.app" 2>/dev/null
cp -R Kord.app /Applications/ || {
  echo
  echo "Couldn't copy into Applications. Drag Kord.app there yourself, then"
  echo "run this again."
  echo; read -p "Press return to close."; exit 1
}

echo "  Starting Kord..."
open -a /Applications/Kord.app
echo
echo "Done. Kord is in your Applications folder and should open in your"
echo "browser in a few seconds. From now on, just open it from Applications"
echo "or Spotlight."
echo
read -p "Press return to close."
