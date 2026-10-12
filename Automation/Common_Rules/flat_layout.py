"""Read ordered PDF text when visual-layout spacing distorts glyph boundaries.

These structural readers use the actual embedded text, not spelling guesses.
Missing or alternative units remain unresolved for the review form.
"""
from datetime import datetime
import re
from .accounting import cents, money, state_code, TAXES, EXPORT_COUNTRIES


def supported_flat(text):
    return (('SELLER / SUPPLIER\n' in text and 'BUYER / BILL TO\n' in text and 'Supply classification:' in text) or
            ('Invoice Details\nInvoice No:' in text and 'Billed To (Buyer)\n' in text) or
            ('SELLER\n' in text and 'BUYER\n' in text and 'TOTAL TAXABLE VALUE\n' in text) or
            ('EXPORTER (SELLER):\n' in text and 'CONSIGNEE (BUYER):\n' in text) or
            ('supply consists of exactly' in text and 'HSN classification' in text))


def date(value):
    value=re.sub(r'(\d)(?:st|nd|rd|th)\b',r'\1',value)
    for fmt in ('%d-%b-%Y','%d/%m/%Y','%d %b %Y','%Y-%m-%d'):
        try:return datetime.strptime(value,fmt).date().isoformat()
        except ValueError:pass
    raise ValueError('Invoice date needs review: '+value)


