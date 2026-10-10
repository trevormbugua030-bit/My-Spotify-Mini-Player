#!/usr/bin/env python3
"""A compact Spotify controller for Omarchy and other MPRIS desktops.

It communicates with the local Spotify client over the standard MPRIS D-Bus
interface.  No Spotify account token or web API credentials are needed.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import threading
import urllib.request
from pathlib import Path

import gi

gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk


APP_ID = "org.omarchy.SpotifyMiniPlayer"
BUS_NAME = "org.mpris.MediaPlayer2.spotify"
OBJECT_PATH = "/org/mpris/MediaPlayer2"
PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
PROPS_IFACE = "org.freedesktop.DBus.Properties"
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "spotify-mini-player" / "art"

CSS = """
window {
  background: linear-gradient(145deg, #101716 0%, #0d1211 48%, #15111b 100%);
  color: #f1f5f3;
}

.player-shell { padding: 22px 24px 24px; }
.topline { color: #9aaba3; font-size: 12px; font-weight: 700; letter-spacing: 0.10em; }
.brand { color: #f6f8f7; font-size: 19px; font-weight: 750; letter-spacing: -0.02em; }
.live-pill { background: #173d2d; border: 1px solid #23794f; border-radius: 999px; color: #a7ffd0; font-size: 11px; font-weight: 750; padding: 5px 10px; }
.offline-pill { background: #282d2b; border: 1px solid #3e4943; border-radius: 999px; color: #c1cac5; font-size: 11px; font-weight: 750; padding: 5px 10px; }
.art-frame { background: radial-gradient(circle at 26% 20%, #405953 0%, #1b2825 42%, #121715 100%); border: 1px solid rgba(255,255,255,0.10); border-radius: 24px; box-shadow: 0 16px 36px rgba(0,0,0,0.34); }
.art-frame image { color: #caf9da; }
.art-fallback { color: #b1e8c5; opacity: 0.88; }
.song-title { color: #f8fbf9; font-size: 27px; font-weight: 800; letter-spacing: -0.035em; }
.artist { color: #b9c5be; font-size: 16px; font-weight: 600; }
.album { color: #809087; font-size: 13px; }
.time { color: #98a79f; font-size: 12px; font-feature-settings: "tnum"; }
progressbar trough { min-height: 5px; border-radius: 99px; background: #2a3631; }
progressbar progress { min-height: 5px; border-radius: 99px; background: linear-gradient(90deg, #1ed760, #7ff0a9); }
button.control { min-width: 48px; min-height: 48px; border-radius: 99px; background: transparent; border: 1px solid transparent; color: #d8e3dd; }
button.control:hover { background: #26332e; border-color: #3b5046; color: white; }
button.control:disabled { color: #53615a; background: transparent; }
button.primary-control { min-width: 66px; min-height: 66px; border-radius: 99px; background: #1ed760; color: #07150c; border: 1px solid #75f0a0; box-shadow: 0 8px 20px rgba(30,215,96,0.25); }
button.primary-control:hover { background: #50e884; color: #031008; }
button.primary-control:disabled { background: #314239; border-color: #314239; color: #7b8e84; box-shadow: none; }
.empty-title { color: #f6faf7; font-size: 25px; font-weight: 800; letter-spacing: -0.03em; }
.empty-copy { color: #a8b6af; font-size: 15px; }
button.open-spotify { border-radius: 12px; background: #1ed760; color: #07150c; font-weight: 750; padding: 10px 16px; }
button.open-spotify:hover { background: #54ec8b; }
"""


def display_time(microseconds: int) -> str:
    """Render the MPRIS microsecond duration in a compact clock format."""
    seconds = max(0, int(microseconds // 1_000_000))
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


class SpotifyMiniPlayer(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.proxy: Gio.DBusProxy | None = None
        self.props_proxy: Gio.DBusProxy | None = None
        self.current_art_url = ""
        self.duration = 0
        self.position = 0
        self.playback_status = "Stopped"
        self.art_picture: Gtk.Picture | None = None
        self.art_fallback: Gtk.Image | None = None
        self.play_button: Gtk.Button | None = None
        self.next_button: Gtk.Button | None = None
        self.previous_button: Gtk.Button | None = None
        self.status_pill: Gtk.Label | None = None
        self.title_label: Gtk.Label | None = None
        self.artist_label: Gtk.Label | None = None
        self.album_label: Gtk.Label | None = None
        self.elapsed_label: Gtk.Label | None = None
        self.remaining_label: Gtk.Label | None = None
        self.progress: Gtk.ProgressBar | None = None
        self.empty_stack: Gtk.Stack | None = None

    def do_activate(self) -> None:
        if self.get_active_window():
            self.get_active_window().present()
            return

        provider = Gtk.CssProvider()
        provider.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        window = Adw.ApplicationWindow(application=self, title="Spotify Mini Player")
        window.set_default_size(430, 660)
        window.set_size_request(370, 550)
        window.set_resizable(True)
        window.set_icon_name("multimedia-player-symbolic")
        window.set_content(self.build_ui())
        self.install_actions()
        self.connect_player()
        self.refresh()
        GLib.timeout_add_seconds(1, self.tick)
        window.present()

    def build_ui(self) -> Gtk.Widget:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        root.add_css_class("player-shell")

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        header.set_margin_bottom(22)
        identity = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        label = Gtk.Label(label="NOW PLAYING", xalign=0)
        label.add_css_class("topline")
        brand = Gtk.Label(label="Spotify mini player", xalign=0)
        brand.add_css_class("brand")
        identity.append(label)
        identity.append(brand)
        header.append(identity)
        header.append(Gtk.Box(hexpand=True))
        self.status_pill = Gtk.Label(label="CONNECTING")
        self.status_pill.add_css_class("offline-pill")
        header.append(self.status_pill)
        root.append(header)

        self.empty_stack = Gtk.Stack()
        self.empty_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.empty_stack.set_vexpand(True)
        self.empty_stack.add_named(self.build_player_view(), "player")
        self.empty_stack.add_named(self.build_empty_view(), "empty")
        root.append(self.empty_stack)
        return root

    def build_player_view(self) -> Gtk.Widget:
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        panel.set_vexpand(True)

        art_overlay = Gtk.Overlay()
        art_overlay.add_css_class("art-frame")
        art_overlay.set_size_request(-1, 318)
        self.art_picture = Gtk.Picture()
        self.art_picture.set_content_fit(Gtk.ContentFit.COVER)
        self.art_picture.set_can_shrink(True)
        self.art_picture.set_hexpand(True)
        self.art_picture.set_vexpand(True)
        art_overlay.set_child(self.art_picture)
        self.art_fallback = Gtk.Image.new_from_icon_name("audio-x-generic-symbolic")
        self.art_fallback.set_pixel_size(84)
        self.art_fallback.add_css_class("art-fallback")
        self.art_fallback.set_halign(Gtk.Align.CENTER)
        self.art_fallback.set_valign(Gtk.Align.CENTER)
        art_overlay.add_overlay(self.art_fallback)
        panel.append(art_overlay)

        details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        details.set_margin_top(22)
        self.title_label = Gtk.Label(label="Looking for a track…", xalign=0, ellipsize=3)
        self.title_label.add_css_class("song-title")
        self.title_label.set_lines(1)
        self.artist_label = Gtk.Label(label="Spotify", xalign=0, ellipsize=3)
        self.artist_label.add_css_class("artist")
        self.album_label = Gtk.Label(label="", xalign=0, ellipsize=3)
        self.album_label.add_css_class("album")
        details.append(self.title_label)
        details.append(self.artist_label)
        details.append(self.album_label)
        panel.append(details)

        time_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        time_row.set_margin_top(19)
        self.elapsed_label = Gtk.Label(label="0:00", xalign=0)
        self.elapsed_label.add_css_class("time")
        self.remaining_label = Gtk.Label(label="−0:00", xalign=1)
        self.remaining_label.add_css_class("time")
        time_row.append(self.elapsed_label)
        time_row.append(Gtk.Box(hexpand=True))
        time_row.append(self.remaining_label)
        panel.append(time_row)
        self.progress = Gtk.ProgressBar()
        self.progress.set_fraction(0)
        self.progress.set_margin_top(7)
        panel.append(self.progress)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        controls.set_halign(Gtk.Align.CENTER)
        controls.set_margin_top(19)
        self.previous_button = self.make_button("media-skip-backward-symbolic", "Previous track", "control")
        self.previous_button.connect("clicked", lambda *_: self.control("Previous"))
        self.play_button = self.make_button("media-playback-start-symbolic", "Play", "primary-control")
        self.play_button.connect("clicked", lambda *_: self.control("PlayPause"))
        self.next_button = self.make_button("media-skip-forward-symbolic", "Next track", "control")
        self.next_button.connect("clicked", lambda *_: self.control("Next"))
        controls.append(self.previous_button)
        controls.append(self.play_button)
        controls.append(self.next_button)
        panel.append(controls)
        return panel

    def build_empty_view(self) -> Gtk.Widget:
        empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        empty.set_valign(Gtk.Align.CENTER)
        empty.set_vexpand(True)
        empty.set_halign(Gtk.Align.CENTER)
        icon = Gtk.Image.new_from_icon_name("spotify-symbolic")
        icon.set_pixel_size(72)
        icon.add_css_class("art-fallback")
        empty.append(icon)
        title = Gtk.Label(label="Spotify is not ready", justify=Gtk.Justification.CENTER)
        title.add_css_class("empty-title")
        empty.append(title)
        copy = Gtk.Label(
            label="Open Spotify and start a track.\nThis player will connect automatically.",
            justify=Gtk.Justification.CENTER,
        )
        copy.add_css_class("empty-copy")
        empty.append(copy)
        open_button = Gtk.Button(label="Open Spotify")
        open_button.add_css_class("open-spotify")
        open_button.set_margin_top(8)
        open_button.connect("clicked", self.open_spotify)
        empty.append(open_button)
        return empty

    @staticmethod
    def make_button(icon: str, tooltip: str, css_class: str) -> Gtk.Button:
        button = Gtk.Button.new_from_icon_name(icon)
        button.set_tooltip_text(tooltip)
        button.add_css_class(css_class)
        return button

    def install_actions(self) -> None:
        for name, method, accelerators in (
            ("playpause", "PlayPause", ["space"]),
            ("previous", "Previous", ["Left"]),
            ("next", "Next", ["Right"]),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _action, _parameter, command=method: self.control(command))
            self.add_action(action)
            self.set_accels_for_action(f"app.{name}", accelerators)

    def connect_player(self) -> bool:
        if self.proxy is not None:
            return True
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            self.proxy = Gio.DBusProxy.new_sync(
                bus, Gio.DBusProxyFlags.NONE, None, BUS_NAME, OBJECT_PATH, PLAYER_IFACE, None
            )
            self.props_proxy = Gio.DBusProxy.new_sync(
                bus, Gio.DBusProxyFlags.NONE, None, BUS_NAME, OBJECT_PATH, PROPS_IFACE, None
            )
            self.proxy.connect("g-properties-changed", self.on_properties_changed)
            return True
        except GLib.Error:
            self.proxy = None
            self.props_proxy = None
            return False

    def on_properties_changed(self, _proxy: Gio.DBusProxy, _changed: GLib.Variant, _invalidated: list[str]) -> None:
        self.refresh()

    def tick(self) -> bool:
        self.refresh(read_position=True)
        return True

    def refresh(self, read_position: bool = False) -> None:
        connected = self.connect_player()
        if not connected or self.proxy is None:
            self.set_disconnected()
            return

        try:
            metadata = self.property("Metadata") or {}
            self.playback_status = self.property("PlaybackStatus") or "Stopped"
            self.duration = int(metadata.get("mpris:length", 0))
            if read_position:
                self.position = self.get_position()
            else:
                self.position = int(self.property("Position") or self.position)
            title = str(metadata.get("xesam:title") or "No track selected")
            artist = metadata.get("xesam:artist") or metadata.get("xesam:albumArtist") or ["Spotify"]
            if isinstance(artist, str):
                artist = [artist]
            album = str(metadata.get("xesam:album") or "")
            self.set_connected(title, ", ".join(map(str, artist)), album, metadata.get("mpris:artUrl", ""))
            can_control = bool(self.property("CanControl"))
            self.previous_button.set_sensitive(can_control and bool(self.property("CanGoPrevious")))
            self.next_button.set_sensitive(can_control and bool(self.property("CanGoNext")))
            self.play_button.set_sensitive(can_control and bool(self.property("CanPlay")))
        except GLib.Error:
            self.proxy = None
            self.props_proxy = None
            self.set_disconnected()

    def property(self, name: str):
        if self.proxy is None:
            return None
        value = self.proxy.get_cached_property(name)
        return value.unpack() if value is not None else None

    def get_position(self) -> int:
        if self.props_proxy is None:
            return self.position
        result = self.props_proxy.call_sync(
            "Get", GLib.Variant("(ss)", (PLAYER_IFACE, "Position")), Gio.DBusCallFlags.NONE, 600, None
        )
        value = result.unpack()[0]
        return int(value.unpack() if isinstance(value, GLib.Variant) else value)

    def set_connected(self, title: str, artist: str, album: str, art_url: str) -> None:
        self.empty_stack.set_visible_child_name("player")
        self.status_pill.set_label("●  LIVE")
        self.status_pill.remove_css_class("offline-pill")
        self.status_pill.add_css_class("live-pill")
        self.title_label.set_label(title)
        self.artist_label.set_label(artist)
        self.album_label.set_label(album)
        is_playing = self.playback_status == "Playing"
        self.play_button.set_icon_name("media-playback-pause-symbolic" if is_playing else "media-playback-start-symbolic")
        self.play_button.set_tooltip_text("Pause" if is_playing else "Play")
        fraction = min(1.0, self.position / self.duration) if self.duration else 0
        self.progress.set_fraction(fraction)
        self.elapsed_label.set_label(display_time(self.position))
        self.remaining_label.set_label("−" + display_time(max(0, self.duration - self.position)))
        if art_url and art_url != self.current_art_url:
            self.current_art_url = art_url
            self.load_art_async(art_url)

    def set_disconnected(self) -> None:
        self.empty_stack.set_visible_child_name("empty")
        self.status_pill.set_label("OFFLINE")
        self.status_pill.remove_css_class("live-pill")
        self.status_pill.add_css_class("offline-pill")

    def control(self, method: str) -> None:
        if not self.connect_player() or self.proxy is None:
            self.set_disconnected()
            return
        try:
            self.proxy.call_sync(method, None, Gio.DBusCallFlags.NONE, 1000, None)
            GLib.timeout_add(100, self.refresh_once)
        except GLib.Error:
            self.proxy = None
            self.props_proxy = None
            self.set_disconnected()

    def refresh_once(self) -> bool:
        self.refresh(read_position=True)
        return False

    def open_spotify(self, _button: Gtk.Button) -> None:
        try:
            subprocess.Popen(["spotify"], start_new_session=True)
        except OSError:
            pass

    def load_art_async(self, url: str) -> None:
        def worker() -> None:
            try:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                path = CACHE_DIR / hashlib.sha256(url.encode()).hexdigest()
                if not path.exists():
                    request = urllib.request.Request(url, headers={"User-Agent": "SpotifyMiniPlayer/1.0"})
                    data = urllib.request.urlopen(request, timeout=8).read()
                    temporary = path.with_suffix(".part")
                    temporary.write_bytes(data)
                    temporary.replace(path)
                GLib.idle_add(self.apply_art, url, str(path))
            except Exception:
                GLib.idle_add(self.art_failed, url)

        threading.Thread(target=worker, daemon=True).start()

    def apply_art(self, url: str, path: str) -> bool:
        if url != self.current_art_url:
            return False
        try:
            texture = Gdk.Texture.new_from_file(Gio.File.new_for_path(path))
            self.art_picture.set_paintable(texture)
            self.art_fallback.set_visible(False)
        except GLib.Error:
            self.art_failed(url)
        return False

    def art_failed(self, url: str) -> bool:
        if url == self.current_art_url:
            self.art_picture.set_paintable(None)
            self.art_fallback.set_visible(True)
        return False


if __name__ == "__main__":
    SpotifyMiniPlayer().run(None)
