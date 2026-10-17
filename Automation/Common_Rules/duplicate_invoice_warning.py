"""Advisory invoice-number/date comparison; no reading, deletion or blocking."""
from collections import defaultdict
from .invoice_dates import normalize_date

PREFIX='Duplicate invoice: '


def warnings(records):
    groups=defaultdict(list)
    for index,record in enumerate(records):
        if record.get('listing_only'):continue
        invoice=record.get('invoice') or {}
        number=' '.join(str(invoice.get('number') or '').split()).casefold()
        date=normalize_date(invoice.get('date'))
        if not number or not date:continue
        # Client is an isolation boundary. The business comparison itself uses
        # only invoice number/date, never seller identity, amounts or PDF bytes.
        groups[(record.get('client'),number,date)].append(index)
    result={}
    for (_,_,date),indices in groups.items():
        if len(indices)<2:continue
        number=str(records[indices[0]]['invoice']['number']).strip()
        notice=(PREFIX+'number '+number+' and date '+date+' appear '+str(len(indices))+
                ' times in this client. Files are retained; you may continue after review.')
        for index in indices:result[index]=notice
    return result


def annotate(records):
    found=warnings(records)
    for index,record in enumerate(records):
        # Advisory metadata stays outside invoice facts and blocking errors.
        record.pop('duplicate_warning',None)
        for field in ('notices','tally_review_warnings'):
            if field in record:record[field]=[n for n in record[field] if not str(n).startswith(PREFIX)]
        if index in found:
            record['duplicate_warning']=found[index]
            record.setdefault('notices',[]).append(found[index])
    return found
