#!/usr/bin/env python3
"""Config-driven Arabic/French documentary video generator CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from docvideo.audio_tts import export_mp3, generate_all_cues
from docvideo.music_synth import build_master_audio
from docvideo.video_renderer import DocumentaryVideoRenderer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a 1080p bilingual documentary video from a project JSON config."
    )
    parser.add_argument(
        "--project",
        type=Path,
        default=Path("examples/hichem_jouaber/project.json"),
        help="Path to the project JSON file (default: examples/hichem_jouaber/project.json).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Override output MP4 path specified in project.json.",
    )
    parser.add_argument(
        "--rebuild-audio",
        action="store_true",
        help="Re-synthesize TTS cues and re-mix master audio track even if files already exist.",
    )
    parser.add_argument(
        "--audio-only",
        action="store_true",
        help="Synthesize TTS cues and master audio mix, then exit without rendering video.",
    )
    parser.add_argument(
        "--previews-only",
        action="store_true",
        help="Render sample PNG preview frames for each scene instead of encoding full MP4.",
    )
    return parser.parse_args()


def load_project(project_path: Path) -> Tuple[Dict[str, Any], Path]:
    resolved = project_path.resolve()
    with open(resolved, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    # Paths inside project.json can be relative to repo root (`root_dir`) or config dir
    root_cfg = data.get("base_dir")
    if root_cfg:
        base_dir = (resolved.parent / root_cfg).resolve()
    else:
        base_dir = Path.cwd().resolve()
    return data, base_dir


def main() -> None:
    args = parse_args()
    project, base_dir = load_project(args.project)

    video_cfg = project.get("video", {})
    audio_cfg = project.get("audio", {})
    paths_cfg = project.get("paths", {})

    total_duration = float(video_cfg.get("duration", 119.0))
    sr = int(audio_cfg.get("sample_rate", 44100))

    audio_dir = (base_dir / paths_cfg.get("audio_dir", "assets/audio")).resolve()
    preview_dir = (base_dir / paths_cfg.get("preview_dir", "assets/previews")).resolve()
    master_wav = audio_dir / paths_cfg.get("master_wav_name", "master_audio.wav")
    master_mp3 = audio_dir / paths_cfg.get("master_mp3_name", "master_audio_corrected.mp3")
    output_mp4 = (
        args.output.resolve()
        if args.output
        else (base_dir / paths_cfg.get("output_mp4", "output_video.mp4")).resolve()
    )

    audio_cues: List[Dict[str, Any]] = project["audio_cues"]

    # Step 1: Generate TTS segments (including spliced multi-part phonetic fixes)
    generate_all_cues(
        audio_cues=audio_cues,
        audio_dir=audio_dir,
        audio_cfg=audio_cfg,
        force=args.rebuild_audio,
    )

    # Step 2: Mix voice cues with procedural score & smooth ducking
    cue_timings = build_master_audio(
        audio_cues=audio_cues,
        audio_dir=str(audio_dir),
        total_duration=total_duration,
        out_wav_path=str(master_wav),
        sr=sr,
        rebuild=args.rebuild_audio,
    )
    if args.rebuild_audio or not master_mp3.exists():
        export_mp3(master_wav, master_mp3)

    # Subtitles: (start_t, end_t + 0.35s tail hold, display text)
    subtitles: List[Tuple[float, float, str]] = [
        (s0, s1 + 0.35, text) for _, s0, s1, text in cue_timings
    ]

    if args.audio_only:
        print(f"[DONE] Audio pipeline complete. Master WAV: {master_wav}")
        return

    # Step 3: Initialize video renderer
    renderer = DocumentaryVideoRenderer(project=project, base_dir=base_dir)

    if args.previews_only:
        saved = renderer.export_previews(preview_dir=preview_dir, subtitles=subtitles)
        print(f"[DONE] Saved {len(saved)} scene preview(s) to {preview_dir}")
        for p in saved:
            print(f"  - {p}")
        return

    # Step 4: Render full 1080p MP4 via FFmpeg rawvideo pipe
    out_file = renderer.render_video(
        master_audio_wav=master_wav,
        output_mp4=output_mp4,
        subtitles=subtitles,
    )
    print(f"[DONE] Rendered video: {out_file} ({out_file.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()

