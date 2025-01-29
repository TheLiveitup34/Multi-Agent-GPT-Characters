import socket
import threading
import time
from dataclasses import dataclass
from typing import List, Set
import keyboard
import datetime
import emoji
import os
import sys

@dataclass
class TwitchMessage:
    channel: str
    username: str
    message: str
    timestamp: float

class TwitchChatViewer:
    def __init__(self):
        self.server = "irc.chat.twitch.tv"
        self.port = 6667
        self.nickname = "justinfan12345"  # Anonymous connection
        self.channels: Set[str] = set()
        self.socket = socket.socket()
        self.running = False
        self.logging_enabled = False
        self.log_file = None
        
        # Create logs directory if it doesn't exist
        self.logs_dir = "twitch_logs"
        os.makedirs(self.logs_dir, exist_ok=True)

    def toggle_logging(self):
        self.logging_enabled = not self.logging_enabled
        if self.logging_enabled:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.log_file = open(f"{self.logs_dir}/twitch_chat_{timestamp}.log", "a", encoding="utf-8")
            print("\n[System] Logging enabled - saving to file")
        else:
            if self.log_file:
                self.log_file.close()
                self.log_file = None
            print("\n[System] Logging disabled")

    def connect(self):
        try:
            print(f"[System] Connecting to {self.server}...")
            self.socket.connect((self.server, self.port))
            self.socket.send(f"NICK {self.nickname}\r\n".encode())
            time.sleep(1)  # Give some time for the connection to establish
            self.running = True
            print("[System] Connected successfully!")
            return True
        except Exception as e:
            print(f"[Error] Failed to connect: {e}")
            return False

    def join_channel(self, channel: str):
        if not channel.startswith('#'):
            channel = f"#{channel}"
        self.channels.add(channel)
        if self.running:
            print(f"[System] Joining channel: {channel}")
            self.socket.send(f"JOIN {channel}\r\n".encode())
            time.sleep(0.5)  # Rate limiting for joins

    def leave_channel(self, channel: str):
        if not channel.startswith('#'):
            channel = f"#{channel}"
        if channel in self.channels:
            self.channels.remove(channel)
            if self.running:
                self.socket.send(f"PART {channel}\r\n".encode())

    def format_message(self, msg: TwitchMessage) -> str:
        timestamp = datetime.datetime.fromtimestamp(msg.timestamp).strftime("%Y-%m-%d %H:%M:%S")
        return f"[{timestamp}] {msg.channel} - {msg.username}: {emoji.demojize(msg.message)}"

    def _process_message(self, message: str):
        if message.startswith("PING"):
            self.socket.send("PONG :tmi.twitch.tv\r\n".encode())
            return

        try:
            # Extract username and channel from IRC message
            if "PRIVMSG" not in message:
                return

            username_part = message.split('!', 1)[0][1:]
            channel = message.split('PRIVMSG', 1)[1].split(':', 1)[0].strip()
            msg_content = message.split('PRIVMSG', 1)[1].split(':', 1)[1].strip()

            twitch_message = TwitchMessage(
                channel=channel,
                username=username_part,
                message=msg_content,
                timestamp=time.time()
            )

            # Format the message once for both console and file
            formatted_message = self.format_message(twitch_message)

            # Log to file if enabled
            if self.logging_enabled and self.log_file:
                # remove the #channel from the message
                formatted_message = formatted_message.replace(f"{twitch_message.channel} - ", "")
                self.log_file.write(formatted_message + "\n")
                self.log_file.flush()

            # Print to console
            print(formatted_message)

        except Exception as e:
            print(f"[Error] Processing message: {e}")

    def _read_messages(self):
        buffer = ""
        while self.running:
            try:
                new_data = self.socket.recv(2048).decode('utf-8', errors='ignore')
                if not new_data:
                    if self.running:
                        print("[Warning] Lost connection, attempting to reconnect...")
                        self.socket.close()
                        self.socket = socket.socket()
                        if self.connect():
                            for channel in self.channels:
                                self.join_channel(channel)
                    continue

                buffer += new_data
                messages = buffer.split("\r\n")
                buffer = messages.pop()

                for message in messages:
                    if message:
                        self._process_message(message)

            except Exception as e:
                print(f"[Error] Reading messages: {e}")
                if not self.running:
                    break
                time.sleep(1)

    def _keyboard_handler(self):
        keyboard.on_press_key('l', lambda _: self.toggle_logging())
        keyboard.on_press_key('q', lambda _: self.stop())

    def start(self):
        if not self.channels:
            print("[Error] No channels specified. Please add channels before starting.")
            return False

        if not self.connect():
            return False

        print("[System] Joining channels...")
        # Join all channels
        for channel in self.channels:
            self.join_channel(channel)

        # Start message reading thread
        thread = threading.Thread(target=self._read_messages)
        thread.daemon = True
        thread.start()

        # Start keyboard handler thread
        keyboard_thread = threading.Thread(target=self._keyboard_handler)
        keyboard_thread.daemon = True
        keyboard_thread.start()

        print("\n[System] Chat viewer started!")
        print("Controls:")
        print("- Press 'L' to toggle logging")
        print("- Press 'Q' to quit")
        return True

    def stop(self):
        print("\n[System] Shutting down...")
        self.running = False
        if self.log_file:
            self.log_file.close()
        self.socket.close()
        sys.exit(0)
        
        
if __name__ == "__main__":
    # Create viewer instance
    viewer = TwitchChatViewer()
    
    # Add channels to monitor (replace these with actual channels you want to monitor)
    # viewer.join_channel("fliberjig1official")  # Example channel
    # viewer.join_channel("im_so_twitch")  # Example channel
    viewer.join_channel("theliveitup34official")  # Example channel
    
    # Start the viewer
    if viewer.start():
        # Keep the main thread running
        while viewer.running:
            try:
                time.sleep(0.1)
            except KeyboardInterrupt:
                viewer.stop()
    else:
        print("[Error] Failed to start viewer")
        sys.exit(1)