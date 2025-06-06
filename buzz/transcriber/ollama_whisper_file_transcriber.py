import logging
import math
import os
import subprocess
import tempfile
import requests
import json
from typing import Optional, List

from PyQt6.QtCore import QObject

from buzz.settings.settings import Settings
from buzz.transcriber.file_transcriber import FileTranscriber
from buzz.transcriber.transcriber import FileTranscriptionTask, Segment, Task


class OllamaWhisperFileTranscriber(FileTranscriber):
    """
    OllamaWhisperFileTranscriber transcribes an audio file to text using a locally hosted
    Ollama API instance. It follows the same pattern as OpenAIWhisperAPIFileTranscriber
    but connects to a local Ollama server instead of OpenAI's API.
    """
    
    def __init__(self, task: FileTranscriptionTask, parent: Optional["QObject"] = None):
        super().__init__(task=task, parent=parent)
        
        settings = Settings()
        # Get Ollama API URL from settings or use default
        self.ollama_api_url = settings.value(
            key=Settings.Key.OLLAMA_API_URL, 
            default_value="http://localhost:11434"
        )
        # Get Ollama model name from settings or use default
        self.ollama_model = settings.value(
            key=Settings.Key.OLLAMA_MODEL,
            default_value="whisper"  # Default model name in Ollama
        )
        
        self.task = task.transcription_options.task
        logging.debug("Will use Ollama API on %s with model %s",
                      self.ollama_api_url, self.ollama_model)

    def transcribe(self) -> List[Segment]:
        logging.debug(
            "Starting Ollama Whisper file transcription, file path = %s, task = %s",
            self.transcription_task.file_path,
            self.task,
        )

        # Convert input file to mp3 format for processing
        mp3_file = tempfile.mktemp() + ".mp3"

        cmd = [
            "ffmpeg",
            "-threads", "0",
            "-loglevel", "panic",
            "-i", self.transcription_task.file_path, mp3_file
        ]

        result = subprocess.run(cmd, capture_output=True)

        if result.returncode != 0:
            logging.warning(f"FFMPEG audio load warning. Process return code was not zero: {result.returncode}")

        if len(result.stderr):
            logging.warning(f"FFMPEG audio load error. Error: {result.stderr.decode()}")
            raise Exception(f"FFMPEG Failed to load audio: {result.stderr.decode()}")

        # Get audio duration
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            mp3_file,
        ]
        
        duration_secs = float(
            subprocess.run(cmd, capture_output=True, check=True).stdout.decode("utf-8")
        )

        total_size = os.path.getsize(mp3_file)
        max_chunk_size = 25 * 1024 * 1024  # 25MB max chunk size

        self.progress.emit((0, 100))

        if total_size < max_chunk_size:
            return self.get_segments_for_file(mp3_file)

        # If the file is larger than max_chunk_size, split into chunks
        # and transcribe each chunk separately
        num_chunks = math.ceil(total_size / max_chunk_size)
        chunk_duration = duration_secs / num_chunks

        segments = []

        for i in range(num_chunks):
            chunk_start = i * chunk_duration
            chunk_end = min((i + 1) * chunk_duration, duration_secs)

            chunk_file = tempfile.mktemp() + ".mp3"

            cmd = [
                "ffmpeg",
                "-i", mp3_file,
                "-ss", str(chunk_start),
                "-to", str(chunk_end),
                "-c", "copy",
                chunk_file,
            ]
            
            subprocess.run(cmd, capture_output=True, check=True)
            logging.debug('Created chunk file "%s"', chunk_file)

            segments.extend(
                self.get_segments_for_file(
                    chunk_file, offset_ms=int(chunk_start * 1000)
                )
            )
            os.remove(chunk_file)
            self.progress.emit((i + 1, num_chunks))

        os.remove(mp3_file)  # Clean up the temporary mp3 file
        return segments

    def get_segments_for_file(self, file: str, offset_ms: int = 0) -> List[Segment]:
        """
        Send the audio file to Ollama API for transcription and parse the results.
        
        Args:
            file: Path to the audio file
            offset_ms: Time offset in milliseconds for chunked files
            
        Returns:
            List of Segment objects with transcription results
        """
        try:
            # Prepare the API endpoint URL for audio processing
            api_url = f"{self.ollama_api_url}/api/audio"
            logging.debug(f"Sending request to Ollama API: {api_url}")
            
            # Check if Ollama is running by making a simple request to the base URL
            try:
                check_response = requests.get(f"{self.ollama_api_url}")
                logging.debug(f"Ollama server status check: {check_response.status_code} - {check_response.text[:100]}")
            except Exception as e:
                logging.error(f"Failed to connect to Ollama server: {str(e)}")
            
            # Read audio file as binary data
            with open(file, "rb") as audio_file:
                files = {
                    'file': ('audio.mp3', audio_file, 'audio/mpeg')
                }
                
                # Prepare parameters
                data = {
                    'model': self.ollama_model,
                    'prompt': self.transcription_task.transcription_options.initial_prompt,
                    'language': self.transcription_task.transcription_options.language or None,
                    'response_format': 'verbose_json',
                    'task': self.transcription_task.transcription_options.task.value
                }
                
                # Filter out None values
                data = {k: v for k, v in data.items() if v is not None}
                
                logging.debug(f"Ollama API request data: {data}")
                
                # Make the API request
                logging.debug(f"Sending audio file: {file} (size: {os.path.getsize(file)} bytes)")
                response = requests.post(api_url, files=files, data=data)
                logging.debug(f"Ollama API response status: {response.status_code}")
                
                if not response.ok:
                    logging.error(f"Ollama API error: {response.status_code} - {response.text}")
                    
                    # Try to check available endpoints
                    try:
                        endpoints_response = requests.get(f"{self.ollama_api_url}/api")
                        logging.debug(f"Available API endpoints: {endpoints_response.status_code} - {endpoints_response.text[:200]}")
                    except Exception as e:
                        logging.error(f"Failed to check API endpoints: {str(e)}")
                        
                    return [Segment(0, 0, f"Error: {response.status_code} - {response.text}", "")]
                
                # Parse the response
                try:
                    result = response.json()
                    
                    # Create segments from the result
                    # Note: This assumes Ollama API returns a compatible format
                    # You may need to adjust this based on actual Ollama API response
                    if 'segments' in result:
                        return [
                            Segment(
                                int(segment.get("start", 0) * 1000 + offset_ms),
                                int(segment.get("end", 0) * 1000 + offset_ms),
                                segment.get("text", ""),
                                ""  # Empty translation field
                            )
                            for segment in result['segments']
                        ]
                    elif 'text' in result:
                        # If segments aren't available, create a single segment with the text
                        return [Segment(offset_ms, offset_ms + int(duration_secs * 1000), result['text'], "")]
                    else:
                        logging.error(f"Unexpected Ollama API response format: {result}")
                        return [Segment(0, 0, "Error: Unexpected API response format", "")]
                        
                except json.JSONDecodeError:
                    logging.error(f"Failed to parse Ollama API response: {response.text}")
                    return [Segment(0, 0, f"Error: Invalid JSON response", "")]
                
        except Exception as e:
            logging.exception(f"Error transcribing with Ollama: {str(e)}")
            return [Segment(0, 0, f"Error: {str(e)}", "")]

    def stop(self):
        # Nothing to stop in the current implementation
        # Could be extended if implementing async processing
        pass
