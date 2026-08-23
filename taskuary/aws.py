"""AWS connector - boto3 with keys from the card (the write-only secret IS the secret
access key); leave everything blank and boto3's default chain takes over (env vars,
~/.aws/credentials, an instance role). Three report/tool types: 'aws' calls ANY service
operation, 's3_object' reads or lists a bucket, 'cloudwatch_logs' greps a log group.
"""
import json
from datetime import datetime, timedelta


def _boto3():
    try: import boto3
    except ImportError: raise RuntimeError('boto3 not installed - pip install taskuary[aws]')
    return boto3


def client(cfg: dict, service: str):
    kw = {k: v for k, v in {'region_name': cfg.get('region'),
                            'aws_access_key_id': cfg.get('access_key_id'),
                            'aws_secret_access_key': cfg.get('secret_access_key')}.items() if v}
    return _boto3().client(service, **kw)


def test(cfg: dict) -> dict:
    """STS caller identity - proves the keys (or the default chain) actually authenticate."""
    try:
        who = client(cfg, 'sts').get_caller_identity()
        return {'ok': True, 'detail': f"authenticated · account {who['Account']} · {who['Arn']}"}
    except Exception as e:
        return {'ok': False, 'error': str(e)[:500]}


def dot_path(data, path):
    for k in (path or '').split('.'):
        if k: data = data[int(k)] if isinstance(data, list) else (data or {}).get(k)
    return data


def run_aws(cfg: dict):
    """{"service", "operation", "params": {...}, "path": "a.b"} - any boto3 call: service=s3
    operation=list_buckets, service=logs operation=describe_log_groups, service=athena...
    A list at `path` (or the first list in the response) comes back row-capped and honest."""
    from .reports import row_limit, rows_out, BODY_CHARS
    out = getattr(client(cfg, cfg['service']), cfg['operation'])(**(cfg.get('params') or {}))
    if isinstance(out, dict): out.pop('ResponseMetadata', None)
    data = dot_path(out, cfg.get('path')) if cfg.get('path') else out
    if isinstance(data, dict) and not cfg.get('path'):
        lists = [v for v in data.values() if isinstance(v, list)]
        if len(lists) == 1 and len(data) == 1: data = lists[0]   # the one-key list envelope
    if isinstance(data, list):
        lim, mine = row_limit(cfg)
        return rows_out(data, lim, unit='items', mine=mine)
    return 'ok', json.dumps(data, indent=1, default=str)[:BODY_CHARS]


def run_s3_object(cfg: dict):
    """{"bucket", "key"} fetches the object itself (text head); {"bucket", "prefix"} lists
    what's under it (key, size, modified)."""
    from .reports import row_limit, rows_out, BODY_CHARS
    s3 = client(cfg, 's3')
    if cfg.get('key'):
        o = s3.get_object(Bucket=cfg['bucket'], Key=cfg['key'])
        raw = o['Body'].read(BODY_CHARS + 1)
        size = int(o.get('ContentLength') or len(raw))
        head = f"s3://{cfg['bucket']}/{cfg['key']} · {size} bytes" + (' (shown truncated)' if len(raw) > BODY_CHARS else '')
        return head, raw.decode('utf-8', errors='replace')[:BODY_CHARS]
    lim, mine = row_limit(cfg)
    r = s3.list_objects_v2(Bucket=cfg['bucket'], Prefix=cfg.get('prefix') or '', MaxKeys=min(lim + 1, 1000))
    rows = [{'key': o['Key'], 'size': o['Size'], 'modified': str(o['LastModified'])} for o in r.get('Contents') or []]
    return rows_out(rows, lim, unit='objects', mine=mine)


def run_cloudwatch_logs(cfg: dict):
    """{"log_group", "pattern", "hours": 24} - recent events from a CloudWatch log group.
    Pattern uses CloudWatch filter syntax: '?ERROR ?Exception' means any of these words."""
    from .reports import row_limit, rows_out
    lim, mine = row_limit(cfg)
    start = int((datetime.now() - timedelta(hours=float(cfg.get('hours') or 24))).timestamp() * 1000)
    kw = {'logGroupName': cfg['log_group'], 'startTime': start, 'limit': min(lim + 1, 10000)}
    if cfg.get('pattern'): kw['filterPattern'] = cfg['pattern']
    ev = client(cfg, 'logs').filter_log_events(**kw).get('events') or []
    rows = [{'at': datetime.fromtimestamp(e['timestamp'] / 1000).strftime('%Y-%m-%d %H:%M:%S'),
             'stream': e.get('logStreamName'), 'message': (e.get('message') or '').strip()[:500]} for e in ev]
    return rows_out(rows, lim, unit='events', mine=mine)
