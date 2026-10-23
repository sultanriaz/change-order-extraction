from typer.testing import CliRunner
from co_extract.cli import app
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
runner=CliRunner()

def test_offline_extract_cli(tmp_path):
    response=runner.invoke(app,['extract',str(ROOT/'examples/sample.pdf'),'--out',str(tmp_path),'--mock'])
    assert response.exit_code==0,response.output
    assert (tmp_path/'sample.json').exists()
    assert 'needs_review' in response.output

def test_smoke_without_key(monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY',raising=False)
    response=runner.invoke(app,['smoke'])
    assert response.exit_code==2
