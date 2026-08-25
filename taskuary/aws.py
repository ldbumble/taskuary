"""AWS connector - boto3 with keys from the card (the write-only secret IS the secret
access key); leave everything blank and boto3's default chain takes over (env vars,
~/.aws/credentials, an instance role). Three report/tool types: 'aws' calls ANY service
operation, 's3_object' reads or lists a bucket, 'cloudwatch_logs' greps a log group.
"""
import json
from datetime import datetime, timedelta
from loguru import logger


def _boto3():
    try: import boto3
    except ImportError:
        # `pip install taskuary[aws]` is a TRAP on an install whose metadata predates the
        # extra (an editable install pins its dist-info at install time): pip prints
        # "does not provide the extra 'aws'", says everything is already satisfied, and
        # installs nothing. Naming the package itself always works.
        raise RuntimeError('boto3 is not installed - run: pip install boto3 '
                           '(or re-run pip install -e .[aws] from the repo)')
    return boto3


# One card, many regions. CloudWatch log groups exist PER REGION - the same account shows a
# completely different set in us-east-1 and us-east-2 - so a single region field meant half an
# account was invisible with no sign that anything was missing. The field takes a list now
# ("us-east-2, us-east-1"); one value still behaves exactly as it did.
def regions(cfg: dict) -> list:
    """The regions to sweep, in order. [None] = no region set, so boto3's own default chain
    decides (env, ~/.aws/config, an instance role) - which is what a blank field always meant."""
    out = [r.strip() for r in str(cfg.get('region') or '').replace(';', ',').replace(' ', ',').split(',') if r.strip()]
    return list(dict.fromkeys(out)) or [None]


def _key(addr: str, region):
    """What makes this object itself. A bucket is global - its name IS its identity, and the
    region only says which endpoint to read it from. A log group is regional, so its name means
    nothing without one."""
    return addr if addr.startswith('s3://') else (addr, region)


