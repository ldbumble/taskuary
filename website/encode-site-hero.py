"""Encode captured hero frames into a compact, stable-palette README GIF."""
from pathlib import Path
import sys

from PIL import Image


source = Path(sys.argv[1] if len(sys.argv) > 1 else ".readme-hero-frames")
target = Path(sys.argv[2] if len(sys.argv) > 2 else "../docs/hero.gif")
files = sorted(source.glob("*.jpg")) or sorted(source.glob("*.png"))
if not files:
    raise SystemExit(f"no captured frames in {source}")

width = 960
with Image.open(files[0]) as first:
    height = round(first.height * width / first.width)


def scaled(filename: Path) -> Image.Image:
    with Image.open(filename) as image:
        return image.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)


# One palette prevents colors from flickering between frames. Representative frames cover the
# opening assembly, finished room, walking agent, live screens, and raised-hand state.
sample_count = min(12, len(files))
sample_indexes = [round(i * (len(files) - 1) / max(1, sample_count - 1)) for i in range(sample_count)]
samples = [scaled(files[index]) for index in sample_indexes]
sheet = Image.new("RGB", (width * 4, height * 3), "#f6f4f1")
for index, image in enumerate(samples):
    sheet.paste(image, ((index % 4) * width, (index // 4) * height))
palette = sheet.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)

frames = [scaled(filename).quantize(palette=palette, dither=Image.Dither.NONE) for filename in files]
frames[0].save(
    target,
    save_all=True,
    append_images=frames[1:],
    duration=160,
    loop=0,
    optimize=True,
    disposal=1,
)
print(f"Wrote {target} ({width}x{height}, {len(frames)} frames, {target.stat().st_size:,} bytes).")
