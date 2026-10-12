"""Explicit billed-to tables and receipt item blocks with printed evidence.

Read roles before metadata, join only description continuations, and derive INR
net unit rates only from printed percentage discounts/exchange rates. Original
prices, currencies and item extensions remain available for reconciliation.
"""
from datetime import datetime
from decimal import Decimal
import re

from .accounting import cents, money, state_code, TAXES

SAMPLE_NOTICE='Sample invoice generated for software testing. All names, GSTINs and figures are fictional.'


def marked_sample(text):
    normalized=' '.join(text.casefold().split())
    return (('synthetic test invoice - not valid for gst filing or commercial use' in normalized and
             'all business names, gstins, references and transactions are fictitious' in normalized) or SAMPLE_NOTICE.casefold() in normalized or
            'sample invoice for software testing. fictional data.' in normalized or
            ('synthetic sample for ocr/accounting automation testing only.' in normalized and
             'not a valid tax invoice. all gstins and buyer identities are fictional.' in normalized))


def spans(line):
    return [(match.start(),match.end(),match[0].strip()) for match in
            re.finditer(r'\S.*?(?=\s{2,}|$)',line)]


def parse_role_table(text,headers):
    raw=[line for line in text.splitlines() if line.strip()]
    buyer_index=next((i for i,line in enumerate(raw) if 'Billed To (Recipient)' in line),None)
    table_index=next((i for i,line in enumerate(raw) if re.match(r'\s*Sr\s{2,}',line) and re.search(r'HSN',line)),None)
    if buyer_index is None or table_index is None or table_index<=buyer_index:
        return None
    warnings=[]
    inv={'source_layout':'tabular_roles_v1','currency':'INR','items':[],
         'dummy_document':marked_sample(text),'extraction_warnings':warnings}
    header='\n'.join(raw[:buyer_index])
    seller_ids=list(dict.fromkeys(re.findall(r'GSTIN:\s*(\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[A-Z0-9])\b',header)))
    if len(seller_ids)==1:inv['seller_gstin']=seller_ids[0]
    else:warnings.append('Seller GSTIN missing or ambiguous in the seller header')
    signatories=list(dict.fromkeys(re.findall(r'^\s*For\s+(.+?)\s*$',text,re.M)))
    if len(signatories)==1 and any(cell.casefold()==signatories[0].casefold() or cell.casefold().startswith(signatories[0].casefold()+' |')
                                  for line in raw[:buyer_index] for _,_,cell in spans(line)):
        inv['seller_name']=signatories[0]
    else:warnings.append('Seller banner/signatory identity needs review')
    seller_state=re.findall(r'(?:State Code\s+|(?:Seller|From) Location:.*?\()(\d{2})\b',header)
    if seller_state and len(set(seller_state))==1:inv['seller_state']=seller_state[0]
    else:warnings.append('Printed seller state missing or conflicting')
    seller_address=[];inside=False
    for line in raw[:buyer_index]:
        cells=spans(line)
        if not cells:continue
        # A decorative logo can precede the seller banner in another column.
        name=inv.get('seller_name','')
        if name and any(cell.casefold().startswith(name.casefold()) for _,_,cell in cells):
            inside=True
            for _,_,cell in cells:
                if cell.casefold().startswith(name.casefold()+' |'):
                    seller_address.extend(part.strip() for part in cell.split('|')[1:])
            continue
        if inside:
            cell=cells[0][2]
            if cell.startswith(('GSTIN:','Ph:','Seller Location:','From Location:')):inside=False
            elif not re.match(r'(?:Invoice|Supply|Place|Reverse)\b',cell):seller_address.append(cell)
    if seller_address:inv['seller_address']=', '.join(seller_address)

    # Metadata labels can be in the right column above or beside the buyer.
    aliases={'Invoice No.':'number','Invoice Date':'date','Supply Type':'printed_supply_type',
        'Place of Supply':'place_of_supply','Reverse Charge':'reverse_charge',
        'Destination':'buyer_country','Currency / Rate':'printed_fx',
        'Shipping Bill No.':'shipping_bill_number','Shipping Bill Date':'shipping_bill_date',
        'Port Code':'port_code','LUT':'lut_reference'}
    for line in raw[:table_index]:
        for label,key in aliases.items():
            match=re.search(r'(?:^|\s{2,})'+re.escape(label)+r'\s{2,}(\S.*?)\s*$',line)
            if match:
                value=match[1].strip()
                if key in inv and inv[key]!=value:warnings.append('Ambiguous '+key+' in invoice metadata')
                else:inv[key]=value
    for index,line in enumerate(raw[:table_index-1]):
        match=re.search(r'Shipping Bill\s{2,}(\d{2}-[A-Za-z]{3}-\d{4})\s*$',line)
        if match and re.search(r'\s{2,}Date\s*$',raw[index+1]):inv['shipping_bill_date']=match[1]
    try:inv['date']=datetime.strptime(inv.get('date',''),'%d-%b-%Y').date().isoformat()
    except ValueError:warnings.append('Invoice date needs review')
    treatment=inv.get('printed_supply_type','').casefold()
    if treatment.startswith('export') and inv.get('place_of_supply') not in ('96-Other Countries','Outside India'):
        warnings.append('Export place of supply conflicts with the printed export treatment')
    if treatment.startswith('export - without payment of igst'):
        inv.update(supply='EXPORT',classification='export_lut',export_mode='LUT_without_payment',place_of_supply='Outside India')
        if not re.search(r'Declaration: Supply meant for export under Letter of Undertaking without payment of integrated tax\.',text):
            warnings.append('LUT export declaration missing or conflicting')
    elif treatment=='export - with payment of igst':
        inv.update(supply='EXPORT',classification='export_igst',export_mode='with_payment_of_IGST',place_of_supply='Outside India')
        if 'Declaration: Supply meant for export on payment of integrated tax.' not in text:
            warnings.append('IGST-paid export declaration missing or conflicting')
    elif treatment.startswith('exempt supply'):
        inv.update(supply='EXEMPT',classification='exempt')
    elif treatment.startswith('nil-rated supply'):
        inv.update(supply='EXEMPT',classification='nil_rated')
    elif treatment=='intra-state':inv.update(supply='INTRA',classification='taxable')
    elif treatment=='inter-state':inv.update(supply='INTER',classification='taxable')
    else:warnings.append('Supply treatment missing or unsupported')
    if inv.get('reverse_charge','').casefold()!='no':warnings.append('Reverse charge treatment needs review')
    if inv.get('supply')!='EXPORT':
        try:inv['place_of_supply']=state_code(inv.get('place_of_supply',''))
        except ValueError as exc:warnings.append(str(exc))

    buyer=[]
    heading=spans(raw[buyer_index])
    other_start=heading[1][0]-3 if len(heading)>1 else len(raw[buyer_index])
    for line in raw[buyer_index+1:table_index]:
        cells=spans(line)
        if cells and cells[0][0]<other_start:buyer.append(cells[0][2])
    if buyer:inv['buyer_name']=buyer[0]
    buyer_text='\n'.join(buyer)
    buyer_ids=list(dict.fromkeys(re.findall(r'^GSTIN:\s*(.*)$',buyer_text,re.M)))
    if inv.get('supply')=='EXPORT':
        if buyer_ids:warnings.append('Overseas buyer has an unexpected Indian GSTIN field')
        inv.update(buyer_gstin='',buyer_registration='Unregistered',buyer_state='Outside India')
        tax_ids=re.findall(r'^Tax ID:\s*(.*)$',buyer_text,re.M)
        if len(set(tax_ids))==1:inv['buyer_foreign_tax_id']=tax_ids[0]
        countries=re.findall(r'^Country:\s*(.*)$',buyer_text,re.M)
        if len(set(countries))==1:
            if inv.get('buyer_country') and inv['buyer_country']!=countries[0]:warnings.append('Export destination conflicts with buyer country')
            inv['buyer_country']=countries[0]
    elif len(buyer_ids)==1:
        if buyer_ids[0].casefold()=='unregistered (urp)':inv.update(buyer_gstin='',buyer_registration='Unregistered')
        else:inv['buyer_gstin']=buyer_ids[0]
        states=re.findall(r'State Code\s+(\d{2})',buyer_text)
        if len(set(states))==1:inv['buyer_state']=states[0]
    else:warnings.append('Buyer GSTIN/registration missing or ambiguous')
    address=[]
    for cell in buyer[1:]:
        if cell.startswith(('GSTIN:','Tax ID:','Buyer Location:')):break
        address.append(cell)
    if address:inv['buyer_address']=', '.join(address)
    if inv.get('shipping_bill_number') or inv.get('port_code'):
        inv['shipping_bill_port']='; '.join(inv[key] for key in ('shipping_bill_number','shipping_bill_date','port_code','lut_reference') if inv.get(key))

    # Join wrapped heading fragments by their horizontal centres. Data rows
    # retain explicit ordered cells, with unknown extra columns rejected.
    heading_cells=spans(raw[table_index]);labels=[cell[2] for cell in heading_cells]
    centers=[(a+b)/2 for a,b,_ in heading_cells]
    first_row=next((i for i in range(table_index+1,len(raw)) if re.match(r'^\s*\d+\s{2,}',raw[i])),None)
    if first_row is None:warnings.append('No item rows');return inv
    for line in raw[table_index+1:first_row]:
        for a,b,fragment in spans(line):
            index=min(range(len(centers)),key=lambda j:abs(centers[j]-(a+b)/2))
            labels[index]+=fragment
    def decode(label):
        normalized=re.sub(r'[^a-z0-9%]','',label.casefold())
        special={'sr':'sequence','hsnsac':'hsn','disc%':'discount_rate','discount%':'discount_rate',
            'taxablevalue':'value','cgst%':'cgst_rate','sgst%':'sgst_rate','igst%':'igst_rate',
            'cgstamt':'printed_cgst','sgstamt':'printed_sgst','igstamt':'printed_igst','total':'printed_total'}
        if normalized in special:return special[normalized]
        if re.fullmatch(r'rate(?:usd|aed)',normalized):return 'foreign_rate'
        if re.fullmatch(r'amount(?:usd|aed)',normalized):return 'foreign_value'
        if normalized=='taxableinr':return 'value'
        if normalized=='igstinr':return 'printed_igst'
        return next((key for key,values in headers.items() if any(re.sub(r'[^a-z0-9%]','',value.casefold())==normalized for value in values)),None)
    columns=[decode(label) for label in labels]
    if None in columns or len(set(columns))!=len(columns):warnings.append('Unknown or duplicate item headings: '+', '.join(label for label,key in zip(labels,columns) if key is None));return inv
    for needed in ('name','hsn','quantity','unit','value'):
        if needed not in columns:warnings.append('Missing item column: '+needed)
    if warnings:return inv
    name_index=columns.index('name');name_start=None;name_end=None
    for line in raw[first_row:]:
        if re.search(r'(?:Total Taxable Value|Taxable Value \(INR\)|Invoice Value \(|GST Payable|Grand Total|Round Off|Terms:)',line):break
        row=spans(line)
        if re.match(r'^\s*\d+\s{2,}',line):
            if len(row)!=len(columns):warnings.append('Incomplete item row; review column alignment');continue
            item=dict(zip(columns,(cell[2] for cell in row)))
            item.pop('sequence',None);inv['items'].append(item)
            name_start=row[name_index][0]
            name_end=row[name_index+1][0] if name_index+1<len(row) else len(line)
        elif len(row)==1 and inv['items'] and name_start is not None and name_start-2<=row[0][0]<name_end:
            inv['items'][-1]['name']+=' '+row[0][2]
        else:warnings.append('Unrecognized item continuation needs review')

    totals={'Total Taxable Value':'taxable','Taxable Value (INR)':'taxable','Grand Total':'total',
        'CGST':'cgst','SGST':'sgst','IGST':'igst','Round Off':'round_off'}
    for line in raw[first_row:]:
        for label,key in totals.items():
            match=re.search(r'(?:^|\s{2,})'+re.escape(label)+r'\s{2,}((?:(?:INR|Rs\.)\s*|₹)?-?[\d,.]+)\s*$',line)
            if match:
                value=str(cents(match[1]))
                if key in inv and inv[key]!=value:warnings.append('Conflicting '+key+' total')
                else:inv[key]=value
    is_export=inv.get('supply')=='EXPORT'
    fx=inv.get('printed_fx','')
    if fx:
        match=re.fullmatch(r'(USD|AED) 1 = INR ([\d,.]+)',fx)
        if not is_export or not match:warnings.append('Unsupported/missing export exchange-rate basis')
        else:
            inv['foreign_currency']=match[1];inv['exchange_rate']=str(money(match[2]))
            foreign=re.findall(r'Invoice Value \('+match[1]+r'\)\s{2,}'+match[1]+r'\s+([\d,.]+)',text)
            if len(foreign)==1:inv['foreign_invoice_value']=str(cents(foreign[0]))
            else:warnings.append('Foreign invoice total missing or ambiguous')
    if inv.get('classification') in ('exempt','nil_rated'):
        if not re.search(r'GST Payable\s{2,}NIL',text):warnings.append('Bill of supply needs explicit NIL GST payable')
        else:
            for tax in TAXES:inv[tax]='0.00'
    for item in inv['items']:
        try:
            qty=money(item['quantity']);value=money(item['value'])
            if is_export:
                if not inv.get('exchange_rate'):raise ValueError('Export item needs a printed exchange rate')
                foreign_rate=money(item['foreign_rate']);foreign_value=money(item['foreign_value']);exchange=money(inv['exchange_rate'])
                if cents(qty*foreign_rate)!=cents(foreign_value) or cents(foreign_value*exchange)!=cents(value):raise ValueError('Foreign item value does not reconcile to the printed INR value')
                item['rate']=format(foreign_rate*exchange,'f')
            else:
                printed_rate=money(item['rate']);discount=item.pop('discount_rate','-')
                if discount!='-' and money(discount):
                    discount=money(discount)
                    if discount<0 or discount>100:raise ValueError('Invalid printed discount percentage')
                    item['list_rate']=format(printed_rate,'f');item['discount_rate']=format(discount,'f')
                    item['rate']=format(printed_rate*(1-discount/100),'f')
            if cents(qty*money(item['rate']))!=cents(value):raise ValueError('Net item unit rate does not reconcile to quantity and taxable value')
            for tax in TAXES:
                if inv.get('classification') in ('exempt','nil_rated'):item[tax+'_rate']='0'
                elif tax+'_rate' not in item:
                    absent=(tax=='igst' and inv.get('supply')=='INTRA') or (tax in ('cgst','sgst') and inv.get('supply') in ('INTER','EXPORT'))
                    if absent:item[tax+'_rate']='0'
                    else:raise ValueError('Missing printed item '+tax.upper()+' rate')
                if tax+'_rate' in item:item[tax+'_rate']=str(money(item[tax+'_rate'].replace(' (LUT)','')))
                if 'printed_'+tax in item and cents(value*money(item[tax+'_rate'])/100)!=cents(item['printed_'+tax]):raise ValueError('Printed item '+tax.upper()+' does not reconcile')
            if item.get('printed_total') and cents(value+sum(cents(value*money(item[tax+'_rate'])/100) for tax in TAXES))!=cents(item['printed_total']):raise ValueError('Printed gross item total does not reconcile')
        except (ValueError,KeyError,ArithmeticError) as exc:warnings.append(str(exc))
    for tax in TAXES:
        if tax not in inv and inv['items'] and all(item.get(tax+'_rate') is not None and money(item[tax+'_rate'])==0 for item in inv['items']):inv[tax]='0.00'
    return inv


