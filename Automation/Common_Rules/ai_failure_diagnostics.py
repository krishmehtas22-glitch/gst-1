"""Keep provider failure evidence visible without treating fallback as success."""


def prior_failure(root,record):
    """Previous errors are evidence only, never extraction/review approval."""
    from pathlib import Path
    from .engine import read_json
    path=Path(root)/'.invoice_app'/'AI_First_Last_Run.json'
    try:
        sources=read_json(path).get('sources',[])
        for row in sources:
            if (row.get('client'),row.get('digest'),row.get('path'))==(record.get('client'),record.get('digest'),record.get('path')):
                return {k:row[k] for k in ('ai_failure_provider','ai_failure_reason') if isinstance(row.get(k),str)}
    except (ValueError,OSError,KeyError,TypeError):pass
    return {}


def failure_details(answer,primary,stopped=False):
    if answer.get('status') in ('extracted','approved_review'):return {}
    attempts=answer.get('attempts') or []
    reasons=[]
    for attempt in attempts:
        if not isinstance(attempt,dict):continue
        reason=attempt.get('error')
        if isinstance(reason,str) and reason.strip():
            message=str(attempt.get('provider') or primary)+': '+' '.join(reason.split())[:900]
            if message not in reasons:reasons.append(message)
    if not reasons and isinstance(answer.get('error'),str) and answer['error'].strip():
        reasons.append(' '.join(answer['error'].split())[:900])
    if not reasons:
        reasons.append('AI processing was stopped before this invoice completed.' if stopped else
                       'No completed AI read is available. The provider did not return a recorded failure reason; check the selected provider and its last batch report.')
    return {'ai_failure_provider':primary,'ai_failure_reason':' | '.join(reasons[-3:])}


def recovery_instruction(field):
    if field=='AI extraction':
        return ('Cancel import, select the affected invoice and use Analyse with your chosen provider after resolving the error above. '
                'Alternatively, Edit invoice, compare every field with the source, correct the missing values, and Save changes to XML to record a human review. '
                'Then reopen Import. Import anyway cannot approve an unreviewed extraction.')
    if field=='Saved invoice review':return 'Edit this invoice and save a new review against its current source; do not reuse a mismatched saved review.'
    if field=='Source invoice':return 'Restore the exact source or explicitly process the changed file, then prepare fresh XML.'
    if field=='Tally snapshot':return 'Refresh and select the destination company master snapshot, then prepare fresh XML.'
    return 'Open the source to compare. Edit invoice to correct it, or acknowledge the listed issues and import the unchanged XML.'
