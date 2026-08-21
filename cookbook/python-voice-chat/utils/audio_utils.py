import numpy as np
import sounddevice as sd

DEFAULT_SAMPLE_RATE = 44_100


def record_audio(
    sample_rate=DEFAULT_SAMPLE_RATE,
    chunk_ms=50,
    silence_threshold=0.01,
    silence_ms=1_000,
    max_seconds=15,
):
    """Record from first speech until one second of silence."""
    chunk_size = int(sample_rate * chunk_ms / 1_000)
    silence_chunks = int(silence_ms / chunk_ms)
    max_chunks = int(max_seconds * 1_000 / chunk_ms)
    pre_roll = []
    recorded = []
    speaking = False
    quiet_chunks = 0

    print(f"Listening... (max {max_seconds}s). Speak when ready.")
    with sd.InputStream(samplerate=sample_rate, channels=1, dtype="float32") as stream:
        for _ in range(max_chunks):
            chunk, overflowed = stream.read(chunk_size)
            if overflowed:
                print("Warning: Audio buffer overflowed!")
            volume = np.sqrt(np.mean(chunk**2))

            if not speaking:
                pre_roll.append(chunk)
                pre_roll = pre_roll[-3:]
                if volume > silence_threshold:
                    speaking = True
                    recorded.extend(pre_roll)
                continue

            recorded.append(chunk)
            quiet_chunks = quiet_chunks + 1 if volume < silence_threshold else 0
            if quiet_chunks >= silence_chunks:
                break

    if not recorded:
        print("No speech detected within the maximum recording duration.")
        return None, sample_rate
    return np.concatenate(recorded), sample_rate


def play_audio_data(audio_data, sample_rate):
    print(
        f"Playing {len(audio_data) / sample_rate:.2f}s of audio "
        f"at {sample_rate:,} Hz..."
    )
    sd.play(audio_data, sample_rate)
    sd.wait()
    print("Playback finished.")


if __name__ == "__main__":
    print("Microphone and playback demo")
    print("Speak once; recording stops after one second of silence.\n")
    audio, rate = record_audio(max_seconds=10)
    if audio is None:
        raise RuntimeError("No speech was detected")
    print(f"Captured {len(audio) / rate:.2f}s at {rate:,} Hz.")
    play_audio_data(audio, rate)
