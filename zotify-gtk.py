#!/usr/bin/env python3
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio, GObject
from pathlib import Path
from argparse import Namespace
from zotify import Session, OAuth
from zotify.config import Config
from zotify.collections import Collection, Album, Artist, Playlist, Track, Episode
from zotify.utils import AudioFormat, Quality, ImageSize, PlayableType
from threading import Thread
import webbrowser

class ZotifyWindow(Gtk.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set up window properties
        self.set_title("Zotify")
        self.set_default_size(800, 600)
        
        # Main layout structure with toast overlay
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        # Add toast overlay
        self.toast_overlay = Adw.ToastOverlay()
        self.toast_overlay.set_child(self.main_box)
        self.set_child(self.toast_overlay)

        # Header bar
        self.create_header_bar()
        
        # Main content area
        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.content_box.set_margin_start(10)
        self.content_box.set_margin_end(10)
        self.content_box.set_margin_top(10)
        self.content_box.set_margin_bottom(10)
        self.main_box.append(self.content_box)
        
        # URL entry
        self.url_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.url_box.set_hexpand(True)
        
        self.url_entry = Gtk.Entry()
        self.url_entry.set_placeholder_text("Enter Spotify URL or URI")
        self.url_entry.set_hexpand(True)
        self.url_entry.connect("activate", self.on_url_entered)
        self.url_box.append(self.url_entry)
        
        self.download_button = Gtk.Button(label="Download")
        self.download_button.connect("clicked", self.on_download_clicked)
        self.download_button.add_css_class("suggested-action")
        self.url_box.append(self.download_button)
        
        self.content_box.append(self.url_box)
        
        # Output format section
        output_group = Adw.PreferencesGroup()
        output_group.set_title("Output Format")
        
        # Output format entry
        self.output_format_row = Adw.EntryRow()
        self.output_format_row.set_title("Format")
        self.output_format_row.set_text("{artist} - {song_name}")
        output_group.add(self.output_format_row)
        
        # Add format info button
        info_button = Gtk.Button()
        info_button.set_icon_name("help-about-symbolic")
        info_button.add_css_class("flat")
        info_button.connect("clicked", self.show_format_help)
        self.output_format_row.add_suffix(info_button)
        
        # Add examples dropdown
        example_button = Gtk.MenuButton()
        example_button.set_icon_name("view-list-symbolic")
        example_button.add_css_class("flat")
        
        example_menu = Gio.Menu.new()
        examples = [
            "{playlist}/{artist} - {song_name}",
            "{playlist}/{playlist_num} - {artist} - {song_name}",
            "{artist} - {song_name}",
            "{artist}/{album}/{album_num} - {artist} - {song_name}"
        ]
        for example in examples:
            example_menu.append(example, f"app.set_format('{example}')")
        
        example_button.set_menu_model(example_menu)
        self.output_format_row.add_suffix(example_button)
        
        self.content_box.append(output_group)
        
        # Download progress
        self.progress_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.progress_box.set_visible(False)
        self.progress_label = Gtk.Label()
        self.progress_bar = Gtk.ProgressBar()
        self.progress_box.append(self.progress_label)
        self.progress_box.append(self.progress_bar)
        self.content_box.append(self.progress_box)
        
        # Download history
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        
        self.history_list = Gtk.ListBox()
        self.history_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.history_list.add_css_class("boxed-list")
        scroll.set_child(self.history_list)
        
        self.content_box.append(scroll)
        
        # Initialize config and session
        self.config = Config()
        self.session = None
        
        # Try to load existing credentials
        try:
            if self.config.credentials_path.exists():
                self.session = Session.from_file(
                    self.config.credentials_path,
                    language=self.config.language
                )
                GLib.idle_add(
                    self.show_toast,
                    "Successfully logged in using saved credentials!"
                )
            else:
                GLib.idle_add(self.show_login_dialog)
        except Exception as e:
            print(f"Failed to load credentials: {str(e)}")
            GLib.idle_add(self.show_login_dialog)

    def show_format_help(self, button):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Output Format Placeholders",
            body="""Available placeholders:
            
{artist} - The song artist
{album} - The song album
{song_name} - The song name
{release_year} - The song release year
{disc_number} - The disc number
{track_number} - The track number
{id} - The song id
{track_id} - The track id
{album_id} - (albums only) ID of the album
{album_num} - (albums only) Incrementing track number
{playlist} - (playlists only) Name of the playlist
{playlist_num} - (playlists only) Incrementing track number""",
        )
        dialog.add_response("ok", "OK")
        dialog.present()

    def create_header_bar(self):
        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        
        # Menu button
        menu = Gio.Menu.new()
        menu.append("Preferences", "app.preferences")
        menu.append("About", "app.about")
        
        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("open-menu-symbolic")
        menu_button.set_menu_model(menu)
        header.pack_end(menu_button)

    def show_login_dialog(self):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Login to Spotify",
            body="Please enter your Spotify username to continue",
        )
        
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("ok", "Login")
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
        
        username_entry = Gtk.Entry()
        username_entry.set_margin_top(10)
        username_entry.set_margin_bottom(10)
        username_entry.set_activates_default(True)
        dialog.set_extra_child(username_entry)
        
        dialog.connect("response", self.on_login_response, username_entry)
        dialog.present()

    def on_login_response(self, dialog, response, username_entry):
        if response == "ok":
            username = username_entry.get_text()
            if username:
                dialog.destroy()
                self.start_oauth_flow(username)
            else:
                username_entry.add_css_class("error")
        else:
            self.close()

    def start_oauth_flow(self, username):
        oauth = OAuth(username)
        auth_url = oauth.auth_interactive()
        
        # Open browser for login
        webbrowser.open(auth_url)
        
        # Start session in background
        thread = Thread(target=self.complete_login, args=(oauth,))
        thread.daemon = True
        thread.start()
        
        # Show loading dialog
        self.show_loading_dialog("Waiting for login...")

    def show_loading_dialog(self, message):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Loading",
            body=message,
        )
        spinner = Gtk.Spinner()
        spinner.start()
        spinner.set_margin_top(10)
        spinner.set_margin_bottom(10)
        dialog.set_extra_child(spinner)
        dialog.present()
        self.loading_dialog = dialog

    def complete_login(self, oauth):
        try:
            self.session = Session.from_oauth(
                oauth,
                self.config.credentials_path,
                self.config.language
            )
            GLib.idle_add(self.on_login_complete)
        except Exception as e:
            GLib.idle_add(self.on_login_error, str(e))

    def on_login_complete(self):
        self.loading_dialog.destroy()
        self.show_toast("Successfully logged in!")

    def on_login_error(self, error):
        self.loading_dialog.destroy()
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Login Error",
            body=f"Failed to login: {error}",
        )
        dialog.add_response("ok", "OK")
        dialog.present()

    def show_toast(self, message):
        toast = Adw.Toast.new(message)
        self.toast_overlay.add_toast(toast)

    def on_url_entered(self, entry):
        self.start_download(entry.get_text())

    def on_download_clicked(self, button):
        self.start_download(self.url_entry.get_text())

    def start_download(self, url):
        if not url:
            return
        if not self.session:
            self.show_toast("Not logged in!")
            return
            
        # Ensure we have a valid token
        try:
            self.session.api().invoke_url("me")
        except Exception as e:
            print(f"Session validation error: {str(e)}")
            self.show_toast("Session expired, please log in again")
            self.show_login_dialog()
            return
            
        self.url_entry.set_sensitive(False)
        self.download_button.set_sensitive(False)
        self.progress_box.set_visible(True)
        self.progress_label.set_text("Starting download...")
        self.progress_bar.set_fraction(0)
        
        thread = Thread(target=self.download_content, args=(url,))
        thread.daemon = True
        thread.start()

    def download_content(self, url):
        try:
            print(f"Starting download for URL: {url}")
            
            # Parse URL and create collection
            print("Parsing URL...")
            collection = self.parse_url(url)
            print(f"Created collection with {len(collection.playables)} playable items")
            
            # Debug: Print first few playable items
            for i, playable in enumerate(collection.playables[:3]):
                print(f"Playable {i}: type={playable.type}, id={playable.id}")
            
            # Download each track
            total = len(collection.playables)
            for i, playable in enumerate(collection.playables):
                GLib.idle_add(
                    self.progress_label.set_text,
                    f"Downloading {i+1} of {total}"
                )
                GLib.idle_add(
                    self.progress_bar.set_fraction,
                    (i) / total
                )
                
                print(f"\nDownloading: type={playable.type}, id={playable.id}")
                if playable.type == PlayableType.TRACK:
                    track = self.session.get_track(playable.id, Quality.AUTO)
                elif playable.type == PlayableType.EPISODE:
                    track = self.session.get_episode(playable.id)
                else:
                    print(f"Unknown playable type: {playable.type}")
                    continue
                output = track.create_output(
                    playable.library,
                    playable.output_template
                )
                
                file = track.write_audio_stream(output)
                
                if self.config.save_metadata:
                    file.write_metadata(track.metadata)
                    file.write_cover_art(track.get_cover_art())
                
                GLib.idle_add(self.add_history_item, track.name)
            
            GLib.idle_add(self.download_complete)
            
        except Exception as e:
            print(f"Download error: {str(e)}")
            GLib.idle_add(self.download_error, str(e))

    def parse_url(self, url):
        """Parse Spotify URL/URI and return appropriate collection"""
        # Handle Spotify URIs (spotify:type:id)
        if url.startswith("spotify:"):
            parts = url.split(":")
            if len(parts) == 3:
                type_name = parts[1]
                id = parts[2]
            else:
                raise ValueError("Invalid Spotify URI format")
        # Handle URLs (https://open.spotify.com/type/id)
        else:
            # Clean the URL
            url = url.strip()
            url = url.split("?")[0]  # Remove query parameters
            url = url.rstrip("/")    # Remove trailing slash
            
            # Extract the type and ID
            if "open.spotify.com" in url:
                parts = url.split("/")
                try:
                    type_name = parts[-2]
                    id = parts[-1]
                except IndexError:
                    raise ValueError("Invalid Spotify URL format")
            else:
                raise ValueError("Invalid Spotify URL or URI format")

        # Map types to collection classes
        type_map = {
            "album": Album,
            "artist": Artist,
            "playlist": Playlist,
            "track": Track,
            "episode": Episode
        }
        
        if type_name not in type_map:
            raise ValueError(f"Unsupported content type: {type_name}")
            
        # Get the API client and make sure we have an active session
        if not self.session:
            raise ValueError("Not logged in")
            
        try:
            collection = type_map[type_name](id, self.session.api(), self.config)
            if not collection.playables:
                raise ValueError("No playable items found in collection")
            return collection
        except Exception as e:
            raise ValueError(f"Failed to create collection: {str(e)}")

    def add_history_item(self, name):
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        box.set_margin_top(5)
        box.set_margin_bottom(5)
        
        label = Gtk.Label(label=name, xalign=0)
        label.set_hexpand(True)
        box.append(label)
        
        success_icon = Gtk.Image.new_from_icon_name("object-select-symbolic")
        box.append(success_icon)
        
        row.set_child(box)
        self.history_list.prepend(row)

    def download_complete(self):
        self.progress_box.set_visible(False)
        self.url_entry.set_text("")
        self.url_entry.set_sensitive(True)
        self.download_button.set_sensitive(True)
        self.show_toast("Download complete!")

    def download_error(self, error):
        self.progress_box.set_visible(False)
        self.url_entry.set_sensitive(True)
        self.download_button.set_sensitive(True)
        
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Download Error",
            body=f"Failed to download: {error}",
        )
        dialog.add_response("ok", "OK")
        dialog.present()

