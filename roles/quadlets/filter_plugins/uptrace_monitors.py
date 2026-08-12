import hashlib
import json

import yaml


def _parse_metric_alias(expr):
    """Convert a 'metric_name as $alias' string into a {name, alias} dict."""
    expr = expr.strip()
    if ' as ' in expr:
        name, alias = expr.split(' as ', 1)
        return {'name': name.strip(), 'alias': alias.strip()}
    return {'name': expr, 'alias': None}


def uptrace_monitors(yaml_content):
    """Extract the `monitors:` section of a Uptrace dashboard YAML template and
    convert it to a list of {name, payload, hash} MetricMonitor API payloads
    (2.0.x schema). The hash is a stable fingerprint used for idempotency."""
    data = yaml.safe_load(yaml_content) or {}
    monitors = data.get('monitors') or []
    out = []
    for m in monitors:
        payload = {
            'name': m['name'],
            'type': 'metric',
            'state': 'active',
            'notifyEveryoneByEmail': False,
            'channelIds': [],
            'params': {
                'metrics': [_parse_metric_alias(s) for s in (m.get('metrics') or [])],
                'query': '\n'.join(m.get('query') or []),
                'column': m.get('column', ''),
                'columnUnit': m.get('column_unit', ''),
                'checkNumPoint': m.get('check_num_point', 5),
                'timeOffset': m.get('time_offset', 0),
                'minAllowedValue': m.get('min_allowed_value'),
                'maxAllowedValue': m.get('max_allowed_value'),
            },
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
        ).hexdigest()
        out.append({'name': payload['name'], 'payload': payload, 'hash': digest})
    return out


class FilterModule(object):
    def filters(self):
        return {
            'uptrace_monitors': uptrace_monitors,
        }

