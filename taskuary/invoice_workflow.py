"""State machine for the Zoho monthly invoice workflow.

A schedule opens a batch; it never creates or sends an invoice by itself.  The operator confirms
the amounts, Prepare creates/reuses Zoho *drafts*, and ordinary Taskuary Review approvals send
one customer at a time.  Every transition is persisted, so leaving the page loses nothing.
"""
import json
from datetime import date, datetime


def period_now(): return date.today().strftime('%Y-%m')


def _cfg(source): return json.loads(source.get('ConfigJson') or '{}')


def _reference(source_id, customer_id, period):
    return f'TASKUARY-{int(source_id)}-{period}-{customer_id}'[:100]


def _roll_email(text, previous, invoice_number, period):
    """Keep last month's approved wording while advancing identifiers we know are stale."""
    out = str(text or '')
    if previous:
        if previous.get('InvoiceNumber') and invoice_number:
            out = out.replace(str(previous['InvoiceNumber']), str(invoice_number))
        old_period = str(previous.get('Period') or '')
        if old_period:
            out = out.replace(old_period, period)
            try:
                old_label = datetime.strptime(old_period, '%Y-%m').strftime('%B %Y')
                new_label = datetime.strptime(period, '%Y-%m').strftime('%B %Y')
                out = out.replace(old_label, new_label)
            except ValueError: pass
    return out


def _connection(store, connector_id, action='zoho_invoice_draft'):
    from . import scopes, zoho
    c = store.get_connector(connector_id, with_secret=True)
    if not c or c.get('Type') != 'zoho_invoice': raise RuntimeError('choose a Zoho Invoice connector for this workflow')
    if not c.get('Active'): raise RuntimeError('the Zoho Invoice connection is off')
    scopes.require(c, action)
    return zoho.connection(store, connector_id)


def _status(store, batch_id):
    rows = store.invoice_items(batch_id)
    states = {x.get('Status') for x in rows}
    if rows and states <= {'sent', 'skipped'}: status = 'done'
    elif 'error' in states: status = 'needs_attention'
    elif states & {'review_ready', 'draft'}: status = 'review'
    elif rows and all(x.get('Amount') not in (None, '') for x in rows): status = 'ready'
    else: status = 'needs_amounts'
    store.update_invoice_batch(batch_id, {'Status': status})
    return status


def detail(store, batch_id):
    batch = store.invoice_batch(batch_id)
    if not batch: return None
    return {**batch, 'items': store.invoice_items(batch_id)}


def open_batch(store, source, period=None):
    """Open one period once and copy prior totals as editable suggestions."""
    from . import zoho
    cfg, period = _cfg(source), str(period or period_now())
    if len(period) != 7 or period[4] != '-': raise ValueError('period must be YYYY-MM')
    customers = cfg.get('customers') or []
    if not customers: raise RuntimeError('choose at least one Zoho customer before running this workflow')
    connector_id = int(cfg.get('connector_id') or source.get('ConnectorId') or 0)
    conn = _connection(store, connector_id, 'zoho_invoices')
    existed = store.invoice_batch_for(source['SourceId'], period)
    bid = store.create_invoice_batch(source['SourceId'], period)
    if not existed:
        for customer in customers:
            cid = str(customer.get('customer_id') or '')
            if not cid: continue
            fields = {'BatchId': bid, 'ConnectorId': connector_id, 'CustomerId': cid,
                      'CustomerName': customer.get('customer_name') or cid,
                      'Recipient': customer.get('recipient') or '', 'Currency': customer.get('currency') or 'USD',
                      'Reference': _reference(source['SourceId'], cid, period), 'Status': 'needs_amount'}
            try:
                prior = zoho.latest_invoice(conn, cid, period)
                if prior:
                    total = float(prior.get('total') or 0)
                    fields.update({'PreviousAmount': total, 'Amount': total,
                                   'TemplateInvoiceId': str(prior.get('invoice_id') or ''),
                                   'Status': 'ready' if total > 0 else 'needs_amount'})
                else:
                    fields['Error'] = 'No prior sent invoice was found. Create the first invoice in Zoho, then refresh this batch.'
            except Exception as e:
                fields['Error'] = f'Could not read the prior invoice: {str(e)[:240]}'
            store.add_invoice_item(fields)
        title = cfg.get('title') or source.get('Address') or 'Monthly invoices'
        stamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        mid = store.add_message({'ExternalId': f'invoice-batch:{source["SourceId"]}:{period}',
            'ConversationId': f'invoice-workflow:{source["SourceId"]}', 'Channel': 'report',
            'SourceName': title, 'Subject': f'{title} — {period} amounts ready to confirm',
            'FromName': title, 'SentAt': stamp,
            'BodyText': f'{len(store.invoice_items(bid))} customer invoices are staged. Confirm the amounts in Reports, then prepare drafts for Review.',
            'Status': 'feed'})
        store.add_route(mid, None, 'feed', None, 'monthly invoice workflow opened; no invoices created or sent', [], 'report')
        store.update_invoice_batch(bid, {'MessageId': mid})
        store.audit('invoice_batch', bid, 'open', 'report', 'agent', {'source_id': source['SourceId'], 'period': period})
    _status(store, bid)
    return detail(store, bid)


