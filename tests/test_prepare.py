import argparse
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('convert', ROOT/'convert.py')
convert = importlib.util.module_from_spec(spec); spec.loader.exec_module(convert)

class PrepareTests(unittest.TestCase):
    def book(self, root):
        files = {
            'META-INF/container.xml': '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/book.opf"/></rootfiles></container>',
            'OEBPS/book.opf': '<package xmlns="http://www.idpf.org/2007/opf"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Test Book</dc:title><dc:creator>Test Author</dc:creator></metadata><manifest><item id="b" href="b.xhtml" media-type="application/xhtml+xml"/><item id="a" href="a.xhtml" media-type="application/xhtml+xml"/><item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/></manifest><spine><itemref idref="a"/><itemref idref="b"/></spine></package>',
            'OEBPS/toc.ncx': '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/"><navMap><navPoint><navLabel><text>First</text></navLabel><content src="a.xhtml"/></navPoint></navMap></ncx>',
            'OEBPS/a.xhtml': '<html><head><title>Skip head</title></head><body><h1>Start</h1><p>One &amp; two.</p><script>Ignore code.</script></body></html>',
            'OEBPS/b.xhtml': '<html><body><p>Last paragraph.</p></body></html>',
        }
        for name, text in files.items():
            p=root/name; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(text)
        return files

    def test_directory_and_zip_preserve_spine_and_text(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); source=root/'source.epub'; files=self.book(source)
            zipped=root/'source.zip.epub'
            with zipfile.ZipFile(zipped,'w') as z:
                for name,text in files.items(): z.writestr(name,text)
            for i,book in enumerate([source,zipped]):
                project=root/f'output-{i}'
                args=argparse.Namespace(source=book,project=project,model_dir=root/'models',sensor_dir=root/'sensors',voice='af_heart',speed=.95)
                convert.prepare(args)
                chapters=json.loads((project/'chapters.json').read_text())
                self.assertEqual([c['id'] for c in chapters],['a','b'])
                self.assertEqual(chapters[0]['title'],'First')
                self.assertEqual((project/'build/01-a.txt').read_text(),'Start\n\nOne & two.')
                self.assertEqual(json.loads((project/'book.json').read_text())['author'],'Test Author')
                convert.plan(project,json.loads((project/'book.json').read_text()))
                plan=json.loads((project/'kokoro-heart-build/parallel-plan.json').read_text())
                self.assertEqual(set(plan),{'01-a','02-b'})
                with self.assertRaises(ValueError): convert.prepare(args)

    def test_paths_cannot_escape_book(self):
        with self.assertRaises(ValueError): convert.internal('OEBPS','../../outside')
        self.assertEqual(convert.internal('OEBPS','../META-INF/container.xml'),'META-INF/container.xml')

    def test_guarded_worker_has_no_subprocess_temperature_timeout(self):
        import ast
        tree=ast.parse((ROOT/'scripts/kokoro_audiobook.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='wait_until_cool')
        def forbidden(): self.fail('A paused worker must not use the timed thermal subprocess')
        scope={'GUARDED':True,'thermal_state':forbidden}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'regression','exec'),scope)
        scope['wait_until_cool']()

if __name__ == '__main__': unittest.main()
