import hashlib
import json
from pathlib import Path
import tempfile
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

import app_bridge as app
from scripts.runtime_settings import DEFAULTS, validate, atomic_json, lock_audio_settings
import test_prepare


class AppTests(unittest.TestCase):
    def test_detached_job_records_an_engine_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/'scripts').mkdir(); project=root/'book'; project.mkdir()
            for name in ('app_job.py','runtime_settings.py'):
                shutil.copyfile(app.REPO/'scripts'/name,root/'scripts'/name)
            (root/'convert.py').write_text('import sys\nassert sys.argv[1]=="run"\nraise SystemExit(13)\n')
            process=subprocess.Popen([sys.executable,str(root/'scripts/app_job.py'),str(project)],stdin=subprocess.PIPE,start_new_session=True)
            atomic_json(project/'app-run.json',dict(pid=process.pid,exit_code=None))
            process.communicate(b'1',timeout=10)
            self.assertEqual(process.returncode,13)
            self.assertEqual(app.read(project/'app-run.json')['exit_code'],13)

    def test_temperature_relationships_and_limit(self):
        self.assertEqual(validate({})['ceiling_c'], 90)
        for settings in ({'ceiling_c': 95}, {'pause_c': 89}, {'resume_c': 87}, {'speed': float('nan')}):
            with self.assertRaises(ValueError): validate(settings)

    def test_prepare_progress_save_and_receipt_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root/'sample.epub'; project = root/'output'
            test_prepare.PrepareTests().book(source)
            result = app.dispatch(dict(action='prepare', project=str(project), config=dict(
                source=str(source), model_dir=str(root/'models'), sensor_dir=str(root/'sensors'),
                title='My title', author='', voice='af_bella', speed=1.1)))
            self.assertEqual(result['config']['title'], 'My title')
            self.assertEqual(result['config']['author'], 'Test Author')
            self.assertEqual(result['progress']['total'], 6)
            self.assertFalse(result['active'])
            config = result['config']; lock_audio_settings(project, config)
            chapter = json.loads((project/'chapters.json').read_text())[0]
            text = (project/'build'/f'{chapter["file"]}.txt').read_text()
            receipt = project/'kokoro-heart-build'/chapter['file']/'0001.json'
            receipt.parent.mkdir(parents=True)
            atomic_json(receipt, dict(voice='af_bella', speed=1.1, frames=24000,
                signature=hashlib.sha256(('af_bella'+str(1.1)+text).encode()).hexdigest()))
            receipt.with_suffix('.flac').touch()
            result = app.snapshot(project)
            self.assertEqual(result['progress']['saved'], 4)
            with self.assertRaisesRegex(ValueError, 'Saved audio'):
                app.dispatch(dict(action='save',project=str(project),config={'speed': 1.2}))
            result = app.dispatch(dict(action='save',project=str(project),config={'pause_c': 85}))
            self.assertEqual(result['config']['pause_c'],85)

    def test_gui_controls_and_duplicate_rejection(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            with patch.object(app, 'state', return_value=({},True,False)), patch.object(app, 'snapshot', return_value={}):
                app.dispatch(dict(action='pause',project=folder))
                self.assertTrue((project/'pause.request').exists())
                with patch.object(app, 'read', return_value={}):
                    app.dispatch(dict(action='resume',project=folder))
                self.assertFalse((project/'pause.request').exists())
                app.dispatch(dict(action='stop',project=folder))
                self.assertTrue((project/'stop.request').exists())
            with patch.object(app,'state',return_value=({},True,True)), patch.object(app,'read',return_value={}):
                with self.assertRaisesRegex(ValueError,'already running'):
                    app.dispatch(dict(action='start',project=folder))

    def test_settings_cannot_change_audio_during_active_job(self):
        with tempfile.TemporaryDirectory() as folder:
            project=Path(folder); atomic_json(project/'book.json',DEFAULTS)
            with patch.object(app,'state',return_value=({},True,False)):
                with self.assertRaisesRegex(ValueError,'Pause or stop'):
                    app.dispatch(dict(action='save',project=folder,config={'segment_rest':2}))


if __name__ == '__main__': unittest.main()
