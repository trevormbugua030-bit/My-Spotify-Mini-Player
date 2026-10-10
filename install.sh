#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
data_home="${XDG_DATA_HOME:-${HOME}/.local/share}"
app_dir="${data_home}/spotify-mini-player"
bin_dir="${HOME}/.local/bin"
applications_dir="${data_home}/applications"
app_path="${app_dir}/spotify-mini-player.py"
launcher_path="${bin_dir}/spotify-mini-player"
desktop_path="${applications_dir}/spotify-mini-player.desktop"

if [[ "${1:-}" == "--uninstall" ]]; then
  rm -f -- "${launcher_path}" "${desktop_path}"
  rm -rf -- "${app_dir}"
  printf 'Removed Spotify Mini-Player from this user account.\n'
  exit 0
elif [[ $# -ne 0 ]]; then
  printf 'Usage: %s [--uninstall]\n' "$0" >&2
  exit 2
fi

if ! python3 -c 'import gi; gi.require_version("Adw", "1"); gi.require_version("Gtk", "4.0"); from gi.repository import Adw, Gtk' 2>/dev/null; then
  printf '%s\n' \
    'GTK 4 and libadwaita Python bindings are required but were not found.' \
    'Install the system packages for python-gobject, GTK 4, and libadwaita, then rerun this script.' >&2
  exit 1
fi

install -d -- "${app_dir}" "${bin_dir}" "${applications_dir}"
install -m 0644 -- "${script_dir}/spotify-mini-player.py" "${app_path}"

cat > "${launcher_path}" <<EOF
#!/usr/bin/env bash
exec python3 "${app_path}" "\$@"
EOF
chmod 0755 -- "${launcher_path}"

# Escape characters that have special meaning in a quoted Desktop Entry Exec argument.
desktop_launcher="$(printf '%s' "${launcher_path}" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\$/\\$/g; s/`/\\`/g')"
cat > "${desktop_path}" <<EOF
[Desktop Entry]
Type=Application
Name=Spotify Mini-Player
Comment=Control Spotify playback from your desktop
Exec="${desktop_launcher}"
Icon=multimedia-player-symbolic
Terminal=false
Categories=AudioVideo;Player;
EOF
chmod 0644 -- "${desktop_path}"

printf 'Installed Spotify Mini-Player. Launch it from your app menu or run:\n  %s\n' "${launcher_path}"
