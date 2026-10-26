#!/bin/sh
# Builds a Debian/Ubuntu package:  dist/opennovella_<version>_all.deb
#
#   sh packaging/build_deb.sh
#
# Needs dpkg-deb (any Debian/Ubuntu system). If pygame is available the demo's
# artwork is generated and included; otherwise the demo uses placeholders.
#
# OpenNovella - created by Shawn Rapaz and Claude Code.
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
PKG_DIR="$ROOT/packaging/debian"
VERSION=$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$ROOT/opennovella/__init__.py")
NAME=opennovella
STAGE="$ROOT/build/deb/${NAME}_${VERSION}"
OUT="$ROOT/dist/${NAME}_${VERSION}_all.deb"

[ -n "$VERSION" ] || { echo "Could not read __version__ from opennovella/__init__.py" >&2; exit 1; }
command -v dpkg-deb >/dev/null || { echo "dpkg-deb not found - run this on Debian/Ubuntu" >&2; exit 1; }

echo "Building $NAME $VERSION ..."
rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN" \
         "$STAGE/usr/bin" \
         "$STAGE/usr/lib/$NAME/examples" \
         "$STAGE/usr/share/applications" \
         "$STAGE/usr/share/icons/hicolor/scalable/apps" \
         "$STAGE/usr/share/doc/$NAME" \
         "$STAGE/usr/share/man/man1"

# --- the engine (pure Python, so the package is architecture-independent) ---
cp -r "$ROOT/opennovella" "$STAGE/usr/lib/$NAME/"
find "$STAGE/usr/lib/$NAME" -name __pycache__ -prune -exec rm -rf {} +

# --- the demo, with generated artwork when possible ---
mkdir -p "$STAGE/usr/lib/$NAME/examples/demo"
cp "$ROOT/examples/demo/story.json" "$ROOT/examples/demo/make_art.py" "$STAGE/usr/lib/$NAME/examples/demo/"
if python3 -c "import pygame" >/dev/null 2>&1; then
    SDL_VIDEODRIVER=dummy PYGAME_HIDE_SUPPORT_PROMPT=1 \
        python3 "$STAGE/usr/lib/$NAME/examples/demo/make_art.py" >/dev/null
    echo "  demo artwork generated"
else
    echo "  pygame not available here: the demo will use placeholder art"
fi

# --- launcher, desktop entry, icon, man page, docs ---
install -m 755 "$PKG_DIR/opennovella.sh" "$STAGE/usr/bin/$NAME"
install -m 644 "$PKG_DIR/opennovella.desktop" "$STAGE/usr/share/applications/"
install -m 644 "$PKG_DIR/opennovella.svg" "$STAGE/usr/share/icons/hicolor/scalable/apps/"
sed "s/@VERSION@/$VERSION/" "$PKG_DIR/opennovella.1" | gzip -9n > "$STAGE/usr/share/man/man1/$NAME.1.gz"
install -m 644 "$ROOT/README.md" "$ROOT/BUG_REPORT.md" "$PKG_DIR/copyright" "$STAGE/usr/share/doc/$NAME/"
sed "s/@VERSION@/$VERSION/; s/@DATE@/$(date -R)/" "$PKG_DIR/changelog" \
    | gzip -9n > "$STAGE/usr/share/doc/$NAME/changelog.Debian.gz"

# --- maintainer scripts and control file ---
install -m 755 "$PKG_DIR/postinst" "$PKG_DIR/prerm" "$STAGE/DEBIAN/"
find "$STAGE" -type d -exec chmod 755 {} +
find "$STAGE/usr" -type f ! -path "*/usr/bin/*" -exec chmod 644 {} +
INSTALLED_SIZE=$(du -sk "$STAGE/usr" | cut -f1)
sed "s/@VERSION@/$VERSION/; s/@SIZE@/$INSTALLED_SIZE/" "$PKG_DIR/control" > "$STAGE/DEBIAN/control"
(cd "$STAGE" && find usr -type f -exec md5sum {} + | sort -k2 > DEBIAN/md5sums)
chmod 644 "$STAGE/DEBIAN/control" "$STAGE/DEBIAN/md5sums"

mkdir -p "$ROOT/dist"
dpkg-deb --root-owner-group -Zxz --build "$STAGE" "$OUT" >/dev/null
echo "Done: $OUT"
echo "Install with:  sudo apt install \"$OUT\""
