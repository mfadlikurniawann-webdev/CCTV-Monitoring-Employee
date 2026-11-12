import math
import os
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def load_config():
    load_dotenv(ROOT / '.env')
    path = Path(os.getenv('MONITOR_CONFIG', 'cameras.yaml'))
    if not path.is_absolute():
        path = ROOT / path
    cfg = yaml.safe_load(path.read_text(encoding='utf-8'))
    if os.getenv('PHONE_MODEL'):
        cfg['phone_model'] = os.environ['PHONE_MODEL']
    for key in ('sample_fps', 'minimum_seconds', 'gap_seconds', 'retention_days'):
        value = float(cfg[key])
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f'{key} must be positive and finite')
        cfg[key] = value
    if not 0 < float(cfg['confidence']) <= 1:
        raise ValueError('confidence must be between 0 and 1')
    cfg['confidence'] = float(cfg['confidence'])
    if not isinstance(cfg['image_size'], int) or cfg['image_size'] < 32:
        raise ValueError('image_size must be an integer >= 32')
    if cfg['gap_seconds'] < 1 / cfg['sample_fps']:
        raise ValueError('gap_seconds must cover at least one sample interval')
    classes = cfg.get('phone_class_ids')
    if classes is not None and (not isinstance(classes, list) or not classes or
                                any(not isinstance(i, int) or i < 0 for i in classes)):
        raise ValueError('phone_class_ids must be null or a nonempty list of nonnegative integers')
    ids = set()
    if not cfg.get('cameras'):
        raise ValueError('At least one camera is required')
    for camera in cfg['cameras']:
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,40}', camera['id']) or camera['id'] in ids:
            raise ValueError('Camera IDs must be unique safe names')
        ids.add(camera['id'])
        names = set()
        for zone in camera.get('zones', []):
            if not zone['name'] or zone['name'] in names:
                raise ValueError('Zone names must be unique within a camera')
            names.add(zone['name'])
            points = zone['points']
            if len(points) < 3 or any(len(p) != 2 or any(not 0 <= v <= 1 for v in p) for p in points):
                raise ValueError('Zones require at least 3 normalized points')
    return cfg


def resolve_source(source):
    if isinstance(source, int):
        return source
    source = str(source)
    if source.startswith('env:'):
        source = os.getenv(source[4:], '')
        if not source:
            raise ValueError('Camera source environment variable is empty')
    if source.startswith(('rtsp://', 'rtsps://')):
        return source
    if '://' in source:
        raise ValueError('Only RTSP URLs or local video paths are allowed')
    path = Path(source)
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_file():
        raise ValueError('Configured local video does not exist')
    return str(path.resolve())
