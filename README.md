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
