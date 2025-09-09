#!/usr/bin/env python3
import argparse
import requests
import time
import pygame
import os
import json
import hashlib
import signal
import sys
from threading import Thread
from datetime import datetime
from urllib.parse import urlparse
import logging

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SOUND = os.path.join(SCRIPT_DIR, "sound.mp3")
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
LOG_FILE = os.path.join(SCRIPT_DIR, "file_watcher.log")

# Global flag for graceful shutdown
shutdown_flag = False

# Animation components
class Colors:
    """ANSI color codes for terminal output"""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    
    # Colors
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    
    # Bright colors
    BRIGHT_BLACK = '\033[90m'
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'
    BRIGHT_WHITE = '\033[97m'

class ProgressBar:
    """Beautiful progress bar with animations"""
    def __init__(self, total=None, width=30, fill_char='█', empty_char='░'):
        self.total = total
        self.width = width
        self.fill_char = fill_char
        self.empty_char = empty_char
        self.current = 0
        self.start_time = time.time()
        
    def update(self, current=None, add=None):
        if current is not None:
            self.current = current
        elif add is not None:
            self.current += add
            
    def get_bar(self):
        if self.total is None:
            return ""
        
        progress = min(self.current / self.total, 1.0)
        filled = int(progress * self.width)
        bar = self.fill_char * filled + self.empty_char * (self.width - filled)
        
        # Add gradient effect
        if filled > 0:
            bar = f"{Colors.BRIGHT_CYAN}{bar[:filled]}{Colors.BRIGHT_BLACK}{bar[filled:]}{Colors.RESET}"
        
        percentage = int(progress * 100)
        return f"[{bar}] {percentage}%"
    
    def get_eta(self):
        if self.total is None or self.current == 0:
            return ""
        
        elapsed = time.time() - self.start_time
        rate = self.current / elapsed
        remaining = (self.total - self.current) / rate if rate > 0 else 0
        
        if remaining > 60:
            return f"ETA: {int(remaining // 60)}m {int(remaining % 60)}s"
        else:
            return f"ETA: {int(remaining)}s"

class Spinner:
    """Animated spinner with various styles"""
    STYLES = {
        'dots': ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'],
        'bars': ['▁', '▂', '▃', '▄', '▅', '▆', '▇', '█', '▇', '▆', '▅', '▄', '▃', '▂'],
        'arrows': ['←', '↖', '↑', '↗', '→', '↘', '↓', '↙'],
        'clock': ['🕐', '🕑', '🕒', '🕓', '🕔', '🕕', '🕖', '🕗', '🕘', '🕙', '🕚', '🕛'],
        'earth': ['🌍', '🌎', '🌏'],
        'moon': ['🌑', '🌒', '🌓', '🌔', '🌕', '🌖', '🌗', '🌘'],
        'pulse': ['●', '◐', '◑', '◒', '◓', '◔', '◕', '◖', '◗', '◘'],
        'wave': ['▰', '▱▰', '▱▱▰', '▱▱▱▰', '▱▱▱▱▰', '▱▱▱▱▱▰', '▱▱▱▱▱▱▰', '▱▱▱▱▱▱▱▰'],
    }
    
    def __init__(self, style='dots', speed=0.1):
        self.frames = self.STYLES.get(style, self.STYLES['dots'])
        self.speed = speed
        self.current_frame = 0
        self.last_update = time.time()
        
    def get_frame(self):
        now = time.time()
        if now - self.last_update > self.speed:
            self.current_frame = (self.current_frame + 1) % len(self.frames)
            self.last_update = now
        return self.frames[self.current_frame]

