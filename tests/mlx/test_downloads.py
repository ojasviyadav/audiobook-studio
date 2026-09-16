from pathlib import Path
import hashlib
import tempfile
import unittest
from unittest.mock import Mock, patch
from scripts import download_models_resumable as downloader

class Response:
    status_code=206
    def __init__(self,content_range,blocks):self.headers={'Content-Range':content_range};self.blocks=blocks
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def raise_for_status(self):pass
    def iter_content(self,size):return iter(self.blocks)

class DownloadTests(unittest.TestCase):
    def test_interrupted_range_retries_and_completed_part_is_reused(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'000.part';client=Mock()
            client.get.side_effect=[Response('bytes 0-5/6',[b'abc']),Response('bytes 0-5/6',[b'abc',b'def'])]
            with patch.object(downloader,'session',return_value=client),patch.object(downloader.time,'sleep'):
                self.assertEqual(downloader.fetch_part('https://example.test/file',0,5,path,6),6)
                self.assertEqual(downloader.fetch_part('https://example.test/file',0,5,path,6),6)
            self.assertEqual(path.read_bytes(),b'abcdef')
            self.assertEqual(client.get.call_count,2)
            self.assertFalse(path.with_suffix('.pending').exists())

    def test_wrong_range_cannot_be_saved(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'000.part';client=Mock()
            client.get.return_value=Response('bytes 0-5/12',[b'abcdef'])
            with patch.object(downloader,'session',return_value=client),patch.object(downloader.time,'sleep'):
                with self.assertRaisesRegex(RuntimeError,'failed after retries'):
                    downloader.fetch_part('https://example.test/file',6,11,path,12)
            self.assertFalse(path.exists())

    def test_full_file_digest_rejects_equal_size_corruption(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'model';path.write_bytes(b'abcdef')
            file={'size':6,'sha256':hashlib.sha256(b'abcdef').hexdigest(),'git_blob_sha1':None}
            self.assertTrue(downloader.valid(path,file))
            path.write_bytes(b'abcdeg')
            self.assertFalse(downloader.valid(path,file))