def client(cfg: dict, service: str, region: str = None):
    """`region` overrides the card - what a per-object call uses, because a discovered object
    knows which region it was found in and the card's FIRST region is only a default."""
    kw = {k: v for k, v in {'region_name': region or regions(cfg)[0],
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


def discover(store, cfg: dict, connector_id: int, actor: str = 'owner') -> dict:
    """What can these keys SEE? Every S3 bucket and CloudWatch log group is registered as
    a source with its own mode picker - report (default: selectable on the Reports tab,
    nothing polled), feed (new items shown on the Timeline), tasks (through triage), or
    off. A list that partially fails still registers what it found."""
    # WHAT MAKES AN OBJECT ITSELF differs by service, and getting this wrong loses rows either
    # way. A log group is (name, region): /aws/lambda/ingest in us-east-1 and the one in
    # us-east-2 are unrelated groups that happen to share a name, and keying on the name alone
    # registers whichever came first and drops the other. A BUCKET is its name and nothing
    # else - S3 is one global namespace - so keying a bucket on (name, region) would file the
    # same bucket twice the moment get_bucket_location answered differently than last time
    # (a permission removed, a fallback taken), splitting its mode across two rows.
    known = {}
    for row in store.list_sources(active_only=False):
        if row['Channel'] != 'aws': continue
        known[_key(row['Address'], json.loads(row.get('ConfigJson') or '{}').get('region'))] = row
    regs = regions(cfg)
    found = []                                     # [(address, region)]
    # S3 is one global namespace - listing it once per region would return the same buckets
    # every time. Each bucket's OWN region is asked for separately, because a client pointed at
    # the wrong one gets a 301 the moment it tries to read the objects.
    try:
        for b in client(cfg, 's3').list_buckets().get('Buckets') or []:
            try:
                loc = client(cfg, 's3').get_bucket_location(Bucket=b['Name']).get('LocationConstraint')
                where = loc or 'us-east-1'         # the API answers None for us-east-1, historically
            except Exception:
                where = regs[0]                    # no permission to ask: the card's first region
            found.append((f"s3://{b['Name']}", where))
    except Exception as e:
        logger.warning(f'aws discovery: s3 list failed: {e}')
    for reg in regs:
        try:
            # describe_log_groups caps at 50 PER CALL, so a single call silently truncates an
            # account with hundreds of lambdas - page until the token runs out (bounded).
            logs, tok, pages = client(cfg, 'logs', reg), None, 0
            while pages < 8:
                r = logs.describe_log_groups(limit=50, **({'nextToken': tok} if tok else {}))
                found += [(f"logs://{g['logGroupName']}", reg) for g in r.get('logGroups') or []]
                tok, pages = r.get('nextToken'), pages + 1
                if not tok: break
        except Exception as e:
            # one bad region must not cost the others: a key without permission in eu-west-1 is
            # a reason to skip eu-west-1, not to discover nothing
            logger.warning(f'aws discovery: log groups failed in {reg or "the default region"}: {e}')
    added, stamped = 0, 0
    for addr, reg in found:
        # a row discovered before the card knew about regions carries none. It is the SAME
        # object, so it is adopted and stamped - not replaced by a second copy that would take
        # the polling while the owner's mode pick sat on the row above it.
        row = known.get(_key(addr, reg)) or known.get(_key(addr, None))
        if row:
            scfg = json.loads(row.get('ConfigJson') or '{}')
            if not scfg.get('region') and reg:
                store.save_source({'SourceId': row['SourceId'],
                                   'ConfigJson': json.dumps({**scfg, 'region': reg})}, actor)
                known.pop(_key(addr, None), None)
                known[_key(addr, reg)] = {**row, 'ConfigJson': json.dumps({**scfg, 'region': reg})}
                stamped += 1
            continue
        store.save_source({'Channel': 'aws', 'Address': addr, 'ConnectorId': connector_id, 'Active': 1,
                           'Owner': 'discovered', 'ConfigJson': json.dumps({'mode': 'report', 'region': reg})}, actor)
        known[_key(addr, reg)] = {'SourceId': None, 'Address': addr,
                                  'ConfigJson': json.dumps({'mode': 'report', 'region': reg})}
        added += 1
    out = {'found': len(found), 'added': added, 'stamped': stamped, 'regions': [r for r in regs if r]}
    if not found:
        out['hint'] = ('the keys authenticate but list nothing - they need s3:ListAllMyBuckets and '
                       'logs:DescribeLogGroups (AmazonS3ReadOnlyAccess + CloudWatchLogsReadOnlyAccess '
                       'cover both). The log above says which call failed.')
    return out


def catalog(store, service: str = None) -> dict:
    """What is callable here, WITHOUT calling AWS: botocore ships the service and operation
    models on disk, so both lists are local metadata - no credentials, no region, no request.

    Typing `service` and `operation` by hand meant knowing boto3's naming from memory and
    finding out you had it wrong only when a scheduled report failed. `seen` is what discovery
    actually found in this account, first in the list, because 400-odd alphabetical service
    names is a haystack rather than a choice. `read` marks the operations that only look:
    a report is a thing you read, and describe_/list_/get_ is nearly always what you want.
    """
    import botocore.session
    from botocore import xform_name
    sess = botocore.session.get_session()
    # the objects discovery actually found, each WITH THE REGION it was found in. Handing back a
    # bare name was a real bug: a log group is (name, region) - /aws/lambda/x in us-east-2 and the
    # one in us-east-1 are unrelated groups - so a name picked from a list and run against the
    # card's FIRST region answers "The specified log group does not exist", which is true and
    # completely misleading. The region travels with the pick now.
    objs = [(s['Address'] or '', json.loads(s.get('ConfigJson') or '{}').get('region') or '')
            for s in store.list_sources(active_only=False) if s['Channel'] == 'aws']
    groups = sorted(({'name': a[len('logs://'):], 'region': r} for a, r in objs if a.startswith('logs://')),
                    key=lambda g: (g['region'], g['name']))
    buckets = sorted(({'name': a[len('s3://'):], 'region': r} for a, r in objs if a.startswith('s3://')),
                     key=lambda b: b['name'])
    seen = sorted({'logs' for _ in groups[:1]} | {'s3' for _ in buckets[:1]})
    out = {'seen': seen, 'services': sorted(sess.get_available_services()),
           'log_groups': groups, 'buckets': buckets}
    if service:
        try:
            names = [xform_name(o) for o in sess.get_service_model(service).operation_names]
        except Exception as e:
            return {**out, 'service': service, 'operations': [], 'error': str(e)[:200]}
        read = [n for n in names if n.startswith(('list_', 'describe_', 'get_', 'head_', 'query', 'scan', 'select_'))]
        out.update({'service': service, 'operations': sorted(read) + sorted(set(names) - set(read)),
                    'read': sorted(read)})
    return out


def poll_source(store, cfg: dict, src: dict, since, llm=None, file_only=False) -> int:
    """One discovered object in tasks/feed mode. s3://bucket -> a Timeline item per NEW
    object; logs://group -> ONE batched item of the new matching events (default pattern:
    errors - one row per log line would flood the funnel it feeds)."""
    from .ingest import ingest_message
    scfg = json.loads(src.get('ConfigJson') or '{}')
    # the object's OWN region, stamped on it at discovery. Sources found before the card took
    # a list have none, and the card's first region is exactly what they were found with.
    reg = scfg.get('region')
    addr, floor, n = src['Address'], since.strftime('%Y-%m-%d %H:%M:%S'), 0
    if addr.startswith('s3://'):
        bucket = addr[5:]
        r = client(cfg, 's3', reg).list_objects_v2(Bucket=bucket, MaxKeys=200)
        for o in r.get('Contents') or []:
            at = o.get('LastModified')
            stamp = at.astimezone().strftime('%Y-%m-%d %H:%M:%S') if hasattr(at, 'astimezone') else str(at)
            if stamp < floor: continue
            out = ingest_message(store, file_only=file_only, msg={
                'external_id': f"aws:{reg or '-'}:{bucket}:{o['Key']}:{stamp[:16]}", 'channel': 'aws',
                'subject': f"New in {addr}: {o['Key']}" + (f' ({reg})' if reg else ''),
                'body': f"[S3 object landed - {o.get('Size')} bytes]\ns3://{bucket}/{o['Key']}",
                'from_name': addr, 'conversation_id': f'aws:{addr}', 'sent_at': stamp,
                'source_name': addr}, llm=llm)
            n += out['status'] != 'duplicate'
    elif addr.startswith('logs://'):
        group = addr[7:]
        pat = scfg.get('pattern') or '?ERROR ?Exception ?FATAL'
        ev = client(cfg, 'logs', reg).filter_log_events(logGroupName=group, filterPattern=pat, limit=100,
                                                        startTime=int(since.timestamp() * 1000)).get('events') or []
        if ev:
            lines = '\n'.join(f"{datetime.fromtimestamp(e['timestamp'] / 1000).strftime('%H:%M:%S')} "
                              f"{(e.get('message') or '').strip()[:300]}" for e in ev[:50])
            stamp = datetime.fromtimestamp(ev[-1]['timestamp'] / 1000).strftime('%Y-%m-%d %H:%M:%S')
            out = ingest_message(store, file_only=file_only, msg={
                'external_id': f"awslogs:{reg or '-'}:{group}:{ev[-1].get('eventId') or stamp}", 'channel': 'aws',
                'subject': f"{len(ev)} matching log events in {group}" + (f' ({reg})' if reg else ''),
                'body': f"[CloudWatch {group} - pattern {pat}]\n{lines}",
                'from_name': addr, 'conversation_id': f'aws:{addr}', 'sent_at': stamp,
                'source_name': addr}, llm=llm)
            n += out['status'] != 'duplicate'
    return n


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


LOG_PAGE_CAP = 12        # one report is worth this many FilterLogEvents calls, not unbounded


def run_cloudwatch_logs(cfg: dict):
    """{"log_group", "pattern", "hours": 24} - recent events from a CloudWatch log group.
    Pattern uses CloudWatch filter syntax: '?ERROR ?Exception' means any of these words."""
    from .reports import row_limit, rows_out
    lim, mine = row_limit(cfg)
    start = int((datetime.now() - timedelta(hours=float(cfg.get('hours') or 24))).timestamp() * 1000)
    hours = float(cfg.get('hours') or 24)
    kw = {'logGroupName': cfg['log_group'], 'startTime': start, 'limit': min(max(lim + 1, 1000), 10000)}
    if cfg.get('pattern'): kw['filterPattern'] = cfg['pattern']
    where = regions(cfg)[0]
    try:
        cl = client(cfg, 'logs', where)
        # FilterLogEvents PAGES, and its pages are not full ones. It scans log streams and hands
        # back whatever that pass found, with a nextToken - so a lambda (one stream per
        # invocation) answered a single call with nine events while the rest of the day sat behind
        # the token. "9 events" then read as "a quiet day", which for a report asked to find
        # ERRORS is the worst way to be wrong. Page until the cap is covered or the token runs
        # out; PAGE_CAP stops a busy group from turning one report into a thousand calls.
        ev, tok, pages = [], None, 0
        while pages < LOG_PAGE_CAP:
            r = cl.filter_log_events(**kw, **({'nextToken': tok} if tok else {}))
            ev += r.get('events') or []
            tok, pages = r.get('nextToken'), pages + 1
            if not tok or len(ev) > lim: break
    except Exception as e:
        # "The specified log group does not exist" is true and useless: it does exist, in another
        # region. AWS cannot say that because it only knows the region it was asked about - but we
        # know which one we asked, so we say it.
        if 'ResourceNotFoundException' not in type(e).__name__ and 'does not exist' not in str(e): raise
        raise RuntimeError(f"no log group {cfg['log_group']} in {where or 'the default region'} - a log "
                           'group belongs to ONE region, so the same name in another region is a '
                           'different group. Pick it from the list again (each entry says its region), '
                           "or set this source's region to the one it lives in.") from None
    # newest first: when the cap bites, the recent end of the window is the half worth keeping,
    # and AWS hands these back oldest-first
    ev.sort(key=lambda e: e.get('timestamp') or 0, reverse=True)
    rows = [{'at': datetime.fromtimestamp(e['timestamp'] / 1000).strftime('%Y-%m-%d %H:%M:%S'),
             'stream': e.get('logStreamName'), 'message': (e.get('message') or '').strip()[:500]} for e in ev]
    hrs = f'{hours:g}h'
    head, body = rows_out(rows, lim, unit=f'events in the last {hrs}', mine=mine)
    # a scan that stopped at the page bound is not "all of it", and only this code knows
    if tok and len(ev) <= lim:
        head += f' — stopped after {LOG_PAGE_CAP} pages, so there may be more; narrow it with a filter pattern'
    return head, body
