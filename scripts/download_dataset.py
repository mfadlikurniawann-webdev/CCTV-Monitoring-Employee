"""Download only on explicit execution, using the user's Kaggle credentials."""
import argparse
import subprocess
import sys
import zipfile
from pathlib import Path

DATASET = 'a165079/cellphoneobjectdetectionusingyolov7'
ROOT = Path(__file__).resolve().parents[1]


def safe_extract(archive, destination):
    destination = destination.resolve()
    with zipfile.ZipFile(archive) as zip_file:
        if sum(i.file_size for i in zip_file.infolist()) > 5 * 1024**3:
            raise ValueError('Unexpected expanded archive size (>5 GiB)')
        for member in zip_file.infolist():
            target = (destination / member.filename).resolve()
            if not target.is_relative_to(destination) or (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Unsafe ZIP entry')
        zip_file.extractall(destination)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Download selected Kaggle phone detection dataset (~210 MB).')
    parser.add_argument('--accept-dataset-terms', action='store_true', help='Confirm you have reviewed the dataset/source license')
    args = parser.parse_args()
    if not args.accept_dataset_terms:
        parser.error('Review Kaggle and original source terms, then pass --accept-dataset-terms')
    downloads = ROOT / 'data/downloads'
    destination = ROOT / 'data/kaggle-phone'
    downloads.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        parser.error('data/kaggle-phone already exists. Use another copy or inspect it; it will not be overwritten.')
    subprocess.run([sys.executable, '-m', 'kaggle', 'datasets', 'download', '-d', DATASET,
                    '-p', str(downloads)], check=True)
    archives = list(downloads.glob('*.zip'))
    if len(archives) != 1:
        raise RuntimeError('Expected exactly one ZIP in data/downloads; inspect this folder')
    destination.mkdir()
    safe_extract(archives[0], destination)
    print(f'Extracted to {destination}. Next: python scripts/prepare_dataset.py')
