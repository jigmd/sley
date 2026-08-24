import os

from openai import OpenAI


def text_to_speech_api(text: str) -> bytes:
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    response = client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice="alloy",  # Other voices include echo, fable, onyx, nova, and shimmer.
        input=text,
        response_format="mp3",  # Opus, AAC, and FLAC are also available.
    )
    return response.content


if __name__ == "__main__":
    text = "Hello from Sley! This is a direct text-to-speech test."
    output = "tts_output.mp3"
    print(f"Synthesizing: {text}")
    audio = text_to_speech_api(text)
    with open(output, "wb") as audio_file:
        audio_file.write(audio)
    print(f"Saved {len(audio):,} bytes to {output}")
    print("Run speech_to_text.py next to transcribe the generated file.")
