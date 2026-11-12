"""Inspect downloaded YOLO labels; generate a new safe config, not execute supplied YAML."""
import argparse
import math
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def names_from(raw):
    if isinstance(raw, dict):
        raw = {int(k): v for k, v in raw.items()}
        if sorted(raw) != list(range(len(raw))):
            raise ValueError('Class IDs must be contiguous from zero')
        raw = [raw[i] for i in range(len(raw))]
    if not isinstance(raw, list) or not raw or any(not isinstance(n, str) or not n.strip() for n in raw):
        raise ValueError('Expected nonempty class names')
    return raw


def validate_label(path, classes):
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        if not line.strip():
            continue
        values = list(map(float, line.split()))
        if len(values) != 5 or not all(math.isfinite(v) for v in values):
            raise ValueError(f'Expected YOLO detection row in {path}')
        cls, x, y, w, h = values
        if not cls.is_integer() or not 0 <= cls < classes or not all(0 <= v <= 1 for v in (x,y,w,h)) or w <= 0 or h <= 0:
            raise ValueError(f'Invalid class or normalized box in {path}')


def prepare(folder):
    folder = folder.resolve()
    configs = list(folder.rglob('data.yaml')) + list(folder.rglob('data.yml'))
    if len(configs) != 1:
        raise ValueError(f'Expected one data.yaml, found {len(configs)}. Specify a narrower --input folder.')
    original = configs[0]
    raw = yaml.safe_load(original.read_text(encoding='utf-8'))
    names = names_from(raw.get('names'))
    # Resolve actual image folders instead of trusting third-party absolute paths.
    roots = [original.parent, original.parent / 'images']
    out = {'names': names, 'nc': len(names)}
    counts = {}
    for split, aliases in [('train', ['train']), ('val', ['valid', 'val']), ('test', ['test'])]:
        candidates = set()
        for base in roots:
            for alias in aliases:
                for candidate in [base / alias / 'images', base / alias]:
                    if candidate.is_dir() and any(p.suffix.lower() in {'.jpg','.jpeg','.png','.bmp','.webp'} for p in candidate.iterdir()):
                        candidates.add(candidate.resolve())
        if not candidates:
            if split == 'test':
                continue
            raise ValueError(f'Cannot find {split} images beside {original}; inspect archive layout')
        if len(candidates) != 1:
            raise ValueError(f'Ambiguous {split} image directory')
        image_dir = candidates.pop()
        label_dir = image_dir.parent / 'labels' if image_dir.name == 'images' else image_dir.parent.parent / 'labels' / image_dir.name
        if not label_dir.is_dir():
            raise ValueError(f'Label directory missing: {label_dir}')
        images = [p for p in image_dir.iterdir() if p.suffix.lower() in {'.jpg','.jpeg','.png','.bmp','.webp'}]
        for image in images:
            label = label_dir / (image.stem + '.txt')
            if not label.exists():
                raise ValueError(f'Missing label: {label}. Add an empty file only for verified negative images.')
            validate_label(label, len(names))
        counts[split] = len(images)
        out[split] = image_dir.as_posix()
    return out, counts


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, default=ROOT / 'data/kaggle-phone')
    args = parser.parse_args()
    config, counts = prepare(args.input)
    target = ROOT / 'data/phone-data.yaml'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(config, sort_keys=False), encoding='utf-8')
    print(f'Classes: {config["names"]}; images: {counts}\nGenerated: {target}')
    print('Review class names, sample annotations and duplicate images before training.')
