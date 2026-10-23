"""Split-safe evaluation. Mock results are explicitly not Gemini performance evidence."""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from co_extract.confidence import features, fit_dev, score_orders
from co_extract.ingest import load_document
from co_extract.llm import GeminiClient, MockLLM
from co_extract.normalize import normalize_order
from co_extract.pipeline import Pipeline
from co_extract.schema import from_llm
from co_extract.baseline_regex import baseline
from eval.metrics import FIELDS, accept_curve, align_orders, ece, equal, flatten, line_item_f1, summarize

ROOT=Path(__file__).resolve().parents[1]
RESULTS=ROOT/'eval'/'results'


def read_manifest() -> list[dict]:
    """Load generated manifest once, without test split in calibration code."""
    return json.loads((ROOT/'data/synthetic/manifest.json').read_text())


def calibrate(client, manifest: list[dict], path: Path) -> dict:
    """Fit field logistic model and select document acceptance on DEV ONLY."""
    dev = [row for row in manifest if row['split']=='dev']
    rows: list[list[float]]=[]; labels: list[int]=[]
    pipeline = Pipeline(client)
    docs = []
    for row in dev:
        doc=load_document(ROOT/row['source'])
        result=pipeline.run(ROOT/row['source'])
        truth=json.loads((ROOT/row['truth']).read_text())['orders']
        matched=align_orders(result.orders,truth)
        docs.append((doc,result,matched))
        for order, ref in matched:
            if order is None:
                continue
            for field in FIELDS:
                item=getattr(order,field)
                if item.value is None:
                    continue
                expectation=(ref or {}).get(field)
                normalized=item.normalized_value if item.normalized_value is not None else (
                    None if 'ambiguous_date' in item.flags else item.value)
                rows.append(features(item,doc))
                labels.append(int(equal(field,normalized,expectation)))
    params=fit_dev(rows,labels,client.model_id)
    if params.get('calibrated'):
        document_scores=[]
        for doc,result,matched in docs:
            score=score_orders(result.orders,doc,params=params)
            correct=bool(matched) and all(
                order is not None and ref is not None and all(
                    equal(name,getattr(order,name).normalized_value if getattr(order,name).normalized_value is not None else
                          (None if 'ambiguous_date' in getattr(order,name).flags else getattr(order,name).value),
                          ref.get(name)) for name in ('change_order_number','total_amount','date_issued','owner','contractor'))
                for order,ref in matched)
            clean=not result.validation_report and 'possible_prompt_injection' not in result.warnings
            document_scores.append((score,int(correct and clean)))
        candidates=[]
        for t in sorted(set([0.0,1.0]+[round(s,4) for s,_ in document_scores])):
            eligible=[label for score,label in document_scores if score>=t]
            if eligible and sum(eligible)/len(eligible)>=.95:
                candidates.append(t)
        params['review_threshold']=min(candidates,default=1.01)
        params['dev_document_autoaccepted']=sum(s>=params['review_threshold'] for s,_ in document_scores)
    path.write_text(json.dumps(params,indent=2))
    return params


