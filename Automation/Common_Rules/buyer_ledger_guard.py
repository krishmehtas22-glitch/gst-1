"""Accounting-role checks independent of AI confidence and buyer GSTIN."""
import re


def compact(value):return re.sub(r'[\W_]+','',str(value or '').casefold())


SYSTEM_NAMES={'sales','salesaccount','salesledger','cgst','sgst','igst','cess','roundoff','invoicedifferencesreview'}
PARTY_GROUPS={'sundrydebtors','sundrycreditors'}


def party_conflict(candidate):
    if not candidate:return ''
    name=candidate.get('name','');group=candidate.get('parent','')
    reserved=compact(name) in SYSTEM_NAMES or bool(re.fullmatch(r'(?:cgst|sgst|igst|cess)\d+',compact(name)))
    if reserved:return "Buyer ledger '"+name+"' uses a reserved sales/tax/adjustment name (Under: "+(group or 'missing')+'). Select a correct party ledger in Review buyer ledger.'
    if compact(group) not in PARTY_GROUPS:
        return "Buyer ledger '"+name+"' is Under '"+(group or 'missing')+"', which is not a verified party group. Review buyer ledger; custom subgroup ancestry is not present in this snapshot."
    return ''


def validate_system_roles(masters,catalog,vouchers):
    """A debtor named Sales is unsafe even when a different buyer is selected."""
    used={compact(n.text) for n in vouchers.iter('LEDGERNAME')}
    existing={compact(e['name']):e for e in catalog.values() if e['kind']=='ledgers'}
    for ledger in masters.iter('LEDGER'):
        name=ledger.get('NAME') or ledger.findtext('NAME') or ''
        key=compact(name)
        if key not in SYSTEM_NAMES or key not in used or key not in existing:continue
        target=existing[key];expected=ledger.findtext('PARENT') or ''
        if compact(target['parent'])!=compact(expected):
            raise ValueError("Existing Tally ledger '"+target['name']+"' is Under '"+target['parent']+
                "', but this voucher needs it Under '"+expected+"'. Correct the ledger in Tally and read masters again. Previous XML retained; no ledger was altered.")
