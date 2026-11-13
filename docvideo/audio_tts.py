"""Edge-TTS synthesis, phonetic multi-part splicing, and transcription verification."""

from __future__ import annotations

import asyncio
import os
import subprocess
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

import edge_tts
import numpy as np

from .music_synth import load_wav_float, save_wav_float

DEFAULT_VOICE = "ar-SA-HamedNeural"
DEFAULT_RATE = "+18%"
DEFAULT_PITCH = "-2Hz"
DEFAULT_SR = 44100


async def synthesize_mp3(
    text: str,
    out_mp3: Path,
    voice: str = DEFAULT_VOICE,
    rate: str = DEFAULT_RATE,
    pitch: str = DEFAULT_PITCH,
) -> None:
    """Synthesize text to an MP3 file using Edge-TTS."""
    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await comm.save(str(out_mp3))


def convert_to_wav(
    src_path: Path,
    dst_wav: Path,
    sr: int = DEFAULT_SR,
    af: Optional[str] = None,
) -> None:
    """Convert an audio file to mono PCM16 WAV via FFmpeg, applying optional audio filters."""
    dst_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-i", str(src_path)]
    if af:
        cmd += ["-af", af]
    cmd += ["-ar", str(sr), "-ac", "1", "-acodec", "pcm_s16le", str(dst_wav)]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if res.returncode != 0:
        err = res.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"FFmpeg conversion failed for {src_path}: {err}")


def trim_silence_int16(
    samples: np.ndarray,
    threshold: int = 200,
    pad_before: int = 800,
    pad_after: int = 800,
) -> np.ndarray:
    """Trim leading and trailing low-amplitude samples from an int16 waveform."""
    idx = np.where(np.abs(samples) > threshold)[0]
    if len(idx) == 0:
        return samples
    start = max(0, int(idx[0]) - pad_before)
    end = min(len(samples), int(idx[-1]) + pad_after)
    return samples[start:end]


