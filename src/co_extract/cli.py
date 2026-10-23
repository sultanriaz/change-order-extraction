"""Typer CLI for extraction, fixture generation, evaluation, and one-call live smoke."""
from __future__ import annotations

import json
import os
from pathlib import Path

import typer
from rich.console import Console

from co_extract.config import Settings
from co_extract.confidence import score_orders
from co_extract.ingest import load_document
from co_extract.llm import GeminiClient, MockLLM, ModelError
from co_extract.normalize import normalize_order
from co_extract.pipeline import Pipeline
from co_extract.prompts import PROMPT_VERSION, page_prompt
from co_extract.schema import DocumentResult, LLMOutput, RunMetadata, from_llm
from co_extract.validate import validate_order

app = typer.Typer(help='Evidence-grounded change-order extraction (human-review-first).', no_args_is_help=True)
console = Console(stderr=True)
SUPPORTED = {'.pdf','.txt','.md','.png','.jpg','.jpeg'}


def _client(mock: bool = False):
    """Make offline fallback explicit, never call it Gemini."""
    if mock or not os.getenv('GEMINI_API_KEY'):
        console.print('[yellow]OFFLINE HEURISTIC MODE: MockLLM != Gemini; no model accuracy inferred.[/yellow]')
        return MockLLM()
    try:
        return GeminiClient()
    except ModelError as exc:
        console.print(f'[red]{exc}[/red]')
        raise typer.Exit(2) from exc


@app.command('extract')
def extract_cli(source: Path = typer.Argument(..., help='PDF/image/text file or directory'),
                out: Path = typer.Option(Path('out'), '--out', help='JSON output directory'),
                mock: bool = typer.Option(False, '--mock', help='Force clearly labeled offline heuristic'),
                self_consistency: int = typer.Option(1, '--self-consistency', min=1, max=5),
                no_cache: bool = typer.Option(False, '--no-cache'),
                vision: bool = typer.Option(False, '--vision', help='Send OCR PDF bytes to Gemini too')) -> None:
    """Process a document or batch, preserving safe failure results."""
    if not source.exists():
        console.print('[red]Input not found[/red]')
        raise typer.Exit(2)
    files = sorted(p for p in source.rglob('*') if p.is_file() and p.suffix.lower() in SUPPORTED) if source.is_dir() else [source]
    if not files:
        console.print('[red]No supported files found[/red]')
        raise typer.Exit(2)
    out.mkdir(parents=True,exist_ok=True)
    pipe = Pipeline(_client(mock), calibration_path=Path('eval/results/mock_confidence_params.json') if mock else None)
    results=pipe.batch(files,self_consistency=self_consistency,use_cache=not no_cache,vision=vision)
    for src,result in zip(files,results):
        dest=out/(src.stem+'.json')
        dest.write_text(result.model_dump_json(indent=2),encoding='utf-8')
        console.print(f'{src.name} -> {dest} | orders={len(result.orders)} | needs_review={result.needs_review}')
    if len(files)==1:
        typer.echo(results[0].model_dump_json(indent=2))


@app.command('schema')
def schema_cli(out: Path = typer.Option(Path('docs/schema.json'),'--out')) -> None:
    """Export Pydantic internal result JSON Schema."""
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(DocumentResult.model_json_schema(),indent=2))
    console.print(f'Schema saved to {out}')


@app.command('generate-data')
def generate_data_cli() -> None:
    """Recreate deterministically seeded fixtures (overwrites generated corpus)."""
    from scripts.generate_synthetic import generate
    console.print(generate())


@app.command('eval')
def eval_cli(live: bool = typer.Option(False,'--live',help='Use paid Gemini calls, not offline mock')) -> None:
    """Fit on DEV, evaluate held-out TEST and regenerate report/plot."""
    from eval.run_eval import run
    console.print(json.dumps(run(mock=not live),indent=2))


@app.command('smoke')
def smoke_cli(sample: Path = typer.Option(Path('examples/sample.pdf'),'--sample')) -> None:
    """Perform exactly one primary live Gemini generation, validate, and print review metadata."""
    try:
        client=GeminiClient()
        doc=load_document(sample)
        reply=client.complete(page_prompt(doc.pages),source_hash=doc.source_hash,use_cache=False)
        output=LLMOutput.model_validate_json(reply.text)
        orders=[normalize_order(from_llm(order)) for order in output.orders]
        issues=[issue for order in orders for issue in validate_order(order)]
        confidence=score_orders(orders,doc)
        result=DocumentResult(orders=orders,document_confidence=confidence,
                              needs_review=confidence<Settings.from_env().review_threshold or bool(issues),
                              validation_report=issues,
                              metadata=RunMetadata(model=client.model_id,prompt_version=PROMPT_VERSION,
                                                   source_hash=doc.source_hash,latency_ms=reply.latency_ms,
                                                   input_tokens=reply.input_tokens,output_tokens=reply.output_tokens))
        typer.echo(result.model_dump_json(indent=2))
    except Exception as exc:
        console.print(f'[red]Live smoke failed ({type(exc).__name__}). Verify GEMINI_API_KEY, model ID and SDK setup.[/red]')
        raise typer.Exit(2) from exc


if __name__ == '__main__':
    app()
