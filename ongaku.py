#!/usr/bin/env python3
import curses
import threading
import json
import yt_dlp
import vlc
import os
import time
import uuid
import signal
import sys
import struct
import math
from pathlib import Path
from typing import List, Dict, Optional

class MusicPlayer:
    def __init__(self):
        self.search_results = []
        
        # Try to initialize VLC with better error handling
        try:
            # Try to find VLC library explicitly
            import os
            import platform
            
            # Set VLC plugin path for different platforms
            if platform.system() == 'Linux':
                # Common VLC locations on Linux
                vlc_paths = ['/usr/lib/vlc', '/usr/lib64/vlc', '/usr/local/lib/vlc']
                for path in vlc_paths:
                    if os.path.exists(path):
                        os.environ['VLC_PLUGIN_PATH'] = path
                        break
            
            self.vlc_instance = vlc.Instance('--no-video', '--quiet')
            if self.vlc_instance is None:
                raise Exception("VLC instance creation failed")
            self.player = self.vlc_instance.media_player_new()
        except Exception as e:
            print(f"Error: Could not initialize VLC. Please make sure VLC is installed.")
            print(f"On Linux: sudo apt install vlc (or your distro's equivalent)")
            print(f"On Windows: Download from https://www.videolan.org/vlc/")
            print(f"On macOS: brew install vlc")
            import sys
            sys.exit(1)
        self.is_playing = False
        self.current_track = None
        self.current_duration = 0  # Track duration in seconds
        self.stream_cache = {}  # Cache extracted stream URLs
        self.current_query = ""  # Store current search query for pagination
        self.total_fetched = 0  # Track how many results we've fetched
        self.volume = 100  # Default volume (0-100)
        self.favorites = []  # List of favorite tracks
        self.favorites_file = Path.home() / "ongaku" / "favorites.json"
        self.playlists = []  # List of playlists
        self.playlists_file = Path.home() / "ongaku" / "playlists.json"
        self.current_playlist = None  # Currently playing playlist
        self.current_playlist_index = -1  # Current track index in playlist
        self.visualizer = None  # Reference to visualizer for immediate clearing
        self.load_favorites()
        self.load_playlists()
        
    def search_youtube(self, query: str, limit: int = 10) -> List[Dict]:
        """Search YouTube using yt-dlp and return results"""
        self.current_query = query
        self.total_fetched = 0
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'force_generic_extractor': False,
        }
        
        results = []
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                search_results = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
                
                for entry in search_results.get('entries', []):
                    results.append({
                        'title': entry.get('title', 'Unknown'),
                        'url': f"https://youtube.com/watch?v={entry.get('id', '')}",
                        'duration': entry.get('duration', 0),
                        'uploader': entry.get('uploader', 'Unknown'),
                        'id': entry.get('id', '')
                    })
                self.total_fetched = len(results)
        except Exception as e:
            pass
            
        return results
    
    def fetch_more_results(self, count: int = 10) -> List[Dict]:
        """Fetch more results for the current query"""
        if not self.current_query:
            return []
            
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'force_generic_extractor': False,
        }
        
        new_results = []
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # YouTube search actually fetches more results than requested
                # We fetch a larger batch and slice what we need
                total_to_fetch = self.total_fetched + count + 10
                search_results = ydl.extract_info(f"ytsearch{total_to_fetch}:{self.current_query}", download=False)
                
                entries = search_results.get('entries', [])
                # Get only the new results we haven't seen yet
                for entry in entries[self.total_fetched:self.total_fetched + count]:
                    if entry:  # Make sure entry exists
                        new_results.append({
                            'title': entry.get('title', 'Unknown'),
                            'url': f"https://youtube.com/watch?v={entry.get('id', '')}",
                            'duration': entry.get('duration', 0),
                            'uploader': entry.get('uploader', 'Unknown'),
                            'id': entry.get('id', '')
                        })
                
                self.total_fetched += len(new_results)
        except Exception as e:
            pass
            
        return new_results
    
    def extract_stream_url(self, url: str) -> Optional[str]:
        """Extract direct stream URL from YouTube URL"""
        video_id = url.split('watch?v=')[-1] if 'watch?v=' in url else url.split('/')[-1]
        
        # Check cache first
        if video_id in self.stream_cache:
            return self.stream_cache[video_id]
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'logger': None,  # Disable logging
            'no_color': True,
            'nocheckcertificate': True,  # Help with SSL issues
            'ignoreerrors': True,  # Continue on errors
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                stream_url = info.get('url') if info else None
                
                # Cache the stream URL
                if stream_url:
                    self.stream_cache[video_id] = stream_url
                
                return stream_url
        except Exception:
            return None
    
    def play_track(self, url: str, title: str, duration: int = 0, from_playlist=False):
        """Play a track using VLC"""
        self.stop(clear_playlist=not from_playlist)  # Stop current playback, preserve playlist context if needed
        
        # Clear visualizer immediately when starting new track
        if self.visualizer:
            self.visualizer.clear_immediately()
        
        # Extract stream URL
        stream_url = self.extract_stream_url(url)
        if not stream_url:
            return False
        
        self.current_track = title
        self.current_duration = duration
        
        # Create media and play
        media = self.vlc_instance.media_new(stream_url)
        self.player.set_media(media)
        self.player.audio_set_volume(self.volume)
        self.player.play()
        
        self.is_playing = True
        return True
    
    def stop(self, clear_playlist=True):
        """Stop current playback"""
        if self.player:
            self.player.stop()
            self.is_playing = False
            self.current_track = None
            self.current_duration = 0
            if clear_playlist:
                self.current_playlist = None
                self.current_playlist_index = -1
    
    def toggle_pause(self):
        """Toggle pause/play"""
        if self.player and self.is_playing:
            self.player.pause()
    
    def set_volume(self, volume: int):
        """Set volume (0-100)"""
        self.volume = max(0, min(100, volume))
        if self.player:
            self.player.audio_set_volume(self.volume)
    
    def volume_up(self):
        """Increase volume by 5"""
        self.set_volume(self.volume + 5)
    
    def volume_down(self):
        """Decrease volume by 5"""
        self.set_volume(self.volume - 5)
    
    def get_current_time(self):
        """Get current playback position in seconds"""
        if self.player and self.is_playing:
            time_ms = self.player.get_time()
            if time_ms != -1:
                current_seconds = time_ms // 1000
                # Cap at duration to prevent showing times beyond track length
                if self.current_duration > 0:
                    return min(current_seconds, self.current_duration)
                return current_seconds
        return 0
    
    def get_progress_info(self):
        """Get current time, duration, and progress percentage"""
        current_time = self.get_current_time()
        if self.current_duration > 0:
            progress = current_time / self.current_duration
        else:
            progress = 0
        return current_time, self.current_duration, progress
    
    def load_favorites(self):
        """Load favorites from JSON file"""
        try:
            if self.favorites_file.exists():
                with open(self.favorites_file, 'r') as f:
                    self.favorites = json.load(f)
        except Exception:
            self.favorites = []
    
    def save_favorites(self):
        """Save favorites to JSON file"""
        try:
            # Create directory if it doesn't exist
            self.favorites_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.favorites_file, 'w') as f:
                json.dump(self.favorites, f, indent=2)
        except Exception:
            pass
    
    def add_to_favorites(self, track: Dict):
        """Add a track to favorites"""
        # Check if track is already in favorites (by ID)
        if not any(fav.get('id') == track.get('id') for fav in self.favorites):
            self.favorites.append(track)
            self.save_favorites()
            return True
        return False
    
    def remove_from_favorites(self, track_id: str):
        """Remove a track from favorites by ID"""
        original_len = len(self.favorites)
        self.favorites = [fav for fav in self.favorites if fav.get('id') != track_id]
        if len(self.favorites) < original_len:
            self.save_favorites()
            return True
        return False
    
    def is_favorite(self, track_id: str) -> bool:
        """Check if a track is in favorites"""
        return any(fav.get('id') == track_id for fav in self.favorites)
    
    def load_playlists(self):
        """Load playlists from JSON file"""
        try:
            if self.playlists_file.exists():
                with open(self.playlists_file, 'r') as f:
                    self.playlists = json.load(f)
        except Exception:
            self.playlists = []
    
    def save_playlists(self):
        """Save playlists to JSON file"""
        try:
            # Create directory if it doesn't exist
            self.playlists_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.playlists_file, 'w') as f:
                json.dump(self.playlists, f, indent=2)
        except Exception:
            pass
    
    def create_playlist(self, name: str, tracks: List[Dict]) -> bool:
        """Create a new playlist"""
        if not name or not tracks:
            return False
        
        playlist = {
            'id': str(uuid.uuid4()),
            'name': name,
            'tracks': tracks,
            'created': time.time()
        }
        self.playlists.append(playlist)
        self.save_playlists()
        return True
    
    def update_playlist(self, playlist_id: str, name: str, tracks: List[Dict]) -> bool:
        """Update an existing playlist"""
        if not name or not tracks:
            return False
        
        for i, playlist in enumerate(self.playlists):
            if playlist.get('id') == playlist_id:
                self.playlists[i]['name'] = name
                self.playlists[i]['tracks'] = tracks
                self.save_playlists()
                return True
        return False
    
    def delete_playlist(self, playlist_id: str) -> bool:
        """Delete a playlist by ID"""
        original_len = len(self.playlists)
        self.playlists = [p for p in self.playlists if p.get('id') != playlist_id]
        if len(self.playlists) < original_len:
            self.save_playlists()
            return True
        return False
    
    def play_playlist_track(self, playlist_id: str, track_index: int):
        """Play a specific track from a playlist"""
        playlist = next((p for p in self.playlists if p.get('id') == playlist_id), None)
        if not playlist or track_index >= len(playlist.get('tracks', [])):
            return False
        
        self.current_playlist = playlist
        self.current_playlist_index = track_index
        track = playlist['tracks'][track_index]
        return self.play_track(track['url'], track['title'], track.get('duration', 0), from_playlist=True)
    
    def play_next_in_playlist(self):
        """Play the next track in the current playlist"""
        if not self.current_playlist:
            return False
        
        tracks = self.current_playlist.get('tracks', [])
        if not tracks:
            return False
        
        # Move to next track or loop back to start
        self.current_playlist_index = (self.current_playlist_index + 1) % len(tracks)
        track = tracks[self.current_playlist_index]
        
        # Force stop current track first
        if self.player:
            self.player.stop()
        
        # Add a small delay to ensure clean transition
        import time
        time.sleep(0.2)
        
        # Try to play next track with error handling
        try:
            success = self.play_track(track['url'], track['title'], track.get('duration', 0), from_playlist=True)
            return success
        except Exception:
            # If this track fails, try the next one
            if len(tracks) > 1:
                return self.play_next_in_playlist()
            return False
    
    def check_playback_status(self):
        """Check if current track has ended and handle playlist continuation"""
        if not self.is_playing or not self.player or not self.current_playlist:
            return
        
        current_time = self.get_current_time()
        state = self.player.get_state()
        
        # Track ended if VLC reports ended state or we've reached the end
        track_ended = (
            state == vlc.State.Ended or 
            (self.current_duration > 0 and current_time >= self.current_duration - 1)
        )
        
        if track_ended:
            self.is_playing = False
            self.play_next_in_playlist()

