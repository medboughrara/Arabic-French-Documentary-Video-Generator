"""Config-driven 1080p documentary video renderer using Pillow, NumPy, and FFmpeg."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from .text_renderer import TextRenderer

DEFAULT_COLORS: Dict[str, List[int]] = {
    "navy": [10, 22, 42, 255],
    "card_bg": [12, 24, 46, 205],
    "gold": [212, 175, 55, 255],
    "gold_soft": [212, 175, 55, 130],
    "cream": [248, 246, 240, 255],
    "silver": [185, 200, 220, 255],
    "teal": [38, 132, 148, 255],
    "muted": [148, 163, 184, 255],
}


def resolve_color(
    val: Any, palette: Dict[str, Tuple[int, int, int, int]]
) -> Tuple[int, int, int, int]:
    if isinstance(val, str):
        if val in palette:
            return palette[val]
        raise KeyError(f"Unknown color name '{val}'")
    if isinstance(val, (list, tuple)):
        if len(val) == 3:
            return (int(val[0]), int(val[1]), int(val[2]), 255)
        if len(val) == 4:
            return (int(val[0]), int(val[1]), int(val[2]), int(val[3]))
    raise ValueError(f"Invalid color specification: {val!r}")


def build_palette(color_cfg: Optional[Dict[str, List[int]]]) -> Dict[str, Tuple[int, int, int, int]]:
    merged = dict(DEFAULT_COLORS)
    if color_cfg:
        merged.update(color_cfg)
    return {k: (int(v[0]), int(v[1]), int(v[2]), int(v[3]) if len(v) > 3 else 255) for k, v in merged.items()}


def cover_resize(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Resize and center-crop `img` to cover `target_w x target_h` cleanly."""
    src_w, src_h = img.size
    scale = max(target_w / src_w, target_h / src_h)
    new_w, new_h = int(round(src_w * scale)), int(round(src_h * scale))
    resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    x0 = (new_w - target_w) // 2
    y0 = (new_h - target_h) // 2
    return resized.crop((x0, y0, x0 + target_w, y0 + target_h))