def update_amount(store, batch_id, item_id, values):
    row = store.invoice_item(item_id)
    if not row or row.get('BatchId') != batch_id: raise KeyError('invoice item not found in this batch')
    if row.get('Status') in ('sent', 'review_ready'): raise ValueError('this item is already prepared; reject its Review draft before changing the amount')
    patch = {k: values[k] for k in ('Amount','Recipient','Description') if k in values}
    if 'Amount' in patch:
        try: patch['Amount'] = round(float(str(patch['Amount']).replace(',', '').replace('$', '')), 2)
        except (TypeError, ValueError): raise ValueError('amount must be a number')
        if patch['Amount'] <= 0: raise ValueError('amount must be greater than zero')
    patch.update({'Status': 'ready' if patch.get('Amount', row.get('Amount')) else 'needs_amount', 'Error': None})
    out = store.update_invoice_item(item_id, patch); _status(store, batch_id)
    return out


def prepare(store, batch_id):
    """Create draft invoices and durable Review rows. One failure does not hide other customers."""
    from . import zoho
    batch = store.invoice_batch(batch_id)
    if not batch: raise KeyError('invoice batch not found')
    source = store.get_source(batch['SourceId']); cfg = _cfg(source)
    made, reused, errors = 0, 0, []
    for item in store.invoice_items(batch_id):
        if item.get('Status') in ('sent', 'skipped', 'review_ready'): continue
        if not item.get('Amount'):
            errors.append(f"{item.get('CustomerName')}: amount is missing"); continue
        try:
            conn = _connection(store, item['ConnectorId'])
            template = item.get('TemplateInvoiceId')
            if not template:
                prior = zoho.latest_invoice(conn, item['CustomerId'], batch['Period'])
                template = str((prior or {}).get('invoice_id') or '')
                if template: store.update_invoice_item(item['ItemId'], {'TemplateInvoiceId': template})
            if not template: raise RuntimeError('no prior invoice exists to duplicate')
            inv = zoho.create_draft_from(conn, template, item['Amount'], item['Reference'], batch['Period'])
            invoice_id = str(inv.get('invoice_id') or '')
            if not invoice_id: raise RuntimeError('Zoho created no invoice id')
            mail = zoho.email_content(conn, invoice_id)
            previous = store.last_sent_invoice_item(batch['SourceId'], item['CustomerId'], batch['Period'])
            raw_subject = (previous or {}).get('Subject') or mail.get('subject') or f"Invoice for {batch['Period']}"
            raw_body = (previous or {}).get('Body') or mail.get('body') or f"Please find invoice {inv.get('invoice_number') or ''} attached."
            subject = _roll_email(raw_subject, previous, inv.get('invoice_number'), batch['Period'])
            body = _roll_email(raw_body, previous, inv.get('invoice_number'), batch['Period'])
            recipient = item.get('Recipient') or ', '.join(mail.get('to') or [])
            title = cfg.get('title') or source.get('Address') or 'Monthly invoices'
            external_id = f'zoho-draft:{invoice_id}'
            prior_msg = store.message_by_external(external_id)
            prior_review = next((r for r in store.reviews_for_message(prior_msg['MessageId'])
                                 if r.get('Status') == 'pending'), None) if prior_msg else None
            if prior_review:
                store.update_invoice_item(item['ItemId'], {'InvoiceId': invoice_id,
                    'InvoiceNumber': inv.get('invoice_number'), 'ReviewId': prior_review['ReviewId'],
                    'Subject': prior_msg.get('Subject') or subject, 'Body': prior_review.get('DraftText') or body,
                    'Recipient': recipient, 'Status': 'review_ready', 'Error': None})
                reused += 1
                continue
            mid = store.add_message({'ExternalId': f'zoho-draft:{invoice_id}',
                'ConversationId': f'zoho-invoice:{item["CustomerId"]}', 'Channel': 'zoho_invoice',
                'SourceName': title, 'Subject': subject, 'FromName': 'Taskuary', 'SentAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'BodyText': body, 'Direction': 'out', 'Status': 'draft'})
            deliver = {'kind': 'zoho_invoice', 'channel': 'zoho_invoice', 'to': recipient,
                       'subject': subject, 'invoice_id': invoice_id, 'item_id': item['ItemId'],
                       'batch_id': batch_id, 'period': batch['Period'], 'customer': item['CustomerName'],
                       'amount': item['Amount'], 'previous_amount': item.get('PreviousAmount'),
                       'connector_id': item['ConnectorId'], 'invoice_number': inv.get('invoice_number')}
            rid = store.add_review({'MessageId': mid, 'Kind': 'outbound', 'Status': 'pending', 'DraftText': body,
                'Reason': f"{item['CustomerName']} · {item.get('Currency') or 'USD'} {float(item['Amount']):,.2f} · approve to send from Zoho",
                'Deliver': json.dumps(deliver)})
            store.update_invoice_item(item['ItemId'], {'InvoiceId': invoice_id,
                'InvoiceNumber': inv.get('invoice_number'), 'ReviewId': rid, 'Subject': subject,
                'Body': body, 'Recipient': recipient, 'Status': 'review_ready', 'Error': None})
            reused += int(bool(inv.get('existing'))); made += int(not inv.get('existing'))
        except Exception as e:
            msg = str(e)[:300]; errors.append(f"{item.get('CustomerName')}: {msg}")
            store.update_invoice_item(item['ItemId'], {'Status': 'error', 'Error': msg})
    _status(store, batch_id)
    store.audit('invoice_batch', batch_id, 'prepare', 'owner', detail={'created': made, 'reused': reused, 'errors': len(errors)})
    return {'ok': not errors, 'created': made, 'reused': reused, 'errors': errors, 'batch': detail(store, batch_id)}


def mark_sent(store, item_id, subject, body):
    item = store.invoice_item(item_id)
    if not item: return
    store.update_invoice_item(item_id, {'Status': 'sent', 'Subject': subject, 'Body': body, 'Error': None})
    _status(store, item['BatchId'])


def mark_send_error(store, item_id, error):
    item = store.invoice_item(item_id)
    if not item: return
    store.update_invoice_item(item_id, {'Status': 'review_ready', 'Error': str(error)[:300]})
    _status(store, item['BatchId'])


def mark_skipped(store, item_id):
    item = store.invoice_item(item_id)
    if not item: return
    store.update_invoice_item(item_id, {'Status': 'skipped', 'Error': None})
    _status(store, item['BatchId'])


def run_report(store, source, cfg):
    batch = open_batch(store, source)
    body = f"{len(batch['items'])} customer invoice(s) staged for {batch['Period']}. Confirm amounts, then prepare drafts. Nothing has been sent."
    return {'message_id': batch.get('MessageId'), 'subject': f"{cfg.get('title') or source.get('Address')} — {batch['Period']} batch open",
            'files': 0, 'summary': body, 'batch_id': batch['BatchId']}
