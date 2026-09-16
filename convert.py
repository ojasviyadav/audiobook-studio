"""Prepare, resume, and inspect local Kokoro audiobook projects."""
from pathlib import Path, PurePosixPath
from html.parser import HTMLParser
from urllib.parse import unquote
import argparse
import ast
import hashlib
import json
import os
import posixpath
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

REPO = Path(__file__).resolve().parent
NS = {'o': 'http://www.idpf.org/2007/opf', 'n': 'http://www.daisy.org/z3986/2005/ncx/',
      'c': 'urn:oasis:names:tc:opendocument:xmlns:container',
      'dc': 'http://purl.org/dc/elements/1.1/'}

class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.body = False
        self.hidden = 0
        self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag == 'body': self.body = True
        if tag in ('script', 'style'): self.hidden += 1
        if self.body and tag in ('div', 'p', 'br', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'tr'):
            self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in ('script', 'style'): self.hidden = max(0, self.hidden - 1)
        if self.body and tag in ('div', 'p', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'tr'):
            self.parts.append('\n')
        if tag == 'body': self.body = False
    def handle_data(self, data):
        if self.body and not self.hidden: self.parts.append(data)
    def text(self):
        return '\n\n'.join(s for line in ''.join(self.parts).splitlines()
                           if (s := re.sub(r'\s+', ' ', line).strip()))

def internal(base, href):
    name = posixpath.normpath(posixpath.join(base, unquote(href.split('#')[0])))
    if name.startswith('/') or '..' in PurePosixPath(name).parts:
        raise ValueError('EPUB path is outside the book')
    return name

def prepare(args):
    source, project = args.source.resolve(), args.project.resolve()
    if project.exists() and any(project.iterdir()):
        raise ValueError('Project directory is not empty. Use run to resume it.')
    archive = zipfile.ZipFile(source) if source.is_file() else None
    def read(name):
        if archive:
            return archive.read(name)
        path = (source / name).resolve()
        if not path.is_relative_to(source):
            raise ValueError('EPUB path is outside the book')
        return path.read_bytes()
    try:
        container = ET.fromstring(read('META-INF/container.xml'))
        opf_name = container.find('c:rootfiles/c:rootfile', NS).attrib['full-path']
        opf_name = internal('', opf_name)
        opf = ET.fromstring(read(opf_name))
        base = posixpath.dirname(opf_name)
        manifest = {e.attrib['id']: e.attrib for e in opf.findall('o:manifest/o:item', NS)}
        title = opf.findtext('o:metadata/dc:title', default=source.stem, namespaces=NS).strip()
        author = opf.findtext('o:metadata/dc:creator', default='Unknown author', namespaces=NS).strip()
        titles = {}
        for item in manifest.values():
            if item.get('media-type') == 'application/x-dtbncx+xml':
                ncx_name = internal(base, item['href'])
                ncx = ET.fromstring(read(ncx_name))
                for point in ncx.findall('.//n:navPoint', NS):
                    content, label = point.find('n:content', NS), point.findtext('n:navLabel/n:text', namespaces=NS)
                    if content is not None and label:
                        titles.setdefault(internal(posixpath.dirname(ncx_name), content.attrib['src']), label)
            elif 'nav' in item.get('properties', '').split():
                nav_name = internal(base, item['href'])
                nav = ET.fromstring(read(nav_name))
                for link in nav.iter():
                    if link.tag.rsplit('}', 1)[-1] == 'a' and link.get('href'):
                        href = link.get('href')
                        if '://' not in href:
                            titles.setdefault(internal(posixpath.dirname(nav_name), href), ''.join(link.itertext()).strip())
        sections = []
        for ref in opf.findall('o:spine/o:itemref', NS):
            ident = ref.attrib['idref']
            item = manifest[ident]
            if item.get('media-type') not in ('application/xhtml+xml', 'text/html'):
                continue
            name = internal(base, item['href'])
            markup = read(name).decode('utf-8-sig')
            parser = TextParser(); parser.feed(markup)
            text = parser.text()
            if not text: continue
            slug = re.sub(r'[^A-Za-z0-9_-]', '_', ident)
            stem = f'{len(sections)+1:02d}-{slug}'
            sections.append(({'id': ident, 'file': stem, 'title': titles.get(name, ident),
                              'words': len(text.split())}, text))
        if not sections:
            raise ValueError('No readable EPUB body text found')
        cover_item = next((i for i in manifest.values() if 'cover-image' in i.get('properties', '').split()), None)
        if cover_item is None:
            cover_meta = opf.find("o:metadata/o:meta[@name='cover']", NS)
            if cover_meta is not None:
                cover_item = manifest.get(cover_meta.get('content'))
        cover_bytes = read(internal(base, cover_item['href'])) if cover_item else None
        (project/'build').mkdir(parents=True, exist_ok=True)
        for chapter, text in sections:
            (project/'build'/f'{chapter["file"]}.txt').write_text(text)
        (project/'chapters.json').write_text(json.dumps([c for c,t in sections], indent=2))
        cover = None
        if cover_bytes:
            suffix = PurePosixPath(cover_item['href']).suffix
            cover = project / ('cover' + suffix)
            cover.write_bytes(cover_bytes)
        safe_title = re.sub(r'[/\\\x00-\x1f]', '_', title)
        config = dict(title=title, author=author, source=str(source), voice=args.voice, speed=args.speed,
                      model_dir=str(args.model_dir.resolve()), sensor_dir=str(args.sensor_dir.resolve()),
                      cover=str(cover) if cover else None, output_name=f'{safe_title} — {args.voice}.m4b')
        (project/'book.json').write_text(json.dumps(config, indent=2))
        print(f'Prepared {len(sections)} sections and {sum(c["words"] for c,t in sections):,} words in {project}')
    finally:
        if archive: archive.close()

