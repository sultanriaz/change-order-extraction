import json
from pathlib import Path
import pytest
from co_extract.ingest import CorruptDocument, EmptyDocument, load_document

ROOT = Path(__file__).resolve().parents[1]

def test_generator_counts():
    manifest = json.loads((ROOT / 'data/synthetic/manifest.json').read_text())
    assert len(manifest) == 120
    assert [sum(row['split'] == s for row in manifest) for s in ('train','dev','test')] == [60,20,40]
    assert all((ROOT / row['source']).exists() and (ROOT / row['truth']).exists() for row in manifest)
    for tag in {tag for row in manifest for tag in row['tags']}:
        assert sum(tag in row['tags'] for row in manifest) >= 5

def test_pdf_page_numbers():
    result = load_document(ROOT / 'examples/sample.pdf')
    assert result.pages[0].num == 1
    assert 'Change Order Number:' in result.pages[0].text
    assert len(result.source_hash) == 64

def test_input_errors(tmp_path):
    invalid = tmp_path/'fail.pdf'
    invalid.write_bytes(b'badpdf')
    with pytest.raises(CorruptDocument):
        load_document(invalid)
    empty = tmp_path/'empty.txt'
    empty.write_text('  ')
    with pytest.raises(EmptyDocument):
        load_document(empty)