class AudioVisualizer:
    def __init__(self, bars=15):
        self.bars = bars
        self.frequency_bands = [0.0] * bars
        self.current_track = None  # Track the current song to detect changes
        self.needs_redraw = False  # Flag to force immediate redraw
        
    def update_from_vlc(self, player):
        """Sophisticated audio analysis using VLC data"""
        if not player or not player.is_playing:
            # Clear all bars immediately when not playing
            for i in range(len(self.frequency_bands)):
                self.frequency_bands[i] = 0.0
            self.current_track = None
            return
            
        # Check if actually playing (not paused)
        try:
            vlc_state = player.get_state()
            if vlc_state == vlc.State.Paused:
                # Paused - fade out slowly
                for i in range(len(self.frequency_bands)):
                    self.frequency_bands[i] *= 0.92  # Slow fade
                return
            elif vlc_state != vlc.State.Playing:
                # Stopped or other non-playing state - clear immediately
                for i in range(len(self.frequency_bands)):
                    self.frequency_bands[i] = 0.0
                return
        except:
            # If we can't get state, clear immediately
            for i in range(len(self.frequency_bands)):
                self.frequency_bands[i] = 0.0
            return
            
        # Get VLC playback data
        volume = player.audio_get_volume()
        time_ms = player.get_time()
        
        if volume < 0 or time_ms <= 0:
            return
        
        # Check if track changed - clear visualizer immediately like progress bar
        try:
            current_media = player.get_media()
            media_id = str(current_media) if current_media else None
            if self.current_track != media_id:
                # Track changed - clear bars immediately
                for i in range(len(self.frequency_bands)):
                    self.frequency_bands[i] = 0.0
                self.current_track = media_id
                return  # Skip this update to show immediate clearing
        except:
            pass
        
        # Sophisticated frequency analysis based on real playback data
        base_amplitude = volume / 100.0
        time_factor = (time_ms / 1000.0) * 2.0
        
        for i in range(self.bars):
            freq_ratio = i / (self.bars - 1)
            
            # Different frequency bands behave differently
            if freq_ratio < 0.3:  # Bass range
                base_level = 0.7
                variation = math.sin(time_factor * 1.2 + i * 0.5) * 0.4
                bass_boost = math.sin(time_factor * 0.8) * 0.3
                target = base_level + variation + bass_boost
            elif freq_ratio < 0.7:  # Mid range  
                base_level = 0.5
                variation = math.sin(time_factor * 1.8 + i * 0.3) * 0.3
                mid_boost = math.cos(time_factor * 1.1) * 0.2
                target = base_level + variation + mid_boost
            else:  # Treble range
                base_level = 0.4
                variation = math.sin(time_factor * 2.5 + i * 0.8) * 0.4
                treble_spike = math.sin(time_factor * 3.0) * 0.2
                target = base_level + variation + treble_spike
            
            # Scale by actual volume
            target *= base_amplitude
            target = max(0.0, min(1.0, target))
            
            # Smooth transitions for realistic audio feel
            if target > self.frequency_bands[i]:
                smoothing = 0.6  # Quick attack
            else:
                smoothing = 0.2  # Slower decay
                
            self.frequency_bands[i] = (smoothing * target + 
                                     (1 - smoothing) * self.frequency_bands[i])
    
    def get_bars(self, max_height=6):
        """Get visualizer bars scaled to max_height"""
        bars = []
        for level in self.frequency_bands:
            bar_height = int(level * max_height)
            bars.append(min(bar_height, max_height))
        return bars
    
    def clear_immediately(self):
        """Clear all visualizer bars immediately - for track changes"""
        for i in range(len(self.frequency_bands)):
            self.frequency_bands[i] = 0.0
        self.current_track = None
        self.needs_redraw = True  # Flag to force immediate redraw

