---
machine-display: false
---

# Text to Speech

A speech utility turns text into audio bytes, a stream, or a durable media
reference. Keep that choice out of graph control:

```python
from typing import Protocol


class SpeechSynthesizer(Protocol):
    async def synthesize(self, text: str) -> bytes: ...
```

```typescript
interface SpeechSynthesizer {
  synthesize(text: string): Promise<Uint8Array>
}
```

For large or streamed audio, return an application stream or storage reference
instead of buffering all bytes. Tests can inject a fake that returns a small
known payload.

## Graph Integration

```python
async def speak(context):
    audio = await synthesizer.synthesize(context.state["answer"])
    await audio_output.play(audio)
```

This leaf emits nothing and exits its Flow normally. Use a self-link only when
the application intentionally starts another conversation turn.

## Operational Rules

- Set a provider-side timeout.
- Validate supported voice, format, and sample-rate configuration before the
  run when possible.
- Avoid storing large audio blobs in state unless later nodes need them.
- Keep temporary-file ownership and deletion in the audio utility.
- Do not assume cancellation can stop a synchronous playback or provider call.
- Treat spoken model output as user-visible content subject to the same safety
  policy as displayed text.

See the voice-chat cookbook project for speech recognition, model response, and
playback in one loop.
