import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--epochs', type=int, default=50)
    parser.add_argument('--batch', type=int, default=4)
    parser.add_argument('--imgsz', type=int, default=640)
    parser.add_argument('--device', default='cpu', help='cpu or GPU index e.g. 0')
    args = parser.parse_args()
    if min(args.epochs, args.batch, args.imgsz) <= 0:
        parser.error('epochs, batch, imgsz must be positive')
    dataset = ROOT / 'data/phone-data.yaml'
    if not dataset.is_file():
        parser.error('Run scripts/prepare_dataset.py first')
    from ultralytics import YOLO
    model = YOLO('yolo11n.pt')
    model.train(data=str(dataset), epochs=args.epochs, batch=args.batch, imgsz=args.imgsz,
                device=args.device, workers=0, seed=42, project=str(ROOT / 'runs'), name='phone')
    model.val(data=str(dataset), split='val', device=args.device)
    print(f'Best weights: {model.trainer.best}')
    print('Set PHONE_MODEL in .env to this best.pt path, then restart the dashboard.')
