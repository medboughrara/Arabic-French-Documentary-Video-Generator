#!/usr/bin/env python3
"""Utility script to generate clean cropped assets from composite source photos."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Tuple

from PIL import Image, ImageEnhance

# Default crop definitions matching assets/ilboursa_img.jpg (1280x732)
DEFAULT_CROPS: Dict[str, Tuple[int, int, int, int]] = {
    "book_front": (710, 0, 1280, 732),
    "book_back": (0, 0, 530, 732),
    "portrait_suit": (888, 360, 1102, 572),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Export cropped portrait/book images for inspection.")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("assets/ilboursa_img.jpg"),
        help="Composite source image path.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("assets/crops"),
        help="Output directory for cropped PNGs.",
    )
    args = parser.parse_args()

    img = Image.open(args.source).convert("RGB")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    for name, box in DEFAULT_CROPS.items():
        cropped = img.crop(box)
        if name == "portrait_suit":
            cropped = ImageEnhance.Sharpness(cropped).enhance(1.3)
            cropped = ImageEnhance.Contrast(cropped).enhance(1.06)
        out_path = args.out_dir / f"{name}.png"
        cropped.save(out_path)
        print(f"Saved {name}: {out_path} ({cropped.size[0]}x{cropped.size[1]})")


if __name__ == "__main__":
    main()

