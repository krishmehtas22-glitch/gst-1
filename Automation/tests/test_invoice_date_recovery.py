from copy import deepcopy
from pathlib import Path
import json,shutil
import xml.etree.ElementTree as ET
import pytest
from Common_Rules.invoice_dates import normalize_date,labelled_date,recover_date
from Common_Rules.desktop import inspect_sources,process_sources
from Common_Rules.tally_review_export import enable,export_all
from Common_Rules.engine import read_json,write_json


@pytest.mark.parametrize('raw',[
    '2026-10-13','20261013','13/10/2026','13-10-2026','13.10.2026',
    '13/10/26','13-10-26','13.10.26','2026/10/13','13-Oct-26',
    '13 October 2026','13th October, 2026','Tuesday, 13 Oct 2026',
    'Oct 13, 2026','2026-10-13T00:00:00Z','2026-10-13 12:00:00+05:30',
    'Invoice Date: 13-Oct-2026','13102026','10/13/2026',
])
def test_supported_formats_write_same_real_calendar_date(raw):
    assert normalize_date(raw)=='2026-10-13'


@pytest.mark.parametrize('raw',['2026-02-30','31/04/26','not printed','20261313','2026-13-13','',None])
def test_invalid_missing_date_never_becomes_today(raw):
    assert normalize_date(raw) is None


def test_invoice_date_priority_not_due_or_shipping():
    assert labelled_date('Due Date: 15/10/26\nInvoice Date: 13/10/26\nShipping date: 14/10/26')=='2026-10-13'
    assert labelled_date('Invoice Date: unavailable  Due Date: 15/10/26') is None
    assert labelled_date('Due Date: 15/10/26') is None
    assert labelled_date('Invoice Date:\n13-Oct-26')=='2026-10-13'
    assert labelled_date('Invoice Date: 13/10/26\nInvoice Date: 14/10/26') is None


def setup(root):
    folder=root/'Client';folder.mkdir()
    shutil.copy2(Path(__file__).parent/'fixtures/client23/Sales_Invoice_126_INTRA.pdf',folder/'invoice.pdf')
    return inspect_sources(root)[0]


def test_cached_source_recovers_null_ai_date_without_touching_parties_or_items(tmp_path):
    record=setup(tmp_path)
    before=deepcopy(record['invoice']);record['invoice']['date']=None
    cache=tmp_path/'.invoice_app/extraction'/(record['digest']+'.json')
    saved=read_json(cache);saved['invoice']['date']='2026-10-15'
    saved['text']='Invoice Date: 13-Oct-26\nDue Date: 15-Oct-26'
    write_json(cache,saved)
    assert recover_date(tmp_path,record)=='2026-10-13'
    after=record['invoice']
    for key in before:
        if key!='date':assert after[key]==before[key]
    assert after['date_raw'] is None and 'verified' in after['date_evidence']
    enable(tmp_path,'Client')
    # Recovered date normalizes a short-year AI/retained review date too.
    record['invoice']['date']='13-Oct-26'
    export_all(tmp_path,[record],True)
    voucher=ET.parse(Path(record['output_path'])/'Sales_Vouchers.xml').find('.//VOUCHER')
    assert voucher.findtext('DATE')==voucher.findtext('EFFECTIVEDATE')=='20261013'
    assert record['invoice']['items']==before['items']


def test_actual_pdf_recovers_missing_date_when_no_cache_is_present(tmp_path):
    record=setup(tmp_path);expected=record['invoice']['date']
    cache=tmp_path/'.invoice_app/extraction'/(record['digest']+'.json');cache.unlink()
    record['invoice']['date']='unreadable'
    assert recover_date(tmp_path,record)==expected


def test_changed_source_cache_cannot_supply_date(tmp_path):
    record=setup(tmp_path)
    record['invoice']['date']=None
    Path(record['path']).write_bytes(b'changed')
    assert recover_date(tmp_path,record) is None
    assert record['invoice']['date'] is None


def test_short_year_export_date_does_not_change_existing_seller_quantity_or_guid(tmp_path):
    record=setup(tmp_path);record['invoice']['date']='13-Oct-26'
    before=deepcopy(record['invoice'])
    export_all(tmp_path,[record],True)
    first=ET.parse(Path(record['output_path'])/'Sales_Vouchers.xml')
    guid=first.findtext('.//GUID')
    export_all(tmp_path,[record],True)
    second=ET.parse(Path(record['output_path'])/'Sales_Vouchers.xml')
    assert second.findtext('.//GUID')==guid
    assert second.findtext('.//DATE')=='20261013'
    for key in before:
        if key!='date':assert record['invoice'][key]==before[key]
    assert record['invoice']['seller_name']==before['seller_name']


def test_cached_due_date_is_not_promoted_to_invoice_date(tmp_path,monkeypatch):
    record=setup(tmp_path);record['invoice']['date']=None
    cache=tmp_path/'.invoice_app/extraction'/(record['digest']+'.json')
    saved=read_json(cache);saved['invoice']['date']='2026-10-15';saved['text']='Due Date: 15-Oct-26'
    write_json(cache,saved)
    import Common_Rules.extraction as extraction
    monkeypatch.setattr(extraction,'text_from_pdf',lambda path:'Due Date: 15-Oct-26')
    assert recover_date(tmp_path,record) is None
