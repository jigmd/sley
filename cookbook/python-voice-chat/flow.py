from caskada import Flow
from nodes import answer, capture_audio, speak, transcribe

capture_audio.link(transcribe)
transcribe.link(answer)
answer.link(speak)
speak.link(capture_audio, "next_turn")

voice_chat = Flow(capture_audio)
