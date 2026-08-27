from nodes import answer, capture_audio, speak, transcribe
from sley import Flow

capture_audio.link(transcribe)
transcribe.link(answer)
answer.link(speak)
speak.link(capture_audio, "next_turn")

voice_chat = Flow(capture_audio, max_activations=400)
