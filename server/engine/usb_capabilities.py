"""Bounded USB diagnostic import. JSON is evidence context, never authorization.

The live AKA path remains the separate authenticated mTLS backend. No report
can authorize calls or provide a subscriber identity, even if it says observed.
"""
import json
import re

STAGES = ('modem_at', 'card_access', 'apdu', 'usim_aka', 'epdg', 'ims',
          'voice_capability', 'incoming_call', 'outgoing_call', 'two_way_audio')
TOP = {'schema', 'product', 'version', 'timestamp_utc', 'simulated', 'identity',
       'stages', 'route_status', 'calling_authorized', 'subscriber_number_available', 'limitations'}
TOKENS = {'modem_at': {'not_tested', 'basic_at_response'},
          'card_access': {'not_tested', 'sim_ready_status_only'},
          'apdu': {'not_tested', 'fixed_select_mf_9000'}}

class InvalidCapabilityReport(ValueError):
    pass


def _unique(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise InvalidCapabilityReport('Duplicate field')
        d[k] = v
    return d


def parse_usb_report(raw):
    if not isinstance(raw, bytes) or len(raw) > 16384:
        raise InvalidCapabilityReport('Report must be bounded UTF-8 bytes')
    try:
        report = json.loads(raw, object_pairs_hook=_unique)
        if not isinstance(report, dict) or set(report) != TOP:
            raise ValueError()
        if report['schema'] != 'nexvary.usb.capabilities.v1' or report['product'] != 'NEXVARY USB Studio':
            raise ValueError()
        if type(report['simulated']) is not bool or report['calling_authorized'] is not False or report['subscriber_number_available'] is not False or report['route_status'] != 'Not Verified':
            raise ValueError()
        identity = report['identity']
        if not isinstance(identity, dict) or set(identity) != {'manufacturer','model','firmware','usb_id'}:
            raise ValueError()
        for name, value in identity.items():
            if value is None:
                continue
            pattern = r'[0-9A-Fa-f]{4}:[0-9A-Fa-f]{4}' if name == 'usb_id' else r'[A-Za-z0-9][A-Za-z0-9 ._-]{0,47}'
            if not isinstance(value, str) or not re.fullmatch(pattern, value):
                raise ValueError()
        stages = report['stages']
        if not isinstance(stages, dict) or set(stages) != set(STAGES):
            raise ValueError()
        for name, row in stages.items():
            if not isinstance(row, dict) or set(row) != {'state','evidence'}:
                raise ValueError()
            if row['state'] not in {'observed','simulated','not_verified'} or row['evidence'] not in TOKENS.get(name, {'not_tested'}):
                raise ValueError()
            if (name not in TOKENS and row['state'] != 'not_verified') or (report['simulated'] and row['state'] == 'observed'):
                raise ValueError()
            if (row['state'] == 'not_verified') != (row['evidence'] == 'not_tested'):
                raise ValueError()
        # Ignore uncontrolled timestamp/limitations rather than copying arbitrary
        # imported text into logs or control decisions.
        return {'schema': report['schema'], 'identity': identity,
                'simulated': report['simulated'], 'stages': stages,
                'route_status': 'Not Verified', 'calling_authorized': False,
                'subscriber_number_available': False, 'trusted_attestation': False}
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise InvalidCapabilityReport('Invalid redacted USB capability contract') from None
