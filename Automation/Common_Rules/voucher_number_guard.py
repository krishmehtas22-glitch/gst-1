"""Read-only prerequisite: Tally must retain the invoice's voucher number.

Tally imports numbers according to the destination Voucher Type configuration:
https://help.tallysolutions.com/import-data-faq/
https://help.tallysolutions.com/use-voucher-numbering-methods/
No voucher type or existing voucher is altered here.
"""
import xml.etree.ElementTree as ET


def check_numbering(plan, company, transport):
    from .tally_import import response_xml
    required=set()
    for filename,data in plan:
        if filename!='Sales_Vouchers.xml':continue
        for voucher in response_xml(data).iter('VOUCHER'):
            required.add(voucher.findtext('VOUCHERTYPENAME') or voucher.get('VCHTYPE') or 'Sales')
    if not required:return
    doc=ET.fromstring('''<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>InvoiceReaderVoucherNumbering</ID></HEADER><BODY><DESC><STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES><TDL><TDLMESSAGE><COLLECTION NAME="InvoiceReaderVoucherNumbering" ISMODIFY="No"><TYPE>VoucherType</TYPE><FETCH>Name,NumberingMethod</FETCH></COLLECTION></TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>''')
    ET.SubElement(doc.find('.//STATICVARIABLES'),'SVCURRENTCOMPANY').text=company
    guidance=('No import sent. To keep invoice numbers as Sales voucher numbers in '+company+
              ', open Tally: Alt+G > Alter Master > Voucher Type > Sales > Method of voucher numbering > Manual; save with Ctrl+A. '
              'If multiple numbering series are enabled, review the applicable series. Then reopen Import to Tally. '
              'Existing vouchers are not renumbered by this app; do not reimport them to correct their numbers.')
    try:
        result=response_xml(transport(ET.tostring(doc,encoding='utf-8',xml_declaration=True)))
        if result.find('.//LINEERROR') is not None:raise ValueError('Tally rejected the numbering lookup')
        methods={name:[] for name in required}
        for node in result.iter('VOUCHERTYPE'):
            name=node.get('NAME') or node.findtext('NAME')
            if name in methods:methods[name].append(node.findtext('NUMBERINGMETHOD') or '')
        if any(values!=['Manual'] for values in methods.values()):
            observed='; '.join(name+': '+(', '.join(v or 'unknown' for v in values) or 'not returned') for name,values in sorted(methods.items()))
            raise ValueError('Numbering read from Tally: '+observed)
    except (ValueError,OSError) as exc:
        raise ValueError(guidance+'\n'+str(exc)) from exc
