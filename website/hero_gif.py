"""Assemble the README hero GIF from the frames hero_frames.mjs captured.

Pillow rather than ffmpeg/ImageMagick, neither of which is on this machine. Two things
decide whether a UI GIF is watchable: a palette that does not band the flat panel greys
(one shared adaptive palette, built from the busiest frame, so colours never shift between
frames) and honest scaling (integer-ish downscale with LANCZOS, no sharpening halos).

    python hero_gif.py [--width 1200] [--colors 128]
"""
import argparse, json, pathlib, sys
from PIL import Image

HERE = pathlib.Path(__file__).parent
SRC = HERE / '_hero'
OUT = HERE.parent / 'docs' / 'hero.gif'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--width', type=int, default=1200)
    ap.add_argument('--colors', type=int, default=128)
    ap.add_argument('--out', default=str(OUT))
    a = ap.parse_args()
    man = json.loads((SRC / 'frames.json').read_text())
    if not man['frames']: sys.exit('no frames captured')

    scale = a.width / man['width']
    size = (a.width, int(man['height'] * scale) // 2 * 2)
    raw = [Image.open(SRC / f['file']).convert('RGB').resize(size, Image.LANCZOS) for f in man['frames']]

    # ONE palette for the whole animation, taken from the frame with the most distinct colours
    # (the report chart). A per-frame palette makes the greys crawl between frames.
    busiest = max(raw, key=lambda im: len(im.getcolors(maxcolors=1 << 24) or [1]))
    pal = busiest.quantize(colors=a.colors, method=Image.MEDIANCUT)
    seq = [im.quantize(palette=pal, dither=Image.FLOYDSTEINBERG) for im in raw]

    seq[0].save(a.out, save_all=True, append_images=seq[1:],
                duration=[f['delay'] for f in man['frames']], loop=0, optimize=True, disposal=2)
    kb = pathlib.Path(a.out).stat().st_size / 1024
    print(f'{a.out} — {len(seq)} frames, {size[0]}x{size[1]}, {kb:.0f} KB')
    if kb > 9000: print('WARNING: over ~9MB; drop --colors or --width, or cut frames')


if __name__ == '__main__':
    main()
