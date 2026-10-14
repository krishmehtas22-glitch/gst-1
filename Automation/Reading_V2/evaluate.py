"""Offline comparison report. Never generate XML, update caches, or call AI."""
from pathlib import Path
from datetime import datetime
import argparse
import json
import csv
import sys
import os
from .reader import read_invoice,equal,ai_input,CORE
from Common_Rules.extraction import parse_text,text_from_pdf

EXCLUDED={'.invoice_app','.git','.venv','.build-venv','dist','build','__pycache__','node_modules'}


def csv_value(value):
    return "'"+value if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')) else value


def discover_pdfs(folder):
    folder=Path(folder).resolve()
    if folder.is_file():return [folder] if folder.suffix.lower()=='.pdf' else []
    return sorted(p for p in folder.rglob('*') if p.is_file() and p.suffix.lower()=='.pdf'
                  and not any(part in EXCLUDED for part in p.relative_to(folder).parts[:-1]))


def compare(paths,output,emit_ai_input=False,progress=print):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=False)
    rows=[];models=[]
    for index,path in enumerate(paths,1):
        path=Path(path);progress(f'Reading {index}/{len(paths)}: {path.name}')
        entry={'path':str(path.resolve()),'file':path.name}
        try:
            baseline=parse_text(text_from_pdf(path))
            result=read_invoice(path,baseline)
            filename=f'{index:04d}_{result["source_sha256"][:16]}.json'
            (output/filename).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            differences={field:{'current':baseline.get(field),'candidate':result['invoice'].get(field)}
                for field in CORE if baseline.get(field)!=result['invoice'].get(field)
                and not equal(baseline.get(field),result['invoice'].get(field),field)}
            entry.update(result_file=filename,source_sha256=result['source_sha256'],
                pages=len(result['document']['pages']),word_count=sum(len(p['tokens']) for p in result['document']['pages']),
                current_item_count=len(baseline.get('items',[])),candidate_item_count=len(result['invoice'].get('items',[])),
                positioned_item_count=sum(len(t['rows']) for t in result['table_candidates']),
                positioned_fields=sum(bool(e) and e['origin']=='positioned_label' for e in result['field_evidence'].values()),
                legacy_fallback_fields=result['legacy_fallback_fields'],conflicts=result['conflicts'],
                differences=differences,review_required=result['review_required'],warnings=result['warnings'])
            if emit_ai_input:
                try:(output/filename.replace('.json','_ai_input.json')).write_text(ai_input(result),encoding='utf-8')
                except ValueError as exc:entry['ai_input_note']=str(exc)
            models.append({'name':path.name,'source_pdf':path.resolve().as_uri(),'baseline':{k:baseline.get(k) for k in CORE},
                'candidate':{k:result['invoice'].get(k) for k in CORE},'evidence':result['field_evidence'],
                'checks':result['checks'],'conflicts':result['conflicts'],'review_required':result['review_required'],
                'fallback':result['legacy_fallback_fields'],'pages':[{'number':p['number'],'width':p['width'],'height':p['height'],
                    'words':[[t['id'],t['text'],*[round(v,5) for v in t['box']]] for t in p['tokens']]} for p in result['document']['pages']]})
        except Exception as exc:
            entry['error']=type(exc).__name__+': '+str(exc)
            models.append({'name':path.name,'source_pdf':path.resolve().as_uri(),
                'baseline':{},'candidate':{},'evidence':{},'checks':[],
                'conflicts':[{'read_error':entry['error']}],'review_required':True,'fallback':[],'pages':[]})
        rows.append(entry)
    summary={'mode':'shadow_only','baseline':'Current local PDF reader; no AI requests or saved results modified.',
        'evaluated':len(rows),'succeeded':sum('error' not in r for r in rows),
        'failed':sum('error' in r for r in rows),'review_required':sum(r.get('review_required',False) for r in rows),
        'documents_with_positioned_tables':sum(r.get('positioned_item_count',0)>0 for r in rows),
        'documents_with_field_differences':sum(bool(r.get('differences')) for r in rows),
        'accuracy_measured':False,'accuracy_note':'Coverage and agreement are not accuracy. Independently reviewed ground truth is required.',
        'no_ai_requests':True,'no_tally_imports':True,'active_reader_changed':False,'documents':rows}
    (output/'Summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    with (output/'Comparison.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['File','Current items','Candidate items','Positioned items','Positioned fields','Review required','Error'])
        for r in rows:writer.writerow([csv_value(value) for value in [r['file'],r.get('current_item_count'),r.get('candidate_item_count'),r.get('positioned_item_count'),r.get('positioned_fields'),r.get('review_required'),r.get('error','')]])
    template=(Path(__file__).parent/'report.html').read_text(encoding='utf-8')
    data=json.dumps({'summary':{k:v for k,v in summary.items() if k!='documents'},'models':models},ensure_ascii=False)
    # Invoice text can contain markup. Never place unescaped source text in HTML.
    data=data.replace('&','\\u0026').replace('<','\\u003c').replace('>','\\u003e')
    (output/'Report.html').write_text(template.replace('/*REPORT_DATA*/{}',data),encoding='utf-8')
    return summary


def main():
    parser=argparse.ArgumentParser(description='Compare a separate position-aware reader with the current local reader. No AI/XML/Tally writes.')
    parser.add_argument('folder',type=Path,help='PDF or invoice parent folder')
    parser.add_argument('--output',type=Path,help='New report folder; existing folders are never overwritten')
    parser.add_argument('--ai-input',action='store_true',help='Save proposed structured AI input without making a request')
    parser.add_argument('--open-report',action='store_true',help='Open the local comparison report on Windows')
    args=parser.parse_args()
    paths=discover_pdfs(args.folder)
    if not paths:parser.error('No PDFs found in the selected location.')
    parent=args.folder if args.folder.is_dir() else args.folder.parent
    output=args.output or parent/'.invoice_app'/'reading_v2_evaluations'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    result=compare(paths,output,args.ai_input)
    print(f'Compared {result["evaluated"]} PDFs; {result["failed"]} failures. Report: {output.resolve()/"Report.html"}')
    print('Comparison only. Accuracy is not yet measured. No AI requests, XML generation or Tally imports sent.')
    if args.open_report and sys.platform=='win32':os.startfile(str(output.resolve()/'Report.html'))
    if result['failed']:raise SystemExit(1)


if __name__=='__main__':main()