def prepare_background(
    img_path: Path,
    width: int,
    height: int,
    brightness: float = 0.55,
    saturation: float = 0.85,
) -> Image.Image:
    """Load, cover-crop to 1080p, grade, and add subtle vignette contrast."""
    # Pre-scale slightly larger (1.14x) so Ken Burns zoom/pan stays sharp
    stage_w = int(round(width * 1.14))
    stage_h = int(round(height * 1.14))
    img = Image.open(img_path).convert("RGB")
    img = cover_resize(img, stage_w, stage_h)
    img = ImageEnhance.Color(img).enhance(saturation)
    img = ImageEnhance.Brightness(img).enhance(brightness)

    # Subtle bottom-up gradient vignette for crisp text readability
    grad = Image.new("RGBA", (stage_w, stage_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(grad)
    for y in range(stage_h):
        frac = y / stage_h
        alpha = int(35 + 115 * (frac ** 1.6))
        draw.line([(0, y), (stage_w, y)], fill=(6, 12, 24, alpha))
    graded = Image.alpha_composite(img.convert("RGBA"), grad).convert("RGB")
    return graded


def make_framed_sprite(
    img_path: Path,
    size: Tuple[int, int],
    crop_box: Optional[Tuple[int, int, int, int]] = None,
    border_color: Tuple[int, int, int, int] = (212, 175, 55, 220),
    radius: int = 24,
    sharpness: Optional[float] = None,
    contrast: Optional[float] = None,
    border_width: int = 3,
    pad: int = 22,
) -> Image.Image:
    """Create a rounded, shadowed, gold-framed RGBA sprite."""
    img = Image.open(img_path).convert("RGB")
    if crop_box is not None:
        img = img.crop(crop_box)
    if sharpness is not None:
        img = ImageEnhance.Sharpness(img).enhance(sharpness)
    if contrast is not None:
        img = ImageEnhance.Contrast(img).enhance(contrast)

    w, h = size
    inner = img.resize((w, h), Image.Resampling.LANCZOS).convert("RGBA")

    mask = Image.new("L", (w, h), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.rounded_rectangle((0, 0, w, h), radius=radius, fill=255)
    rounded_inner = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    rounded_inner.paste(inner, (0, 0), mask)

    canvas_w = w + 2 * pad
    canvas_h = h + 2 * pad
    shadow = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    sdraw.rounded_rectangle(
        (pad + 6, pad + 10, pad + w + 6, pad + h + 10),
        radius=radius,
        fill=(0, 0, 0, 145),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=10))
    shadow.paste(rounded_inner, (pad, pad), rounded_inner)

    bdraw = ImageDraw.Draw(shadow)
    bdraw.rounded_rectangle(
        (pad, pad, pad + w, pad + h),
        radius=radius,
        outline=border_color,
        width=border_width,
    )
    return shadow


def ken_burns_frame(
    bg_rgb: Image.Image,
    progress: float,
    z0: float,
    z1: float,
    px0: float,
    py0: float,
    px1: float,
    py1: float,
    out_w: int,
    out_h: int,
) -> Image.Image:
    """Crop and zoom from a graded background image for smooth Ken Burns motion."""
    progress = max(0.0, min(1.0, progress))
    z = z0 + (z1 - z0) * progress
    px = px0 + (px1 - px0) * progress
    py = py0 + (py1 - py0) * progress

    src_w, src_h = bg_rgb.size
    crop_w = min(src_w, int(round(src_w / z)))
    crop_h = min(src_h, int(round(src_h / z)))
    max_x = max(0, src_w - crop_w)
    max_y = max(0, src_h - crop_h)
    x0 = int(round(max_x * px))
    y0 = int(round(max_y * py))

    cropped = bg_rgb.crop((x0, y0, x0 + crop_w, y0 + crop_h))
    return cropped.resize((out_w, out_h), Image.Resampling.BILINEAR)


def _element_active(elem: Dict[str, Any], t_rel: float) -> bool:
    start = float(elem.get("start_offset", 0.0))
    end = elem.get("end_offset")
    if t_rel < start:
        return False
    if end is not None and t_rel >= float(end):
        return False
    return True


def _compute_active_subtitle(
    t: float,
    subtitles: List[Tuple[float, float, str]],
) -> str:
    for s0, s1, text in subtitles:
        if s0 <= t <= s1:
            return text
    return ""


class DocumentaryVideoRenderer:
    """Declarative project-driven documentary renderer."""

    def __init__(self, project: Dict[str, Any], base_dir: Path) -> None:
        self.project = project
        self.base_dir = base_dir
        video_cfg = project.get("video", {})
        self.width = int(video_cfg.get("width", 1920))
        self.height = int(video_cfg.get("height", 1080))
        self.fps = int(video_cfg.get("fps", 24))
        self.total_duration = float(video_cfg.get("duration", 119.0))
        self.crossfade_sec = float(video_cfg.get("crossfade_sec", 0.6))
        self.show_progress_bar = bool(video_cfg.get("show_progress_bar", True))

        self.palette = build_palette(project.get("colors"))
        self.text = TextRenderer(project.get("fonts"))

        self.scenes: List[Dict[str, Any]] = project["scenes"]
        self.backgrounds: Dict[str, Image.Image] = {}
        self.sprites: Dict[str, Image.Image] = {}
        self._overlay_cache: Dict[Tuple[Any, ...], Image.Image] = {}

        self._load_assets()

    def _resolve_path(self, rel_or_abs: str) -> Path:
        p = Path(rel_or_abs)
        if p.is_absolute():
            return p
        return self.base_dir / p

    def _load_assets(self) -> None:
        assets_cfg = self.project.get("assets", {})
        for bg_id, spec in assets_cfg.get("backgrounds", {}).items():
            path = self._resolve_path(spec["path"])
            self.backgrounds[bg_id] = prepare_background(
                path,
                self.width,
                self.height,
                brightness=float(spec.get("brightness", 0.55)),
                saturation=float(spec.get("saturation", 0.85)),
            )

        for sp_id, spec in assets_cfg.get("sprites", {}).items():
            path = self._resolve_path(spec["path"])
            crop_raw = spec.get("crop")
            crop_box = tuple(int(v) for v in crop_raw) if crop_raw else None
            border_c = resolve_color(spec.get("border_color", "gold"), self.palette)
            self.sprites[sp_id] = make_framed_sprite(
                path,
                size=(int(spec["size"][0]), int(spec["size"][1])),
                crop_box=crop_box,
                border_color=border_c,
                radius=int(spec.get("radius", 24)),
                sharpness=spec.get("sharpness"),
                contrast=spec.get("contrast"),
                border_width=int(spec.get("border_width", 3)),
                pad=int(spec.get("pad", 22)),
            )

    def _build_overlay(self, scene_idx: int, active_mask: Tuple[bool, ...]) -> Image.Image:
        cache_key = (scene_idx, active_mask)
        if cache_key in self._overlay_cache:
            return self._overlay_cache[cache_key]

        scene = self.scenes[scene_idx]
        ov = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(ov)

        self.text.draw_top_header(
            draw,
            scene["label_ar"],
            scene["label_fr"],
            self.width,
            self.palette,
        )

        elements = scene.get("elements", [])
        for elem, is_on in zip(elements, active_mask):
            if not is_on:
                continue
            kind = elem["type"]

            if kind == "sprite":
                sp_img = self.sprites[elem["sprite"]]
                cx, cy = int(elem["center"][0]), int(elem["center"][1])
                px = cx - sp_img.width // 2
                py = cy - sp_img.height // 2
                ov.paste(sp_img, (px, py), sp_img)

            elif kind == "rect":
                r = elem["rect"]
                fill = resolve_color(elem["fill"], self.palette) if "fill" in elem else None
                outline = (
                    resolve_color(elem["outline"], self.palette)
                    if "outline" in elem
                    else None
                )
                self.text.rounded_rect(
                    draw,
                    (int(r[0]), int(r[1]), int(r[2]), int(r[3])),
                    radius=int(elem.get("radius", 18)),
                    fill=fill,
                    outline=outline,
                    width=int(elem.get("width", 1)),
                )

            elif kind == "line":
                p = elem["points"]
                color = resolve_color(elem.get("color", "gold"), self.palette)
                draw.line(
                    [(int(p[0]), int(p[1])), (int(p[2]), int(p[3]))],
                    fill=color,
                    width=int(elem.get("width", 2)),
                )

            elif kind == "text_ar":
                xy = (int(elem["xy"][0]), int(elem["xy"][1]))
                color = resolve_color(elem.get("color", "cream"), self.palette)
                self.text.draw_text_ar(
                    draw,
                    xy,
                    elem["text"],
                    int(elem["size"]),
                    color,
                    font_role=elem.get("font_role", "ar_bold"),
                    anchor=elem.get("anchor", "mm"),
                    max_w=elem.get("max_w"),
                )

            elif kind == "text_ltr":
                xy = (int(elem["xy"][0]), int(elem["xy"][1]))
                color = resolve_color(elem.get("color", "silver"), self.palette)
                self.text.draw_text_ltr(
                    draw,
                    xy,
                    elem["text"],
                    int(elem["size"]),
                    color,
                    font_role=elem.get("font_role", "fr_bold"),
                    anchor=elem.get("anchor", "mm"),
                )

        self._overlay_cache[cache_key] = ov
        return ov

    def _render_scene_frame(
        self,
        scene_idx: int,
        t_global: float,
        sub_text: str,
        include_subtitle: bool = True,
    ) -> Image.Image:
        scene = self.scenes[scene_idx]
        s0 = float(scene["start"])
        s1 = float(scene["end"])
        t_rel = max(0.0, t_global - s0)
        dur = max(0.001, s1 - s0)
        prog = min(1.0, t_rel / dur)

        kb = scene.get("ken_burns", {})
        bg_img = self.backgrounds[scene["background"]]
        base = ken_burns_frame(
            bg_img,
            prog,
            z0=float(kb.get("z0", 1.02)),
            z1=float(kb.get("z1", 1.12)),
            px0=float(kb.get("px0", 0.5)),
            py0=float(kb.get("py0", 0.5)),
            px1=float(kb.get("px1", 0.5)),
            py1=float(kb.get("py1", 0.5)),
            out_w=self.width,
            out_h=self.height,
        ).convert("RGBA")

        elements = scene.get("elements", [])
        active_mask = tuple(_element_active(el, t_rel) for el in elements)
        ov = self._build_overlay(scene_idx, active_mask)
        frame = Image.alpha_composite(base, ov)

        if include_subtitle and sub_text:
            sub_ov = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
            sdraw = ImageDraw.Draw(sub_ov)
            self.text.draw_subtitle_bar(
                sdraw, sub_text, self.width, self.height, self.palette
            )
            frame = Image.alpha_composite(frame, sub_ov)

        if self.show_progress_bar:
            pdraw = ImageDraw.Draw(frame)
            pw = int(round(self.width * min(1.0, max(0.0, t_global / self.total_duration))))
            pdraw.rectangle([0, self.height - 6, pw, self.height], fill=self.palette["gold"])

        return frame.convert("RGB")

    def _find_scene_index(self, t: float) -> int:
        for idx, sc in enumerate(self.scenes):
            if float(sc["start"]) <= t < float(sc["end"]):
                return idx
        return len(self.scenes) - 1

    def render_frame_at(
        self, t: float, subtitles: List[Tuple[float, float, str]]
    ) -> Image.Image:
        """Render a single composited RGB frame at timestamp `t`, including crossfades."""
        sub_text = _compute_active_subtitle(t, subtitles)
        idx = self._find_scene_index(t)
        scene = self.scenes[idx]
        s1 = float(scene["end"])

        frame = self._render_scene_frame(idx, t, sub_text, include_subtitle=True)
        if (
            self.crossfade_sec > 0
            and idx + 1 < len(self.scenes)
            and (s1 - t) < self.crossfade_sec
        ):
            alpha = 1.0 - max(0.0, (s1 - t) / self.crossfade_sec)
            next_frame = self._render_scene_frame(
                idx + 1, t, sub_text, include_subtitle=True
            )
            frame = Image.blend(frame, next_frame, alpha)

        # Gentle fade-in (0.8s) and fade-out (1.2s)
        if t < 0.8:
            black = Image.new("RGB", (self.width, self.height), (0, 0, 0))
            frame = Image.blend(black, frame, t / 0.8)
        elif t > (self.total_duration - 1.2):
            black = Image.new("RGB", (self.width, self.height), (0, 0, 0))
            rem = max(0.0, (self.total_duration - t) / 1.2)
            frame = Image.blend(black, frame, rem)

        return frame

    def export_previews(
        self,
        preview_dir: Path,
        subtitles: List[Tuple[float, float, str]],
        timestamps: Optional[List[float]] = None,
    ) -> List[Path]:
        """Save representative PNG frames per scene for visual QA without a full render."""
        preview_dir.mkdir(parents=True, exist_ok=True)
        if timestamps is None:
            timestamps = [
                round((float(sc["start"]) + float(sc["end"])) * 0.5, 2)
                for sc in self.scenes
            ]
        saved: List[Path] = []
        for idx, t in enumerate(timestamps, start=1):
            img = self.render_frame_at(t, subtitles)
            out_path = preview_dir / f"preview_{idx:02d}_t{int(round(t)):03d}s.png"
            img.save(out_path)
            saved.append(out_path)
        return saved

    def render_video(
        self,
        master_audio_wav: Path,
        output_mp4: Path,
        subtitles: List[Tuple[float, float, str]],
        log_path: Optional[Path] = None,
    ) -> Path:
        """Stream all frames via raw RGB pipe to FFmpeg and mux with `master_audio_wav`."""
        output_mp4.parent.mkdir(parents=True, exist_ok=True)
        total_frames = int(round(self.total_duration * self.fps))
        if log_path is None:
            log_path = output_mp4.with_suffix(".ffmpeg.log")

        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "rawvideo",
            "-vcodec",
            "rawvideo",
            "-s",
            f"{self.width}x{self.height}",
            "-pix_fmt",
            "rgb24",
            "-r",
            str(self.fps),
            "-i",
            "-",
            "-i",
            str(master_audio_wav),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-strict",
            "-2",
            "-b:a",
            "192k",
            "-shortest",
            str(output_mp4),
        ]

        t0 = time.time()
        # Redirect stderr to a file on Windows to prevent pipe buffer deadlock.
        with open(log_path, "wb") as lf:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=lf,
            )
            assert proc.stdin is not None
            try:
                for frame_idx in range(total_frames):
                    t = frame_idx / self.fps
                    img = self.render_frame_at(t, subtitles)
                    proc.stdin.write(np.asarray(img, dtype=np.uint8).tobytes())
                    if (frame_idx + 1) % (self.fps * 15) == 0 or frame_idx + 1 == total_frames:
                        elapsed = time.time() - t0
                        pct = 100.0 * (frame_idx + 1) / total_frames
                        print(
                            f"[RENDER] Frame {frame_idx + 1}/{total_frames} "
                            f"({pct:.1f}%) - {elapsed:.1f}s elapsed"
                        )
            finally:
                proc.stdin.close()
                ret = proc.wait()

        if ret != 0:
            raise RuntimeError(
                f"FFmpeg video encoding failed (exit {ret}). Check log: {log_path}"
            )
        return output_mp4

