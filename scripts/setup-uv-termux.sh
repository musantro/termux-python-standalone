#!/usr/bin/env bash

# Configure uv to use the Termux/Android Python catalog.
#
# This file is intentionally source-only. An exported variable in a child
# process cannot change the caller's shell, so use:
#
#   source ./scripts/setup-uv-termux.sh
#
# An optional argument selects a release tag or a complete catalog URL. The
# default is the mutable GitHub `latest` release pointer.

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
	printf 'This helper must be sourced in the current shell:\n' >&2
	printf '  source %s [release-tag|catalog-url]\n' "$0" >&2
	exit 2
fi

termux_python_repo=${TERMUX_PYTHON_REPO:-musantro/termux-python-standalone}
termux_python_ref=${1:-${TERMUX_PYTHON_RELEASE:-latest}}

case "$termux_python_ref" in
	latest)
		termux_python_catalog_url="https://github.com/${termux_python_repo}/releases/latest/download/python-downloads.json"
		;;
	https://*|http://*|file://*)
		termux_python_catalog_url=$termux_python_ref
		;;
	[A-Za-z0-9._-]*)
		termux_python_catalog_url="https://github.com/${termux_python_repo}/releases/download/${termux_python_ref}/python-downloads.json"
		;;
	*)
		printf 'Invalid release tag or catalog URL: %s\n' "$termux_python_ref" >&2
		return 2
		;;
esac

termux_python_arch=$(uname -m)
if [[ "$termux_python_arch" != "aarch64" ]]; then
	printf 'This catalog contains aarch64 builds; detected architecture: %s\n' "$termux_python_arch" >&2
	return 1
fi

# `getprop` is available on Android. Keep the check optional so the helper is
# also useful in a Termux-like test container where it may not be present.
if command -v getprop >/dev/null 2>&1; then
	termux_python_android_api=$(getprop ro.build.version.sdk 2>/dev/null || true)
	if [[ "$termux_python_android_api" =~ ^[0-9]+$ ]] && (( termux_python_android_api < 24 )); then
		printf 'This catalog requires Android API 24 or newer; detected API %s\n' \
			"$termux_python_android_api" >&2
		return 1
	fi
fi

export UV_PYTHON_DOWNLOADS_JSON_URL="$termux_python_catalog_url"
# uv defaults to automatic downloads, but setting this explicitly avoids a
# previous `UV_PYTHON_DOWNLOADS=never` setting silently disabling the catalog.
export UV_PYTHON_DOWNLOADS=automatic

printf 'Configured uv to use: %s\n' "$UV_PYTHON_DOWNLOADS_JSON_URL" >&2
printf 'Inspect available builds with: uv python list --only-downloads --show-urls\n' >&2

unset termux_python_repo termux_python_ref termux_python_catalog_url \
	termux_python_arch termux_python_android_api