class AnimatedDisplay:
    """Main animated display handler"""
    def __init__(self, use_colors=True):
        self.use_colors = use_colors and self._supports_color()
        self.spinners = {}
        self.progress_bars = {}
        self.lines = {}
        self.last_height = 0
        
    def _supports_color(self):
        """Check if terminal supports colors"""
        return hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()
    
    def _color(self, text, color):
        """Apply color if supported"""
        if self.use_colors:
            return f"{color}{text}{Colors.RESET}"
        return text
    
    def _clear_lines(self, count):
        """Clear the last count lines"""
        for _ in range(count):
            sys.stdout.write('\033[F\033[K')  # Move up and clear line
    
    def create_spinner(self, key, style, speed=0.1):
        """Create a new spinner"""
        self.spinners[key] = Spinner(style, speed)
        
    def create_progress_bar(self, key, total=None, width=30):
        """Create a new progress bar"""
        self.progress_bars[key] = ProgressBar(total, width)
        
    def update_line(self, key, text):
        """Update a line of text"""
        self.lines[key] = text
        
    def update_progress(self, key, current=None, add=None):
        """Update progress bar"""
        if key in self.progress_bars:
            self.progress_bars[key].update(current, add)
            
    def render(self):
        """Render all animations"""
        if shutdown_flag:
            return
            
        # Clear previous output
        if self.last_height > 0:
            self._clear_lines(self.last_height)
        
        output_lines = []
        
        # Render spinners and progress bars
        for key in sorted(self.lines.keys()):
            line = self.lines[key]
            
            # Add spinner if exists
            if key in self.spinners:
                spinner_frame = self.spinners[key].get_frame()
                spinner_colored = self._color(spinner_frame, Colors.BRIGHT_YELLOW)
                line = f"{spinner_colored} {line}"
            
            # Add progress bar if exists
            if key in self.progress_bars:
                bar = self.progress_bars[key].get_bar()
                eta = self.progress_bars[key].get_eta()
                if bar:
                    line = f"{line} {bar}"
                if eta:
                    line = f"{line} {self._color(eta, Colors.DIM)}"
            
            output_lines.append(line)
        
        # Print all lines
        for line in output_lines:
            print(line)
        
        self.last_height = len(output_lines)
        
    def clear(self):
        """Clear all animations"""
        if self.last_height > 0:
            self._clear_lines(self.last_height)
            self.last_height = 0
        
    def success(self, message):
        """Show success message"""
        checkmark = self._color('✓', Colors.BRIGHT_GREEN)
        print(f"{checkmark} {message}")
        
    def error(self, message):
        """Show error message"""
        cross = self._color('✗', Colors.BRIGHT_RED)
        print(f"{cross} {message}")
        
    def warning(self, message):
        """Show warning message"""
        warning = self._color('⚠', Colors.BRIGHT_YELLOW)
        print(f"{warning} {message}")
        
    def info(self, message):
        """Show info message"""
        info = self._color('ℹ', Colors.BRIGHT_BLUE)
        print(f"{info} {message}")

# Global animated display instance
display = AnimatedDisplay()
spinner_style = 'dots'  # Global spinner style

def setup_logging(verbose=False):
    """Setup logging configuration"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler()
        ]
    )

def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully"""
    global shutdown_flag
    shutdown_flag = True
    display.clear()
    display.warning("Received interrupt signal. Shutting down gracefully...")
    sys.exit(0)

def load_config():
    """Load configuration from JSON file"""
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        print(f"⚠️ Invalid JSON in {CONFIG_FILE}")
        return {}