def parse_receipt(text):
    if not re.search(r'^\s*Customer:\s*\S',text,re.M) or not re.search(r'^\s*\d+\.\s+.*\nHSN \d+ GST [\d.]+%\n',text,re.M):return None
    warnings=[]
    inv={'source_layout':'receipt_items_v1','currency':'INR','dummy_document':marked_sample(text),'items':[],'extraction_warnings':warnings}
    if re.search(r'(?:Reverse Charge|reverse charge basis)\s*:\s*Yes\b',text,re.I):warnings.append('Reverse charge treatment needs review')
    lines=[line.strip() for line in text.splitlines() if line.strip()]
    inv['seller_name']=lines[0]
    seller_block='\n'.join(lines[:next(i for i,line in enumerate(lines) if line.startswith('Inv No:'))])
    seller_ids=re.findall(r'GSTIN:\s*(\w{15})\b',seller_block)
    if len(set(seller_ids))==1:inv['seller_gstin']=seller_ids[0]
    else:warnings.append('Receipt seller GSTIN needs review')
    states=re.findall(r'Seller Location:.*?\((\d{2})\)',seller_block)
    if len(set(states))==1:inv['seller_state']=states[0]
    else:warnings.append('Receipt seller state needs review')
    inv['seller_address']=' '.join(line for line in lines[1:lines.index(next(line for line in lines if line.startswith('GSTIN:')))] )
    labels={'Inv No':'number','Date':'date','Customer':'buyer_name','Buyer GSTIN':'buyer_gstin',
        'Place of Supply':'place_of_supply','Supply':'printed_supply_type','Taxable':'taxable','CGST':'cgst','SGST':'sgst','Round off':'round_off','TOTAL':'total'}
    for line in lines:
        for label,key in labels.items():
            match=re.fullmatch(re.escape(label)+r':\s*(.*)',line)
            if match:inv[key]=match[1]
    try:
        inv['date']=datetime.strptime(inv['date'],'%d-%b-%Y').date().isoformat()
        inv['place_of_supply']=state_code(inv['place_of_supply'])
        inv['buyer_state']=inv['place_of_supply']
    except (ValueError,KeyError) as exc:warnings.append(str(exc))
    if inv.get('buyer_gstin')=='Unregistered':inv.update(buyer_gstin='',buyer_registration='Unregistered')
    if inv.get('printed_supply_type')=='Intra-State (B2C)':inv.update(supply='INTRA',classification='taxable',igst='0.00')
    else:warnings.append('Unsupported receipt supply')
    for index,line in enumerate(lines):
        if not re.match(r'^\d+\. ',line):continue
        if index+2>=len(lines):warnings.append('Incomplete receipt item');continue
        hsn=re.fullmatch(r'HSN (\d+) GST ([\d.]+)%',lines[index+1])
        values=re.fullmatch(r'([\d,.]+) (\w+) x ([\d,.]+) = ([\d,.]+)',lines[index+2])
        if not hsn or not values:warnings.append('Receipt item metadata/extension needs review');continue
        gst=money(hsn[2]);inv['items'].append({'name':line.split('. ',1)[1],'hsn':hsn[1],
            'quantity':values[1],'unit':values[2],'rate':values[3],'value':values[4],
            'cgst_rate':str(gst/2),'sgst_rate':str(gst/2),'igst_rate':'0'})
    for key in ('taxable','cgst','sgst','round_off','total'):
        if key in inv:inv[key]=str(cents(inv[key]))
    return inv
