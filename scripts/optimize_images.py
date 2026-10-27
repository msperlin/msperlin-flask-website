"""Generate optimized WebP derivatives for the images shown on the site.

Originals stay untouched in static/img/. Derivatives go to static/img/opt/
together with manifest.json, which app.py uses to emit intrinsic width/height
attributes (prevents layout shift while images load).

Requires ImageMagick (`magick`). Run from the repository root:

    python scripts/optimize_images.py
"""

import glob
import json
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(ROOT, 'static', 'img')
OUT_DIR = os.path.join(IMG_DIR, 'opt')
MANIFEST = os.path.join(OUT_DIR, 'manifest.json')

# Displayed at 200x200 CSS px on the home page -> 2x for retina.
PROFILE_WIDTH = 400
# Card covers are displayed at 150-170 CSS px wide -> 2x for retina.
COVER_WIDTH = 340


def local_path(image_field):
    """Map a JSON image field ("static/img/x.jpg" or "/static/img/x.jpg") to disk."""
    if not image_field or image_field.startswith(('http://', 'https://')):
        return None
    name = os.path.basename(image_field)
    path = os.path.join(IMG_DIR, name)
    return path if os.path.exists(path) else None


def referenced_images():
    paths = {os.path.join(IMG_DIR, 'profile.png')}

    for pattern in ('publications', 'books'):
        for filename in glob.glob(os.path.join(ROOT, 'data', pattern, '*.json')):
            with open(filename, encoding='utf-8') as handle:
                data = json.load(handle)
            for key in ('image', 'cover_image'):
                path = local_path(data.get(key))
                if path:
                    paths.add(path)

    return sorted(p for p in paths if os.path.exists(p))


def convert(src, width, square=False):
    stem = os.path.splitext(os.path.basename(src))[0]
    dest = os.path.join(OUT_DIR, stem + '.webp')

    args = ['magick', src, '-auto-orient', '-strip']
    if square:
        args += ['-resize', f'{width}x{width}^', '-gravity', 'center',
                 '-extent', f'{width}x{width}']
    else:
        args += ['-resize', f'{width}x']
    args += ['-quality', '82', dest]

    subprocess.run(args, check=True)

    out = subprocess.check_output(
        ['magick', 'identify', '-format', '%w %h', dest], text=True)
    w, h = (int(v) for v in out.split())
    return stem, w, h, os.path.getsize(src), os.path.getsize(dest)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    manifest = {}
    before = after = 0
    for src in referenced_images():
        is_profile = os.path.basename(src) == 'profile.png'
        width = PROFILE_WIDTH if is_profile else COVER_WIDTH
        stem, w, h, src_size, dest_size = convert(src, width, square=is_profile)
        manifest[os.path.basename(src)] = {'w': w, 'h': h}
        before += src_size
        after += dest_size
        print(f'{os.path.basename(src):55s} {src_size // 1024:5d} KB -> {dest_size // 1024:4d} KB  ({w}x{h})')

    with open(MANIFEST, 'w', encoding='utf-8') as handle:
        json.dump(manifest, handle, indent=0, sort_keys=True)
        handle.write('\n')

    print(f'\n{len(manifest)} images: {before / 1024 / 1024:.1f} MB -> {after / 1024 / 1024:.1f} MB')


if __name__ == '__main__':
    main()
