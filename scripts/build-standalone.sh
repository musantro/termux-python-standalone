#!/usr/bin/env bash
set -euo pipefail

# This script is run inside the GitHub Actions matrix. It builds the pinned
# Termux python recipe and turns its .deb payload into uv's install_only layout.

: "${PYTHON_VERSION:?set PYTHON_VERSION, e.g. 3.13.13}"
: "${TERMUX_PACKAGES_REF:?set TERMUX_PACKAGES_REF to a pinned commit}"
: "${OUTPUT_DIR:?set OUTPUT_DIR to the artifact directory}"

repo_dir=${TERMUX_PACKAGES_DIR:-"$PWD/.termux-packages"}
mkdir -p "$OUTPUT_DIR"

if [[ ! -d "$repo_dir/.git" ]]; then
	git clone --filter=blob:none https://github.com/termux/termux-packages.git "$repo_dir"
fi
git -C "$repo_dir" fetch --depth=1 origin "$TERMUX_PACKAGES_REF"
git -C "$repo_dir" checkout --detach "$TERMUX_PACKAGES_REF"

cd "$repo_dir"

# The package recipe already contains the Android-specific patches, configure
# probes, and host-build Python setup maintained by Termux.
./build-package.sh -a aarch64 -I -f python

deb=$(find output -maxdepth 1 -type f -name 'python_*.deb' -print -quit)
if [[ -z "$deb" ]]; then
	echo "Could not find the built python .deb in $PWD/output" >&2
	exit 1
fi

work_dir=$(mktemp -d)
trap 'rm -rf "$work_dir"' EXIT
dpkg-deb -x "$deb" "$work_dir/deb"

termux_prefix="$work_dir/deb/data/data/com.termux/files/usr"
if [[ ! -d "$termux_prefix/bin" || ! -d "$termux_prefix/lib/python${PYTHON_VERSION%.*}" ]]; then
	echo "Unexpected Termux package layout under $termux_prefix" >&2
find "$work_dir/deb" -maxdepth 6 -type d | sort | head -80 >&2
	exit 1
fi

install_dir="$work_dir/install"
mkdir -p "$install_dir"
cp -a "$termux_prefix/." "$install_dir/"

# Keep the archive focused on the Python package. Runtime libraries supplied by
# the normal Termux dependency set remain shared with the system installation;
# libpython itself is included in the package payload.
rm -rf "$install_dir/share/man" "$install_dir/share/doc" "$install_dir/var"

archive="$OUTPUT_DIR/cpython-${PYTHON_VERSION}-android-aarch64.tar.gz"
tar -C "$work_dir" -czf "$archive" install
sha256sum "$archive" > "$archive.sha256"
printf 'Built %s\n' "$archive"
