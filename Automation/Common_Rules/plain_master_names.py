"""Readable master identities; no batch IDs and no changes to invoice values."""
from collections import defaultdict


class PlainMasterNames:
    def __init__(self, records, clean):
        self.clean=clean
        parties=defaultdict(set);stocks=defaultdict(set)
        for record in records:
            inv=record.get('invoice') or {}
            buyer=clean(inv.get('buyer_name'))
            if buyer:parties[buyer].add(self.party_identity(inv))
            for item in inv.get('items') or []:
                name=clean(item.get('name')) or 'Item unresolved'
                stocks[name].add(self.stock_identity(item,inv))
        reserved={'Sales','CGST','SGST','IGST','Cess','Round Off','Invoice differences - review'}
        self.parties=self._allocate(parties,self._party_description,reserved,
            lambda token,variants:'GSTIN '+(token[0] or 'not supplied') if sum(t[0]==token[0] for t in variants)==1 else self._party_description(token))
        self.stocks=self._allocate(stocks,self._stock_description,set(),
            lambda token,variants:token[0] if sum(t[0]==token[0] for t in variants)==1 else self._stock_description(token))

    def party_identity(self,invoice):
        return tuple(self.clean(invoice.get(field)) for field in ('buyer_gstin','buyer_state','buyer_address'))

    @staticmethod
    def _party_description(token):
        gstin,state,address=token
        return '; '.join(['GSTIN '+(gstin or 'not supplied')]+(['State '+state] if state else [])+(['Address '+address] if address else []))

    def stock_identity(self,item,invoice):
        return (self.clean(item.get('unit')) or 'Units', self.clean(item.get('hsn')),
                *(str(item.get(t+'_rate')) for t in ('cgst','sgst','igst')),
                str(invoice.get('classification')))

    @staticmethod
    def _stock_description(token):
        unit,hsn,cgst,sgst,igst,kind=token
        return f'{unit}; HSN {hsn or "not supplied"}; GST C{cgst} S{sgst} I{igst}; {kind}'

    @staticmethod
    def _allocate(groups,describe,reserved,short_label):
        result={};occupied=set(reserved);originals=set(groups)
        # Printed names take precedence over generated descriptive variants.
        for name,variants in sorted(groups.items()):
            if len(variants)==1 and name not in occupied:
                token=next(iter(variants));result[name,token]=name;occupied.add(name)
        for name,variants in sorted(groups.items()):
            for token in sorted(variants):
                if (name,token) in result:continue
                # Unit alone suffices when each variant has its own unit.
                label=short_label(token,variants)
                base=f'{name} ({label})';candidate=base;index=2
                while candidate in originals or candidate in occupied:
                    candidate=f'{base} ({index})';index+=1
                result[name,token]=candidate;occupied.add(candidate)
        return result

    def party(self,buyer,gstin,invoice):
        return self.parties.get((buyer,self.party_identity(invoice)),buyer)

    def stock(self,item,invoice):
        name=self.clean(item.get('name')) or 'Item unresolved'
        return self.stocks[name,self.stock_identity(item,invoice)]
