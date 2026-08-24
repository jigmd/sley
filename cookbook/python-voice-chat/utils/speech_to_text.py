import io
import os
from pathlib import Path

from openai import OpenAI


def speech_to_text_api(audio_data: bytes):
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    audio_file = io.BytesIO(audio_data)
    audio_file.name = "audio.wav"
    transcript = client.audio.transcriptions.create(
        model="gpt-4o-transcribe", file=audio_file
    )
    return transcript.text


if __name__ == "__main__":
    audio_path = Path("tts_output.mp3")
    if not audio_path.is_file():
        raise FileNotFoundError(
            "tts_output.mp3 is missing; run text_to_speech.py first"
        )
    print(f"Transcribing {audio_path}...")
    print(f"Transcript: {speech_to_text_api(audio_path.read_bytes())}")
