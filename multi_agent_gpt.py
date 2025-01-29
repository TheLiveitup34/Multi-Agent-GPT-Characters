from flask import Flask, render_template, session, request
from flask_socketio import SocketIO, emit
import threading
import time
import keyboard
import random
import logging
import sys
import os
import signal
from rich import print
import atexit

from audio_player import AudioManager
from eleven_labs import ElevenLabsManager
# from openai_chat import OpenAiManager
from ollama_chat import OllamaManager
from whisper_openai import WhisperManager
# from obs_websockets import OBSWebsocketsManager
from ai_prompts import *

# Global flags for shutdown
shutdown_flag = threading.Event()
flask_shutdown_flag = threading.Event()

socketio = SocketIO
app = Flask(__name__, host_matching=False)
app.config['SERVER_NAME'] = "127.0.0.1:5151"
socketio = SocketIO(app, async_mode="threading")
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# Store thread references globally
all_threads = []

@app.route("/")
def home():
    return render_template('index.html')

@app.route("/agent")
def agent():
    return render_template('agent.html')

@socketio.event
def connect():
    print("[green]The server connected to client!")

whisper_manager = WhisperManager()
elevenlabs_manager = ElevenLabsManager()
audio_manager = AudioManager()

speaking_lock = threading.Lock()
conversation_lock = threading.Lock()

agents_paused = False

class Agent():
    def __init__(self, agent_name, agent_id, filter_name, all_agents, system_prompt, elevenlabs_voice):
        self.activated = False
        self.name = agent_name
        self.agent_id = agent_id
        self.filter_name = filter_name
        self.all_agents = all_agents
        self.voice = elevenlabs_voice
        self.break_loop = False
        backup_file_name = f"backup_history_{agent_name}.txt"
        self.ollama_manager = OllamaManager(system_prompt, backup_file_name)
        self.ollama_manager.logging = False

    def run(self):
        while not shutdown_flag.is_set():
            if self.break_loop:
                print(f"[italic red] {self.name} has been TERMINATED")
                break
            if not self.activated:
                time.sleep(0.1)
                continue
            
            try:
                print(f"[italic purple] {self.name} has been ACTIVATED.")
                
                self.activated = False
                print(f"[italic purple] {self.name} has STARTED speaking.")
                
                with conversation_lock:
                    if shutdown_flag.is_set():
                        break
                    openai_answer = self.ollama_manager.chat_with_history("Okay what is your response? Try to be as chaotic and bizarre and adult-humor oriented as possible. Again, 3 sentences maximum.")
                    openai_answer = openai_answer.replace("*", "")
                    print(f'[magenta]Got the following response:\n{openai_answer}')

                    for agent in self.all_agents:
                        if agent is not self:
                            agent.ollama_manager.chat_history.append({"role": "user", "content": f"[{self.name}] {openai_answer}"})
                            agent.ollama_manager.save_chat_to_backup()

                if shutdown_flag.is_set():
                    break
                    
                tts_file = elevenlabs_manager.text_to_audio(openai_answer, self.voice, False)
                audio_and_timestamps = whisper_manager.audio_to_text(tts_file, "sentence")

                with speaking_lock:
                    if shutdown_flag.is_set():
                        break
                    socketio.emit('start_agent', {'agent_id': self.agent_id})
                    tts_file_name = tts_file.split(os.path.sep)[-1]
                    site_tts_file = f"static/msg/{tts_file_name}"
                    socketio.emit('agent_audio', {'agent_id': self.agent_id, 'audio': site_tts_file})

                    try:
                        for i in range(len(audio_and_timestamps)):
                            if shutdown_flag.is_set():
                                break
                            current_sentence = audio_and_timestamps[i]
                            duration = current_sentence['end_time'] - current_sentence['start_time']
                            socketio.emit('agent_message', {'agent_id': self.agent_id, 'text': f"{current_sentence['text']}"})
                            time.sleep(duration)
                            if i < (len(audio_and_timestamps) - 1):
                                time_between_sentences = audio_and_timestamps[i+1]['start_time'] - current_sentence['end_time']
                                time.sleep(time_between_sentences)
                    except Exception as e:
                        print(f"[magenta] Error processing sentence: {str(e)}")
                    
                    socketio.emit('clear_agent', {'agent_id': self.agent_id})
                    time.sleep(1)

                print(f"[italic purple] {self.name} has FINISHED speaking.")
            
            except Exception as e:
                print(f"[red]Error in agent {self.name}: {str(e)}")
                if shutdown_flag.is_set():
                    break