def plan(project, config):
    # Read only the pure splitting function; do not import the narration runtime.
    tree = ast.parse((REPO/'scripts/kokoro_audiobook.py').read_text())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'batches')
    scope = {}; exec(compile(ast.Module(body=[fn], type_ignores=[]), 'batches', 'exec'), scope)
    chapters = json.loads((project/'chapters.json').read_text())
    remaining = []
    work = project/'kokoro-heart-build'; work.mkdir(exist_ok=True)
    for chapter in chapters:
        pending = 0
        for n, text in enumerate(scope['batches']((project/'build'/f'{chapter["file"]}.txt').read_text()), 1):
            path = work/chapter['file']/f'{n:04d}.json'
            signature = hashlib.sha256((config['voice']+str(config['speed'])+text).encode()).hexdigest()
            try:
                done = path.with_suffix('.flac').exists() and json.loads(path.read_text())['signature'] == signature
            except (OSError, ValueError, KeyError): done = False
            if not done: pending += len(text.split())
        remaining.append((pending, chapter['file']))
    loads, assignment = [0,0,0], {}
    for words, stem in sorted(remaining, reverse=True):
        worker = min(range(3), key=lambda i: loads[i])
        assignment[stem] = worker; loads[worker] += words
    (work/'parallel-plan.json').write_text(json.dumps(assignment, indent=2))
    print('Remaining words per worker:', loads, flush=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('source', type=Path)
    prep.add_argument('--project', type=Path, required=True)
    prep.add_argument('--model-dir', type=Path, required=True)
    prep.add_argument('--sensor-dir', type=Path, default=REPO/'vendor/smctemp')
    prep.add_argument('--voice', default='af_heart')
    prep.add_argument('--speed', type=float, default=0.95)
    for command in ('run', 'status', 'benchmark'):
        p=sub.add_parser(command); p.add_argument('project', type=Path)
    args=parser.parse_args()
    if args.command == 'prepare':
        if not 0.5 <= args.speed <= 2: parser.error('speed must be between 0.5 and 2')
        prepare(args); return
    project=args.project.resolve(); config=json.loads((project/'book.json').read_text())
    env=dict(os.environ, AUDIOBOOK_PROJECT=str(project), AUDIOBOOK_SENSORS=config['sensor_dir'])
    if args.command in ('run', 'benchmark'):
        # Keep a lock for this entire invocation to prevent duplicate workers.
        import fcntl
        with (project/'conversion.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            plan(project, config)
            command = [sys.executable,str(REPO/'scripts/temperature_guard.py')]
            if args.command == 'benchmark':
                command += [sys.executable,str(REPO/'scripts/benchmark_kokoro.py')]
            subprocess.run(command, env=env, check=True)
    else:
        subprocess.run([sys.executable,str(REPO/'scripts/narration_progress.py')], env=env, check=True)

if __name__ == '__main__':
    main()