def save_config(config):
    """Save configuration to JSON file"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"⚠️ Failed to save config: {e}")

def get_file_hash(file_path):
    """Calculate MD5 hash of a file"""
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception:
        return None

def fetch_file(file_url, save_path, headers=None, check_size=False, expected_size=None, url_key=None):
    try:
        if url_key:
            display.create_spinner(url_key, style=spinner_style)
            display.update_line(url_key, f"Checking {os.path.basename(file_url)}...")
            display.render()

        # HEAD request to check existence
        head_response = requests.head(file_url, timeout=10, headers=headers or {})
        if head_response.status_code == 200:
            content_length = head_response.headers.get('content-length')
            if content_length:
                file_size = int(content_length)
                if url_key:
                    display.update_line(url_key, f"Found {os.path.basename(file_url)} ({file_size/1024/1024:.2f} MB)")
                    display.render()
                if check_size and expected_size and file_size != expected_size:
                    if url_key:
                        display.error(f"File size mismatch. Expected: {expected_size}, Got: {file_size}")
                    return False
                if url_key:
                    display.create_progress_bar(url_key, file_size)
                    display.update_line(url_key, f"Downloading {os.path.basename(file_url)}...")

        response = requests.get(file_url, stream=True, timeout=30, headers=headers or {})
        if response.status_code == 200:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            downloaded = 0
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if url_key:
                            display.update_progress(url_key, downloaded)
                            display.render()
                            time.sleep(0.01)
            if url_key:
                display.success(f"Downloaded {os.path.basename(file_url)}")
            return True
        else:
            if url_key:
                display.warning(f"HTTP {response.status_code} for {file_url}")
            return False
    except Exception as e:
        if url_key:
            display.error(f"Error: {str(e)}")
        return False

def play_sound(sound_path):
    try:
        pygame.mixer.init()
        pygame.mixer.music.load(sound_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)
    except Exception as e:
        print(f"⚠️ Failed to play sound: {e}")

def send_notification(message, webhook_url=None):
    """Send notification (e.g., to Slack, Discord, etc.)"""
    if webhook_url:
        try:
            payload = {"text": message}
            requests.post(webhook_url, json=payload, timeout=10)
            display.info(f"Notification sent")
        except Exception as e:
            display.error(f"Failed to send notification: {e}")

def auto_name_file(url, save_path):
    """Auto-generate filename from URL if save_path is a directory"""
    if os.path.isdir(save_path) or save_path.endswith('/'):
        # Extract filename from URL
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)
        
        # If no filename in URL, use timestamp
        if not filename or '.' not in filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"downloaded_{timestamp}.file"
        
        return os.path.join(save_path, filename)
    
    return save_path

def watch_multiple_urls(urls, base_output_dir, interval, **kwargs):
    """Watch multiple URLs simultaneously with animated display"""
    threads = []
    
    display.info(f"Starting to watch {len(urls)} URLs...")
    
    for i, url in enumerate(urls):
        output_path = os.path.join(base_output_dir, f"file_{i+1}")
        output_path = auto_name_file(url, output_path)
        
        url_key = f"url_{i+1}"
        
        thread = Thread(target=watch_single_url, args=(url, output_path, interval, url_key), kwargs=kwargs)
        thread.daemon = True
        threads.append(thread)
        thread.start()
        
        # Initialize display for this URL
        display.create_spinner(url_key, style=spinner_style)
        display.update_line(url_key, f"Initializing {os.path.basename(url)}...")
    
    # Animation loop
    while any(thread.is_alive() for thread in threads) and not shutdown_flag:
        display.render()
        time.sleep(0.1)
    
    # Wait for all threads to complete
    for thread in threads:
        thread.join()
    
    display.clear()
    display.success("All downloads completed!")

def watch_single_url(url, output_path, interval, url_key=None, **kwargs):
    """Watch a single URL with animated display"""
    global shutdown_flag
    
    attempt = 0
    max_attempts = kwargs.get('max_attempts', 0)  # 0 means unlimited
    
    while not shutdown_flag:
        attempt += 1
        
        if max_attempts > 0 and attempt > max_attempts:
            if url_key:
                display.error(f"Max attempts ({max_attempts}) reached for {os.path.basename(url)}")
            break
        
        if url_key:
            display.update_line(url_key, f"Attempt {attempt} - {os.path.basename(url)}")
        
        if fetch_file(url, output_path, 
                     headers=kwargs.get('headers'),
                     check_size=kwargs.get('check_size', False),
                     expected_size=kwargs.get('expected_size'),
                     url_key=url_key):
            
            # Success! Play sound and send notifications
            if not kwargs.get('no_sound', False):
                sound_path = kwargs.get('sound') or DEFAULT_SOUND
                if os.path.exists(sound_path):
                    Thread(target=play_sound, args=(sound_path,)).start()
            
            # Send webhook notification
            if kwargs.get('webhook'):
                message = f"✅ File downloaded successfully: {url} -> {output_path}"
                send_notification(message, kwargs.get('webhook'))
            
            break
        
        if shutdown_flag:
            break
        
        # Show countdown for next attempt
        if url_key:
            for remaining in range(interval, 0, -1):
                if shutdown_flag:
                    break
                display.update_line(url_key, f"Waiting {remaining}s before retry - {os.path.basename(url)}")
                time.sleep(1)
        else:
            time.sleep(interval)

def main():
    global spinner_style  # Declare as global so we can modify it
    
    # Setup signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    
    parser = argparse.ArgumentParser(
        description="Advanced file watcher - Monitor URLs until files are available, then download them.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s https://example.com/file.zip
  %(prog)s https://example.com/file.zip -O ./downloads/ -i 10
  %(prog)s -m urls.txt -O ./downloads/ --webhook https://hooks.slack.com/...
  %(prog)s https://example.com/file.zip --max-attempts 20 --expected-size 1048576
        """
    )
    
    # Main arguments
    parser.add_argument("url", nargs='?', help="URL of the file to download")
    parser.add_argument("-O", "--out", default="./downloaded.file", help="Path to save the downloaded file")
    parser.add_argument("-i", "--interval", type=int, default=5, help="Retry interval in seconds (default: 5)")
    
    # Sound options
    parser.add_argument("--no-sound", action="store_true", help="Don't play a sound when download completes")
    parser.add_argument("--sound", help="Path to a .mp3 or .wav file to play when the download succeeds")
    
    # Multiple URLs
    parser.add_argument("-m", "--multiple", help="Text file containing multiple URLs (one per line)")
    
    # Advanced options
    parser.add_argument("--max-attempts", type=int, default=0, help="Maximum number of attempts (0 = unlimited)")
    parser.add_argument("--expected-size", type=int, help="Expected file size in bytes")
    parser.add_argument("--check-size", action="store_true", help="Verify file size matches expected size")
    parser.add_argument("--headers", help="JSON string of HTTP headers to send")
    parser.add_argument("--webhook", help="Webhook URL for notifications (Slack, Discord, etc.)")
    
    # Utility options
    parser.add_argument("--spinner", choices=list(Spinner.STYLES.keys()), help="Spinner style (default: dots)")
    parser.add_argument("--config", help="Load settings from JSON config file")
    parser.add_argument("--save-config", help="Save current settings to JSON config file")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    parser.add_argument("--daemon", action="store_true", help="Run in daemon mode (background)")
    
    args = parser.parse_args()
    
    # Set spinner style if provided
    if args.spinner:
        spinner_style = args.spinner
    
    # Setup logging
    setup_logging(args.verbose)
    
    # Load config if specified
    config = {}
    if args.config:
        config = load_config()
        display.info(f"Loaded configuration from {args.config}")
    
    # Parse headers if provided
    headers = None
    if args.headers:
        try:
            headers = json.loads(args.headers)
        except json.JSONDecodeError:
            display.error("Invalid JSON in headers argument")
            return
    
    # Handle multiple URLs
    if args.multiple:
        if not os.path.exists(args.multiple):
            display.error(f"File not found: {args.multiple}")
            return
        
        try:
            with open(args.multiple, 'r') as f:
                urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            
            if not urls:
                display.error("No URLs found in file")
                return
            
            # Create output directory if it doesn't exist
            os.makedirs(args.out, exist_ok=True)
            
            watch_multiple_urls(urls, args.out, args.interval,
                              no_sound=args.no_sound,
                              sound=args.sound,
                              max_attempts=args.max_attempts,
                              expected_size=args.expected_size,
                              check_size=args.check_size,
                              headers=headers,
                              webhook=args.webhook)
        except Exception as e:
            display.error(f"Error reading URLs file: {e}")
            return
    
    elif args.url:
        # Single URL mode
        output_path = auto_name_file(args.url, args.out)
        
        # Show initial info
        display.info(f"Watching URL: {args.url}")
        display.info(f"Output: {output_path}")
        display.info(f"Interval: {args.interval}s")
        if args.max_attempts > 0:
            display.info(f"Max attempts: {args.max_attempts}")
        
        # Create animation display
        display.create_spinner('main', style=spinner_style)
        display.update_line('main', f"Initializing {os.path.basename(args.url)}...")
        
        # Start watching in a thread so we can animate
        thread = Thread(target=watch_single_url, args=(args.url, output_path, args.interval, 'main'),
                       kwargs={
                           'no_sound': args.no_sound,
                           'sound': args.sound,
                           'max_attempts': args.max_attempts,
                           'expected_size': args.expected_size,
                           'check_size': args.check_size,
                           'headers': headers,
                           'webhook': args.webhook
                       })
        thread.daemon = True
        thread.start()
        
        # Animation loop
        while thread.is_alive() and not shutdown_flag:
            display.render()
            time.sleep(0.1)
        
        thread.join()
        display.clear()
        
    else:
        display.error("No URL provided. Use -h for help.")
        return
    
    # Save config if requested
    if args.save_config:
        config_data = {
            'interval': args.interval,
            'max_attempts': args.max_attempts,
            'headers': headers,
            'webhook': args.webhook,
            'sound': args.sound,
            'no_sound': args.no_sound
        }
        save_config(config_data)
        display.success(f"Configuration saved to {CONFIG_FILE}")

if __name__ == "__main__":
    main()