class Human():
    def __init__(self, name, all_agents):
        self.name = name
        self.all_agents = all_agents

    def run(self):
        global agents_paused
        while not shutdown_flag.is_set():
            try:
                if keyboard.is_pressed('num 9') or keyboard.is_pressed('ctrl+c'):
                    print("[italic red] Initiating shutdown...")
                    shutdown_flag.set()
                    flask_shutdown_flag.set()
                    break

                if keyboard.is_pressed('num 7'):
                    if shutdown_flag.is_set():
                        break
                    agents_paused = True
                    print(f"[italic red] Agents have been paused")

                    print(f"[italic green] {self.name} has STARTED speaking.")
                    mic_audio = audio_manager.record_audio(end_recording_key='num 8', audio_device="Voicemeeter Out B1")

                    with conversation_lock:
                        if shutdown_flag.is_set():
                            break
                        transcribed_audio = whisper_manager.audio_to_text(mic_audio)
                        print(f"[teal]Got the following audio from {self.name}:\n{transcribed_audio}")

                        for agent in self.all_agents:
                            agent.ollama_manager.chat_history.append({"role": "user", "content": f"[{self.name}] {transcribed_audio}"})
                            agent.ollama_manager.save_chat_to_backup()
                            
                    
                    print(f"[italic magenta] {self.name} has FINISHED speaking.")

                    agents_paused = False
                    random_agent = random.randint(0, len(self.all_agents)-1)
                    print(f"[cyan]Activating Agent {random_agent+1}")
                    self.all_agents[random_agent].activated = True

                # check if f6 is pressed then get the newest file in twitch logs and send it to the chatbot and summarize the response
                if keyboard.is_pressed('f6'):
                    if shutdown_flag.is_set():
                        break
                    agents_paused = True
                    print(f"[italic red] Agents have been paused")

                    print(f"[italic green] {self.name} has STARTED speaking.")
                  
                    with conversation_lock:
                        # look in the twitch logs folder and get the newest file
                        if shutdown_flag.is_set():
                            break

                        newest_file = ""
                        for file in os.listdir(os.path.join(os.path.abspath(os.curdir), "twitch_logs")):
                            if file.endswith(".log"):
                                # get the time of the file
                                # if the time is greater than the newest time then set the newest file to the current file
                                # if the time is less than the newest time then continue
                                if newest_file == "":
                                    newest_file = file
                                else:
                                    if os.path.getctime(os.path.join(os.path.abspath(os.curdir), "twitch_logs", file)) > os.path.getctime(os.path.join(os.path.abspath(os.curdir), "twitch_logs", newest_file)):
                                        newest_file = file
                        
                        print(os.path.join(os.path.abspath(os.curdir), "twitch_logs", newest_file))
                        with open(os.path.join(os.path.abspath(os.curdir), "twitch_logs", newest_file), "r") as f:
                            chat_text = f.read()

                        for agent in self.all_agents:
                            agent.ollama_manager.chat_history.append({"role": "user", "content": f"[{self.name}] Summerize chat and give an answer to what you think is the question and 'chat' is there name and add a spin on how you feel about it: {chat_text}"})
                            agent.ollama_manager.save_chat_to_backup()
                        
                    print(f"[italic magenta] {self.name} has FINISHED speaking.")

                    random_agent = random.randint(0, len(self.all_agents)-1)
                    print(f"[cyan]Activating Agent {random_agent+1}")
                    self.all_agents[random_agent].activated = True

                if keyboard.is_pressed('f4'):
                    print("[italic red] Agents have been paused")
                    agents_paused = True
                    time.sleep(1)
                
                if keyboard.is_pressed('num 1'):
                    print("[cyan]Activating Agent 1")
                    agents_paused = False
                    self.all_agents[0].activated = True
                    time.sleep(1)

                time.sleep(0.05)

            except Exception as e:
                print(f"[red]Error in human input: {str(e)}")
                if shutdown_flag.is_set():
                    break

