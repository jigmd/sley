---
complexity: 7
---

# Voice Chat

A continuous voice conversation with microphone capture, speech recognition,
an LLM response, and speech playback.

Audio, transcription, and response are values for one turn, so each handler
passes them through `context.input`. Only conversation history belongs in
shared run state.

The capture node demonstrates the difference between normal termination and a
hard End. Its unlabelled link normally continues to transcription. When no
speech is detected, `context.end()` bypasses that link and finishes the branch.

## Run

```bash
export OPENAI_API_KEY="your-api-key"
pip install -r requirements.txt
python main.py
```

PortAudio must be installed for microphone access.

## Explore the Audio Pieces

The utilities are intentionally runnable on their own. This lets you learn each
external service before following the complete conversation loop:

```bash
python utils/audio_utils.py       # record one phrase and play it back
python utils/text_to_speech.py    # create tts_output.mp3
python utils/speech_to_text.py    # transcribe that generated file
python utils/call_llm.py          # send one text-only prompt
```

Once those pieces make sense, `nodes.py` shows how `context.input` carries the
audio and text for one turn while `context.state` retains conversation history.
