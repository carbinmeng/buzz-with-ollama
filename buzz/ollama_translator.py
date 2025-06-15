import os
import logging
import queue
import requests
import json
import time

from typing import Optional, Dict, Any, List
from PyQt6.QtCore import QObject, pyqtSignal

#from buzz.settings.settings import Settings
from buzz.store.keyring_store import get_password, Key
from buzz.transcriber.transcriber import TranscriptionOptions
from buzz.widgets.transcriber.advanced_settings_dialog import AdvancedSettingsDialog

import os
from dotenv import load_dotenv
load_dotenv()

class OllamaTranslator(QObject):
  translation = pyqtSignal(str, int)
  finished = pyqtSignal()
  is_running = False

  def __init__(
    self,
    transcription_options: TranscriptionOptions,
    advanced_settings_dialog: AdvancedSettingsDialog,
    parent: Optional[QObject] = None,
  ) -> None:
    super().__init__(parent)

    logging.debug(f"OllamaTranslator init: {transcription_options}")

    self.transcription_options = transcription_options
    self.advanced_settings_dialog = advanced_settings_dialog
    self.advanced_settings_dialog.transcription_options_changed.connect(
      self.on_transcription_options_changed
    )

    self.queue = queue.Queue()
    
    # Initialize conversation history
    self.message_history = []
    self.max_history_length = int(os.getenv(
      "OLLAMA_HISTORY_LENGTH",
      "50"
    ))
    self.conversation_timeout = int(os.getenv(
      "OLLAMA_CONVERSATION_TIMEOUT",
      "20"
    ))

    #settings = Settings()
    # Get Ollama API URL from settings or environment
    self.ollama_api_url = os.getenv(
      "OLLAMA_BASE_URL",
      "http://localhost:11434"
    )
    # Get Ollama model name from settings or environment
    self.ollama_model = os.getenv(
      "OLLAMA_MODEL",
      "llama3.1:8b"  # Default model name in Ollama
    )
    
    logging.debug(f"OllamaTranslator using API URL: {self.ollama_api_url} and model: {self.ollama_model}, history length: {self.max_history_length}, conversation timeout: {self.conversation_timeout}")
    
    # Verify Ollama connection
    try:
      check_response = requests.get(f"{self.ollama_api_url}")
      logging.debug(f"Ollama server status check: {check_response.status_code}")
      self.is_available = check_response.status_code == 200
    except Exception as e:
      logging.error(f"Failed to connect to Ollama server: {str(e)}")
      self.is_available = False

  def start(self):
    logging.debug("Starting Ollama translation queue")

    self.is_running = True
    last_activity_time = time.time()

    while self.is_running:
      try:
        transcript, transcript_id = self.queue.get(timeout=1)
      except queue.Empty:
        # Check if we should reset conversation due to inactivity
        if time.time() - last_activity_time > self.conversation_timeout and self.message_history:
          logging.debug(f"Resetting conversation history due to {self.conversation_timeout}s of inactivity")
          self.message_history = []
        continue

      # Update activity time
      last_activity_time = time.time()

      # Check if Ollama is available
      if not self.is_available:
        logging.warning("Ollama server is not available. Skipping translation.")
        next_translation = transcript  # Use original text as fallback
      else:
        try:
          # Prepare the API endpoint URL for chat
          api_url = f"{self.ollama_api_url}/api/chat"
          
          # Build messages array with history
          messages = [
            {"role": "system", "content": self.transcription_options.llm_prompt}
          ]
          
          # Add conversation history
          messages.extend(self.message_history)
          
          # Add current user message
          messages.append({"role": "user", "content": transcript})
          
          # Prepare request data
          data = {
            "model": self.ollama_model,
            "messages": messages,
            "stream": False
          }
          
          logging.debug(f"Sending request to Ollama API: {api_url}, history length: {len(self.message_history)}, total messages: {len(messages)}, last message: {messages[-1]['content']}")
          # Log out all messages content
          # for item in messages:
          #   logging.debug(f"Sending message content: {item['content']}")

          
          # Make the API request
          response = requests.post(api_url, json=data)
          
          if response.status_code == 200:
            result = response.json()
            logging.debug(f"Received translation response: {result}")
            
            if "message" in result and "content" in result["message"]:
              next_translation = result["message"]["content"]
              
              # Remove <think> tags and their content if present
              import re
              next_translation = re.sub(r'<think>.*?</think>', '', next_translation, flags=re.DOTALL)
              # Also handle the case with backslash in closing tag
              next_translation = re.sub(r'<think>.*?<\\think>', '', next_translation, flags=re.DOTALL)
              # Strip any leading/trailing whitespace
              next_translation = next_translation.strip()
              
              # Add the exchange to history
              self.message_history.append({"role": "user", "content": transcript})
              self.message_history.append({"role": "assistant", "content": next_translation})
              
              # Trim history if it gets too long (keep most recent exchanges)
              if len(self.message_history) > self.max_history_length * 2:  # *2 because each exchange is 2 messages
                self.message_history = self.message_history[-self.max_history_length * 2:]
                #logging.debug(f"Trimmed conversation history to {len(self.message_history)} messages")
            else:
              logging.error(f"Unexpected response format: {result}")
              next_translation = transcript  # Use original text as fallback
          else:
            logging.error(f"Ollama API error: {response.status_code} - {response.text}")
            next_translation = transcript  # Use original text as fallback
            
        except Exception as e:
          logging.error(f"Error during Ollama translation: {e}")
          next_translation = transcript  # Use original text as fallback

      self.translation.emit(next_translation, transcript_id)

  def on_transcription_options_changed(
    self, transcription_options: TranscriptionOptions
  ):
    logging.debug(f"Transcription options changed: {transcription_options}")
    self.transcription_options = transcription_options

  def enqueue(self, transcript: str, transcript_id: Optional[int] = None):
    logging.debug(f"Enqueuing transcript for translation: {transcript[:50]}...")
    self.queue.put((transcript, transcript_id))

  def stop(self):
    logging.debug("Stopping Ollama translation queue")
    self.is_running = False
