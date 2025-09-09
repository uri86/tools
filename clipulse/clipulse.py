#!/usr/bin/env python3
"""
clipulse - Clipboard Activity Monitor & Logger
A cross-platform CLI tool for monitoring and managing clipboard activity
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import time
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import hashlib
import difflib
import requests

# Cross-platform clipboard handling
try:
    import pyperclip
except ImportError:
    print("Error: pyperclip is required. Install with: pip install pyperclip")
    sys.exit(1)

# For TUI mode
try:
    import curses
    HAS_CURSES = True
except ImportError:
    HAS_CURSES = False

class ClipboardEntry:
    def __init__(self, content: str, timestamp: datetime, source_app: str = "unknown"):
        self.content = content
        self.timestamp = timestamp
        self.source_app = source_app
        self.hash = hashlib.md5(content.encode()).hexdigest()
        
    def to_dict(self) -> Dict:
        return {
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "source_app": self.source_app,
            "hash": self.hash
        }

class ClipulseDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Initialize the SQLite database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clipboard_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                source_app TEXT,
                hash TEXT UNIQUE
            )
        ''')
        conn.commit()
        conn.close()
    
    def add_entry(self, entry: ClipboardEntry) -> bool:
        """Add entry to database, return True if added, False if duplicate"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO clipboard_history (content, timestamp, source_app, hash)
                VALUES (?, ?, ?, ?)
            ''', (entry.content, entry.timestamp.isoformat(), entry.source_app, entry.hash))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            # Duplicate hash
            return False
        finally:
            conn.close()
    
    def get_history(self, limit: int = 100) -> List[ClipboardEntry]:
        """Get clipboard history"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT content, timestamp, source_app FROM clipboard_history
            ORDER BY timestamp DESC LIMIT ?
        ''', (limit,))
        
        entries = []
        for row in cursor.fetchall():
            entries.append(ClipboardEntry(
                content=row[0],
                timestamp=datetime.fromisoformat(row[1]),
                source_app=row[2]
            ))
        
        conn.close()
        return entries
    
    def search_history(self, keyword: str) -> List[ClipboardEntry]:
        """Search clipboard history"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT content, timestamp, source_app FROM clipboard_history
            WHERE content LIKE ? ORDER BY timestamp DESC
        ''', (f'%{keyword}%',))
        
        entries = []
        for row in cursor.fetchall():
            entries.append(ClipboardEntry(
                content=row[0],
                timestamp=datetime.fromisoformat(row[1]),
                source_app=row[2]
            ))
        
        conn.close()
        return entries
    
    def clear_history(self):
        """Clear all clipboard history"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM clipboard_history')
        conn.commit()
        conn.close()
    
    def expire_old_entries(self, minutes: int):
        """Remove entries older than specified minutes"""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM clipboard_history 
            WHERE timestamp < ?
        ''', (cutoff_time.isoformat(),))
        conn.commit()
        conn.close()

class ClipulseConfig:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config = self.load_config()
    
    def load_config(self) -> Dict:
        """Load configuration from file"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return self.default_config()
        return self.default_config()
    
    def default_config(self) -> Dict:
        """Default configuration"""
        return {
            "filters": {
                "ignore_apps": [],
                "ignore_patterns": []
            },
            "notifications": {
                "enabled": False,
                "sensitive_keywords": ["password", "token", "key", "secret"]
            },
            "sync": {
                "webhook_url": None,
                "enabled": False
            },
            "auto_expire": {
                "enabled": False,
                "minutes": 1440  # 24 hours
            }
        }
    
    def save_config(self):
        """Save configuration to file"""
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)

class ClipulseMonitor:
    def __init__(self, db: ClipulseDB, config: ClipulseConfig):
        self.db = db
        self.config = config
        self.running = False
        self.last_content = ""
        
    def get_active_app(self) -> str:
        """Get the currently active application (OS-specific)"""
        try:
            if sys.platform == "darwin":  # macOS
                script = '''
                tell application "System Events"
                    set frontApp to name of first application process whose frontmost is true
                end tell
                '''
                result = subprocess.run(['osascript', '-e', script], 
                                      capture_output=True, text=True)
                return result.stdout.strip() if result.returncode == 0 else "unknown"
            elif sys.platform.startswith("linux"):  # Linux
                try:
                    result = subprocess.run(['xdotool', 'getactivewindow', 'getwindowname'], 
                                          capture_output=True, text=True)
                    return result.stdout.strip() if result.returncode == 0 else "unknown"
                except FileNotFoundError:
                    return "unknown"
            elif sys.platform == "win32":  # Windows
                try:
                    import win32gui
                    return win32gui.GetWindowText(win32gui.GetForegroundWindow())
                except ImportError:
                    return "unknown"
        except Exception:
            return "unknown"
        
        return "unknown"
    
    def should_ignore_content(self, content: str, app: str) -> bool:
        """Check if content should be ignored based on filters"""
        filters = self.config.config["filters"]
        
        # Check app filters
        for ignored_app in filters["ignore_apps"]:
            if ignored_app.lower() in app.lower():
                return True
        
        # Check pattern filters
        for pattern in filters["ignore_patterns"]:
            if re.search(pattern, content, re.IGNORECASE):
                return True
        
        return False
    
    def check_sensitive_content(self, content: str) -> bool:
        """Check if content contains sensitive keywords"""
        if not self.config.config["notifications"]["enabled"]:
            return False
        
        keywords = self.config.config["notifications"]["sensitive_keywords"]
        for keyword in keywords:
            if keyword.lower() in content.lower():
                return True
        return False
    
    def sync_to_webhook(self, entry: ClipboardEntry):
        """Sync clipboard entry to webhook"""
        sync_config = self.config.config["sync"]
        if not sync_config["enabled"] or not sync_config["webhook_url"]:
            return
        
        try:
            response = requests.post(sync_config["webhook_url"], 
                                   json=entry.to_dict(), 
                                   timeout=5)
            if response.status_code != 200:
                print(f"Webhook sync failed: {response.status_code}")
        except Exception as e:
            print(f"Webhook sync error: {e}")
    
    def start_monitoring(self):
        """Start monitoring clipboard"""
        self.running = True
        print("🔍 Clipulse is monitoring your clipboard... (Press Ctrl+C to stop)")
        
        try:
            while self.running:
                try:
                    current_content = pyperclip.paste()
                    
                    if current_content != self.last_content and current_content.strip():
                        app = self.get_active_app()
                        
                        if not self.should_ignore_content(current_content, app):
                            entry = ClipboardEntry(current_content, datetime.now(), app)
                            
                            if self.db.add_entry(entry):
                                print(f"📋 [{entry.timestamp.strftime('%H:%M:%S')}] "
                                      f"From {app}: {current_content[:50]}...")
                                
                                # Check for sensitive content
                                if self.check_sensitive_content(current_content):
                                    print("⚠️  WARNING: Sensitive content detected!")
                                
                                # Sync to webhook
                                self.sync_to_webhook(entry)
                        
                        self.last_content = current_content
                    
                    # Auto-expire old entries
                    if self.config.config["auto_expire"]["enabled"]:
                        self.db.expire_old_entries(self.config.config["auto_expire"]["minutes"])
                    
                    time.sleep(0.5)  # Check every 500ms
                    
                except Exception as e:
                    print(f"Error monitoring clipboard: {e}")
                    time.sleep(1)
                    
        except KeyboardInterrupt:
            print("\n👋 Stopping clipboard monitoring...")
            self.running = False

def setup_data_directory() -> Tuple[str, str]:
    """Setup data directory and return paths"""
    home_dir = Path.home()
    data_dir = home_dir / ".clipulse"
    data_dir.mkdir(exist_ok=True)
    
    db_path = str(data_dir / "clipboard.db")
    config_path = str(data_dir / "config.json")
    
    return db_path, config_path

def format_entry(entry: ClipboardEntry, show_full: bool = False) -> str:
    """Format a clipboard entry for display"""
    timestamp = entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    content = entry.content if show_full else entry.content[:100]
    if len(entry.content) > 100 and not show_full:
        content += "..."
    
    return f"[{timestamp}] {entry.source_app}: {content}"

def show_diff(old_content: str, new_content: str):
    """Show diff between two clipboard entries"""
    diff = difflib.unified_diff(
        old_content.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile='Previous',
        tofile='Current'
    )
    
    print("📊 Content Diff:")
    for line in diff:
        print(line.rstrip())

def tui_mode(db: ClipulseDB):
    """Terminal UI mode for browsing history"""
    if not HAS_CURSES:
        print("TUI mode requires curses. Install with: pip install windows-curses (Windows)")
        return
    
    def main_tui(stdscr):
        curses.curs_set(0)  # Hide cursor
        stdscr.clear()
        
        entries = db.get_history(1000)
        current_selection = 0
        
        while True:
            stdscr.clear()
            height, width = stdscr.getmaxyx()
            
            # Title
            title = "📋 Clipulse History Browser"
            stdscr.addstr(0, (width - len(title)) // 2, title, curses.A_BOLD)
            stdscr.addstr(1, 0, "─" * width)
            
            # Instructions
            instructions = "↑/↓: Navigate | Enter: View full | q: Quit"
            stdscr.addstr(height - 1, 0, instructions)
            
            # Entries list
            start_y = 3
            visible_entries = height - 5
            
            for i, entry in enumerate(entries[current_selection:current_selection + visible_entries]):
                y = start_y + i
                if y >= height - 2:
                    break
                
                display_idx = current_selection + i
                prefix = "→ " if display_idx == current_selection else "  "
                text = f"{prefix}{format_entry(entry)}"
                
                if len(text) > width - 1:
                    text = text[:width - 4] + "..."
                
                attr = curses.A_REVERSE if display_idx == current_selection else curses.A_NORMAL
                stdscr.addstr(y, 0, text, attr)
            
            stdscr.refresh()
            
            # Handle input
            key = stdscr.getch()
            
            if key == ord('q'):
                break
            elif key == curses.KEY_UP and current_selection > 0:
                current_selection -= 1
            elif key == curses.KEY_DOWN and current_selection < len(entries) - 1:
                current_selection += 1
            elif key == ord('\n') or key == ord('\r'):
                # Show full entry
                if current_selection < len(entries):
                    entry = entries[current_selection]
                    stdscr.clear()
                    stdscr.addstr(0, 0, f"Full Content ({entry.timestamp}):", curses.A_BOLD)
                    stdscr.addstr(1, 0, "─" * width)
                    
                    # Display full content
                    lines = entry.content.split('\n')
                    for i, line in enumerate(lines):
                        if i + 3 >= height - 2:
                            break
                        if len(line) > width - 1:
                            line = line[:width - 4] + "..."
                        stdscr.addstr(i + 3, 0, line)
                    
                    stdscr.addstr(height - 1, 0, "Press any key to return...")
                    stdscr.refresh()
                    stdscr.getch()
    
    curses.wrapper(main_tui)

def main():
    parser = argparse.ArgumentParser(description="Clipulse - Clipboard Activity Monitor")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Watch command
    watch_parser = subparsers.add_parser('watch', help='Start monitoring clipboard')
    
    # History command
    history_parser = subparsers.add_parser('history', help='View clipboard history')
    history_parser.add_argument('--limit', type=int, default=20, help='Number of entries to show')
    history_parser.add_argument('--full', action='store_true', help='Show full content')
    history_parser.add_argument('--tui', action='store_true', help='Open terminal UI')
    
    # Search command
    search_parser = subparsers.add_parser('search', help='Search clipboard history')
    search_parser.add_argument('keyword', help='Search keyword')
    search_parser.add_argument('--full', action='store_true', help='Show full content')
    
    # Clear command
    clear_parser = subparsers.add_parser('clear', help='Clear clipboard history')
    
    # Export command
    export_parser = subparsers.add_parser('export', help='Export clipboard history')
    export_parser.add_argument('--json', action='store_true', help='Export as JSON')
    export_parser.add_argument('--txt', action='store_true', help='Export as text')
    export_parser.add_argument('--output', help='Output file path')
    
    # Filter command
    filter_parser = subparsers.add_parser('filter', help='Manage content filters')
    filter_parser.add_argument('--add-app', help='Add app to ignore list')
    filter_parser.add_argument('--add-pattern', help='Add regex pattern to ignore')
    filter_parser.add_argument('--list', action='store_true', help='List current filters')
    filter_parser.add_argument('--clear', action='store_true', help='Clear all filters')
    
    # Expire command
    expire_parser = subparsers.add_parser('expire', help='Remove old entries')
    expire_parser.add_argument('--minutes', type=int, required=True, help='Remove entries older than X minutes')
    
    # Sync command
    sync_parser = subparsers.add_parser('sync', help='Configure sync settings')
    sync_parser.add_argument('--webhook', help='Set webhook URL')
    sync_parser.add_argument('--enable', action='store_true', help='Enable sync')
    sync_parser.add_argument('--disable', action='store_true', help='Disable sync')
    
    # Diff command
    diff_parser = subparsers.add_parser('diff', help='Show diff between recent entries')
    diff_parser.add_argument('--count', type=int, default=2, help='Number of recent entries to compare')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Setup data directory
    db_path, config_path = setup_data_directory()
    db = ClipulseDB(db_path)
    config = ClipulseConfig(config_path)
    
    # Handle commands
    if args.command == 'watch':
        monitor = ClipulseMonitor(db, config)
        monitor.start_monitoring()
    
    elif args.command == 'history':
        if args.tui:
            tui_mode(db)
        else:
            entries = db.get_history(args.limit)
            if not entries:
                print("📋 No clipboard history found.")
                return
            
            print(f"📋 Last {len(entries)} clipboard entries:")
            for entry in entries:
                print(format_entry(entry, args.full))
    
    elif args.command == 'search':
        entries = db.search_history(args.keyword)
        if not entries:
            print(f"🔍 No entries found for '{args.keyword}'")
            return
        
        print(f"🔍 Found {len(entries)} entries for '{args.keyword}':")
        for entry in entries:
            print(format_entry(entry, args.full))
    
    elif args.command == 'clear':
        db.clear_history()
        print("🗑️  Clipboard history cleared.")
    
    elif args.command == 'export':
        entries = db.get_history(10000)  # Export all
        
        if args.json:
            data = [entry.to_dict() for entry in entries]
            output = json.dumps(data, indent=2)
            filename = args.output or "clipboard_history.json"
        else:  # Default to txt
            output = "\n".join(format_entry(entry, True) for entry in entries)
            filename = args.output or "clipboard_history.txt"
        
        with open(filename, 'w') as f:
            f.write(output)
        print(f"📄 Exported {len(entries)} entries to {filename}")
    
    elif args.command == 'filter':
        if args.add_app:
            config.config["filters"]["ignore_apps"].append(args.add_app)
            config.save_config()
            print(f"✅ Added app filter: {args.add_app}")
        
        elif args.add_pattern:
            config.config["filters"]["ignore_patterns"].append(args.add_pattern)
            config.save_config()
            print(f"✅ Added pattern filter: {args.add_pattern}")
        
        elif args.list:
            filters = config.config["filters"]
            print("🔍 Current filters:")
            print(f"  Ignored apps: {filters['ignore_apps']}")
            print(f"  Ignored patterns: {filters['ignore_patterns']}")
        
        elif args.clear:
            config.config["filters"] = {"ignore_apps": [], "ignore_patterns": []}
            config.save_config()
            print("🗑️  All filters cleared.")
    
    elif args.command == 'expire':
        db.expire_old_entries(args.minutes)
        print(f"🕐 Removed entries older than {args.minutes} minutes.")
    
    elif args.command == 'sync':
        if args.webhook:
            config.config["sync"]["webhook_url"] = args.webhook
            config.save_config()
            print(f"🔗 Webhook URL set: {args.webhook}")
        
        if args.enable:
            config.config["sync"]["enabled"] = True
            config.save_config()
            print("✅ Sync enabled.")
        
        if args.disable:
            config.config["sync"]["enabled"] = False
            config.save_config()
            print("❌ Sync disabled.")
    
    elif args.command == 'diff':
        entries = db.get_history(args.count)
        if len(entries) < 2:
            print("📊 Need at least 2 entries for diff.")
            return
        
        show_diff(entries[1].content, entries[0].content)

if __name__ == "__main__":
    main()