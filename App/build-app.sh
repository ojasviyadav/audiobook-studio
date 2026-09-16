#!/bin/zsh
set -euo pipefail
repo="${0:A:h:h}"
cd "$repo"
nice -n 15 swift build -c release -j 1
bundle="$repo/Audiobook Studio.app"
mkdir -p "$bundle/Contents/MacOS" "$bundle/Contents/Resources/Voice Samples"
cp .build/release/AudiobookStudio "$bundle/Contents/MacOS/AudiobookStudio"
cp App/Info.plist "$bundle/Contents/Info.plist"
cp App/Resources/AppIcon.icns App/Resources/AppIcon.png "$bundle/Contents/Resources/"
samples="$repo:h/Audiobooks/Emotional Design/Kokoro samples"
for voice in Heart Bella Michael; do
  if [[ -f "$samples/$voice.mp3" ]]; then
    cp "$samples/$voice.mp3" "$bundle/Contents/Resources/Voice Samples/"
  fi
done
codesign --force --sign - "$bundle"
print "Built $bundle"
