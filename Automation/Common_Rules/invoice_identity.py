"""Retain verified local identity when an AI omits it; never overwrite facts."""
from copy import deepcopy
from pathlib import Path
from .source_documents import verify_source


def missing(value):
    token=str(value or '').strip()
    return not token or token.lower() in ('null','none','unknown','not detected') or token.lower().startswith(('buyer unresolved','unread-'))


def recover_missing_identity(root,record,ai,local):
    result=deepcopy(ai)
    if not missing(result.get('number')) and not missing(result.get('buyer_name')):return result
    verify_source(Path(root),record)
    evidence=[]
    if missing(result.get('number')) and not missing(local.get('number')):
        result['number']=local['number'];evidence.append('Invoice number retained from verified local PDF reading because AI omitted it')
    if missing(result.get('buyer_name')) and not missing(local.get('buyer_name')):
        warnings=' '.join(str(w) for w in local.get('extraction_warnings',[])).lower()
        buyer=str(local['buyer_name']).strip()
        seller=str(local.get('seller_name') or '').strip()
        ambiguous=('buyer' in warnings and any(term in warnings for term in ('ambiguous','conflict','differ')))
        if not ambiguous and buyer.casefold()!=seller.casefold():
            result['buyer_name']=local['buyer_name']
            # Keep related role fields with the locally recovered buyer. Existing
            # AI fields always win; no seller/ship-to or cross-invoice substitution.
            for field in ('buyer_gstin','buyer_state','buyer_address','buyer_registration','buyer_country'):
                if missing(result.get(field)) and local.get(field) not in (None,''):result[field]=local[field]
            evidence.append('Buyer retained from verified local PDF reading because AI omitted it')
    if evidence:result['identity_evidence']=evidence
    return result
