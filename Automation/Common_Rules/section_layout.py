"""Read explicit party/metadata panels without mixing their wrapped columns.

Names need an explicit anchor: a seller signatory matching the seller panel,
or a buyer name repeated at the start of its address. Missing anchors require
review. Amounts never determine tax treatment; a single item's component rates
can be recovered only from its reconciled, explicit tax summary.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
import re

from .accounting import cents, money, STATES, TAXES, EXPORT_COUNTRIES


def parse_section_layout(text, headers):
    raw_lines = [line for line in text.splitlines() if line.strip()]
    lines = [line.strip() for line in raw_lines]
    seller_heading = r'(?:SELLER|SUPPLIER) DETAILS\s{2,}INVOICE (?:DETAILS|INFORMATION)'
    buyer_heading = r'(?:BILL TO / BUYER|BUYER DETAILS|RECIPIENT DETAILS)\s{2,}SUPPLY DETAILS'
    seller_index = next((i for i,line in enumerate(lines) if re.fullmatch(seller_heading,line,re.I)),None)
    if seller_index is None:
        return None
    warnings = []
    inv = {'source_layout':'section_panels_v1','items':[],'extraction_warnings':warnings}
    buyer_index = next((i for i,line in enumerate(lines) if re.fullmatch(buyer_heading,line,re.I)),None)
    if buyer_index is None:
        warnings.append('Buyer/supply panel headings missing; review party roles')
        return inv
    def column_keys(line):
        return [next((key for key,aliases in headers.items() if cell.casefold() in aliases),None)
                for cell in re.split(r'\s{2,}',line)]

    table_index = next((i for i,line in enumerate(lines) if i>buyer_index and
                        all(key in column_keys(line) for key in ('name','hsn','quantity','rate','value'))),None)
    if table_index is None:
        warnings.append('Item table heading missing; review item columns')
        return inv

    def panels(start,end):
        left,right = [],[]
        rows=raw_lines[start+1:end]
        boundaries=[]
        for line in rows:
            gap=re.search(r'(?<=\S)\s{2,}(?=\S)',line)
            if gap:
                boundaries.append(gap.end())
        boundary=min(boundaries) if boundaries else None
        for line in rows:
            gap=re.search(r'(?<=\S)\s{2,}(?=\S)',line)
            if gap:
                left.append(line[:gap.start()].strip());right.append(line[gap.end():].strip())
            elif boundary is not None:
                # A wrapped panel can continue after the other column ends.
                (right if len(line)-len(line.lstrip())>=boundary else left).append(line.strip())
            else:
                warnings.append('Party/metadata columns have no readable boundary')
        return ' '.join(left),' '.join(right)

    seller,metadata = panels(seller_index,buyer_index)
    buyer,supply = panels(buyer_index,table_index)
    labels = ('Invoice No','Invoice Number','Invoice Date','Currency','Reverse Charge',
              'GSTIN','State Code','Buyer GSTIN','Ship To','Place of Supply','Supply',
              'Seller State','Dispatch From')
    label_pattern = '|'.join(re.escape(label) for label in sorted(labels,key=len,reverse=True))

    def field(block,label):
        matches=list(re.finditer(r'(?:^|\s)('+label_pattern+r')\s*:\s*',block,re.I))
        values=[block[match.end():matches[i+1].start() if i+1<len(matches) else len(block)]
                for i,match in enumerate(matches) if match[1].casefold()==label.casefold()]
        values = list(dict.fromkeys(v.strip() for v in values if v.strip()))
        if len(values)>1:
            warnings.append('Ambiguous '+label+' in panel')
        return values[0] if len(values)==1 else None

    inv['number'] = field(metadata,'Invoice No') or field(metadata,'Invoice Number')
    date = field(metadata,'Invoice Date')
    try:
        inv['date'] = datetime.strptime(date or '', '%d/%m/%Y').date().isoformat()
    except ValueError:
        warnings.append('Invoice date needs review')
    inv['currency'] = field(metadata,'Currency')
    if inv['currency']!='INR' or (field(metadata,'Reverse Charge') or '').casefold()!='no':
        warnings.append('Currency/reverse charge treatment needs review')
    inv['seller_gstin'] = field(seller,'GSTIN')
    inv['seller_state'] = field(seller,'State Code')
    printed_seller_state=field(supply,'Seller State')
    if printed_seller_state:
        state_match=re.fullmatch(r'(.+?)\s*\((\d{2})\)',printed_seller_state)
        if not state_match or state_match[2]!=inv.get('seller_state') or STATES.get(state_match[2],'').casefold()!=state_match[1].strip().casefold():
            warnings.append('Seller state labels conflict; review seller identity')
    # The footer explicitly names the seller; corroborate it inside that panel.
    names = list(dict.fromkeys(re.findall(r'^For\s+(.+?)\s*[-–]\s*Authori[sz]ed Signatory\s*$',text,re.I|re.M)))
    if len(names)==1 and seller.startswith(names[0]+' '):
        inv['seller_name'] = names[0]
        inv['seller_address'] = re.split(r'\bGSTIN\s*:',seller[len(names[0]):],maxsplit=1,flags=re.I)[0].strip()
    else:
        warnings.append('Seller name/address boundary needs review; signatory does not identify one matching seller')
    buyer_gstin = field(buyer,'Buyer GSTIN')
    if buyer_gstin and buyer_gstin.casefold() in ('urp / unregistered','unregistered','urp / not applicable'):
        inv['buyer_gstin']=''
        inv['buyer_registration']='Unregistered'
    else:
        inv['buyer_gstin']=buyer_gstin
    party = re.split(r'\bBuyer GSTIN\s*:',buyer,maxsplit=1,flags=re.I)[0].strip()
    repeated = re.match(r'^(.+?)\s+\1(?=,|\s)',party)
    if repeated:
        inv['buyer_name']=repeated[1]
        inv['buyer_address']=party[len(repeated[1]):].strip()
    else:
        warnings.append('Buyer name/address boundary needs review; no separate name anchor')
    treatment = (field(supply,'Supply') or '').upper()
    pos = field(supply,'Place of Supply') or ''
    if treatment in ('EXPORT LUT','EXPORT IGST'):
        inv['supply']='EXPORT'
        inv['classification']='export_lut' if treatment=='EXPORT LUT' else 'export_igst'
        inv['export_mode']='LUT_without_payment' if treatment=='EXPORT LUT' else 'with_payment_of_IGST'
        inv['place_of_supply']='Outside India'
        country = re.sub(r'\s*\([^()]*\)$','',pos).strip()
        inv['buyer_country']=EXPORT_COUNTRIES.get(country.casefold(),country)
        inv['buyer_state']='Outside India'
        corroboration = (r'Export under LUT without payment of integrated tax' if treatment=='EXPORT LUT'
                         else r'Export with payment of integrated tax')
        if not re.search(corroboration,text,re.I):
            warnings.append('Export mode conflicts with or lacks explicit export remarks')
        shipping = re.search(r'Port of loading:\s*(.*?)\.\s*Shipping\s+Bill:\s*([^\n.]+)',text,re.I)
        if shipping:
            inv['shipping_bill_port']=shipping[1]+'; '+shipping[2]
    else:
        inv['supply']=treatment
        inv['classification'] = 'taxable' if treatment in ('INTRA','INTER') else 'exempt' if treatment=='EXEMPT' else None
        state = re.sub(r'\s*\([^()]*\)$','',pos).strip()
        inv['place_of_supply']=next((code for code,name in STATES.items() if name.casefold()==state.casefold()),state)
        if not inv.get('buyer_gstin'):
            inv['buyer_state']=inv['place_of_supply']
        if treatment=='EXEMPT' and re.search(r'exempt\s*/\s*nil[- ]rated',text,re.I):
            warnings.append('Remarks say exempt / nil-rated; confirm classification in Review')
    summary_index = next((i for i,line in enumerate(lines) if re.fullmatch(r'TAX SUMMARY\s{2,}AMOUNT',line,re.I)),None)
    if summary_index is None:
        warnings.append('Explicit tax summary missing')
        return inv
    summary_labels={'Taxable Value':'taxable','Invoice Total':'total','CGST':'cgst','SGST':'sgst','IGST':'igst'}
    for line in lines[summary_index+1:]:
        matched=re.fullmatch(r'(Taxable Value|Invoice Total|CGST|SGST|IGST)\s{2,}(INR [\d,.]+)',line,re.I)
        if matched:
            key=next(value for label,value in summary_labels.items() if label.casefold()==matched[1].casefold())
            value=str(cents(matched[2]))
            if key in inv and inv[key]!=value:
                warnings.append('Ambiguous '+key+' total')
            else:
                inv[key]=value
    columns=column_keys(lines[table_index])
    if any(key is None for key in columns) or not all(key in columns for key in ('name','hsn','quantity','unit','rate','value')):
        warnings.append('Unrecognized item columns need review')
    else:
        for line in lines[table_index+1:summary_index]:
            row=re.split(r'\s{2,}',line)
            if len(row)!=len(columns):
                warnings.append('Wrapped or incomplete item row needs review')
                continue
            item=dict(zip(columns,row))
            for key in ('quantity','rate','value'):
                try:
                    item[key]=format(money(item[key]),'f')
                except (ValueError,InvalidOperation):
                    warnings.append('Invalid item '+key)
            inv['items'].append(item)
    # A multi-item summary cannot establish each item's GST rate.
    if len(inv['items'])==1 and all(key in inv for key in ('taxable',*TAXES)):
        item=inv['items'][0]
        try:
            value=money(item['value'])
            if value<=0 or cents(value)!=cents(inv['taxable']):
                raise ValueError('Single item does not reconcile to taxable summary')
            for tax in TAXES:
                rate=(money(inv[tax])*100/value).quantize(Decimal('.01'))
                if cents(value*rate/100)!=cents(inv[tax]):
                    raise ValueError('Summary cannot establish an exact item '+tax.upper()+' rate')
                if tax+'_rate' in item and money(item[tax+'_rate'])!=rate:
                    raise ValueError('Printed item '+tax.upper()+' rate conflicts with summary')
                if tax+'_rate' not in item:
                    item[tax+'_rate']=format(rate.normalize(),'f')
            inv['rate_evidence']='Component rates calculated from explicit tax amounts for one reconciled item'
        except (ValueError,InvalidOperation) as exc:
            warnings.append(str(exc))
    elif inv['items'] and any(tax+'_rate' not in item for item in inv['items'] for tax in TAXES):
        warnings.append('Item-wise GST rates missing; totals alone cannot split a multi-item invoice')
    normalized=' '.join(text.split())
    if re.search(r'SYNTHETIC TEST DOCUMENT - NOT FOR REAL GST FILING OR COMMERCIAL USE\. GSTINs and identifiers are fictional\.',normalized,re.I):
        inv['dummy_document']=True
    return {key:value for key,value in inv.items() if value is not None}