def signal_handler(signum, frame):
    print("\n[yellow]Received shutdown signal. Initiating graceful shutdown...")
    
    print("\n[red]Killing Twitch Chat Viewer...")
    os.system('taskkill /f /im cmd.exe /fi "WINDOWTITLE eq Twitch Chat Viewer" 1>nul 2>&1')
    os.system('taskkill /f /im python.exe /fi "WINDOWTITLE eq Twitch Chat Viewer" 1>nul 2>&1')
    shutdown_flag.set()
    flask_shutdown_flag.set()

def start_bot(bot):
    bot.run()

def cleanup():
    print("[yellow]Cleaning up resources...")
    try:
        # Force stop the Flask-SocketIO server
        if not flask_shutdown_flag.is_set():
            flask_shutdown_flag.set()
        
        # Stop all threads
        for thread in all_threads:
            if thread.is_alive():
                try:
                    thread.join(timeout=2.0)  # Wait up to 2 seconds for each thread
                except Exception as e:
                    print(f"[red]Error joining thread: {str(e)}")
        
        # Force exit if threads are still running
        remaining_threads = [t for t in all_threads if t.is_alive()]
        if remaining_threads:
            print("[red]Some threads did not shut down cleanly. Forcing exit...")
            os._exit(1)
            
    except Exception as e:
        print(f"[red]Error during cleanup: {str(e)}")
        os._exit(1)

def flask_thread():
    try:
        socketio.run(app)
    except Exception as e:
        print(f"[red]Flask error: {str(e)}")
    finally:
        if shutdown_flag.is_set():
            os._exit(0)

if __name__ == '__main__':
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Register cleanup function
    atexit.register(cleanup)

    # Initialize all_agents list before creating agents
    all_agents = []

    try:


        # Open up a diffrent terminal and run the following command to twitch chat viewer:
        # python twitch_chat_viewer.py
        # detect if windows or linux
        if os.name == 'nt':
            os.system("start /min cmd /k twitch_chat_run.bat")
        else:
            os.system("start cmd /k twitch_chat_run.sh")
        # Agent 1
        agent1 = Agent("ELDRIN", 1, "Audio Move - Wario Pepper", all_agents, VIDEOGAME_AGENT_1, "Eldrin ")
        agent1_thread = threading.Thread(target=start_bot, args=(agent1,))
        agent1_thread.daemon = True  # Make thread daemon so it won't prevent program exit
        agent1_thread.start()
        all_threads.append(agent1_thread)

        # Add agent to all_agents list after creation
        all_agents.append(agent1)

        # Human thread
        human = Human("Liv", all_agents)
        human_thread = threading.Thread(target=start_bot, args=(human,))
        human_thread.daemon = True  # Make thread daemon so it won't prevent program exit
        human_thread.start()
        all_threads.append(human_thread)

        # Flask thread
        flask_thread = threading.Thread(target=flask_thread)
        flask_thread.daemon = True  # Make thread daemon so it won't prevent program exit
        flask_thread.start()
        all_threads.append(flask_thread)

        print("[italic green]!!AGENTS ARE READY TO GO!!\nPress Num 1 to activate the agent.\nPress F7 to speak to the agents.\nPress Num 9 or Ctrl+C to safely shut down.")

        # Main loop to keep program running until shutdown
        while not shutdown_flag.is_set():
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n[yellow]Keyboard interrupt received. Initiating shutdown...")
        # find a cmd terminal named "Twitch Chat Viewer" and kill the process

        shutdown_flag.set()
        flask_shutdown_flag.set()
    
    except Exception as e:
        print(f"[red]Error in main thread: {str(e)}")
    
    finally:
        cleanup()
        print("[italic red]All threads have been closed.")
        os._exit(0)