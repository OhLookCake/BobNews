#!/usr/bin/env python3
"""Add classic meme-style text to the bottom of an image."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


DEFAULT_INPUT = Path("images/clean.jpg")
DEFAULT_OUTPUT = "meme.jpg"


def find_font(requested_font: str | None) -> str:
    """Return an Impact-like bold condensed font available on this machine."""
    if requested_font:
        if not Path(requested_font).is_file():
            raise FileNotFoundError(f"Font not found: {requested_font}")
        return requested_font

    candidates = [
        # macOS
        "/System/Library/Fonts/Supplemental/Impact.ttf",
        "/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf",
        # Windows
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "impact.ttf"),
        # Common Linux fonts
        "/usr/share/fonts/truetype/msttcorefonts/Impact.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate

    raise FileNotFoundError(
        "Could not find an Impact-like font. Pass one explicitly with --font."
    )


def text_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    stroke_width: int,
) -> int:
    left, _, right, _ = draw.textbbox(
        (0, 0), text, font=font, stroke_width=stroke_width
    )
    return right - left


def split_long_word(
    draw: ImageDraw.ImageDraw,
    word: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    stroke_width: int,
) -> list[str]:
    """Split a single word when it cannot fit on a line by itself."""
    parts: list[str] = []
    part = ""
    for character in word:
        candidate = part + character
        if part and text_width(draw, candidate, font, stroke_width) > max_width:
            parts.append(part)
            part = character
        else:
            part = candidate
    if part:
        parts.append(part)
    return parts


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    stroke_width: int,
) -> str:
    """Wrap text using rendered pixel width, while respecting manual newlines."""
    lines: list[str] = []

    for paragraph in text.splitlines() or [text]:
        words: list[str] = []
        for word in paragraph.split():
            if text_width(draw, word, font, stroke_width) > max_width:
                words.extend(
                    split_long_word(draw, word, font, max_width, stroke_width)
                )
            else:
                words.append(word)

        if not words:
            lines.append("")
            continue

        line = words[0]
        for word in words[1:]:
            candidate = f"{line} {word}"
            if text_width(draw, candidate, font, stroke_width) <= max_width:
                line = candidate
            else:
                lines.append(line)
                line = word
        lines.append(line)

    return "\n".join(lines)


def fit_caption(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: str,
    image_width: int,
    image_height: int,
    size_spec: str | None,
) -> tuple[str, ImageFont.FreeTypeFont, int, int, tuple[int, int, int, int]]:
    """Find the largest wrapped caption that fits the allotted bottom area."""
    max_width = int(image_width * 0.92)
    max_height = int(image_height * 0.30)
    baseline_size = 66

    if size_spec is None:
        font_sizes = range(baseline_size, 11, -1)
    else:
        try:
            if size_spec.startswith(("+", "-")):
                requested_size = baseline_size + int(size_spec)
            else:
                requested_size = int(size_spec)
        except ValueError as error:
            raise ValueError(
                "Font size must be an integer such as +10, -10, or 72."
            ) from error

        if requested_size < 1:
            raise ValueError("Font size must resolve to at least 1 pixel.")
        minimum_size = min(12, requested_size)
        font_sizes = range(requested_size, minimum_size - 1, -1)

    for font_size in font_sizes:
        font = ImageFont.truetype(font_path, font_size)
        stroke_width = max(2, font_size // 18)
        spacing = max(2, font_size // 12)
        wrapped = wrap_text(draw, text, font, max_width, stroke_width)
        bbox = draw.multiline_textbbox(
            (0, 0),
            wrapped,
            font=font,
            spacing=spacing,
            align="center",
            stroke_width=stroke_width,
        )
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        if width <= max_width and height <= max_height:
            return wrapped, font, stroke_width, spacing, bbox

    raise ValueError("The caption is too long to fit legibly on this image.")


def add_caption(
    text: str,
    input_path: Path,
    output_path: Path,
    font_path: str,
    uppercase: bool,
    size_spec: str | None,
) -> None:
    with Image.open(input_path) as opened_image:
        image = ImageOps.exif_transpose(opened_image).convert("RGB")

    if uppercase:
        text = text.upper()

    draw = ImageDraw.Draw(image)
    wrapped, font, stroke_width, spacing, bbox = fit_caption(
        draw, text, font_path, image.width, image.height, size_spec
    )

    text_width_px = bbox[2] - bbox[0]
    text_height_px = bbox[3] - bbox[1]
    bottom_margin = max(16, int(image.height * 0.035))
    x = (image.width - text_width_px) / 2 - bbox[0]
    y = image.height - bottom_margin - text_height_px - bbox[1]

    draw.multiline_text(
        (x, y),
        wrapped,
        font=font,
        fill="white",
        stroke_width=stroke_width,
        stroke_fill="black",
        spacing=spacing,
        align="center",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_options = {"quality": 95, "subsampling": 0} if output_path.suffix.lower() in {
        ".jpg",
        ".jpeg",
    } else {}
    image.save(output_path, **save_options)


def resolve_output_path(output: str) -> Path:
    """Put bare output filenames in ./images and preserve explicit paths."""
    expanded = os.path.expanduser(output)
    path = Path(expanded)
    has_explicit_path = (
        path.is_absolute()
        or path.parent != Path(".")
        or expanded.startswith(f".{os.sep}")
    )
    return path if has_explicit_path else Path("images") / path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Add white, black-outlined meme text to the bottom of an image."
    )
    parser.add_argument("text", nargs="+", help="Caption text (quote it to preserve spacing)")
    parser.add_argument(
        "-i", "--input", type=Path, default=DEFAULT_INPUT, help="Source image"
    )
    parser.add_argument(
        "-o",
        "--output",
        default=DEFAULT_OUTPUT,
        metavar="NAME_OR_PATH",
        help="Output filename or path (bare filenames are placed in ./images)",
    )
    parser.add_argument("--font", help="Path to a .ttf font (Impact is used by default)")
    parser.add_argument(
        "--size",
        metavar="SIZE",
        help=(
            "Starting font size: +N or -N adjusts the automatic baseline; "
            "N sets an absolute pixel size (shrinks as needed to fit)"
        ),
    )
    parser.add_argument(
        "--keep-case", action="store_true", help="Do not convert the caption to uppercase"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    caption = " ".join(args.text).strip()
    if not caption:
        raise SystemExit("Caption text cannot be empty.")

    try:
        font_path = find_font(args.font)
        output_path = resolve_output_path(args.output)
        add_caption(
            caption,
            args.input,
            output_path,
            font_path,
            uppercase=not args.keep_case,
            size_spec=args.size,
        )
    except (FileNotFoundError, OSError, ValueError) as error:
        raise SystemExit(f"Error: {error}") from error

    print(f"Created {output_path}")


if __name__ == "__main__":
    main()