def run(*, mock: bool = True) -> dict:
    """Perform DEV-only tuning, frozen held-out TEST scoring and transparent ablation notes."""
    RESULTS.mkdir(parents=True,exist_ok=True)
    manifest=read_manifest()
    client=MockLLM() if mock else GeminiClient()
    params_path=RESULTS/('mock_confidence_params.json' if mock else 'gemini_confidence_params.json')
    params=calibrate(client,manifest,params_path)
    pipeline=Pipeline(client,calibration_path=params_path)
    rows=[]; baseline_rows=[]; pairs_all=[]; documents=[]
    by_tag=defaultdict(list); by_mode=defaultdict(list); by_quality=defaultdict(list)
    latencies=[]; cost=[]; records=[]; baseline_pairs=[]
    for spec in [r for r in manifest if r['split']=='test']:
        target=ROOT/spec['source']
        result=pipeline.run(target)
        truth=json.loads((ROOT/spec['truth']).read_text())['orders']
        pairs=align_orders(result.orders,truth)
        doc_rows=flatten(pairs)
        rows+=doc_rows; pairs_all+=pairs
        source=load_document(target)
        baseline_orders=[normalize_order(from_llm(o)) for o in baseline(source.pages).orders]
        base_pairs=align_orders(baseline_orders,truth)
        baseline_rows+=flatten(base_pairs)
        baseline_pairs+=base_pairs
        by_tag[spec['tags'][0]]+=doc_rows
        by_mode[spec['mode']]+=doc_rows
        by_quality["ocr" if any(p.source=="ocr" for p in source.pages) else "native_text"]+=doc_rows
        latencies.append(result.metadata.latency_ms)
        cost.append(result.metadata.cost_estimate or 0.0)
        documents.append((spec,result,pairs))
        records.append({'id':spec['id'],'mode':spec['mode'],'tags':spec['tags'],
                        'needs_review':result.needs_review,'confidence':result.document_confidence,
                        'validation_issues':[x.code for x in result.validation_report],
                        'warnings':result.warnings,'field_metrics':summarize(doc_rows),
                        'wrong_fields':[{'field':r['field'],'predicted':r['predicted'],'expected':r['expected']} for r in doc_rows if r['result'] in ('fp','fn','wrong')]})
    (RESULTS/'raw.json').write_text(json.dumps(records,indent=2,default=str))
    summary=summarize(rows)
    ece_score,buckets=ece(rows)
    baseline_score=summarize(baseline_rows)
    chart=RESULTS/'reliability.png'
    fig,ax=plt.subplots(figsize=(5.3,4.2))
    ax.plot([0,1],[0,1],'--',label='Perfect calibration')
    if buckets:
        ax.scatter([b['confidence'] for b in buckets],[b['accuracy'] for b in buckets],
                   s=[max(12,b['count']*1.2) for b in buckets],label='Held-out TEST bins')
    ax.set(xlabel='Mean computed confidence',ylabel='Observed correctness',xlim=(0,1),ylim=(0,1),
           title='Field reliability (non-null predictions)')
    ax.legend(fontsize=8);fig.tight_layout();fig.savefig(chart,dpi=150);plt.close(fig)
    curve=accept_curve(rows)
    result_summary={'model':client.model_id,'prompt_version':__import__('co_extract.prompts',fromlist=['PROMPT_VERSION']).PROMPT_VERSION,
                    'test_documents':len(documents),'dev_documents':20,'field_metrics':summary,
                    'line_item_f1':line_item_f1(pairs_all),'baseline_line_item_f1':line_item_f1(baseline_pairs),
                    'per_field':{name:summarize([r for r in rows if r['field']==name]) for name in FIELDS},
                    'baseline_metrics':baseline_score,
                    'ece':ece_score,'reliability_bins':buckets,'field_accept_curve':curve,
                    'by_tag':{k:summarize(v) for k,v in by_tag.items()},
                    'by_source':{k:summarize(v) for k,v in by_mode.items()},
                    'by_source_quality':{k:summarize(v) for k,v in by_quality.items()},
                    'p50_latency_ms':statistics.median(latencies),'p95_latency_ms':sorted(latencies)[int(.95*(len(latencies)-1))],
                    'total_cost_estimate':sum(cost),'reviewed':sum(r.needs_review for _,r,_ in documents),
                    'calibration':params}
    # Freeze DEV calibrator, compare actual TEST outputs (mock has no independent stochastic/vision capability).
    if mock:
        ablations = {}
        scenarios = {
            'no_grounding': {'grounding_enabled': False},
            'no_validation_retry': {'validation_retry': False},
            'self_consistency_3': {'self_consistency': 3},
            'vision_bytes': {'vision': True},
        }
        test_specs=[r for r in manifest if r['split']=='test'][:8]  # fixed ablation subset
        for name, opts in scenarios.items():
            ablation_rows=[]; confidences=[]; review_count=0
            for spec in test_specs:
                result=pipeline.run(ROOT/spec['source'],**opts)
                truth=json.loads((ROOT/spec['truth']).read_text())['orders']
                ablation_rows.extend(flatten(align_orders(result.orders,truth)))
                confidences.append(result.document_confidence)
                review_count+=int(result.needs_review)
            ablations[name]={
                'field_f1': summarize(ablation_rows)['f1'],
                'mean_document_confidence': statistics.mean(confidences),
                'review_count': review_count,
                'independent_llm_measurement': False, 'n_documents':len(test_specs),
            }
        result_summary['offline_ablations']=ablations
    (RESULTS/'summary.json').write_text(json.dumps(result_summary,indent=2))
    lines=['# Reproducible held-out TEST evaluation','',f'**Mode:** `{client.model_id}`',
           f'**Prompt version:** `{result_summary["prompt_version"]}`',
           f'**Counts:** 60 training (not used in fit), 20 DEV (calibration only), 40 held-out TEST.', '',
           '> **Interpretation:** MockLLM is a regex heuristic test double, not Gemini. Its scores must not be sold as LLM model accuracy or predictive calibration. The baseline uses the SAME heuristic, so equal numbers are expected.', '',
           '| Test metric | Mock/actual selected model | Regex baseline |','|---|---:|---:|',
           f'| Field precision | {summary["precision"]:.4f} | {baseline_score["precision"]:.4f} |',
           f'| Field recall | {summary["recall"]:.4f} | {baseline_score["recall"]:.4f} |',
           f'| Field F1 | {summary["f1"]:.4f} | {baseline_score["f1"]:.4f} |',
           f'| Correct null rate | {summary["correct_null_rate"] if summary["correct_null_rate"] is not None else "N/A"} | {baseline_score["correct_null_rate"] if baseline_score["correct_null_rate"] is not None else "N/A"} |',
           f'| Hallucination rate | {summary["hallucination_rate"] if summary["hallucination_rate"] is not None else "N/A"} | {baseline_score["hallucination_rate"] if baseline_score["hallucination_rate"] is not None else "N/A"} |',
           f'| Line item matched F1 | {result_summary["line_item_f1"]:.4f} | {result_summary["baseline_line_item_f1"]:.4f} |','',
           f'**ECE on extracted non-null TEST fields:** {ece_score:.4f} (10 fixed bins).',
           f'**Documents marked for review:** {result_summary["reviewed"]}/40.',
           f'**Latency p50/p95:** {result_summary["p50_latency_ms"]:.0f}/{result_summary["p95_latency_ms"]:.0f} ms; **cost estimate:** ${sum(cost):.6f} (assumed prices, not invoices).',
           '',f'![Reliability diagram](reliability.png)','',
           '## Hard-case slices (actual TEST)','', '| Tag | N field rows | F1 |','|---|---:|---:|']
    for key,data in sorted(result_summary['by_tag'].items()):
        lines.append(f'| {key} | {data["n_rows"]} | {data["f1"]:.4f} |')
    lines+=['','## Format slices','','| Format | N field rows | F1 |','|---|---:|---:|']
    for key,data in sorted(result_summary['by_source'].items()):
        lines.append(f'| {key} | {data["n_rows"]} | {data["f1"]:.4f} |')
    lines+=['','## Source-quality slices','','| Source quality | N field rows | F1 |','|---|---:|---:|']
    for key,data in sorted(result_summary['by_source_quality'].items()):
        lines.append(f'| {key} | {data["n_rows"]} | {data["f1"]:.4f} |')
    lines+=['','## Field-level metrics','','| Field | Precision | Recall | F1 |', '|---|---:|---:|---:|']
    for key,data in result_summary['per_field'].items():
        lines.append(f'| {key} | {data["precision"]:.4f} | {data["recall"]:.4f} | {data["f1"]:.4f} |')
    lines+=['','## Threshold and ablations', '',
            f'DEV-fitted: `{params.get("calibrated")}`; threshold `{params.get("review_threshold")}`; DEV training rows `{params.get("dev_size")}`.',
            'Calibration is conditional on a non-null extraction, and may be poorly identified in this tiny synthetic DEV set. A target DEV selective precision is not a real-world guarantee.', '',
            'Mock-only ablations: validation retry, self-consistency (temperature 0.5), and vision-vs-text are **not independently measurable** because MockLLM ignores temperature and the PDF bytes and emits already schema-valid JSON. Turning them on would yield artificial null differences, so no gain is reported.',
            'Grounding check ablation changes confidence/review flags but not extracted field F1. For a real comparison run the live model and write independent raw outputs before calculating deltas.',
            '', '### Auto-accept field coverage vs selective error', '', '| Confidence threshold | Coverage | Error among accepted |', '|---:|---:|---:|']
    for t in curve:
        error = "N/A" if t["error_rate"] is None else format(t["error_rate"], ".4f")
        lines.append(f'| {t["threshold"]:.2f} | {t["coverage"]:.4f} | {error} |')
    if mock:
        lines+=['','### Offline ablation runs (same TEST documents; not Gemini evidence)','',
                '| Variant | Field F1 | Mean document confidence | Review count |',
                '|---|---:|---:|---:|',
                f'| Default (same 8) | {summarize([r for _,_,pairs in documents[:8] for r in flatten(pairs)])["f1"]:.4f} | {statistics.mean([res.document_confidence for _,res,_ in documents[:8]]):.4f} | {sum(res.needs_review for _,res,_ in documents[:8])} |']
        for name,val in result_summary['offline_ablations'].items():
            lines.append(f'| {name} | {val["field_f1"]:.4f} | {val["mean_document_confidence"]:.4f} | {val["review_count"]} |')
        lines.append('All variants were actually executed against the first 8 held-out TEST documents. Identical F1 is expected: MockLLM ignores temperature and PDF bytes; the schema never fails, and grounding affects scoring rather than extraction. Differences in confidence are algorithmic, **not validated gains**.')
    lines+=['','## Evaluation limitations','',
            '- All labeled samples are generated by one template family. This is not an estimate of real construction documentation performance.',
            '- Synthetic references describe explicit fields; omitted/ambiguous fields are intentional. Documents and truth are synthetic.',
            '- No production PDF distribution, annotated handwriting, provider response, real-rate-limit, or provider privacy test is available without external credentials and real labeled documents.',
            '- Numeric cost estimates depend on configurable assumptions and reported token metadata.',
            '- `raw.json` lists document IDs, failures and severity codes for reproducible error analysis.']
    (RESULTS/'report.md').write_text('\n'.join(lines)+'\n')
    return result_summary


if __name__=='__main__':
    print(json.dumps(run(),indent=2))
