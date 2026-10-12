"""Recover missing seller names from verified local identities, never buyer names."""
from pathlib import Path
import json
from .party_evidence import legal_name_key


def restore_known_supplier(root,record,demo):
    invoice=record['invoice']
    if invoice.get('seller_name'):return
    if any(any(word in str(error).casefold() for word in ('conflict','ambiguous seller')) for error in invoice.get('extraction_warnings',[])):return
    seller=str(invoice.get('seller_gstin') or '').upper()
    candidates=[];bound=None
    routing=Path(root)/'.invoice_app/routing'/(str(record.get('digest'))+'.json')
    try:
        if routing.exists():bound=json.loads(routing.read_text()).get('company')
        for path in (Path(root)/'.invoice_app/companies').glob('*/client.json'):
            config=json.loads(path.read_text())
            if bool(config.get('demo_only'))!=bool(demo):continue
            source=config.get('source_seller_gstin')
            if not config.get('source_seller_name'):continue
            if seller and seller!=source:continue
            proven=path.parent.name==bound
            if not seller and not proven:continue
            if demo and not proven and legal_name_key(invoice.get('seller_name_candidate',''))!=legal_name_key(config['source_seller_name']):continue
            candidates.append(config)
    except (OSError,ValueError,TypeError):return
    names={config['source_seller_name'] for config in candidates}
    if len(names)==1:
        invoice['seller_name']=next(iter(names));invoice['seller_name_source']='Previously verified supplier identity'
        if not seller and bound:invoice['seller_gstin']=candidates[0]['source_seller_gstin']
