from subprocess import run
import numpy as np
import logging
import os

SAMPLE_RATE = 16000

N_FFT = 400
HOP_LENGTH = 160
CHUNK_LENGTH = 30
N_SAMPLES = CHUNK_LENGTH * SAMPLE_RATE  # 480000 samples in a 30-second chunk


def load_audio(file: str, sr: int = SAMPLE_RATE, save_mp3: bool = True):
    """
    Open an audio file and read as mono waveform, resampling as necessary

    Parameters
    ----------
    file: str
        The audio file to open

    sr: int
        The sample rate to resample the audio if necessary

    Returns
    -------
    A NumPy array containing the audio waveform, in float32 dtype.
    """

    # Check if the file is already an MP3 file
    is_mp3 = file.lower().endswith('.mp3')
    print(f"load_audio: {file}, is_mp3: {is_mp3}")
    # If it's not an MP3 and save_mp3 is True, convert it to MP3
    if not is_mp3 and save_mp3:
        mp3_file = os.path.splitext(file)[0] + '.mp3'
        # Only convert if the MP3 file doesn't already exist
        if not os.path.exists(mp3_file):
            print(f"Converting {file} to MP3 format: {mp3_file}")
            # fmt: off
            convert_cmd = [
                "ffmpeg",
                "-nostdin",
                "-threads", "0",
                "-i", file,
                "-ac", "1",
                "-ar", str(sr),
                "-loglevel", "panic",
                mp3_file
            ]
            # fmt: on
            convert_result = run(convert_cmd, capture_output=True)
            
            if convert_result.returncode != 0:
                print(f"FFMPEG conversion warning. Process return code was not zero: {convert_result.returncode}")
                
            if len(convert_result.stderr):
                print(f"FFMPEG conversion error: {convert_result.stderr.decode()}")
                # If conversion failed, proceed with original file
            else:
                # Use the MP3 file for further processing if conversion was successful
                file = mp3_file
                print(f"Using converted MP3 file for processing: {mp3_file}")
        else:
            # Use the existing MP3 file
            file = mp3_file
            print(f"Using existing MP3 file for processing: {mp3_file}")
    
    # This launches a subprocess to decode audio while down-mixing
    # and resampling as necessary. Requires the ffmpeg CLI in PATH.
    # fmt: off
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-threads", "0",
        "-i", file,
        "-f", "s16le",
        "-ac", "1",
        "-acodec", "pcm_s16le",
        "-ar", str(sr),
        "-loglevel", "panic",
        "-"
    ]
    # fmt: on
    result = run(cmd, capture_output=True)

    if result.returncode != 0:
        logging.warning(f"FFMPEG audio load warning. Process return code was not zero: {result.returncode}")

    if len(result.stderr):
        logging.warning(f"FFMPEG audio load error. Error: {result.stderr.decode()}")
        raise RuntimeError(f"FFMPEG Failed to load audio: {result.stderr.decode()}")

    return np.frombuffer(result.stdout, np.int16).flatten().astype(np.float32) / 32768.0
