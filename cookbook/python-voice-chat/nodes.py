import io

import scipy.io.wavfile
import soundfile
from sley import Context, node
from utils.audio_utils import play_audio_data, record_audio
from utils.call_llm import call_llm
from utils.speech_to_text import speech_to_text_api
from utils.text_to_speech import text_to_speech_api


@node
def capture_audio(context: Context) -> None:
    print("\nListening for your query...")
    audio, sample_rate = record_audio()
    if audio is None:
        print("CaptureAudioNode: Failed to capture audio.")
        # A plain return would follow the unlabelled speech-to-text link.
        context.end()
        return

    print(f"Audio captured ({len(audio) / sample_rate:.2f}s), proceeding to STT.")
    context.emit(input=(audio, sample_rate))


@node
def transcribe(context: Context) -> None:
    audio, sample_rate = context.input
    buffer = io.BytesIO()
    scipy.io.wavfile.write(buffer, sample_rate, audio)
    print("Converting speech to text...")
    text = speech_to_text_api(buffer.getvalue())
    print(f"User: {text}")
    context.emit(input=text)


@node
def answer(context: Context) -> None:
    history = context.state.setdefault("chat_history", [])
    history.append({"role": "user", "content": context.input})
    print("Sending query to LLM...")
    response = call_llm(history)
    print(f"LLM: {response}")
    history.append({"role": "assistant", "content": response})
    context.emit(input=response)


@node
def speak(context: Context) -> None:
    print("Converting LLM response to speech...")
    audio_bytes = text_to_speech_api(context.input)
    audio, sample_rate = soundfile.read(io.BytesIO(audio_bytes))
    print("Playing LLM response...")
    play_audio_data(audio, sample_rate)
    context.emit("next_turn")
