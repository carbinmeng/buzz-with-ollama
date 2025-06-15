import os
import logging
import queue

from typing import Optional, Union
from openai import OpenAI
from PyQt6.QtCore import QObject, pyqtSignal

from buzz.settings.settings import Settings
from buzz.store.keyring_store import get_password, Key
from buzz.transcriber.transcriber import TranscriptionOptions
from buzz.widgets.transcriber.advanced_settings_dialog import AdvancedSettingsDialog
from buzz.ollama_translator import OllamaTranslator
# import keyring
from dotenv import load_dotenv
load_dotenv()

class Translator(QObject):
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

        logging.debug(f"Translator init: {transcription_options}")

        self.transcription_options = transcription_options
        self.advanced_settings_dialog = advanced_settings_dialog
        self.advanced_settings_dialog.transcription_options_changed.connect(
            self.on_transcription_options_changed
        )

        self.queue = queue.Queue()

        settings = Settings()
        self.translation_provider = os.getenv(
            "TRANSLATION_PROVIDER",
            "OLLAMA"
        )
        logging.debug(f"Using translation provider: {self.translation_provider}")
        
        # Initialize the appropriate translator based on provider
        if self.translation_provider == "OLLAMA":
            # Create an Ollama translator instance
            self.ollama_translator = OllamaTranslator(
                transcription_options=transcription_options,
                advanced_settings_dialog=advanced_settings_dialog,
                parent=parent
            )
            self.openai_client = None
            logging.debug("Ollama translator initialized")
        else:  # Default to OpenAI
            self.ollama_translator = None
            
            # custom_openai_base_url = os.getenv(
            #     "TRANSLATION_OPENAI_API_BASE_URL",
            #     settings.value(
            #         key=Settings.Key.CUSTOM_OPENAI_BASE_URL, default_value=""
            #     )
            # )
            
            # openai_api_key = os.getenv(
            #     "TRANSLATION_OPENAI_API_KEY",
            #     get_password(Key.OPENAI_API_KEY)
            # )
            custom_openai_base_url = settings.value(key=Settings.Key.CUSTOM_OPENAI_BASE_URL, default_value="")
            openai_api_key = get_password(Key.OPENAI_API_KEY)
            # Initialize OpenAI client with proper error handling
            try:
                self.openai_client = OpenAI(
                    api_key=openai_api_key,
                    base_url=custom_openai_base_url if custom_openai_base_url else None
                )
                logging.debug("OpenAI client initialized successfully")
            except TypeError as e:
                logging.warning(f"Error initializing OpenAI client: {e}")
                # Fall back to a simpler initialization if there's a TypeError (likely due to proxies)
                self.openai_client = None
                logging.warning("OpenAI client disabled due to initialization error")

    def start(self):
        logging.debug("Starting translation queue")
        
        # If using Ollama, delegate to the Ollama translator
        if self.translation_provider == "OLLAMA" and self.ollama_translator:
            logging.debug("Delegating to Ollama translator")
            self.ollama_translator.translation.connect(self.translation.emit)
            self.ollama_translator.start()
            return
            
        # Otherwise use the OpenAI client
        self.is_running = True

        while self.is_running:
            try:
                transcript, transcript_id = self.queue.get(timeout=1)
            except queue.Empty:
                continue

            # Check if OpenAI client is available
            if self.openai_client is None:
                logging.warning("OpenAI client is not available. Skipping translation.")
                next_translation = transcript  # Use original text as fallback
            else:
                try:
                    completion = self.openai_client.chat.completions.create(
                        model=self.transcription_options.llm_model,
                        messages=[
                            {"role": "system", "content": self.transcription_options.llm_prompt},
                            {"role": "user", "content": transcript}
                        ]
                    )

                    logging.debug(f"Received translation response: {completion}")

                    if completion.choices and completion.choices[0].message:
                        next_translation = completion.choices[0].message.content
                    else:
                        logging.error(f"Translation error! Server response: {completion}")
                        next_translation = transcript  # Use original text as fallback
                except Exception as e:
                    logging.error(f"Error during translation: {e}")
                    next_translation = transcript  # Use original text as fallback

            self.translation.emit(next_translation, transcript_id)

        self.finished.emit()

    def on_transcription_options_changed(
        self, transcription_options: TranscriptionOptions
    ):
        logging.debug(f"Transcription options changed: {transcription_options}")
        self.transcription_options = transcription_options
        
        # Update the Ollama translator if it exists
        if self.ollama_translator:
            self.ollama_translator.on_transcription_options_changed(transcription_options)

    def enqueue(self, transcript: str, transcript_id: Optional[int] = None):
        # logging.debug(f"Enqueuing transcript for translation: {transcript[:50]}...")
        
        # If using Ollama, delegate to the Ollama translator
        if self.translation_provider == "OLLAMA" and self.ollama_translator:
            self.ollama_translator.enqueue(transcript, transcript_id)
        else:
            # Otherwise use the OpenAI queue
            self.queue.put((transcript, transcript_id))

    def stop(self):
        logging.debug("Stopping translation queue")
        
        # If using Ollama, stop the Ollama translator
        if self.translation_provider == "OLLAMA" and self.ollama_translator:
            self.ollama_translator.stop()
        else:
            # Otherwise stop the OpenAI queue
            self.is_running = False
