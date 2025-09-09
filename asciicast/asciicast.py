#!/usr/bin/env python3
"""
asciicast - Record and replay your terminal session like a movie.
Great for tutorials, demos, etc.
"""

import argparse
import json
import os
import pty
import select
import subprocess
import sys
import termios
import time
import tty
from typing import List, Dict, Any

class AsciicastRecorder:
    def __init__(self, output_file: str):
        self.output_file = output_file
        self.events: List[Dict[str, Any]] = []
        self.start_time = None
        
    def record(self, shell: str = None):
        """Record a terminal session"""
        if shell is None:
            shell = os.environ.get('SHELL', '/bin/bash')
            
        print(f"Recording session to {self.output_file}")
        print("Type 'exit' or press Ctrl+D to stop recording")
        
        # Save original terminal settings
        old_tty = termios.tcgetattr(sys.stdin)
        
        try:
            # Create pseudo-terminal
            master, slave = pty.openpty()
            
            # Start shell process
            proc = subprocess.Popen(
                shell,
                stdin=slave,
                stdout=slave,
                stderr=slave,
                close_fds=True,
                preexec_fn=os.setsid
            )
            
            # Close slave in parent process
            os.close(slave)
            
            # Set terminal to raw mode
            tty.setraw(sys.stdin.fileno())
            
            self.start_time = time.time()
            
            # Record header
            header = {
                "version": 2,
                "width": os.get_terminal_size().columns,
                "height": os.get_terminal_size().lines,
                "timestamp": int(self.start_time),
                "env": {
                    "SHELL": shell,
                    "TERM": os.environ.get('TERM', 'xterm-256color')
                }
            }
            
            # Main recording loop
            while proc.poll() is None:
                ready, _, _ = select.select([sys.stdin, master], [], [], 0.1)
                
                if sys.stdin in ready:
                    # Read input from user
                    try:
                        data = os.read(sys.stdin.fileno(), 1024)
                        if data:
                            # Send to shell
                            os.write(master, data)
                            # Record input event
                            self.events.append([
                                time.time() - self.start_time,
                                "i",
                                data.decode('utf-8', errors='replace')
                            ])
                    except OSError:
                        break
                
                if master in ready:
                    # Read output from shell
                    try:
                        data = os.read(master, 1024)
                        if data:
                            # Write to terminal
                            os.write(sys.stdout.fileno(), data)
                            # Record output event
                            self.events.append([
                                time.time() - self.start_time,
                                "o",
                                data.decode('utf-8', errors='replace')
                            ])
                    except OSError:
                        break
            
            # Save recording
            recording = {
                **header,
                "events": self.events
            }
            
            with open(self.output_file, 'w') as f:
                json.dump(recording, f, indent=2)
                
            print(f"\nRecording saved to {self.output_file}")
            
        finally:
            # Restore terminal settings
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_tty)
            try:
                os.close(master)
            except:
                pass

class AsciicastPlayer:
    def __init__(self, input_file: str):
        self.input_file = input_file
        self.recording = None
        
    def load_recording(self):
        """Load recording from file"""
        try:
            with open(self.input_file, 'r') as f:
                self.recording = json.load(f)
        except FileNotFoundError:
            print(f"Error: Recording file '{self.input_file}' not found")
            sys.exit(1)
        except json.JSONDecodeError:
            print(f"Error: Invalid recording file '{self.input_file}'")
            sys.exit(1)
    
    def play(self, speed: float = 1.0):
        """Play back the recording"""
        if not self.recording:
            self.load_recording()
        
        print(f"Playing {self.input_file}")
        print("Press Ctrl+C to stop playback")
        
        # Clear screen
        print("\033[2J\033[H", end='')
        
        try:
            last_time = 0
            for event in self.recording.get('events', []):
                timestamp, event_type, data = event
                
                # Calculate delay
                delay = (timestamp - last_time) / speed
                if delay > 0:
                    time.sleep(delay)
                
                # Only play output events
                if event_type == "o":
                    print(data, end='', flush=True)
                
                last_time = timestamp
                
        except KeyboardInterrupt:
            print("\nPlayback stopped")
        
        print("\nPlayback finished")

def main():
    parser = argparse.ArgumentParser(
        description="Record and replay terminal sessions like a movie"
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Record command
    record_parser = subparsers.add_parser('rec', help='Record a terminal session')
    record_parser.add_argument('output', help='Output file (.cast)')
    record_parser.add_argument('--shell', help='Shell to use (default: $SHELL)')
    
    # Play command
    play_parser = subparsers.add_parser('play', help='Play back a recording')
    play_parser.add_argument('input', help='Input file (.cast)')
    play_parser.add_argument('--speed', type=float, default=1.0, 
                           help='Playback speed multiplier (default: 1.0)')
    
    # Info command
    info_parser = subparsers.add_parser('info', help='Show recording info')
    info_parser.add_argument('input', help='Input file (.cast)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    if args.command == 'rec':
        recorder = AsciicastRecorder(args.output)
        recorder.record(args.shell)
    
    elif args.command == 'play':
        player = AsciicastPlayer(args.input)
        player.play(args.speed)
    
    elif args.command == 'info':
        try:
            with open(args.input, 'r') as f:
                recording = json.load(f)
            
            print(f"File: {args.input}")
            print(f"Version: {recording.get('version', 'unknown')}")
            print(f"Size: {recording.get('width', '?')}x{recording.get('height', '?')}")
            print(f"Duration: {recording['events'][-1][0]:.2f}s" if recording.get('events') else "0s")
            print(f"Events: {len(recording.get('events', []))}")
            print(f"Shell: {recording.get('env', {}).get('SHELL', 'unknown')}")
            
        except Exception as e:
            print(f"Error reading file: {e}")

if __name__ == "__main__":
    main()