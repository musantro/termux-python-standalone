#!/usr/bin/env bash

# Install the uv catalog configuration in the user's shell startup file.
# This script is intentionally interactive. When run through `curl ... | bash`,
# prompts are read from /dev/tty, not from the download pipe.

set -euo pipefail

termux_python_repo=${TERMUX_PYTHON_REPO:-musantro/termux-python-standalone}
termux_python_ref=${TERMUX_PYTHON_RELEASE:-latest}
termux_python_catalog_url="https://github.com/${termux_python_repo}/releases/latest/download/python-downloads.json"

case "$termux_python_ref" in
	latest)
		;;
	https://*|http://*|file://*)
		termux_python_catalog_url=$termux_python_ref
		;;
	[A-Za-z0-9._-]*)
		termux_python_catalog_url="https://github.com/${termux_python_repo}/releases/download/${termux_python_ref}/python-downloads.json"
		;;
	*)
		printf 'Invalid TERMUX_PYTHON_RELEASE: %s\n' "$termux_python_ref" >&2
		exit 2
		;;
esac

shell_name=${SHELL:-}
shell_name=${shell_name##*/}
if [[ -n "${TERMUX_UV_STARTUP_FILE:-}" ]]; then
	startup_file=$TERMUX_UV_STARTUP_FILE
else
	case "$shell_name" in
		zsh)
			startup_dir=${ZDOTDIR:-$HOME}
			startup_file="$startup_dir/.zshrc"
			if [[ ! -e "$startup_file" && -e "$startup_dir/.zprofile" ]]; then
				startup_file="$startup_dir/.zprofile"
			fi
			;;
		bash)
			startup_file="$HOME/.bashrc"
			[[ -e "$startup_file" ]] || startup_file="$HOME/.bash_profile"
			[[ -e "$startup_file" ]] || startup_file="$HOME/.profile"
			;;
		*)
			startup_file="$HOME/.profile"
			;;
	esac
fi

if [[ -d "$startup_file" ]]; then
	printf 'Startup path is a directory, not a file: %s\n' "$startup_file" >&2
	exit 1
fi

block_start='# >>> termux-python-standalone uv catalog >>>'
block_end='# <<< termux-python-standalone uv catalog <<<'
block=$(printf '%s\n%s\n%s\n%s\n' \
	"$block_start" \
	"export UV_PYTHON_DOWNLOADS_JSON_URL=\"$termux_python_catalog_url\"" \
	'export UV_PYTHON_DOWNLOADS=automatic' \
	"$block_end")

if [[ -e "$startup_file" && ! -f "$startup_file" ]]; then
	printf 'Startup path is not a regular file: %s\n' "$startup_file" >&2
	exit 1
fi

block_start_count=0
block_end_count=0
if [[ -f "$startup_file" ]]; then
	block_start_count=$(grep -Fxc "$block_start" "$startup_file" || true)
	block_end_count=$(grep -Fxc "$block_end" "$startup_file" || true)
fi
if (( block_start_count != block_end_count || block_start_count > 1 )); then
	printf 'Refusing to edit malformed or duplicated managed blocks in %s\n' \
		"$startup_file" >&2
	exit 1
fi

temporary_file=$(mktemp)
cleanup() {
	rm -f "$temporary_file"
}
trap cleanup EXIT

if [[ -f "$startup_file" ]]; then
	awk -v start="$block_start" -v end="$block_end" '
		$0 == start { inside = 1; next }
		inside && $0 == end { inside = 0; next }
		!inside { print }
	' "$startup_file" >"$temporary_file"
else
	: >"$temporary_file"
fi
printf '%s' "$block" >>"$temporary_file"

changed=1
if [[ -f "$startup_file" ]] && cmp -s "$startup_file" "$temporary_file"; then
	changed=0
fi

printf '\nuv Termux catalog installer\n'
printf '%s\n' '--------------------------------'
printf 'Catalog: %s\n' "$termux_python_catalog_url"
printf 'Target:  %s\n' "$startup_file"
if (( changed )); then
	if [[ -f "$startup_file" ]]; then
		printf 'Action:  update the managed uv configuration block\n'
	else
		printf 'Action:  create the startup file with the managed uv configuration block\n'
	fi
	printf '\nThe following block is the only content this installer will add or update:\n\n%s\n' "$block"
	printf 'No packages or Python installations will be installed.\n'
else
	printf 'Action:  none; the managed block is already up to date\n'
fi

if (( changed )); then
	if [[ -t 0 ]]; then
		if ! read -r -p 'Authorize this file change? [y/N] ' answer; then
			answer=
		fi
	elif [[ -r /dev/tty ]]; then
		printf 'Authorize this file change? [y/N] ' >&2
		if ! read -r answer </dev/tty; then
			answer=
		fi
	else
		printf '\nInstallation report\n'
		printf '%s\n' '-------------------'
		printf 'Modified: none (cannot ask for authorization without a terminal)\n'
		exit 1
	fi
	case "$answer" in
		y|Y|yes|YES|Yes)
		;;
		*)
			printf '\nInstallation report\n'
			printf '%s\n' '-------------------'
			printf 'Modified: none (authorization not granted)\n'
			exit 0
			;;
	esac

	startup_dir=${startup_file%/*}
	if [[ "$startup_dir" == "$startup_file" ]]; then
		startup_dir=.
	fi
	mkdir -p "$startup_dir"
	if [[ -f "$startup_file" ]]; then
		# cp follows symlinks and preserves the existing startup file's mode.
		cp "$temporary_file" "$startup_file"
	else
		mv "$temporary_file" "$startup_file"
	fi
	changed_description=$([[ "$block_start_count" == 0 ]] && printf 'added' || printf 'updated')
fi

printf '\nInstallation report\n'
printf '%s\n' '-------------------'
if (( changed )); then
	printf 'Modified: %s (%s managed uv configuration block)\n' \
		"$startup_file" "$changed_description"
	printf 'Applied to new shells automatically. For this shell, run:\n'
	printf '  source %q\n' "$startup_file"
else
	printf 'Modified: none\n'
fi
printf 'Catalog configured: %s\n' "$termux_python_catalog_url"
printf 'Verify with: uv python list --only-downloads --show-urls\n'
