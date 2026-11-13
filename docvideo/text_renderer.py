"""Arabic RTL / French LTR font management, shaping, and PIL text helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import arabic_reshaper
from bidi.algorithm import get_display
from PIL import ImageDraw, ImageFont

ColorLike = Union[Tuple[int, int, int], Tuple[int, int, int, int]]

# Default Windows fonts that contain full Arabic Presentation Forms + clean Latin glyphs.
DEFAULT_FONTS: Dict[str, List[str]] = {
    "ar_bold": [
        "C:/Windows/Fonts/calibrib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ],
    "ar_reg": [
        "C:/Windows/Fonts/calibri.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ],
    "fr_bold": [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
    ],
    "fr_reg": [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
    ],
    "fr_ital": [
        "C:/Windows/Fonts/ariali.ttf",
        "C:/Windows/Fonts/calibrii.ttf",
    ],
}


def resolve_font_paths(font_cfg: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Resolve font roles to existing font files, falling back to system defaults."""
    resolved: Dict[str, str] = {}
    font_cfg = font_cfg or {}
    for role, fallbacks in DEFAULT_FONTS.items():
        candidates = []
        if role in font_cfg and font_cfg[role]:
            candidates.append(font_cfg[role])
        candidates.extend(fallbacks)

        chosen = None
        for cand in candidates:
            if Path(cand).exists():
                chosen = cand
                break
        if chosen is None:
            raise FileNotFoundError(
                f"No valid font found for role '{role}'. Tried: {candidates}"
            )
        resolved[role] = chosen
    return resolved


class TextRenderer:
    """Cached font, Arabic reshaper, and drawing helper for RTL/LTR documentary frames."""

    def __init__(self, font_cfg: Optional[Dict[str, str]] = None) -> None:
        self.font_paths = resolve_font_paths(font_cfg)
        self._font_cache: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}
        self._ar_cache: Dict[str, str] = {}
        self._dummy_draw = None

    def get_font(self, role_or_path: str, size: int) -> ImageFont.FreeTypeFont:
        path = self.font_paths.get(role_or_path, role_or_path)
        key = (path, size)
        if key not in self._font_cache:
            self._font_cache[key] = ImageFont.truetype(path, size)
        return self._font_cache[key]

    def reshape_ar(self, text: str) -> str:
        """Shape and reorder Arabic text (with optional embedded numbers/Latin words) for PIL."""
        if text not in self._ar_cache:
            reshaped = arabic_reshaper.reshape(text)
            self._ar_cache[text] = get_display(reshaped)
        return self._ar_cache[text]

    @staticmethod
    def rounded_rect(
        draw: ImageDraw.ImageDraw,
        xy: Tuple[int, int, int, int],
        radius: int,
        fill: Optional[ColorLike] = None,
        outline: Optional[ColorLike] = None,
        width: int = 1,
    ) -> None:
        draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)

    def draw_text_ar(
        self,
        draw: ImageDraw.ImageDraw,
        xy: Tuple[int, int],
        text: str,
        size: int,
        fill: ColorLike,
        font_role: str = "ar_bold",
        anchor: str = "mm",
        max_w: Optional[int] = None,
    ) -> int:
        """Draw reshaped Arabic text, wrapping words cleanly if `max_w` is provided."""
        font = self.get_font(font_role, size)
        x, y = xy

        if not max_w:
            disp = self.reshape_ar(text)
            draw.text((x, y), disp, font=font, fill=fill, anchor=anchor)
            return size

        words = text.split(" ")
        lines: List[str] = []
        cur = ""
        for word in words:
            test = (cur + " " + word).strip()
            disp_t = self.reshape_ar(test)
            bbox = draw.textbbox((0, 0), disp_t, font=font)
            if (bbox[2] - bbox[0]) <= max_w or not cur:
                cur = test
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)

        line_h = int(size * 1.38)
        total_h = line_h * len(lines)
        start_y = y - total_h / 2 + line_h / 2 if "m" in anchor else y
        for idx, line in enumerate(lines):
            disp = self.reshape_ar(line)
            draw.text((x, start_y + idx * line_h), disp, font=font, fill=fill, anchor=anchor)
        return total_h

    def draw_text_ltr(
        self,
        draw: ImageDraw.ImageDraw,
        xy: Tuple[int, int],
        text: str,
        size: int,
        fill: ColorLike,
        font_role: str = "fr_bold",
        anchor: str = "mm",
    ) -> None:
        """Draw left-to-right text (French/English labels and titles)."""
        font = self.get_font(font_role, size)
        draw.text(xy, text, font=font, fill=fill, anchor=anchor)

    def draw_top_header(
        self,
        draw: ImageDraw.ImageDraw,
        scene_label_ar: str,
        scene_label_fr: str,
        width: int,
        colors: Dict[str, Tuple[int, int, int, int]],
    ) -> None:
        """Draw the persistent documentary top badge bar."""
        gold = colors["gold"]
        cream = colors["cream"]
        silver = colors["silver"]
        card_bg = colors["card_bg"]

        self.rounded_rect(
            draw,
            (60, 32, width - 60, 102),
            radius=14,
            fill=(10, 18, 32, 185),
            outline=(212, 175, 55, 110),
            width=1,
        )
        draw.rectangle([width - 80, 44, width - 72, 90], fill=gold)
        self.draw_text_ar(
            draw,
            (width - 96, 67),
            scene_label_ar,
            28,
            cream,
            font_role="ar_bold",
            anchor="rm",
        )
        self.draw_text_ltr(
            draw,
            (90, 67),
            scene_label_fr.upper(),
            20,
            silver,
            font_role="fr_bold",
            anchor="lm",
        )
        # Keep card_bg referenced in palette contract if callers customize it later
        _ = card_bg

    def draw_subtitle_bar(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        width: int,
        height: int,
        colors: Dict[str, Tuple[int, int, int, int]],
    ) -> None:
        """Draw the lower Arabic subtitle bar synchronized to narration cues."""
        if not text:
            return
        cream = colors["cream"]
        bar_h = 112
        y0 = height - bar_h - 30
        self.rounded_rect(
            draw,
            (90, y0, width - 90, y0 + bar_h),
            radius=16,
            fill=(6, 12, 24, 215),
            outline=(212, 175, 55, 105),
            width=1,
        )
        self.draw_text_ar(
            draw,
            (width // 2, y0 + bar_h // 2),
            text,
            29,
            cream,
            font_role="ar_bold",
            anchor="mm",
            max_w=width - 260,
        )