def _read_wav_int16(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wf:
        sr = wf.getframerate()
        frames = wf.readframes(wf.getnframes())
    return np.frombuffer(frames, dtype=np.int16).copy(), sr


def _write_wav_int16(path: Path, data: np.ndarray, sr: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(np.clip(data, -32768, 32767).astype(np.int16).tobytes())


async def _synthesize_spliced_cue(
    cue: Dict[str, Any],
    audio_dir: Path,
    default_voice: str,
    default_rate: str,
    default_pitch: str,
    sr: int,
) -> Path:
    """Generate and splice multiple TTS segments (e.g., cross-lingual phonetic fixes)."""
    cue_id = cue["id"]
    parts: List[Dict[str, Any]] = cue["parts"]
    work_dir = audio_dir / "_parts"
    work_dir.mkdir(parents=True, exist_ok=True)

    chunks: List[np.ndarray] = []
    for idx, part in enumerate(parts):
        part_name = part.get("name", f"part{idx}")
        mp3_path = work_dir / f"{cue_id}_{part_name}.mp3"
        wav_path = work_dir / f"{cue_id}_{part_name}.wav"

        voice = part.get("voice", default_voice)
        rate = part.get("rate", default_rate)
        pitch = part.get("pitch", default_pitch)
        af = part.get("af")

        await synthesize_mp3(part["text"], mp3_path, voice=voice, rate=rate, pitch=pitch)
        convert_to_wav(mp3_path, wav_path, sr=sr, af=af)

        pcm, _ = _read_wav_int16(wav_path)
        trimmed = trim_silence_int16(
            pcm,
            threshold=int(part.get("threshold", 200)),
            pad_before=int(part.get("pad_before", 800)),
            pad_after=int(part.get("pad_after", 800)),
        )

        pause_before = float(part.get("pause_before", 0.0))
        pause_after = float(part.get("pause_after", 0.0))
        if pause_before > 0:
            chunks.append(np.zeros(int(pause_before * sr), dtype=np.int16))
        chunks.append(trimmed)
        if pause_after > 0:
            chunks.append(np.zeros(int(pause_after * sr), dtype=np.int16))

    merged = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.int16)
    out_wav = audio_dir / f"{cue_id}.wav"
    _write_wav_int16(out_wav, merged, sr=sr)

    # Also keep an MP3 copy for quick auditioning.
    out_mp3 = audio_dir / f"{cue_id}.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(out_wav), "-b:a", "192k", str(out_mp3)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return out_wav


async def generate_all_cues_async(
    audio_cues: List[Dict[str, Any]],
    audio_dir: Path,
    audio_cfg: Optional[Dict[str, Any]] = None,
    force: bool = False,
) -> List[Path]:
    """Generate WAV/MP3 files for every cue in `audio_cues`."""
    audio_cfg = audio_cfg or {}
    default_voice = audio_cfg.get("voice", DEFAULT_VOICE)
    default_rate = audio_cfg.get("rate", DEFAULT_RATE)
    default_pitch = audio_cfg.get("pitch", DEFAULT_PITCH)
    sr = int(audio_cfg.get("sample_rate", DEFAULT_SR))

    audio_dir.mkdir(parents=True, exist_ok=True)
    generated: List[Path] = []

    for cue in audio_cues:
        cue_id = cue["id"]
        wav_path = audio_dir / f"{cue_id}.wav"
        mp3_path = audio_dir / f"{cue_id}.mp3"

        if wav_path.exists() and not force:
            generated.append(wav_path)
            continue

        if "parts" in cue and cue["parts"]:
            print(f"[TTS] Synthesizing spliced cue: {cue_id} ({len(cue['parts'])} parts)")
            out = await _synthesize_spliced_cue(
                cue, audio_dir, default_voice, default_rate, default_pitch, sr
            )
            generated.append(out)
        else:
            tts_text = cue.get("tts_text") or cue["text"]
            voice = cue.get("voice", default_voice)
            rate = cue.get("rate", default_rate)
            pitch = cue.get("pitch", default_pitch)
            af = cue.get("af")
            print(f"[TTS] Synthesizing cue: {cue_id}")
            await synthesize_mp3(tts_text, mp3_path, voice=voice, rate=rate, pitch=pitch)
            convert_to_wav(mp3_path, wav_path, sr=sr, af=af)
            generated.append(wav_path)

    return generated


def generate_all_cues(
    audio_cues: List[Dict[str, Any]],
    audio_dir: Path,
    audio_cfg: Optional[Dict[str, Any]] = None,
    force: bool = False,
) -> List[Path]:
    """Synchronous wrapper for `generate_all_cues_async`."""
    return asyncio.run(
        generate_all_cues_async(audio_cues, audio_dir, audio_cfg=audio_cfg, force=force)
    )


def export_mp3(src_wav: Path, dst_mp3: Path, bitrate: str = "192k") -> None:
    """Encode a WAV file to MP3 with FFmpeg."""
    res = subprocess.run(
        ["ffmpeg", "-y", "-i", str(src_wav), "-b:a", bitrate, str(dst_mp3)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    if res.returncode != 0:
        err = res.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"Failed to export MP3 {dst_mp3}: {err}")


def transcribe_wav(wav_path: Path, language: str = "ar-SA") -> str:
    """Optional pronunciation sanity check using SpeechRecognition + Google Web Speech API."""
    import speech_recognition as sr_lib  # Lazy import so base rendering works without it

    tmp_16k = wav_path.with_name(f"{wav_path.stem}_16k_tmp.wav")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(wav_path), "-ar", "16000", "-ac", "1", str(tmp_16k)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        recognizer = sr_lib.Recognizer()
        with sr_lib.AudioFile(str(tmp_16k)) as source:
            audio = recognizer.record(source)
        return recognizer.recognize_google(audio, language=language)
    finally:
        if tmp_16k.exists():
            os.remove(tmp_16k)

