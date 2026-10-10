"""Untrusted reader progress context. Never enables gateway or authenticates."""
import json
FIELDS={'schema','version','simulated','scope','direct_select_mf','ef_dir_read','usim_selected',
        'pcsc_enumerated','aka_verified','calling_authorized','physical_atr_available','electrical_reset_available'}
class InvalidReaderEvidence(ValueError):pass

def parse_reader_evidence(raw):
    def unique(items):
        value={}
        for k,v in items:
            if k in value:raise InvalidReaderEvidence('Duplicate field.')
            value[k]=v
        return value
    try:
        if not isinstance(raw,bytes) or len(raw)>2048:raise ValueError()
        data=json.loads(raw,object_pairs_hook=unique)
        if not isinstance(data,dict) or set(data)!=FIELDS or data['schema']!='nexvary.virtual-sim.v1' or data['scope']!='directory_read_only':raise ValueError()
        if not isinstance(data['version'],str) or len(data['version'])>32:raise ValueError()
        if any(type(data[k]) is not bool for k in FIELDS-{'schema','version','scope'}):raise ValueError()
        if any(data[k] for k in ('aka_verified','calling_authorized','physical_atr_available','electrical_reset_available')):raise ValueError()
        if data['ef_dir_read'] and not data['direct_select_mf']:raise ValueError()
        if data['usim_selected'] and not data['ef_dir_read']:raise ValueError()
        # Import provenance can be spoofed, so even pcsc_enumerated=true is
        # strictly diagnostic; the live mTLS backend remains independent.
        return dict(data,trusted_attestation=False,gateway_enabled=False)
    except (ValueError,TypeError,KeyError,UnicodeError,RecursionError):
        raise InvalidReaderEvidence('Invalid bounded virtual SIM evidence.') from None
