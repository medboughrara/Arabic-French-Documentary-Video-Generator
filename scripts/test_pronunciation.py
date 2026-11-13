#!/usr/bin/env python3
"""Test Edge-TTS phonetic spelling & cross-lingual splicing with ASR verification."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from docvideo.audio_tts import (
    DEFAULT_PITCH,
    DEFAULT_RATE,
    DEFAULT_VOICE,
    convert_to_wav,
    synthesize_mp3,
    transcribe_wav,
)


async def run_test(text: str, voice: str, rate: str, pitch: str, out_dir: Path, asr_lang: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    mp3_path = out_dir / "pronunciation_test.mp3"
    wav_path = out_dir / "pronunciation_test.wav"

    await synthesize_mp3(text, mp3_path, voice=voice, rate=rate, pitch=pitch)
    convert_to_wav(mp3_path, wav_path, sr=44100)
    print(f"Generated: {mp3_path} and {wav_path}")

    if asr_lang:
        try:
            transcript = transcribe_wav(wav_path, language=asr_lang)
            print(f"ASR ({asr_lang}) transcript: {transcript}")
        except Exception as exc:
            print(f"ASR check skipped/failed: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audition an Edge-TTS phrase and optionally run ASR check.")
    parser.add_argument("text", help="Text to synthesize (supports Arabic diacritics).")
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    parser.add_argument("--rate", default=DEFAULT_RATE)
    parser.add_argument("--pitch", default=DEFAULT_PITCH)
    parser.add_argument("--out-dir", type=Path, default=Path("assets/audio/test_tmp"))
    parser.add_argument("--asr-lang", default="ar-SA", help="Language code for Google ASR check (empty to skip).")
    args = parser.parse_args()

    asyncio.run(run_test(args.text, args.voice, args.rate, args.pitch, args.out_dir, args.asr_lang))


if __name__ == "__main__":
    main()

