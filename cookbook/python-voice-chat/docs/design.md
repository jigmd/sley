# Voice Chat Design

One conversation turn is a linear pipeline. The final named link starts the next
turn, so the graph remains readable even though the application is continuous.

```text
capture_audio --> transcribe --> answer --> speak --next_turn--> capture_audio
```

## Control

- Unlabelled links connect the normal stages of one turn.
- The named `next_turn` link is the only cycle.
- `capture_audio` calls `end()` when silence should stop instead of following its
  unlabelled transcription link.

## Data

The data has two different lifetimes:

- `context.input` carries the recording, transcript, and synthesized response
  through one turn.
- `context.state["chat_history"]` survives across turns and gives the LLM the
  conversation so far.

Audio is converted only at the boundary that needs a different representation:
the microphone produces a NumPy array, transcription receives WAV bytes, text to
speech returns MP3 bytes, and playback decodes those bytes back to samples.

## External Pieces

Each file in `utils/` can be run directly. Those small demos make microphone
capture, speech recognition, LLM calls, and speech synthesis independently
observable before they are composed into the Flow.