class MusicPlayerUI:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.player = MusicPlayer()
        self.search_query = ""
        self.selected_index = 0
        self.prev_selected_index = -1  # Track previous selection for partial updates
        self.mode = "main"  # "main", "search", "results", "playlist_create", "playlist_view"
        self.status_message = "Press '/' to search, 'q' to quit"
        self.height, self.width = self.stdscr.getmaxyx()
        self.is_loading_more = False  # Track if we're loading more results
        self.scroll_offset = 0  # Track viewport scrolling
        # Calculate actual visible lines: from line 7 to height-4 (exclusive)
        # Account for visualizer taking 4 lines at the bottom
        self.visible_lines = max(1, self.height - 15)  # Adjusted for actual space available and visualizer
        self.volume_display_until = 0  # Timestamp until which to show volume
        self.viewing_favorites = True  # Flag to track if we're viewing favorites in main mode
        self.playlist_creation_mode = False  # Track if we're creating a playlist
        self.playlist_selected_tracks = []  # Tracks selected for new playlist
        self.playlist_name = ""  # Name for new playlist
        self.current_viewing_playlist = None  # Currently viewing playlist
        self.main_view_type = "combined"  # "combined", "favorites", or "playlists"
        self.editing_playlist_id = None  # ID of playlist being edited
        self.title_scroll_offset = 0  # Current scroll position for long titles
        self.title_scroll_direction = 1  # 1 for right, -1 for left
        self.last_title_scroll_update = 0  # Last time we updated title scroll
        self.resize_detected = False  # Flag for terminal resize detection
        self.visualizer = AudioVisualizer(bars=15)  # Audio visualizer
        
        # Connect visualizer to player for immediate clearing
        self.player.visualizer = self.visualizer
        
        # Setup resize detection
        signal.signal(signal.SIGWINCH, self.handle_resize)
        
        # Setup colors with terminal's default background
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        curses.init_pair(3, curses.COLOR_YELLOW, -1)
        curses.init_pair(4, curses.COLOR_RED, -1)
        
        # Draw static elements once
        self.draw_static_ui()
        
    def handle_resize(self, signum=None, frame=None):
        """Handle terminal resize signal"""
        # Set flag safely without curses operations
        self.resize_detected = True
        
    def update_dimensions(self):
        """Update terminal dimensions and recalculate layout"""
        old_height, old_width = self.height, self.width
        self.height, self.width = self.stdscr.getmaxyx()
        
        # Recalculate visible lines based on new dimensions
        # Account for visualizer taking 4 lines at the bottom
        self.visible_lines = max(1, self.height - 15)
        
        # Adjust scroll offset if terminal got smaller
        if hasattr(self, 'main_display_items'):
            max_items = len(self.main_display_items)
        elif self.mode == "playlist_view" and self.current_viewing_playlist:
            max_items = len(self.current_viewing_playlist.get('tracks', []))
        elif self.mode in ["results", "main"]:
            if self.mode == "main":
                max_items = len(self.player.favorites) + len(self.player.playlists)
            else:
                max_items = len(self.player.search_results)
        else:
            max_items = 0
        
        # Ensure scroll offset doesn't go beyond available items
        if max_items > 0:
            max_scroll = max(0, max_items - self.visible_lines)
            self.scroll_offset = min(self.scroll_offset, max_scroll)
            
            # Ensure selected index is still visible
            if self.selected_index >= max_items:
                self.selected_index = max(0, max_items - 1)
        
        self.resize_detected = False
        return old_height != self.height or old_width != self.width
        
    def draw_static_ui(self):
        """Draw static UI elements that don't change"""
        # Make sure we have minimum terminal size
        if self.height < 10 or self.width < 20:
            self.stdscr.addstr(0, 0, "Terminal too small")
            self.stdscr.refresh()
            return
            
        try:
            header = "🎵 Ongaku 🎵"
            header_pos = max(0, (self.width - len(header)) // 2)
            self.stdscr.addstr(0, header_pos, header[:self.width-1], curses.color_pair(1) | curses.A_BOLD)
            self.stdscr.addstr(1, 0, "─" * (self.width-1))
            search_prompt = "Search: "
            if self.height > 3:
                self.stdscr.addstr(3, 2, search_prompt, curses.color_pair(2))
            if self.height > 3:
                self.stdscr.addstr(self.height - 3, 0, "─" * (self.width-1))
            self.draw_controls()
            self.stdscr.refresh()
        except curses.error:
            # If drawing fails, just refresh and continue
            self.stdscr.refresh()
        
    def update_search_bar(self):
        """Update only the search input area"""
        search_prompt_len = 9  # "Search: " length
        # Clear the search area
        self.stdscr.move(3, 2 + search_prompt_len)
        self.stdscr.clrtoeol()
        
        if self.mode == "search":
            self.stdscr.addstr(3, 2 + search_prompt_len, self.search_query + "_")
        else:
            self.stdscr.addstr(3, 2 + search_prompt_len, self.search_query)
        self.stdscr.refresh()
    
    def update_result_line(self, index):
        """Update a single result line"""
        # Determine which list to use
        if self.mode == "main" and hasattr(self, 'main_display_items'):
            # Use the combined display items for main page
            display_list = self.main_display_items
        elif self.mode == "main":
            display_list = self.player.favorites
        elif self.mode == "playlist_view" and self.current_viewing_playlist:
            display_list = self.current_viewing_playlist.get('tracks', [])
        else:
            display_list = self.player.search_results
            
        if not display_list or index >= len(display_list):
            return
            
        # Calculate display position relative to viewport
        display_index = index - self.scroll_offset
        if display_index < 0 or display_index >= self.visible_lines:
            return  # Outside visible area
            
        y_pos = 7 + display_index
        if y_pos >= self.height - 8:  # Don't draw outside bounds (account for visualizer)
            return
            
        # Handle different item types for main page and playlist view
        if self.mode == "main" and hasattr(self, 'main_display_items'):
            item = display_list[index]
            
            # Clear the line
            self.stdscr.move(y_pos, 2)
            self.stdscr.clrtoeol()
            
            # Format duration for both favorites and playlists
            duration_str = ""
            if item.get('duration'):
                duration = item['duration']
                minutes = int(duration // 60)
                seconds = int(duration % 60)
                duration_str = f"[{minutes}:{seconds:02d}]"
            
            # Get title
            title_width = self.width - 10 if not duration_str else self.width - 20
            title = item['title'][:title_width] if len(item['title']) > title_width else item['title']
            line = f"{index+1:2}. {title}"
            
            # Highlight selected item
            if index == self.selected_index:
                self.stdscr.addstr(y_pos, 2, "▶ ", curses.color_pair(2))
                self.stdscr.addstr(y_pos, 4, line, curses.A_REVERSE)
                if duration_str and self.width - len(duration_str) - 2 > 0:
                    self.stdscr.addstr(y_pos, self.width - len(duration_str) - 2, duration_str, curses.A_REVERSE)
            else:
                self.stdscr.addstr(y_pos, 2, "  ")
                self.stdscr.addstr(y_pos, 4, line)
                if duration_str and self.width - len(duration_str) - 2 > 0:
                    self.stdscr.addstr(y_pos, self.width - len(duration_str) - 2, duration_str, curses.color_pair(3))
        elif self.mode == "playlist_view":
            # Handle playlist tracks
            result = display_list[index]
            
            # Clear the line
            self.stdscr.move(y_pos, 2)
            self.stdscr.clrtoeol()
            
            # Format duration
            duration = result.get('duration', 0)
            if duration:
                minutes = int(duration // 60)
                seconds = int(duration % 60)
                duration_str = f"[{minutes}:{seconds:02d}]"
            else:
                duration_str = "[--:--]"
            
            # Format result line
            title = result['title'][:self.width - 30] if len(result['title']) > self.width - 30 else result['title']
            
            # Add favorite indicator
            fav_indicator = "★ " if self.player.is_favorite(result.get('id', '')) else "  "
            line = f"{index+1:2}. {fav_indicator}{title}"
            
            # Highlight selected item
            if index == self.selected_index:
                self.stdscr.addstr(y_pos, 2, "▶ ", curses.color_pair(2))
                self.stdscr.addstr(y_pos, 4, line, curses.A_REVERSE)
                if self.width - len(duration_str) - 2 > 0:
                    self.stdscr.addstr(y_pos, self.width - len(duration_str) - 2, duration_str, curses.A_REVERSE)
            else:
                self.stdscr.addstr(y_pos, 2, "  ")
                self.stdscr.addstr(y_pos, 4, line)
                if self.width - len(duration_str) - 2 > 0:
                    self.stdscr.addstr(y_pos, self.width - len(duration_str) - 2, duration_str, curses.color_pair(3))
        else:
            # Original logic for search results
            result = display_list[index]
            
            # Clear the line
            self.stdscr.move(y_pos, 2)
            self.stdscr.clrtoeol()
            
            # Format duration
            duration = result.get('duration', 0)
            if duration:
                minutes = int(duration // 60)
                seconds = int(duration % 60)
                duration_str = f"[{minutes}:{seconds:02d}]"
            else:
                duration_str = "[--:--]"
            
            # Format result line
            title = result['title'][:self.width - 30] if len(result['title']) > self.width - 30 else result['title']
            
            # Add favorite indicator
            fav_indicator = "★ " if self.player.is_favorite(result.get('id', '')) else "  "
            line = f"{index+1:2}. {fav_indicator}{title}"
            
            # Highlight selected item
            if index == self.selected_index and self.mode in ["results", "main"]:
                self.stdscr.addstr(y_pos, 2, "▶ ", curses.color_pair(2))
                self.stdscr.addstr(y_pos, 4, line, curses.A_REVERSE)
                self.stdscr.addstr(y_pos, self.width - len(duration_str) - 2, duration_str, curses.A_REVERSE)
            else:
                self.stdscr.addstr(y_pos, 2, "  ")
                self.stdscr.addstr(y_pos, 4, line)
                self.stdscr.addstr(y_pos, self.width - len(duration_str) - 2, duration_str, curses.color_pair(3))
    
    def draw_results(self):
        """Draw search results, favorites, playlists, or playlist tracks"""
        height, width = self.stdscr.getmaxyx()
        
        # Determine what to display
        if self.mode == "main":
            # Show both playlists and favorites on main page
            self.draw_main_page()
            return
        elif self.mode == "playlist_view":
            if self.current_viewing_playlist:
                display_list = self.current_viewing_playlist.get('tracks', [])
                if not display_list:
                    self.stdscr.addstr(5, 2, "This playlist is empty.", curses.color_pair(3))
                    return
            else:
                return
        elif self.mode == "playlist_create" or self.mode == "playlist_edit":
            self.draw_playlist_creation()
            return
        else:
            display_list = self.player.search_results
            if not display_list:
                self.stdscr.addstr(5, 2, "No results. Press '/' to search.", curses.color_pair(3))
                return
        
        # Recalculate visible lines based on current terminal size
        results_start_line = 7
        results_end_line = height - 8  # Account for visualizer (4 lines) + controls
        actual_visible_lines = results_end_line - results_start_line
        
        # Update visible_lines if terminal was resized
        self.visible_lines = max(1, actual_visible_lines)
        
        # Results header
        total = len(display_list)
        if self.mode == "playlist_view":
            header = f"{self.current_viewing_playlist['name']}"
        else:
            header = "Search Results"
        self.stdscr.addstr(5, 2, header, curses.color_pair(2) | curses.A_BOLD)
        
        # Clear the results area first
        for line_num in range(results_start_line, results_end_line):
            self.stdscr.move(line_num, 0)
            self.stdscr.clrtoeol()
        
        # Display only visible results within the viewport
        display_row = 0
        for i in range(self.scroll_offset, min(self.scroll_offset + self.visible_lines, total)):
            y_pos = results_start_line + display_row
            
            # Make sure we don't draw outside screen bounds
            if y_pos >= results_end_line:
                break
                
            result = display_list[i]
            
            # Format duration
            duration = result['duration']
            if duration:
                minutes = int(duration // 60)
                seconds = int(duration % 60)
                duration_str = f"[{minutes}:{seconds:02d}]"
            else:
                duration_str = "[--:--]"
            
            # Format result line
            title = result['title'][:width - 30] if len(result['title']) > width - 30 else result['title']
            
            # Add favorite indicator
            fav_indicator = "★ " if self.player.is_favorite(result.get('id', '')) else "  "
            line = f"{i+1:2}. {fav_indicator}{title}"
            
            # Highlight selected item
            if i == self.selected_index and self.mode in ["results", "main", "playlist_view"]:
                self.stdscr.addstr(y_pos, 2, "▶ ", curses.color_pair(2))
                self.stdscr.addstr(y_pos, 4, line, curses.A_REVERSE)
                if width - len(duration_str) - 2 > 0:
                    self.stdscr.addstr(y_pos, width - len(duration_str) - 2, duration_str, curses.A_REVERSE)
            else:
                self.stdscr.addstr(y_pos, 4, line)
                if width - len(duration_str) - 2 > 0:
                    self.stdscr.addstr(y_pos, width - len(duration_str) - 2, duration_str, curses.color_pair(3))
            
            display_row += 1
    
    def draw_main_page(self):
        """Draw the main page with playlists and favorites"""
        height, width = self.stdscr.getmaxyx()
        
        # Combine playlists and favorites for display
        display_items = []
        
        # Add playlists first
        for playlist in self.player.playlists:
            # Calculate total duration of all tracks in playlist
            tracks = playlist.get('tracks', [])
            total_duration = sum(track.get('duration', 0) for track in tracks)
            
            display_items.append({
                'type': 'playlist',
                'data': playlist,
                'title': f"★ {playlist['name']} ({len(tracks)} tracks)",
                'duration': total_duration
            })
        
        # Add favorites
        for fav in self.player.favorites:
            display_items.append({
                'type': 'favorite',
                'data': fav,
                'title': f"★ {fav['title']}",
                'duration': fav.get('duration', 0)
            })
        
        if not display_items:
            self.stdscr.addstr(5, 2, "No playlists or favorites yet. Press '/' to search, 'F' to favorite, 'E' to create playlist.", curses.color_pair(3))
            return
        
        # Header
        header = "Home"
        self.stdscr.addstr(5, 2, header, curses.color_pair(2) | curses.A_BOLD)
        
        # Clear the results area
        results_start_line = 7
        results_end_line = height - 8  # Account for visualizer (4 lines) + controls
        for line_num in range(results_start_line, results_end_line):
            self.stdscr.move(line_num, 0)
            self.stdscr.clrtoeol()
        
        # Display items
        total = len(display_items)
        display_row = 0
        for i in range(self.scroll_offset, min(self.scroll_offset + self.visible_lines, total)):
            y_pos = results_start_line + display_row
            
            if y_pos >= results_end_line:
                break
            
            item = display_items[i]
            
            # Format duration for both favorites and playlists
            duration_str = ""
            if item.get('duration'):
                duration = item['duration']
                minutes = int(duration // 60)
                seconds = int(duration % 60)
                duration_str = f"[{minutes}:{seconds:02d}]"
            
            # Adjust title width based on whether we have duration
            title_width = width - 10 if not duration_str else width - 20
            title = item['title'][:title_width] if len(item['title']) > title_width else item['title']
            line = f"{i+1:2}. {title}"
            
            # Highlight selected item
            if i == self.selected_index:
                self.stdscr.addstr(y_pos, 2, "▶ ", curses.color_pair(2))
                self.stdscr.addstr(y_pos, 4, line, curses.A_REVERSE)
                if duration_str and width - len(duration_str) - 2 > 0:
                    self.stdscr.addstr(y_pos, width - len(duration_str) - 2, duration_str, curses.A_REVERSE)
            else:
                self.stdscr.addstr(y_pos, 4, line)
                if duration_str and width - len(duration_str) - 2 > 0:
                    self.stdscr.addstr(y_pos, width - len(duration_str) - 2, duration_str, curses.color_pair(3))
            
            display_row += 1
        
        # Store display items for navigation
        self.main_display_items = display_items
    
    def draw_playlist_creation(self):
        """Draw playlist creation interface"""
        height, width = self.stdscr.getmaxyx()
        
        # Header
        header_text = "Editing Playlist" if self.mode == "playlist_edit" else "Creating New Playlist"
        self.stdscr.addstr(5, 2, header_text, curses.color_pair(2) | curses.A_BOLD)
        
        # Playlist name input
        self.stdscr.addstr(7, 2, "Playlist Name: ")
        
        # Check if we're still entering the name or selecting tracks
        is_name_confirmed = self.playlist_name.endswith("_CONFIRMED")
        display_name = self.playlist_name.replace("_CONFIRMED", "")
        
        if not is_name_confirmed:
            # Still entering name - show cursor
            self.stdscr.addstr(7, 17, display_name + "_")
        else:
            # Name confirmed - show without cursor
            self.stdscr.addstr(7, 17, display_name)
        
        # Show favorites for selection
        if is_name_confirmed and not self.player.favorites:
            self.stdscr.addstr(9, 2, "No favorites to add. Press ESC to cancel.", curses.color_pair(3))
            return
        elif is_name_confirmed:
            self.stdscr.addstr(9, 2, "Select tracks (SPACE to toggle, ENTER to create, ESC to cancel):", curses.color_pair(3))
            
            results_start_line = 11
            results_end_line = height - 8  # Account for visualizer (4 lines) + controls
            
            # Clear the area
            for line_num in range(results_start_line, results_end_line):
                self.stdscr.move(line_num, 0)
                self.stdscr.clrtoeol()
            
            # Display favorites with checkboxes
            display_row = 0
            for i, fav in enumerate(self.player.favorites):
                if display_row >= self.visible_lines - 4:
                    break
                    
                y_pos = results_start_line + display_row
                if y_pos >= results_end_line:
                    break
                
                # Check if selected
                is_selected = any(t.get('id') == fav.get('id') for t in self.playlist_selected_tracks)
                checkbox = "[X]" if is_selected else "[ ]"
                
                title = fav['title'][:width - 15] if len(fav['title']) > width - 15 else fav['title']
                line = f"{checkbox} {title}"
                
                # Highlight current item
                if i == self.selected_index:
                    self.stdscr.addstr(y_pos, 2, "▶ ", curses.color_pair(2))
                    self.stdscr.addstr(y_pos, 4, line, curses.A_REVERSE)
                else:
                    self.stdscr.addstr(y_pos, 4, line)
                
                display_row += 1
    
    def draw_controls(self):
        """Draw controls line (static)"""
        if self.height < 2:
            return  # Not enough space for controls
            
        try:
            if self.mode == "playlist_create":
                controls = "Enter : Create | Space : Toggle | ESC : Cancel"
            elif self.mode == "playlist_edit":
                controls = "Enter : Update | Space : Toggle | D : Delete | ESC : Cancel"
            elif self.mode == "playlist_view":
                controls = "Enter : Play | E : Edit | ESC : Main | q : Quit"
            else:
                controls = "/ : Search | ↑↓ : Navigate | Enter : Play/Open | F : Fav | E : Playlist | Space : Pause | ESC : Main | q : Quit"
                if len(controls) > self.width:
                    controls = "/ : Search | Enter : Play | F : Fav | E : Playlist | Space : Pause | q : Quit"
            
            # Truncate to fit and ensure we don't go out of bounds
            controls = controls[:self.width-1]
            x_pos = max(0, min((self.width - len(controls)) // 2, self.width - len(controls) - 1))
            self.stdscr.addstr(self.height - 1, x_pos, controls, curses.color_pair(3))
        except curses.error:
            # If controls can't be drawn, just skip them
            pass
    
    def get_scrollable_title(self, title, max_width):
        """Get scrollable version of title if it's too long"""
        if len(title) <= max_width:
            self.title_scroll_offset = 0  # Reset scroll for short titles
            return title
        
        # Create seamless repeating text: "Title   Title   Title   "
        separator = "   "  # 3 spaces between repetitions
        repeat_unit = title + separator
        
        # Create enough repetitions to fill any possible scroll position
        # We need at least 3 repetitions to ensure seamless scrolling
        repeated_title = repeat_unit * 3
        
        # Reset scroll when we've scrolled through one complete cycle
        if self.title_scroll_offset >= len(repeat_unit):
            self.title_scroll_offset = 0
        
        # Extract the visible portion
        visible_text = repeated_title[self.title_scroll_offset:self.title_scroll_offset + max_width]
        
        # If we don't have enough characters (edge case), pad with spaces
        if len(visible_text) < max_width:
            visible_text = visible_text.ljust(max_width)
        
        return visible_text
    
    def update_title_scroll(self):
        """Update title scrolling animation"""
        current_time = time.time()
        if current_time - self.last_title_scroll_update >= 0.15:  # Update every 150ms (faster)
            self.title_scroll_offset += 1
            self.last_title_scroll_update = current_time
            return True
        return False

    def draw_visualizer(self):
        """Draw audio visualizer bars at the bottom"""
        # Get visualizer data
        bars = self.visualizer.get_bars(max_height=4)  # Smaller height for bottom placement
        
        # Calculate position - center it horizontally
        visualizer_width = len(bars) * 2  # 2 chars per bar (bar + space)
        start_x = max(2, (self.width - visualizer_width) // 2)
        
        # Position it at the bottom, above the controls line
        visualizer_y = self.height - 6  # Above status bar and controls
        visualizer_height = 4
        
        if visualizer_y < 0:  # Make sure it fits
            return
            
        try:
            # Clear the visualizer area
            for y in range(visualizer_y, visualizer_y + visualizer_height):
                if y >= 0 and y < self.height - 2:
                    self.stdscr.move(y, 0)
                    self.stdscr.clrtoeol()
            
            # Only draw if there's audio activity
            if any(bar > 0 for bar in bars):
                # Draw bars from bottom up
                bar_chars = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
                
                for i, height in enumerate(bars):
                    x_pos = start_x + (i * 2)
                    if x_pos >= self.width - 1:
                        break
                        
                    # Draw the bar from bottom to top
                    for y in range(visualizer_height):
                        y_pos = visualizer_y + (visualizer_height - 1 - y)  # Start from bottom
                        if y_pos < 0 or y_pos >= self.height - 2:
                            continue
                            
                        if y < height:
                            # Use different characters for different heights
                            if y == height - 1 and height < visualizer_height:
                                # Top of bar - use partial character
                                char_idx = min(height - 1, len(bar_chars) - 1)
                                self.stdscr.addstr(y_pos, x_pos, bar_chars[char_idx], curses.color_pair(2))
                            else:
                                # Full bar segment
                                self.stdscr.addstr(y_pos, x_pos, "█", curses.color_pair(2))
                        
        except curses.error:
            # If drawing fails, just skip the visualizer
            pass

    def format_time(self, seconds):
        """Format seconds as MM:SS"""
        minutes = int(seconds // 60)
        seconds = int(seconds % 60)
        return f"{minutes}:{seconds:02d}"
    
    def draw_progress_bar(self, current_time, duration, progress, bar_width=30):
        """Draw a progress bar"""
        if duration <= 0:
            return "[--:--] " + "─" * bar_width + " [--:--]"
        
        filled = int(progress * bar_width)
        empty = bar_width - filled
        
        current_str = self.format_time(current_time)
        duration_str = self.format_time(duration)
        
        bar = "█" * filled + "░" * empty
        return f"[{current_str}] {bar} [{duration_str}]"
    
    def update_status(self):
        """Update only the status line"""
        import time
        current_time_stamp = time.time()
        show_volume = current_time_stamp < self.volume_display_until
        
        # Clear status line
        self.stdscr.move(self.height - 2, 2)
        self.stdscr.clrtoeol()
        
        # Now playing with progress bar or status message
        if self.player.is_playing and self.player.current_track:
            current_time, duration, progress = self.player.get_progress_info()
            
            # Calculate components and their sizes
            music_icon = "♫ "
            time_current = self.format_time(current_time) if duration > 0 else "--:--"
            time_duration = self.format_time(duration) if duration > 0 else "--:--"
            time_display = f"[{time_current}] "
            time_end = f" [{time_duration}]"
            
            volume_info = f" | Vol:{self.player.volume}%" if show_volume else ""
            
            # Calculate space for title and progress bar
            fixed_space = len(music_icon) + len(time_display) + len(time_end) + len(volume_info) + 6  # separators and padding
            available_space = self.width - fixed_space
            
            if available_space > 20:  # Minimum space needed
                # Split remaining space between title and progress bar
                # Prefer longer progress bar, but ensure title has some space
                min_title_space = 15
                title_space = min(min_title_space, len(self.player.current_track), available_space // 3)
                progress_bar_space = available_space - title_space - 3  # 3 for " | "
                
                # Use scrollable title if it's long
                title = self.get_scrollable_title(self.player.current_track, title_space)
                
                if progress_bar_space > 5:
                    progress_bar = self.draw_progress_bar(current_time, duration, progress, progress_bar_space)
                    line = f"{music_icon}{title} | {progress_bar}{volume_info}"
                else:
                    # Not enough space for progress bar
                    line = f"{music_icon}{title}{volume_info}"
            else:
                # Very small terminal - just show essentials
                if show_volume:
                    line = f"{music_icon}Playing | Vol:{self.player.volume}%"
                else:
                    time_info = f"{time_current}/{time_duration}" if duration > 0 else "Playing"
                    line = f"{music_icon}{time_info}"
            
            self.stdscr.addstr(self.height - 2, 2, line[:self.width-3], curses.color_pair(2))
        else:
            # Show volume temporarily when not playing
            if show_volume:
                volume_info = f" | Vol:{self.player.volume}%"
                status_line = self.status_message + volume_info
            else:
                status_line = self.status_message
            self.stdscr.addstr(self.height - 2, 2, status_line[:self.width-3])
        
        self.stdscr.refresh()
    
    def handle_search_input(self, key):
        """Handle input in search mode"""
        if key == 10:  # Enter
            if self.search_query:
                self.status_message = "Searching..."
                self.update_status()
                
                # Perform search
                results = self.player.search_youtube(self.search_query)
                self.player.search_results = results
                
                if results:
                    self.mode = "results"
                    self.selected_index = 0
                    self.prev_selected_index = -1
                    self.scroll_offset = 0  # Reset scroll position
                    self.status_message = f"Showing {len(results)} results (scroll down for more)"
                    return True  # Need full redraw for results
                else:
                    self.status_message = "No results found"
                    self.update_status()
                    
        elif key == 27:  # Escape - exit search mode
            if self.player.search_results:
                self.mode = "results"
                self.status_message = f"Showing {len(self.player.search_results)} results"
            else:
                self.mode = "main"
                self.status_message = "★ Favorites" if self.player.favorites else "No favorites yet"
            self.update_search_bar()
            return False
            
        elif key == curses.KEY_BACKSPACE or key == 127:
            self.search_query = self.search_query[:-1]
            self.update_search_bar()
            return False
            
        elif 32 <= key <= 126:  # Printable characters
            self.search_query += chr(key)
            self.update_search_bar()
            return False
        
        return False
    
    def adjust_viewport(self):
        """Adjust viewport to keep selected item visible"""
        # If selected item is above viewport, scroll up
        if self.selected_index < self.scroll_offset:
            self.scroll_offset = self.selected_index
            return True  # Need full redraw
        # If selected item is below viewport, scroll down
        elif self.selected_index >= self.scroll_offset + self.visible_lines:
            self.scroll_offset = self.selected_index - self.visible_lines + 1
            return True  # Need full redraw
        return False
    
    def handle_main_input(self, key):
        """Handle input in main mode (favorites and playlists view)"""
        if not hasattr(self, 'main_display_items') or not self.main_display_items:
            if key == ord('E') or key == ord('e'):  # Start playlist creation
                if not self.player.favorites:
                    self.status_message = "Add some favorites first before creating a playlist!"
                    self.update_status()
                else:
                    self.mode = "playlist_create"
                    self.playlist_name = ""
                    self.playlist_selected_tracks = []
                    self.selected_index = 0
                    return True
            return False
            
        if key == curses.KEY_UP:
            new_index = max(0, self.selected_index - 1)
            if new_index != self.selected_index:
                self.prev_selected_index = self.selected_index
                self.selected_index = new_index
                
                # Check if we need to scroll the viewport
                if self.adjust_viewport():
                    return True  # Need full redraw
                else:
                    # Update only the two affected lines
                    self.update_result_line(self.prev_selected_index)
                    self.update_result_line(self.selected_index)
                    self.stdscr.refresh()
            return False
            
        elif key == curses.KEY_DOWN:
            # Use the length of main_display_items, not favorites!
            new_index = min(len(self.main_display_items) - 1, self.selected_index + 1)
            if new_index != self.selected_index:
                self.prev_selected_index = self.selected_index
                self.selected_index = new_index
                
                # Check if we need to scroll the viewport
                if self.adjust_viewport():
                    return True  # Need full redraw
                else:
                    # Update only the two affected lines
                    self.update_result_line(self.prev_selected_index)
                    self.update_result_line(self.selected_index)
                    self.stdscr.refresh()
            return False
            
        elif key == 10:  # Enter - play selected or open playlist
            if self.main_display_items and self.selected_index < len(self.main_display_items):
                item = self.main_display_items[self.selected_index]
                
                if item['type'] == 'playlist':
                    # Open playlist view
                    self.current_viewing_playlist = item['data']
                    self.mode = "playlist_view"
                    self.selected_index = 0
                    self.scroll_offset = 0
                    self.status_message = f"Playlist: {item['data']['name']}"
                    return True
                else:
                    # Play favorite track
                    selected = item['data']
                    self.status_message = f"Loading: {selected['title'][:50]}..."
                    
                    # Clear visualizer immediately in main thread
                    self.visualizer.clear_immediately()
                    self.draw_visualizer()  # Redraw to show cleared state
                    self.stdscr.refresh()
                    
                    # Play in background thread to avoid blocking UI
                    def play_async():
                        success = self.player.play_track(selected['url'], selected['title'], selected.get('duration', 0))
                        if success:
                            self.status_message = f"Playing: {selected['title'][:50]}"
                        else:
                            self.status_message = "Failed to load track"
                        self.update_status()
                    
                    thread = threading.Thread(target=play_async)
                    thread.daemon = True
                    thread.start()
                    self.update_status()
                
        elif key == ord('F') or key == ord('f'):  # Remove from favorites (only for favorite items)
            if self.main_display_items and self.selected_index < len(self.main_display_items):
                item = self.main_display_items[self.selected_index]
                if item['type'] == 'favorite':
                    track = item['data']
                    self.player.remove_from_favorites(track.get('id', ''))
                    self.status_message = f"Removed from favorites: {track['title'][:50]}"
                    
                    # Adjust selection if needed
                    if self.selected_index >= len(self.main_display_items) - 1 and self.selected_index > 0:
                        self.selected_index -= 1
                    
                    self.update_status()
                    return True  # Need full redraw
                    
        elif key == ord('E') or key == ord('e'):  # Start playlist creation
            if not self.player.favorites:
                self.status_message = "Add some favorites first before creating a playlist!"
                self.update_status()
            else:
                self.mode = "playlist_create"
                self.playlist_name = ""
                self.playlist_selected_tracks = []
                self.selected_index = 0
                return True
        
        return False
    
    def handle_results_input(self, key):
        """Handle input in results mode"""
        if key == curses.KEY_UP:
            new_index = max(0, self.selected_index - 1)
            if new_index != self.selected_index:
                self.prev_selected_index = self.selected_index
                self.selected_index = new_index
                
                # Check if we need to scroll the viewport
                if self.adjust_viewport():
                    return True  # Need full redraw
                else:
                    # Update only the two affected lines
                    self.update_result_line(self.prev_selected_index)
                    self.update_result_line(self.selected_index)
                    self.stdscr.refresh()
            return False
            
        elif key == curses.KEY_DOWN:
            # Check if we need to load more results
            if self.selected_index == len(self.player.search_results) - 1 and not self.is_loading_more:
                # At the last result, try to load more
                self.is_loading_more = True
                self.status_message = "Loading more results..."
                self.update_status()
                
                # Load more in a thread
                def load_more_async():
                    new_results = self.player.fetch_more_results(10)
                    if new_results:
                        self.player.search_results.extend(new_results)
                        self.status_message = f"Showing {len(self.player.search_results)} results"
                    else:
                        self.status_message = f"Showing all {len(self.player.search_results)} results found"
                    self.is_loading_more = False
                    # Force a full redraw to show new results properly
                    self.stdscr.clear()
                    self.draw_static_ui()
                    self.update_search_bar()
                    self.draw_results()
                    self.update_status()
                    
                thread = threading.Thread(target=load_more_async)
                thread.daemon = True
                thread.start()
                
                # Update the main event loop that we need a redraw later
                return False
            
            new_index = min(len(self.player.search_results) - 1, self.selected_index + 1)
            if new_index != self.selected_index:
                self.prev_selected_index = self.selected_index
                self.selected_index = new_index
                
                # Check if we need to scroll the viewport
                if self.adjust_viewport():
                    return True  # Need full redraw
                else:
                    # Update only the two affected lines
                    self.update_result_line(self.prev_selected_index)
                    self.update_result_line(self.selected_index)
                    self.stdscr.refresh()
            return False
            
        elif key == 10:  # Enter - play selected
            if self.player.search_results:
                selected = self.player.search_results[self.selected_index]
                self.status_message = f"Loading: {selected['title'][:50]}..."
                self.needs_redraw = True
                
                # Clear visualizer immediately in main thread
                self.visualizer.clear_immediately()
                self.draw_visualizer()  # Redraw to show cleared state
                self.stdscr.refresh()
                
                # Play in background thread to avoid blocking UI
                def play_async():
                    success = self.player.play_track(selected['url'], selected['title'], selected.get('duration', 0))
                    if success:
                        self.status_message = f"Playing: {selected['title'][:50]}"
                    else:
                        self.status_message = "Failed to load track"
                    self.update_status()
                
                thread = threading.Thread(target=play_async)
                thread.daemon = True
                thread.start()
                self.update_status()
                
        elif key == ord('F') or key == ord('f'):  # Add/remove from favorites
            if self.player.search_results and self.selected_index < len(self.player.search_results):
                track = self.player.search_results[self.selected_index]
                if self.player.is_favorite(track.get('id', '')):
                    self.player.remove_from_favorites(track.get('id', ''))
                    self.status_message = f"Removed from favorites: {track['title'][:50]}"
                else:
                    self.player.add_to_favorites(track)
                    self.status_message = f"Added to favorites: {track['title'][:50]}"
                self.update_status()
                return True  # Need full redraw to update star indicators
                
        elif key == 27:  # ESC - return to main menu
            self.mode = "main"
            self.search_query = ""  # Clear search when returning to main
            self.selected_index = 0 if self.player.favorites else 0
            self.scroll_offset = 0
            self.status_message = "★ Favorites" if self.player.favorites else "No favorites yet"
            return True  # Need full redraw
        
        return False
    
    def update_playlist_creation_line(self, index):
        """Update a single line in playlist creation mode"""
        height, width = self.stdscr.getmaxyx()
        results_start_line = 11
        results_end_line = height - 8  # Account for visualizer (4 lines) + controls
        
        if index >= len(self.player.favorites):
            return
            
        y_pos = results_start_line + index
        if y_pos >= results_end_line:
            return
            
        fav = self.player.favorites[index]
        
        # Clear the line
        self.stdscr.move(y_pos, 2)
        self.stdscr.clrtoeol()
        
        # Check if selected
        is_selected = any(t.get('id') == fav.get('id') for t in self.playlist_selected_tracks)
        checkbox = "[X]" if is_selected else "[ ]"
        
        title = fav['title'][:width - 15] if len(fav['title']) > width - 15 else fav['title']
        line = f"{checkbox} {title}"
        
        # Highlight current item if it's the selected index
        if index == self.selected_index:
            self.stdscr.addstr(y_pos, 2, "▶ ", curses.color_pair(2))
            self.stdscr.addstr(y_pos, 4, line, curses.A_REVERSE)
        else:
            self.stdscr.addstr(y_pos, 4, line)
        
        self.stdscr.refresh()
    
    def update_playlist_name_input(self):
        """Update only the playlist name input line"""
        # Clear and redraw the name input line
        self.stdscr.move(7, 17)
        self.stdscr.clrtoeol()
        
        # Check if we're still entering the name or selecting tracks
        is_name_confirmed = self.playlist_name.endswith("_CONFIRMED")
        display_name = self.playlist_name.replace("_CONFIRMED", "")
        
        if not is_name_confirmed:
            # Still entering name - show cursor
            self.stdscr.addstr(7, 17, display_name + "_")
        else:
            # Name confirmed - show without cursor
            self.stdscr.addstr(7, 17, display_name)
        
        self.stdscr.refresh()
    
    def handle_playlist_creation_input(self, key):
        """Handle input in playlist creation mode"""
        if len(self.playlist_selected_tracks) == 0 and not self.playlist_name.endswith("_CONFIRMED"):
            # Entering playlist name
            if key == 10:  # Enter - finish name entry
                if self.playlist_name:
                    self.playlist_name += "_CONFIRMED"  # Mark that name entry is done
                    self.selected_index = 0
                    return True  # Need full redraw to show track selection UI
            elif key == 27:  # ESC - cancel
                self.mode = "main"
                self.playlist_name = ""
                self.playlist_selected_tracks = []
                self.status_message = "Playlist creation cancelled"
                return True
            elif key == curses.KEY_BACKSPACE or key == 127:
                self.playlist_name = self.playlist_name[:-1]
                self.update_playlist_name_input()
                return False  # No full redraw needed
            elif 32 <= key <= 126:  # Printable characters
                self.playlist_name += chr(key)
                self.update_playlist_name_input()
                return False  # No full redraw needed
        else:
            # Selecting tracks
            if key == curses.KEY_UP:
                prev_index = self.selected_index
                self.selected_index = max(0, self.selected_index - 1)
                if prev_index != self.selected_index:
                    self.update_playlist_creation_line(prev_index)
                    self.update_playlist_creation_line(self.selected_index)
                return False  # No full redraw needed
            elif key == curses.KEY_DOWN:
                prev_index = self.selected_index
                self.selected_index = min(len(self.player.favorites) - 1, self.selected_index + 1)
                if prev_index != self.selected_index:
                    self.update_playlist_creation_line(prev_index)
                    self.update_playlist_creation_line(self.selected_index)
                return False  # No full redraw needed
            elif key == ord(' '):  # Space - toggle selection
                if self.selected_index < len(self.player.favorites):
                    fav = self.player.favorites[self.selected_index]
                    # Check if track is already selected
                    is_selected = any(t.get('id') == fav.get('id') for t in self.playlist_selected_tracks)
                    if is_selected:
                        # Remove from selection
                        self.playlist_selected_tracks = [t for t in self.playlist_selected_tracks if t.get('id') != fav.get('id')]
                    else:
                        # Add to selection
                        self.playlist_selected_tracks.append(fav)
                    # Only update the current line
                    self.update_playlist_creation_line(self.selected_index)
                    return False  # No full redraw needed
            elif key == 10:  # Enter - create or update playlist
                if self.playlist_selected_tracks:
                    # Remove the _CONFIRMED suffix before creating/updating
                    clean_name = self.playlist_name.replace("_CONFIRMED", "")
                    
                    if self.mode == "playlist_edit" and self.editing_playlist_id:
                        # Update existing playlist
                        success = self.player.update_playlist(self.editing_playlist_id, clean_name, self.playlist_selected_tracks)
                        if success:
                            self.status_message = f"Updated playlist: {clean_name}"
                            # Return to playlist view
                            updated_playlist = next((p for p in self.player.playlists if p.get('id') == self.editing_playlist_id), None)
                            if updated_playlist:
                                self.current_viewing_playlist = updated_playlist
                                self.mode = "playlist_view"
                            else:
                                self.mode = "main"
                            self.playlist_name = ""
                            self.playlist_selected_tracks = []
                            self.editing_playlist_id = None
                            self.selected_index = 0
                            return True
                    else:
                        # Create new playlist
                        success = self.player.create_playlist(clean_name, self.playlist_selected_tracks)
                        if success:
                            self.status_message = f"Created playlist: {clean_name}"
                            self.mode = "main"
                            self.playlist_name = ""
                            self.playlist_selected_tracks = []
                            self.selected_index = 0
                            return True
                else:
                    self.status_message = "Select at least one track!"
                    self.update_status()
            elif key == ord('D') or key == ord('d'):  # Delete playlist (only in edit mode)
                if self.mode == "playlist_edit" and self.editing_playlist_id:
                    # Find the playlist name before deleting
                    playlist_name = ""
                    for p in self.player.playlists:
                        if p.get('id') == self.editing_playlist_id:
                            playlist_name = p.get('name', 'Unnamed')
                            break
                    
                    # Delete the playlist
                    self.player.delete_playlist(self.editing_playlist_id)
                    self.status_message = f"Deleted playlist: {playlist_name}"
                    
                    # Return to main
                    self.mode = "main"
                    self.current_viewing_playlist = None
                    self.playlist_name = ""
                    self.playlist_selected_tracks = []
                    self.editing_playlist_id = None
                    self.selected_index = 0
                    self.scroll_offset = 0
                    return True
            elif key == 27:  # ESC - cancel
                if self.mode == "playlist_edit":
                    # Return to playlist view
                    self.mode = "playlist_view"
                    self.status_message = f"Editing cancelled"
                else:
                    # Return to main
                    self.mode = "main"
                    self.status_message = "Playlist creation cancelled"
                self.playlist_name = ""
                self.playlist_selected_tracks = []
                self.editing_playlist_id = None
                return True
        
        return False
    
    def handle_playlist_view_input(self, key):
        """Handle input when viewing a playlist"""
        if not self.current_viewing_playlist:
            return False
        
        tracks = self.current_viewing_playlist.get('tracks', [])
        
        if key == curses.KEY_UP:
            prev_index = self.selected_index
            self.selected_index = max(0, self.selected_index - 1)
            if prev_index != self.selected_index:
                if self.adjust_viewport():
                    return True
                else:
                    # Update only the two affected lines
                    self.update_result_line(prev_index)
                    self.update_result_line(self.selected_index)
                    self.stdscr.refresh()
            return False
            
        elif key == curses.KEY_DOWN:
            prev_index = self.selected_index
            self.selected_index = min(len(tracks) - 1, self.selected_index + 1)
            if prev_index != self.selected_index:
                if self.adjust_viewport():
                    return True
                else:
                    # Update only the two affected lines
                    self.update_result_line(prev_index)
                    self.update_result_line(self.selected_index)
                    self.stdscr.refresh()
            return False
            
        elif key == 10:  # Enter - play track and set playlist mode
            if tracks and self.selected_index < len(tracks):
                self.status_message = f"Starting playlist: {self.current_viewing_playlist['name']}"
                
                # Clear visualizer immediately in main thread
                self.visualizer.clear_immediately()
                self.draw_visualizer()  # Redraw to show cleared state
                self.stdscr.refresh()
                
                # Play in background thread
                def play_playlist_async():
                    success = self.player.play_playlist_track(
                        self.current_viewing_playlist['id'],
                        self.selected_index
                    )
                    if success:
                        self.status_message = f"Playing from playlist: {tracks[self.selected_index]['title'][:50]}"
                    else:
                        self.status_message = "Failed to load track"
                    self.update_status()
                
                thread = threading.Thread(target=play_playlist_async)
                thread.daemon = True
                thread.start()
                self.update_status()
                
        elif key == 27:  # ESC - return to main
            self.mode = "main"
            self.search_query = ""  # Clear search when returning to main
            self.current_viewing_playlist = None
            self.selected_index = 0
            self.scroll_offset = 0
            return True
            
        elif key == ord('E') or key == ord('e'):  # Edit playlist
            if self.current_viewing_playlist:
                # Enter edit mode for the current playlist
                self.mode = "playlist_edit"
                self.playlist_name = self.current_viewing_playlist['name'] + "_CONFIRMED"  # Skip name entry
                self.playlist_selected_tracks = list(self.current_viewing_playlist.get('tracks', []))  # Copy current tracks
                self.editing_playlist_id = self.current_viewing_playlist['id']
                self.selected_index = 0
                self.status_message = f"Editing playlist: {self.current_viewing_playlist['name']}"
                return True
                
        
        return False
    
    def run(self):
        """Main UI loop"""
        self.stdscr.timeout(50)  # 50ms timeout for fast visualizer updates
        needs_full_redraw = True
        last_progress_update = 0
        last_playback_check = 0
        last_visualizer_update = 0
        
        while True:
            # Check for terminal resize
            if self.resize_detected:
                try:
                    # Update curses terminal info
                    curses.update_lines_cols()
                    
                    # Update our dimensions
                    self.update_dimensions()
                    
                    # Force a complete redraw
                    needs_full_redraw = True
                    self.resize_detected = False
                    
                except Exception:
                    # If resize handling fails, still try to redraw
                    needs_full_redraw = True
                    self.resize_detected = False
            
            # Only do full redraw when absolutely needed
            if needs_full_redraw:
                self.stdscr.clear()
                self.draw_static_ui()
                self.update_search_bar()
                self.draw_results()  # This now handles both favorites and search results
                self.draw_visualizer()  # Draw audio visualizer
                self.update_status()
                needs_full_redraw = False
            
            # Update progress bar and title scrolling periodically
            current_time = time.time()
            should_update_status = False
            
            if self.player.is_playing and current_time - last_progress_update >= 1:
                should_update_status = True
                last_progress_update = current_time
            
            # Update title scrolling for long titles
            if self.player.is_playing and self.player.current_track and self.update_title_scroll():
                should_update_status = True
            
            # Update visualizer at high frequency (20 FPS)
            if current_time - last_visualizer_update >= 0.05:  # 50ms = 20 FPS
                if self.player.is_playing:
                    self.visualizer.update_from_vlc(self.player.player)
                    self.draw_visualizer()
                else:
                    self.visualizer.update_from_vlc(None)
                    if any(level > 0.01 for level in self.visualizer.frequency_bands):  # Only redraw if still fading
                        self.draw_visualizer()
                last_visualizer_update = current_time
            
            if should_update_status:
                self.update_status()
            
            # Check for playlist auto-play every 2 seconds
            if current_time - last_playback_check >= 2:
                self.player.check_playback_status()
                last_playback_check = current_time
            
            # Handle input (with timeout for progress updates)
            try:
                key = self.stdscr.getch()
                
                # If timeout (no key pressed), continue to next iteration
                if key == -1:
                    continue
                
                # Handle terminal resize
                if key == curses.KEY_RESIZE:
                    self.resize_detected = True
                    continue
                
                if self.mode == "search":
                    # In search mode, handle ALL input through search handler
                    needs_full_redraw = self.handle_search_input(key)
                    
                elif self.mode == "playlist_create" and not self.playlist_name.endswith("_CONFIRMED"):
                    # In playlist name entry mode, handle ALL input through playlist handler
                    needs_full_redraw = self.handle_playlist_creation_input(key)
                    
                elif key == ord('q'):
                    self.player.stop()
                    break
                    
                elif key == ord('/'):
                    self.mode = "search"
                    self.search_query = ""
                    self.update_search_bar()
                    
                elif key == ord('s'):
                    self.player.stop()
                    self.status_message = "Playback stopped"
                    self.update_status()
                    
                elif key == ord(' '):  # Spacebar - pause/resume (except in playlist track selection)
                    # Don't handle space here if we're in playlist track selection mode
                    if (self.mode == "playlist_create" and self.playlist_name.endswith("_CONFIRMED")) or self.mode == "playlist_edit":
                        # Let the playlist handler deal with it
                        needs_full_redraw = self.handle_playlist_creation_input(key)
                    else:
                        self.player.toggle_pause()
                    
                elif key == ord('+') or key == ord('='):  # Volume up
                    self.player.volume_up()
                    self.volume_display_until = time.time() + 3  # Show for 3 seconds
                    self.update_status()
                    
                elif key == ord('-') or key == ord('_'):  # Volume down
                    self.player.volume_down()
                    self.volume_display_until = time.time() + 3  # Show for 3 seconds
                    self.update_status()
                    
                elif key == 27 and self.mode != "search":  # ESC - return to main (when not in search mode)
                    self.mode = "main"
                    self.search_query = ""  # Clear search when returning to main
                    self.selected_index = 0 if self.player.favorites else 0
                    self.scroll_offset = 0
                    self.status_message = "★ Favorites" if self.player.favorites else "No favorites yet"
                    needs_full_redraw = True
                    
                elif self.mode == "results":
                    needs_full_redraw = self.handle_results_input(key)
                    
                elif self.mode == "main":
                    needs_full_redraw = self.handle_main_input(key)
                    
                elif (self.mode == "playlist_create" and self.playlist_name.endswith("_CONFIRMED")) or self.mode == "playlist_edit":
                    # Track selection mode - handle input
                    needs_full_redraw = self.handle_playlist_creation_input(key)
                    
                elif self.mode == "playlist_view":
                    needs_full_redraw = self.handle_playlist_view_input(key)
                    
            except:
                pass

def main(stdscr):
    ui = MusicPlayerUI(stdscr)
    ui.run()

if __name__ == "__main__":
    # Suppress ALL error output to keep UI clean
    import sys
    import os
    
    # Redirect stderr to devnull to prevent any error messages from breaking the UI
    sys.stderr = open(os.devnull, 'w')
    
    try:
        curses.wrapper(main)
    finally:
        # Restore stderr on exit (for debugging if needed)
        sys.stderr.close()
        sys.stderr = sys.__stderr__