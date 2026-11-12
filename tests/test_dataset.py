import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.download_dataset import safe_extract
from scripts.prepare_dataset import names_from, prepare, validate_label


class DatasetTests(unittest.TestCase):
    def test_names_mapping(self):
        self.assertEqual(names_from({0:'phone'}), ['phone'])
        with self.assertRaises(ValueError):
            names_from({2:'phone'})

    def test_invalid_labels(self):
        with tempfile.TemporaryDirectory() as temp:
            label = Path(temp) / 'label.txt'
            for row in ['1 0.5 0.5 0.1 0.1', '0 nan 0.5 0.1 0.1', '0 0.5 0.5 -1 0.1', '0 1 2']:
                label.write_text(row)
                with self.assertRaises(ValueError):
                    validate_label(label, 1)
            label.write_text('0 0.5 0.5 0.1 0.1')
            validate_label(label, 1)

    def test_roboflow_layout(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / 'data.yaml').write_text('names: [cell-phone]\ntrain: ../train/images\nval: ../valid/images\n')
            for split in ['train', 'valid', 'test']:
                (folder / split / 'images').mkdir(parents=True)
                (folder / split / 'labels').mkdir()
                (folder / split / 'images/x.jpg').write_bytes(b'fake-image-layout-test')
                (folder / split / 'labels/x.txt').write_text('0 0.5 0.5 0.2 0.2')
            config, counts = prepare(folder)
            self.assertEqual(counts, {'train':1, 'val':1, 'test':1})
            self.assertTrue(Path(config['train']).is_absolute())

    def test_zip_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / 'bad.zip'
            with zipfile.ZipFile(archive, 'w') as con:
                con.writestr('../outside.txt', 'bad')
            with self.assertRaises(ValueError):
                safe_extract(archive, Path(temp) / 'out')


if __name__ == '__main__':
    unittest.main()