def parse_flat_layout(text):
    if not supported_flat(text):return None
    warnings=[]
    inv={'source_layout':'ordered_roles_v1','currency':'INR','items':[],
         'extraction_warnings':warnings,'test_document':bool(re.search(r'- GSTR-1 Test Page \d+ of \d+', ' '.join(text.split()))),
         'dummy_document':'SYNTHETIC TEST DATA - NOT A VALID TAX DOCUMENT OR GST REGISTRATION' in text}
    lines=[line.strip() for line in text.splitlines() if line.strip()]
    joined=' '.join(lines)
    starts=('SELLER / SUPPLIER','Invoice Details','SELLER','EXPORTER (SELLER):')
    if sum(lines.count(heading) for heading in starts)>1 or len(re.findall(r'Bill of Supply from ',joined))>1:
        warnings.append('Multiple invoice sections remain in this PDF; review the document before generating a voucher')
    def value(label):
        index=next((i for i,line in enumerate(lines) if line.casefold().startswith(label.casefold())),None)
        if index is None:return None
        remainder=lines[index][len(label):].strip()
        return remainder or (lines[index+1] if index+1<len(lines) else None)
    def role(start,end):
        begin=lines.index(start)+1;finish=lines.index(end)
        block=lines[begin:finish]
        return block[0],block
    def gst_rates(item,combined=None):
        if combined is not None:
            rate=money(combined)
            values=(rate/2,rate/2,0) if inv.get('supply')=='INTRA' else (0,0,rate)
            for tax,rate in zip(TAXES,values):item[tax+'_rate']=str(rate)
        for tax in TAXES:item.setdefault(tax+'_rate','0')

    try:
        if 'SELLER / SUPPLIER' in lines and 'BUYER / BILL TO' in lines:
            inv['seller_name'],seller=role('SELLER / SUPPLIER','BUYER / BILL TO')
            buyer_end=next(line for line in lines if line.lower().startswith('invoice number:'))
            inv['buyer_name'],buyer=role('BUYER / BILL TO',buyer_end)
            seller_gst=re.search(r'GSTIN: (\w{15}) \| State: (.*?) \((\d{2})\)', ' '.join(seller))
            if not seller_gst:raise ValueError('Seller GSTIN/state missing or conflicting')
            inv.update(seller_gstin=seller_gst[1],seller_state=seller_gst[3],seller_address=', '.join(seller[1:-1]))
            if state_code(seller_gst[2])!=seller_gst[3]:raise ValueError('Seller state name/code conflict')
            inv['buyer_address']=buyer[1]
            inv['buyer_gstin']=next(line.split(':',1)[1].strip() for line in buyer if line.startswith('Buyer GSTIN:'))
            inv['number']=value('Invoice number:');inv['date']=date(value('Invoice date:'))
            if value('Currency:')!='INR (Indian Rupees)':raise ValueError('Only explicit INR pricing is supported')
            treatment=value('Supply classification:')
            pos=value('Place of supply:')
            if treatment in ('EXPORT LUT','EXPORT IGST'):
                inv.update(supply='EXPORT',classification='export_lut' if treatment=='EXPORT LUT' else 'export_igst',
                    export_mode='LUT_without_payment' if treatment=='EXPORT LUT' else 'with_payment_of_IGST',
                    place_of_supply='Outside India',buyer_state='Outside India',buyer_registration='Unregistered')
                if inv['buyer_gstin']!='Not applicable - overseas buyer':raise ValueError('Export buyer GSTIN conflicts with overseas treatment')
                inv['buyer_gstin']=''
                country=re.sub(r' \(NA\)$','',pos).split(',')[-1].strip()
                if not pos.endswith('(NA)'):raise ValueError('Export place of supply needs review')
                inv['buyer_country']=EXPORT_COUNTRIES.get(country.casefold(),country)
                if treatment=='EXPORT LUT' and 'Export under LUT without payment of integrated tax.' not in joined:raise ValueError('Explicit LUT declaration missing')
                if treatment=='EXPORT IGST' and 'Export with payment of IGST' not in joined:raise ValueError('Explicit IGST export declaration missing')
                inv['shipping_bill_port']='; '.join(line for line in lines if line.startswith(('Port of loading:','LUT / Shipping bill ref:')))
            else:
                inv.update(supply='EXEMPT' if treatment=='EXEMPT' else treatment,classification='exempt' if treatment=='EXEMPT' else 'taxable')
                state=re.search(r', ([^,]+) \((\d{2})\)$',pos)
                if not state or state_code(state[1])!=state[2]:raise ValueError('Place-of-supply state/code needs review')
                inv['place_of_supply']=state[2]
                if inv['buyer_gstin']=='Unregistered':inv.update(buyer_gstin='',buyer_registration='Unregistered',buyer_state=state[2])
            start=lines.index('AMOUNT (INR)')+1
            finish=next(i for i,line in enumerate(lines) if line.startswith('Unit:'))
            values=lines[start:finish]
            if len(values)!=5:raise ValueError('Item column sequence incomplete')
            item=dict(zip(('name','hsn','quantity','rate','value'),values))
            unit_note=lines[finish];inv['source_unit_note']=unit_note.split('|')[0].strip()
            unit=re.search(r'^Unit:\s*(.*?)\s*\|',unit_note)
            if unit and '/' not in unit[1] and '(' not in unit[1]:item['unit']=unit[1].strip()
            else:item['unit_choice_required']=True
            gst=re.search(r'GST rate: ([\d.]+)%',unit_note)
            if not gst:raise ValueError('Printed GST rate missing')
            item['printed_gst_rate']=gst[1]
            gst_rates(item,'0' if treatment=='EXPORT LUT' else gst[1]);inv['items']=[item]
            for label,key in (('Taxable value','taxable'),('CGST','cgst'),('SGST','sgst'),('IGST','igst'),('GRAND TOTAL','total')):
                inv[key]=str(cents(value(label)))
            if 'Reverse charge: No' not in text:raise ValueError('Reverse charge treatment needs review')

        elif 'Invoice Details' in lines and 'Billed To (Buyer)' in lines:
            seller_start=lines.index('Original for Recipient')+1
            inv['seller_name']=lines[seller_start]
            seller_end=lines.index('Invoice Details');seller=lines[seller_start+1:seller_end]
            inv['seller_gstin']=value('GSTIN:');inv['seller_state']=value('State Code:')
            inv['seller_address']=', '.join(line for line in seller if not line.startswith(('GSTIN:','State Code:')))
            inv['number']=value('Invoice No:');inv['date']=date(value('Date:'))
            if value('Type:')!='B2B (Intra-State)':raise ValueError('Unexpected domestic supply type')
            inv.update(supply='INTRA',classification='taxable')
            index=lines.index('Billed To (Buyer)');inv['buyer_name']=lines[index+1];inv['buyer_address']=lines[index+2]
            inv['buyer_gstin']=value('Buyer GSTIN:');inv['place_of_supply']=state_code(value('Place of Supply:'))
            header=next(line for line in lines if line.startswith('# Item Description HSN Qty Rate Taxable'))
            rates=re.fullmatch(r'# Item Description HSN Qty Rate Taxable CGST ([\d.]+)% SGST ([\d.]+)%',header)
            if not rates:raise ValueError('Printed component GST headings missing')
            row=lines[lines.index(header)+1]
            item=re.fullmatch(r'1 (.+?) (\d{4}|\d{6}|\d{8}) ([\d,]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+)',row)
            if not item:raise ValueError('Domestic item row needs review')
            fields=dict(zip(('name','hsn','quantity','rate','value','printed_cgst','printed_sgst'),item.groups()))
            fields.update(cgst_rate=rates[1],sgst_rate=rates[2],igst_rate='0',unit_choice_required=True)
            inv['items']=[fields];inv.update(taxable=str(cents(fields['value'])),cgst=str(cents(fields['printed_cgst'])),sgst=str(cents(fields['printed_sgst'])),igst='0.00',total=str(cents(value('Grand Total:'))))
            aggregate=lines[lines.index(header)+2]
            expected='Total '+fields['quantity']+' '+fields['value']+' '+fields['printed_cgst']+' '+fields['printed_sgst']
            if aggregate!=expected:raise ValueError('Printed aggregate item row does not reconcile')

        elif 'SELLER' in lines and 'BUYER' in lines:
            inv['seller_name'],seller=role('SELLER','BUYER')
            inv['seller_gstin']=next(line.split(':',1)[1].strip() for line in seller if line.startswith('GSTIN:'))
            inv['seller_state']=inv['seller_gstin'][:2];inv['seller_address']=', '.join(line for line in seller[1:] if not line.startswith('GSTIN:'))
            inv['buyer_name'],buyer=role('BUYER','Line Items');inv['buyer_gstin']=next(line.split(':',1)[1].strip() for line in buyer if line.startswith('GSTIN:'))
            inv['buyer_address']=', '.join(line for line in buyer[1:] if not line.startswith('GSTIN:'))
            number=re.search(r'\|+ (\S+) \|+',text)
            if not number:raise ValueError('Printed invoice reference missing')
            inv['number']=number[1];inv['date']=date(value('INVOICE DATE'))
            inv.update(place_of_supply=state_code(value('PLACE OF SUPPLY')),supply='INTER',classification='taxable')
            if value('SUPPLY TYPE')!='B2B (IGST)':raise ValueError('Interstate type needs review')
            description=value('DESCRIPTION');hsn=value('HSN:');qty=re.fullmatch(r'([\d,]+) (\w+)',value('QTY'))
            tax_header=next(line for line in lines if line.startswith('TAX (IGST'))
            gst=re.fullmatch(r'TAX \(IGST ([\d.]+)%\)',tax_header)
            if not qty or not gst:raise ValueError('Quantity/unit or IGST rate missing')
            item={'name':description,'hsn':hsn,'quantity':qty[1],'unit':qty[2],'rate':str(money(value('RATE'))),
                'value':str(cents(value('TOTAL TAXABLE VALUE'))),'printed_igst':value(tax_header),'printed_total':value('LINE TOTAL')}
            gst_rates(item,gst[1]);inv['items']=[item]
            inv.update(taxable=str(cents(value('TOTAL TAXABLE VALUE'))),cgst='0.00',sgst='0.00',igst=str(cents(value('TOTAL IGST'))),total=str(cents(value('INVOICE TOTAL'))))

        elif 'EXPORTER (SELLER):' in lines and 'CONSIGNEE (BUYER):' in lines:
            start=lines.index('EXPORTER (SELLER):');inv['seller_name']=lines[start+1]
            inv['seller_gstin']=value('GSTIN:');inv['seller_state']=value('State:').split()[0]
            inv['seller_address']=', '.join(lines[start+2:start+4])
            inv['number']=value('INVOICE NO:');inv['date']=date(value('DATE:'))
            begin=lines.index('CONSIGNEE (BUYER):');inv['buyer_name']=lines[begin+1];inv['buyer_address']=lines[begin+2]
            if value('Buyer GSTIN:')!='Unregistered (Foreign Entity)':raise ValueError('Foreign buyer classification needs review')
            if value('Place of Supply (POS):')!='96 - Foreign Country':raise ValueError('Foreign place of supply needs review')
            if 'SUPPLY MEANT FOR EXPORT UNDER LETTER OF UNDERTAKING (LUT).' not in joined:raise ValueError('Explicit LUT declaration missing')
            inv.update(supply='EXPORT',classification='export_lut',export_mode='LUT_without_payment',
                buyer_gstin='',buyer_registration='Unregistered',buyer_state='Outside India',place_of_supply='Outside India')
            port=value('PORT OF DISCHARGE:');country=port.split(',')[-1].strip()
            inv['buyer_country']=EXPORT_COUNTRIES.get(country.casefold(),country)
            inv['shipping_bill_port']='; '.join(label+' '+str(value(label)) for label in ('SHIPPING BILL NO:','PORT OF DISCHARGE:','LUT NUMBER:'))
            item=re.search(r'\b1 (.+?) (\d{4}|\d{6}|\d{8}) ([\d,]+) (Vials|Units|Packs|Tubes|Liters) ([\d,.]+) 0% \(LUT\) ([\d,.]+) TOTAL AMOUNT:',joined)
            if not item:raise ValueError('Wrapped export description/quantity/unit needs review')
            fields=dict(zip(('name','hsn','quantity','unit','rate','value'),item.groups()));gst_rates(fields,'0');inv['items']=[fields]
            inv.update(taxable=str(cents(fields['value'])),total=str(cents(value('TOTAL AMOUNT:'))),cgst='0.00',sgst='0.00',igst='0.00')
            if cents(value('TAX PAYABLE:'))!=0:raise ValueError('LUT export tax payable must be zero')

        else:
            inv['number']=value('REF:');inv['date']=date(value('Generated On:'))
            seller=re.search(r'Bill of Supply from (.*?) \(GSTIN: (\w{15}), Location: (.*?) - State (\d{2})\)',joined)
            buyer=re.search(r'customer, (.*?)\s*, located at (.*?)\. Their registered GST identification number is (\w{15})\.',joined)
            pos=re.search(r'designated as (\d{2}) - ([^.]+)\.',joined)
            item=re.search(r'exactly ([\d,]+) (\w+) \(QTY\) of (.*?) under HSN classification (\d+)\. The mutually agreed rate is ₹ ([\d,.]+) per unit, yielding a total taxable base value of ₹ ([\d,.]+)\.',joined)
            if not seller or not buyer or not pos or not item:raise ValueError('Narrative party/item evidence incomplete')
            inv.update(seller_name=seller[1],seller_gstin=seller[2],seller_address=seller[3],seller_state=seller[4],
                buyer_name=buyer[1],buyer_address=buyer[2],buyer_gstin=buyer[3],place_of_supply=state_code(pos[1]+' - '+pos[2].strip()),supply='EXEMPT',classification='exempt')
            if 'FOR EXEMPTED GOODS UNDER GST' not in joined or 'NIL (0%). No tax has been collected.' not in joined:raise ValueError('Explicit exemption/zero tax evidence missing')
            qty,unit,name,hsn,rate,amount=item.groups();fields={'quantity':qty,'unit':unit,'name':name,'hsn':hsn,'rate':rate,'value':amount};gst_rates(fields,'0');inv['items']=[fields]
            inv.update(taxable=str(cents(amount)),total=str(cents(value('NET AMOUNT PAYABLE'))),cgst='0.00',sgst='0.00',igst='0.00')
        inv.setdefault('round_off','0.00')
    except (ValueError,KeyError,StopIteration,TypeError,IndexError,ArithmeticError) as exc:warnings.append('Ordered PDF text: '+str(exc))
    return inv
