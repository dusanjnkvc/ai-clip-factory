"""Bounded local document extraction with page/section provenance."""
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree
from .media import PipelineError

MAX_BYTES = 15 * 1024 * 1024


def _ocr(image):
    executable = shutil.which('tesseract')
    if not executable:
        return None
    result = subprocess.run([executable, str(image), 'stdout'], capture_output=True,
        encoding='utf-8', errors='replace', timeout=90, shell=False)
    if result.returncode:
        raise PipelineError('Local OCR failed. Review the scan and supply its text manually.')
    return result.stdout[:80000]


def extract_document(path, name=None):
    path = Path(path)
    name = name or path.name
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise PipelineError('Campaign documents must exist and be smaller than 15 MB.')
    sections, warnings = [], []
    suffix = path.suffix.lower()
    if suffix == '.txt':
        try:
            text = path.read_text(encoding='utf-8-sig')
        except UnicodeError as exc:
            raise PipelineError('Save campaign TXT documents as UTF-8.') from exc
        if '\x00' in text:
            raise PipelineError('Campaign TXT contains binary data.')
        sections.append({'source': name + ':text', 'text': text[:120000]})
    elif suffix == '.docx':
        try:
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                if len(entries) > 1000 or sum(x.file_size for x in entries) > 20*1024*1024:
                    raise PipelineError('DOCX expands beyond the safe document limit.')
                raw = archive.read('word/document.xml')
            if b'<!DOCTYPE' in raw or b'<!ENTITY' in raw:
                raise PipelineError('DOCX external entities are unsupported.')
            root = ElementTree.fromstring(raw)
            ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
            text = '\n'.join(''.join(n.itertext()) for n in root.iter(ns+'p'))
            sections.append({'source': name + ':document', 'text': text[:120000]})
        except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
            raise PipelineError('Invalid DOCX campaign document.') from exc
    elif suffix == '.pdf':
        from pypdf import PdfReader
        try:
            reader = PdfReader(path)
            if reader.is_encrypted or len(reader.pages) > 100:
                raise PipelineError('Use an unencrypted PDF of at most 100 pages.')
            with tempfile.TemporaryDirectory(prefix='acf-ocr-') as directory:
                for i, page in enumerate(reader.pages):
                    text = (page.extract_text() or '')[:80000]
                    method = 'text'
                    if not text.strip():
                        rasterizer = shutil.which('pdftoppm')
                        if rasterizer and shutil.which('tesseract') and i < 20:
                            prefix = Path(directory)/'page'
                            result = subprocess.run([rasterizer, '-f', str(i+1), '-l', str(i+1), '-singlefile',
                                '-scale-to', '1800', '-png', str(path), str(prefix)], capture_output=True, timeout=90, shell=False)
                            if result.returncode:
                                raise PipelineError('Unable to rasterize scanned PDF for local OCR.')
                            text = _ocr(prefix.with_suffix('.png')) or ''
                            method = 'ocr_unverified'
                        else:
                            warnings.append(f'{name}:page {i+1} needs OCR. Install local Tesseract and Poppler (pdftoppm), or paste its text. OCR is limited to20 pages per document.')
                    sections.append({'source': f'{name}:page {i+1}:{method}', 'text': text})
        except PipelineError:
            raise
        except Exception as exc:
            raise PipelineError('Unable to extract campaign PDF.') from exc
    elif suffix in {'.png', '.jpg', '.jpeg'}:
        text = _ocr(path)
        if text is None:
            warnings.append(f'{name} needs local Tesseract OCR or manually supplied text.')
        sections.append({'source': name + ':ocr_unverified', 'text': text or ''})
    else:
        raise PipelineError('Use PDF, UTF-8 TXT, DOCX, PNG or JPEG campaign documents.')
    if sum(len(s['text']) for s in sections) > 240000:
        raise PipelineError('Extracted campaign text exceeds 240,000 characters.')
    return sections, warnings
