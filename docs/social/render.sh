#!/bin/sh
# Renders banner.html to upload-ready PNGs. Needs Google Chrome and network access for fonts.
cd "$(dirname "$0")" || exit 1
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
shot() { # name width height [theme]
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2 \
    --window-size="$2,$3" --virtual-time-budget=8000 --screenshot="$PWD/$1@2x.png" \
    "file://$PWD/banner.html?w=$2&h=$3&theme=${4:-dark}" >/dev/null 2>&1
  sips -z "$3" "$2" "$1@2x.png" --out "$1.png" >/dev/null
  rm -f "$1@2x.png"
}
shot healthsurface-linkedin-1584x396 1584 396
shot healthsurface-x-1500x500 1500 500
shot healthsurface-linkedin-light-1584x396 1584 396 light
shot healthsurface-x-light-1500x500 1500 500 light
shot healthsurface-linkedin-paper-1584x396 1584 396 paper
shot healthsurface-x-paper-1500x500 1500 500 paper

# LinkedIn company page cover: laid out at 1200x200, exported at 3.5x (4200x700) with no resize.
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=3.5 \
  --window-size=1200,200 --virtual-time-budget=8000 \
  --screenshot="$PWD/healthsurface-linkedin-company-4200x700.png" \
  "file://$PWD/banner.html?w=1200&h=200&theme=dark" >/dev/null 2>&1