class ZotifyApp(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.connect('activate', self.on_activate)
        
        # Add actions
        self.create_action('preferences', self.on_preferences_action)
        self.create_action('about', self.on_about_action)

    def on_activate(self, app):
        self.win = ZotifyWindow(application=app)
        self.win.present()

    def create_action(self, name, callback):
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)

    def on_preferences_action(self, widget, _):
        dialog = PreferencesDialog(self.win)
        dialog.present()

    def on_about_action(self, widget, _):
        about = Adw.AboutWindow(
            transient_for=self.win,
            application_name='Zotify',
            application_icon='audio-x-generic',
            developer_name='Zotify Contributors',
            version='0.9.7',
            developers=['Zotify Contributors'],
            copyright='© 2024 Zotify Contributors',
            license_type=Gtk.License.CUSTOM,
            website='https://zotify.xyz/',
            issue_url='https://github.com/zotify-dev/zotify/issues'
        )
        about.present()

class PreferencesDialog(Adw.PreferencesWindow):
    def __init__(self, parent):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        
        # Download Settings Page
        self.add_download_page()
        
        # Output Settings Page
        self.add_output_page()
        
        # Advanced Settings Page
        self.add_advanced_page()
        
        # Interface Settings Page
        self.add_interface_page()

    def add_download_page(self):
        page = Adw.PreferencesPage()
        page.set_title("Downloads")
        page.set_icon_name("folder-download-symbolic")
        self.add(page)

        # Audio Quality Group
        quality_group = Adw.PreferencesGroup()
        quality_group.set_title("Audio Quality")
        page.add(quality_group)

        # Quality combo row
        self.quality_row = Adw.ComboRow()
        self.quality_row.set_title("Download Quality")
        self.quality_row.set_subtitle("Audio quality of downloaded songs")
        self.quality_row.set_model(Gtk.StringList.new(["Auto", "Normal", "High", "Very High"]))
        quality_group.add(self.quality_row)

        # Format combo row
        self.format_row = Adw.ComboRow()
        self.format_row.set_title("Audio Format")
        self.format_row.set_subtitle("The download audio format")
        self.format_row.set_model(Gtk.StringList.new(["Vorbis", "AAC", "FDK AAC", "MP3", "OPUS", "FLAC", "WAV"]))
        quality_group.add(self.format_row)

        # Bitrate row
        self.bitrate_row = Adw.SpinRow()
        self.bitrate_row.set_title("Transcode Bitrate")
        self.bitrate_row.set_subtitle("Overwrite the bitrate for ffmpeg encoding (kbps)")
        self.bitrate_row.set_range(0, 320)
        self.bitrate_row.set_value(160)
        quality_group.add(self.bitrate_row)

        # Download Behavior Group
        behavior_group = Adw.PreferencesGroup()
        behavior_group.set_title("Download Behavior")
        page.add(behavior_group)

        # Skip existing files
        self.skip_existing = Adw.SwitchRow()
        self.skip_existing.set_title("Skip Existing Files")
        self.skip_existing.set_subtitle("Skip songs with the same name")
        behavior_group.add(self.skip_existing)

        # Skip previously downloaded
        self.skip_previous = Adw.SwitchRow()
        self.skip_previous.set_title("Skip Previously Downloaded")
        self.skip_previous.set_subtitle("Use a song archive file to skip previously downloaded songs")
        behavior_group.add(self.skip_previous)

        # Download lyrics
        self.download_lyrics = Adw.SwitchRow()
        self.download_lyrics.set_title("Download Lyrics")
        self.download_lyrics.set_subtitle("Downloads synced lyrics in .lrc format")
        behavior_group.add(self.download_lyrics)

    def add_output_page(self):
        page = Adw.PreferencesPage()
        page.set_title("Output")
        page.set_icon_name("folder-music-symbolic")
        self.add(page)

        # Paths Group
        paths_group = Adw.PreferencesGroup()
        paths_group.set_title("Save Locations")
        page.add(paths_group)

        # Music folder
        self.music_dir_row = self.create_folder_row(
            "Music Directory",
            "Directory where Zotify saves music",
            str(Path.home() / "Music/Zotify")
        )
        paths_group.add(self.music_dir_row)

        # Podcast folder
        self.podcast_dir_row = self.create_folder_row(
            "Podcast Directory",
            "Directory where Zotify saves podcasts",
            str(Path.home() / "Podcasts/Zotify")
        )
        paths_group.add(self.podcast_dir_row)

        # Organization Group
        org_group = Adw.PreferencesGroup()
        org_group.set_title("Organization")
        page.add(org_group)

        # Split album discs
        self.split_discs = Adw.SwitchRow()
        self.split_discs.set_title("Split Album Discs")
        self.split_discs.set_subtitle("Saves each disk in its own folder")
        org_group.add(self.split_discs)

    def add_advanced_page(self):
        page = Adw.PreferencesPage()
        page.set_title("Advanced")
        page.set_icon_name("applications-engineering-symbolic")
        self.add(page)

        # Performance Group
        perf_group = Adw.PreferencesGroup()
        perf_group.set_title("Performance")
        page.add(perf_group)

        # Chunk size
        self.chunk_size = Adw.SpinRow()
        self.chunk_size.set_title("Chunk Size")
        self.chunk_size.set_subtitle("Size of download chunks in bytes")
        self.chunk_size.set_range(1000, 100000)
        self.chunk_size.set_value(20000)
        perf_group.add(self.chunk_size)

        # Wait time
        self.wait_time = Adw.SpinRow()
        self.wait_time.set_title("Bulk Wait Time")
        self.wait_time.set_subtitle("The wait time between bulk downloads (seconds)")
        self.wait_time.set_range(0, 10)
        self.wait_time.set_value(1)
        perf_group.add(self.wait_time)

        # Retry attempts
        self.retry_attempts = Adw.SpinRow()
        self.retry_attempts.set_title("Retry Attempts")
        self.retry_attempts.set_subtitle("Number of times to retry failed requests")
        self.retry_attempts.set_range(0, 10)
        self.retry_attempts.set_value(3)
        perf_group.add(self.retry_attempts)

        # Download modes
        self.real_time = Adw.SwitchRow()
        self.real_time.set_title("Real-time Download")
        self.real_time.set_subtitle("Downloads songs as fast as they would be played")
        perf_group.add(self.real_time)

        # Metadata Group
        meta_group = Adw.PreferencesGroup()
        meta_group.set_title("Metadata")
        page.add(meta_group)

        # Save all genres
        self.all_genres = Adw.SwitchRow()
        self.all_genres.set_title("Save All Genres")
        self.all_genres.set_subtitle("Save all relevant genres in metadata")
        meta_group.add(self.all_genres)

        # Genre delimiter
        self.genre_delimiter = Adw.EntryRow()
        self.genre_delimiter.set_title("Genre Delimiter")
        self.genre_delimiter.set_text(",")
        meta_group.add(self.genre_delimiter)

    def add_interface_page(self):
        page = Adw.PreferencesPage()
        page.set_title("Interface")
        page.set_icon_name("preferences-system-symbolic")
        self.add(page)

        # Display Group
        display_group = Adw.PreferencesGroup()
        display_group.set_title("Display")
        page.add(display_group)

        # Show splash
        self.show_splash = Adw.SwitchRow()
        self.show_splash.set_title("Show Splash Screen")
        self.show_splash.set_subtitle("Show the Zotify logo at startup")
        display_group.add(self.show_splash)

        # Progress options
        self.show_progress = Adw.SwitchRow()
        self.show_progress.set_title("Show Progress")
        self.show_progress.set_subtitle("Show download progress bars")
        display_group.add(self.show_progress)

        self.show_skips = Adw.SwitchRow()
        self.show_skips.set_title("Show Skips")
        self.show_skips.set_subtitle("Show messages if a song is being skipped")
        display_group.add(self.show_skips)

        self.show_errors = Adw.SwitchRow()
        self.show_errors.set_title("Show Errors")
        self.show_errors.set_subtitle("Show error messages")
        display_group.add(self.show_errors)

        # Language Group
        lang_group = Adw.PreferencesGroup()
        lang_group.set_title("Language")
        page.add(lang_group)

        # Language combo
        self.language_row = Adw.ComboRow()
        self.language_row.set_title("Interface Language")
        self.language_row.set_subtitle("Language for spotify metadata")
        self.language_row.set_model(Gtk.StringList.new(["English", "Spanish", "French", "German"]))
        lang_group.add(self.language_row)

    def create_folder_row(self, title, subtitle, default_path):
        row = Adw.ActionRow()
        row.set_title(title)
        row.set_subtitle(subtitle)

        # Create box for path display and button
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        
        # Path label
        path_label = Gtk.Label(label=default_path)
        path_label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        path_label.set_xalign(0)
        box.append(path_label)
        
        # Browse button
        button = Gtk.Button()
        button.set_icon_name("folder-symbolic")
        button.add_css_class("flat")
        button.connect("clicked", self.on_folder_clicked, path_label)
        box.append(button)
        
        row.add_suffix(box)
        return row

    def on_folder_clicked(self, button, path_label):
        dialog = Gtk.FileChooserDialog(
            title="Select Folder",
            parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        dialog.add_buttons(
            "_Cancel",
            Gtk.ResponseType.CANCEL,
            "_Select",
            Gtk.ResponseType.ACCEPT,
        )
        dialog.connect("response", self.on_folder_response, path_label)
        dialog.show()

    def on_folder_response(self, dialog, response, path_label):
        if response == Gtk.ResponseType.ACCEPT:
            path_label.set_text(dialog.get_file().get_path())
        dialog.destroy()

class ZotifyApp(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.connect('activate', self.on_activate)
        
        # Add actions
        self.create_action('preferences', self.on_preferences_action)
        self.create_action('about', self.on_about_action)

    def on_activate(self, app):
        self.win = ZotifyWindow(application=app)
        self.win.present()

    def create_action(self, name, callback):
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)

    def on_preferences_action(self, widget, _):
        dialog = PreferencesDialog(self.win)
        dialog.present()

    def on_about_action(self, widget, _):
        about = Adw.AboutWindow(
            transient_for=self.win,
            application_name='Zotify',
            application_icon='audio-x-generic',
            developer_name='Zotify Contributors',
            version='0.9.7',
            developers=['Zotify Contributors'],
            copyright='© 2024 Zotify Contributors',
            license_type=Gtk.License.CUSTOM,
            website='https://zotify.xyz/',
            issue_url='https://github.com/zotify-dev/zotify/issues'
        )
        about.present()

def main():
    app = ZotifyApp(application_id="xyz.zotify.Gui")
    return app.run(None)

if __name__ == "__main__":
    main()
