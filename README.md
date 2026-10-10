# My Spotify Mini-Player

A compact GTK 4 and libadwaita controller for the Spotify desktop client. It reads playback state and sends playback controls over the MPRIS D-Bus interface.

## Requirements

- Python 3
- GTK 4 and libadwaita introspection bindings (`python-gobject`, `Gtk 4`, `Adw 1`)
- Spotify desktop client running in a session with MPRIS support

## Run

```sh
python3 spotify-mini-player.py
```

## Install

Install the system Python bindings for GTK 4 and libadwaita first. Common package names are `python-gobject`, `gtk4`, and `libadwaita` on Arch Linux, and `python3-gi`, `gir1.2-gtk-4.0`, and `gir1.2-adw-1` on Debian or Ubuntu.

Then install for the current user:

```sh
./install.sh
```

The installer places the app in `~/.local/share/spotify-mini-player`, adds a launcher at `~/.local/bin/spotify-mini-player`, and creates an application menu entry. To remove those files:

```sh
./install.sh --uninstall
```
