#!/usr/bin/env bash
set -euo pipefail

# This script is run inside the GitHub Actions matrix. It builds the pinned
# Termux python recipe and turns its .deb payload into uv's install_only layout.

: "${PYTHON_VERSION:?set PYTHON_VERSION, e.g. 3.13.13}"
: "${TERMUX_BUILDER_REF:?set TERMUX_BUILDER_REF to a pinned build-system commit}"
: "${TERMUX_RECIPE_REF:?set TERMUX_RECIPE_REF to a pinned Python recipe commit}"
: "${OUTPUT_DIR:?set OUTPUT_DIR to the artifact directory}"

repo_dir=${TERMUX_PACKAGES_DIR:-"$PWD/.termux-packages"}
mkdir -p "$OUTPUT_DIR"

if [[ ! -d "$repo_dir/.git" ]]; then
	git clone --filter=blob:none https://github.com/termux/termux-packages.git "$repo_dir"
fi
git -C "$repo_dir" fetch --depth=1 origin "$TERMUX_BUILDER_REF" "$TERMUX_RECIPE_REF"
git -C "$repo_dir" checkout --detach "$TERMUX_BUILDER_REF"

# Keep the current build infrastructure (including its Ubuntu/NDK setup), but
# use the exact Python recipe and patches from the requested version's commit.
rm -rf "$repo_dir/packages/python"
git -C "$repo_dir" archive "$TERMUX_RECIPE_REF" packages/python \
	| tar -x -C "$repo_dir"

# The current build infrastructure uses this patch name while building the
# minimal host Python. Older Python recipes used a different sequence of patch
# names, so restore the current compatibility patch alongside the historical
# recipe when necessary.
if [[ ! -f "$repo_dir/packages/python/0008-fix-ctypes-util-find_library.patch" ]]; then
	if git -C "$repo_dir" cat-file -e "$TERMUX_RECIPE_REF:packages/python/0009-fix-ctypes-util-find_library.patch" 2>/dev/null; then
		git -C "$repo_dir" show "$TERMUX_RECIPE_REF:packages/python/0009-fix-ctypes-util-find_library.patch" \
			> "$repo_dir/packages/python/0008-fix-ctypes-util-find_library.patch"
	else
		git -C "$repo_dir" show "$TERMUX_BUILDER_REF:packages/python/0008-fix-ctypes-util-find_library.patch" \
			> "$repo_dir/packages/python/0008-fix-ctypes-util-find_library.patch"
	fi
fi

cd "$repo_dir"

# The package recipe already contains the Android-specific patches, configure
# probes, and host-build Python setup maintained by Termux.
if [[ "${TERMUX_USE_DOCKER:-false}" == "true" ]]; then
	TERMUX_BUILDER_IMAGE_NAME="${TERMUX_BUILDER_IMAGE_NAME:-ghcr.io/termux/package-builder:latest}" \
		./scripts/run-docker.sh ./build-package.sh -a aarch64 -I -f python
else
	./build-package.sh -a aarch64 -I -f python
fi

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

# Termux recipes normally encode the system prefix in the ELF RUNPATH. A uv
# managed installation lives elsewhere, so prefer the archive's own libpython
# and extension modules while retaining the official Termux prefix as a
# fallback for shared runtime dependencies such as sqlite and OpenSSL.
while IFS= read -r -d '' elf; do
	relative=${elf#"$install_dir/"}
	case "$relative" in
		bin/*)
			rpath='$ORIGIN/../lib:/data/data/com.termux/files/usr/lib'
			;;
		lib/python*/lib-dynload/*)
			rpath='$ORIGIN/../..:/data/data/com.termux/files/usr/lib'
			;;
		lib/*.so*)
			rpath='$ORIGIN:/data/data/com.termux/files/usr/lib'
			;;
		*)
			continue
			;;
	esac
	if file -b "$elf" | grep -q '^ELF '; then
		patchelf --set-rpath "$rpath" "$elf"
	fi
done < <(find "$install_dir" -type f \( -perm -111 -o -name '*.so*' \) -print0)

archive="$OUTPUT_DIR/cpython-${PYTHON_VERSION}-android-aarch64.tar.gz"
tar -C "$work_dir" -czf "$archive" install
sha256sum "$archive" > "$archive.sha256"
printf 'Built %s\n' "$archive"
