"""Procedural documentary score synthesizer and voice/music ducking mixer."""

import os
import wave
import numpy as np


def load_wav_float(path):
    """Load a PCM 16-bit WAV file as float32 stereo array normalized to [-1, 1]."""
    with wave.open(path, "rb") as wf:
        sr = wf.getframerate()
        n_ch = wf.getnchannels()
        raw = wf.readframes(wf.getnframes())
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if n_ch == 2:
            data = data.reshape(-1, 2)
        else:
            data = np.column_stack([data, data])
        return data, sr


def save_wav_float(path, data, sr=44100):
    """Save a float32 stereo array normalized to [-1, 1] as 16-bit PCM WAV."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    clipped = np.clip(data, -0.99, 0.99)
    pcm = (clipped * 32767.0).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def synth_documentary_music(total_sec, sr=44100):
    """
    Synthesize a warm, inspiring institutional documentary score
    (Dm9 - Bbmaj7 - Fmaj7 - Cadd9) with soft piano arpeggios and warm strings pad.
    """
    n_samples = int(total_sec * sr)
    t = np.arange(n_samples, dtype=np.float32) / sr
    left = np.zeros(n_samples, dtype=np.float32)
    right = np.zeros(n_samples, dtype=np.float32)

    chords = [
        [146.83, 220.00, 293.66, 349.23, 440.00, 659.25],  # Dm9
        [116.54, 174.61, 233.08, 293.66, 349.23, 523.25],  # Bbmaj7
        [87.31,  174.61, 261.63, 349.23, 440.00, 523.25],  # Fmaj7
        [130.81, 196.00, 261.63, 329.63, 392.00, 587.33],  # Cadd9
    ]

    bar_dur = 4.0
    n_bars = int(np.ceil(total_sec / bar_dur))

    for b in range(n_bars):
        freqs = chords[b % len(chords)]
        start_s = int(b * bar_dur * sr)
        end_s = min(n_samples, int((b + 1.5) * bar_dur * sr))
        if start_s >= n_samples:
            break
        seg_t = np.arange(end_s - start_s, dtype=np.float32) / sr

        env = np.ones_like(seg_t)
        att = seg_t < 1.2
        env[att] = 0.5 * (1.0 - np.cos(np.pi * seg_t[att] / 1.2))
        rel = seg_t > (bar_dur - 0.5)
        rel_t = np.clip((seg_t[rel] - (bar_dur - 0.5)) / 2.0, 0.0, 1.0)
        env[rel] *= 0.5 * (1.0 + np.cos(np.pi * rel_t))

        pad_l = np.zeros_like(seg_t)
        pad_r = np.zeros_like(seg_t)
        for i, f in enumerate(freqs[:5]):
            amp = 0.25 if i == 0 else (0.14 / (i ** 0.4))
            vib = 1.0 + 0.0012 * np.sin(2 * np.pi * (0.4 + 0.1 * i) * seg_t)
            pad_l += amp * np.sin(2 * np.pi * f * 0.999 * seg_t * vib)
            pad_r += amp * np.sin(2 * np.pi * f * 1.001 * seg_t * vib)
            pad_l += (amp * 0.2) * np.sin(2 * np.pi * (f * 2.0) * seg_t)
            pad_r += (amp * 0.2) * np.sin(2 * np.pi * (f * 2.0) * seg_t)

        left[start_s:end_s] += pad_l * env
        right[start_s:end_s] += pad_r * env

        arp_pattern = [1, 2, 3, 4, 5, 4, 3, 2]
        for step_i, note_idx in enumerate(arp_pattern):
            note_start = int((b * bar_dur + step_i * 0.5) * sr)
            note_end = min(n_samples, note_start + int(1.6 * sr))
            if note_start >= n_samples:
                break
            nt = np.arange(note_end - note_start, dtype=np.float32) / sr
            nf = freqs[note_idx]
            n_env = np.exp(-2.8 * nt) * np.minimum(1.0, nt / 0.015)
            tone = (
                0.11 * np.sin(2 * np.pi * nf * nt)
                + 0.035 * np.sin(2 * np.pi * (nf * 2) * nt) * np.exp(-4.0 * nt)
                + 0.012 * np.sin(2 * np.pi * (nf * 3) * nt) * np.exp(-6.0 * nt)
            ) * n_env
            pan = 0.35 + 0.3 * ((step_i % 3) / 2.0)
            left[note_start:note_end] += tone * (1.0 - pan * 0.4)
            right[note_start:note_end] += tone * (0.6 + pan * 0.4)

    fade_in = np.minimum(1.0, t / 2.0)
    fade_out = np.minimum(1.0, (total_sec - t) / 3.5)
    fade = np.clip(fade_in * fade_out, 0.0, 1.0)
    left *= fade
    right *= fade

    peak = max(np.max(np.abs(left)), np.max(np.abs(right)), 1e-6)
    left = left / peak * 0.8
    right = right / peak * 0.8
    return np.column_stack([left, right])


def build_master_audio(audio_cues, audio_dir, total_duration, out_wav_path, sr=44100, rebuild=False):
    """Mix voiceover WAV cues with procedural background music using smooth audio ducking."""
    cue_timings = []
    n_total = int(total_duration * sr)
    voice_track = np.zeros((n_total, 2), dtype=np.float32)
    duck_env = np.ones(n_total, dtype=np.float32) * 0.42

    for cue in audio_cues:
        cue_id = cue["id"]
        start_t = float(cue["start"])
        sub_text = cue.get("subtitle", cue.get("text", ""))
        wav_path = os.path.join(audio_dir, f"{cue_id}.wav")
        data, file_sr = load_wav_float(wav_path)
        dur = len(data) / float(file_sr)
        s_idx = int(start_t * sr)
        e_idx = min(n_total, s_idx + len(data))
        voice_track[s_idx:e_idx] += data[: e_idx - s_idx] * 1.12
        pad_s = max(0, s_idx - int(0.35 * sr))
        pad_e = min(n_total, e_idx + int(0.45 * sr))
        duck_env[pad_s:pad_e] = 0.15
        cue_timings.append((cue_id, start_t, start_t + dur, sub_text))

    if rebuild or not os.path.exists(out_wav_path):
        print("Synthesizing master audio track with documentary score and ducking...")
        win = int(0.4 * sr)
        kernel = np.ones(win, dtype=np.float32) / win
        duck_smooth = np.convolve(duck_env, kernel, mode="same")
        music = synth_documentary_music(total_duration, sr)
        master = voice_track + music * duck_smooth[:, None]
        save_wav_float(out_wav_path, master, sr)
        print(f"Master audio saved to {out_wav_path}")

    return cue_timings

