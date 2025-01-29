import requests
import json
import os
from rich import print
import base64
import sys
from typing import List, Dict, Union, Optional

class OllamaManager:
    def __init__(self, system_prompt=None, chat_history_backup=None, model="deepseek-r1:8b"):
        """
        Initialize OllamaManager with optional system prompt and chat history backup.
        
        Args:
            system_prompt (str, optional): Initial system prompt for the conversation
            chat_history_backup (str, optional): Path to backup file for chat history
            model (str, optional): Name of the Ollama model to use. Defaults to "llama2"
        """
        self.base_url = "http://localhost:11434/api"
        self.model = model
        self.logging = True
        self.chat_history: List[Dict[str, str]] = []
        self.chat_history_backup = chat_history_backup

        # Load chat history from backup if it exists
        if chat_history_backup and os.path.exists(chat_history_backup):
            with open(chat_history_backup, 'r') as file:
                self.chat_history = json.load(file)
        elif system_prompt:
            self.chat_history.append({
                "role": "system",
                "content": system_prompt
            })

    def save_chat_to_backup(self):
        """Save current chat history to backup file if specified"""
        if self.chat_history_backup:
            with open(self.chat_history_backup, 'w') as file:
                json.dump(self.chat_history, file)

    def chat(self, prompt: str) -> Optional[str]:
        """
        Send a single message to Ollama without maintaining chat history.
        
        Args:
            prompt (str): The message to send to Ollama
            
        Returns:
            str: The model's response or None if there's an error
        """
        if not prompt:
            print("Didn't receive input!")
            return None

        prompt_content = {
            "role": "user",
            "content": prompt
        }
        try:
            print("[yellow]\nAsking Ollama a question...")
            response = requests.post(
                f"{self.base_url}/chat",
                json={
                    "model": self.model,
                    "content": prompt_content,
                    "stream": False
                }
            )
            response.raise_for_status()
            result = response.json()
            
            message = result['message']['content']
            while "<think>" in message:
                start = message.find("<think>")
                end = message.find("</think>")
                message = message[:start] + message[end+8:]
            message = message.strip()

            result['message']['content'] = message
            # Add response to chat history

            if self.logging:
                print(f"[green]\n{result['message']['content']}\n")
            return result['message']['content']
            
        except Exception as e:
            # add line number to print statement
            print(f"[red]Error during Ollama request: {str(e)} on line {sys.exc_info()[-1].tb_lineno}")
            return None

    def chat_with_history(self, prompt: Optional[str] = "") -> Optional[str]:
        """
        Send a message to Ollama while maintaining conversation history.
        
        Args:
            prompt (str, optional): The new message to send. If empty, continues the conversation.
            
        Returns:
            str: The model's response or None if there's an error
        """
        try:
            # Add new prompt to chat history if provided
            if prompt:
                self.chat_history.append({
                    "role": "user",
                    "content": prompt
                })

            # Prepare messages in Ollama format
            messages = []
            for chat in self.chat_history:
                # check if content is not a string
                if isinstance(chat['content'], str) == False:
                    # check if content is a list
                    # check if there is a 0th element in the list
                    if isinstance(chat['content'], list) and len(chat['content']) > 0:
                        messages.append({
                            "role": chat['role'],
                            "content": chat['content'][0]["text"]
                        })
                    else:
                        messages.append({
                            "role": chat['role'],
                            "content": chat['content']["content"]
                        })
                else:
                    messages.append({
                        "role": chat['role'],
                        "content": chat['content']
                    })

            print("[yellow]\nAsking Ollama a question...")
            response = requests.post(
                f"{self.base_url}/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False
                }
            )
            response.raise_for_status()
            result = response.json()

            # remove any of the <think> tags from the response its
            message = result['message']['content']
            while "<think>" in message:
                start = message.find("<think>")
                end = message.find("</think>")
                message = message[:start] + message[end+8:]
            message = message.strip()

            result['message']['content'] = message
            # Add response to chat history
            self.chat_history.append({
                "role": "assistant",
                "content": result['message']['content']
            })

            # Save to backup if enabled
            self.save_chat_to_backup()

            if self.logging:
                print(f"[green]\n{result['message']['content']}\n")
            return result['message']['content']

        except Exception as e:
            print(f"[red]Error during Ollama request: {str(e)} on line {sys.exc_info()[-1].tb_lineno}")
            return None

    def analyze_image(self, prompt: str, image_path: str, local_image: bool = True) -> Optional[str]:
        """
        Analyze an image using Ollama (requires a multimodal model like llava).
        
        Args:
            prompt (str): The prompt describing what to analyze in the image
            image_path (str): Path to local image or URL
            local_image (bool): Whether the image_path is a local file (True) or URL (False)
            
        Returns:
            str: The model's response or None if there's an error
        """
        try:
            # Convert image to base64 if it's a local file
            if local_image:
                try:
                    with open(image_path, "rb") as image_file:
                        base64_image = base64.b64encode(image_file.read()).decode("utf-8")
                except Exception as e:
                    print(f"[red]Error reading image file: {str(e)}")
                    return None
            else:
                # For URLs, download the image first
                try:
                    response = requests.get(image_path)
                    response.raise_for_status()
                    base64_image = base64.b64encode(response.content).decode("utf-8")
                except Exception as e:
                    print(f"[red]Error downloading image from URL: {str(e)}")
                    return None

            print("[yellow]\nAsking Ollama to analyze image...")
            response = requests.post(
                f"{self.base_url}/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "images": [base64_image],
                    "stream": False
                }
            )
            response.raise_for_status()
            result = response.json()

            if self.logging:
                print(f"[green]\n{result['response']}\n")
            return result['response']

        except Exception as e:
            print(f"[red]Error during Ollama image analysis: {str(e)}")
            return None