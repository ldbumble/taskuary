"""Credentials that arrive in the mail must not leave in a prompt.

A colleague pastes an API key into an email; triage reads that mail, the coding agent is handed the
thread verbatim (`agents.task_context` writes `BodyText` straight into the prompt), and the key
is now in a request to Anthropic, OpenAI or Azure. The leak is on the way OUT, on the very first
prompt - long before any transcript is stored.

So the message row keeps the owner's mail intact (it is their inbox; a portal code emailed by a
vendor has to stay readable) and the scrub happens at the three doors a prompt can leave by.

The one rule that is easy to get wrong: a git SHA is 40 hex characters. A catch-all
"long hex string" pattern blanks out every commit hash in a coding agent prompt - which is what the
chat scrub did until it came here. Entropy only counts when the line says it holds a secret.
"""
import unittest
from unittest import mock

from taskuary import redact


class WhatCountsAsACredentialTests(unittest.TestCase):
    def test_provider_prefixes_are_replaced_by_a_labelled_placeholder(self):
        for raw, label in [('AKIA' + 'IOSFODNN7EXAMPLE', 'aws-key'),
                           ('ghp_' + 'ABCDEFGHIJKLMNOPQRSTUVWXYZ012345', 'github-token'),
                           ('xoxb-' + '1234567890-abcdefghijklmnop', 'slack-token'),
                           ('sk-' + 'proj9fK2abcdefghijklmnopqrstuvwx', 'api-key')]:
            out = redact.scrub(f'the key is {raw} - use it')
            self.assertNotIn(raw, out); self.assertIn(f'[redacted:{label}]', out)

    def test_a_password_inside_a_url_goes_but_the_host_stays(self):
        out = redact.scrub('clone https://ldbumble:hunter2pass@github.com/northwind/ledger.git now')
        self.assertNotIn('hunter2pass', out); self.assertIn('[redacted:url-credentials]', out)
        self.assertIn('github.com/northwind/ledger.git', out)     # still legible as a URL

    def test_connection_strings_lose_only_the_password(self):
        out = redact.scrub('psql postgres://admin:s3cretPw@db.internal:5432/prod')
        self.assertNotIn('s3cretPw', out); self.assertIn('db.internal:5432/prod', out)
        out = redact.scrub('Server=sql01;Database=books;User Id=sa;Password=Tr0ub4dor;')
        self.assertNotIn('Tr0ub4dor', out); self.assertIn('Server=sql01', out)

    def test_a_private_key_block_goes_whole(self):
        body = ('-----BEGIN RSA PRIVATE KEY-----\n' + 'MIIEowIBAAKCAQEA7x1\n' * 3
                + '-----END RSA PRIVATE KEY-----')
        out = redact.scrub(f'here you go:\n{body}\nthanks')
        self.assertNotIn('MIIEowIBAAKCAQEA7x1', out); self.assertIn('[redacted:private-key]', out)
        self.assertIn('thanks', out)

    def test_a_labelled_secret_goes_even_when_the_value_looks_ordinary(self):
        for line in ['password: hunter2pass', 'API_KEY = abc123def456ghi', 'client_secret: Zx9-Qq_11']:
            out = redact.scrub(line)
            self.assertIn('[redacted:', out)
            self.assertNotIn(line.split(maxsplit=1)[-1].lstrip(':= '), out)

    def test_a_json_client_secret_goes(self):
        raw = '{"client_id": "visible-app", "client_secret": "super-secret-app"}'
        out = redact.scrub(raw)
        self.assertNotIn('super-secret-app', out)
        self.assertIn('visible-app', out)
        self.assertIn('[redacted:secret]', out)

    def test_a_jwt_goes(self):
        jwt = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K27u'
        self.assertNotIn(jwt, redact.scrub(f'Authorization: Bearer {jwt}'))


class WhatMustSurviveTests(unittest.TestCase):
    """Over-redaction is a bug too: the coding agent reads these."""

    def test_a_git_sha_is_not_a_secret(self):
        sha = 'da8dae0012ab34cd56ef7890abcdef1234567890'
        self.assertIn(sha, redact.scrub(f'the regression landed in {sha}, please revert it'))

    def test_a_long_hex_digest_in_ordinary_prose_survives(self):
        digest = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
        self.assertIn(digest, redact.scrub(f'the bundle hash is {digest} on master'))

    def test_ordinary_mail_is_returned_unchanged(self):
        body = 'Hi Alex - the March invoices are attached. Can you approve by Friday? Thanks, Dana'
        self.assertEqual(body, redact.scrub(body))

    def test_empty_and_none_are_safe(self):
        self.assertEqual('', redact.scrub('')); self.assertEqual('', redact.scrub(None))


class TheOwnersMailIsNotTouchedTests(unittest.TestCase):
    def test_storing_a_message_keeps_the_body_verbatim(self):
        """A vendor's one-time portal code is exactly the kind of thing that looks like a secret
        and is the whole point of the mail. The inbox is a mirror; only the prompt is scrubbed."""
        from taskuary.store import MemoryStore
        s = MemoryStore()
        body = 'Your portal code is sk-' + 'proj9fK2abcdefghijklmnopqrstuvwx' + ' - expires in 10 minutes'
        mid = s.add_message({'Channel': 'email', 'Direction': 'in', 'FromEmail': 'vendor@example.com',
                             'Subject': 'Your code', 'BodyText': body, 'SentAt': '2026-09-15T09:00:00'})
        self.assertEqual(body, s.get_message(mid)['BodyText'])



class AShownLineCarriesNoPasswordTests(unittest.TestCase):
    """WALK 19: his "Post on our Chirp account (..., username northwind, password chirp-pass)" became the task's title, and the rail, the
    phone and the Advisor's chat carried the password. A prompt keeps it (the agent signs in with it); what is shown never does."""
    LINE = 'Post the budget tip on Chirp - username northwind, my password is Hunter2!x9'

    def test_a_said_password_is_taken_from_what_is_shown_and_only_there(self):
        self.assertEqual(redact.shown(self.LINE), 'Post the budget tip on Chirp - username northwind, my password is [redacted:password]')
        self.assertEqual(redact.shown('password chirp-pass)'), 'password [redacted:password])')
        self.assertEqual(redact.scrub(self.LINE), self.LINE, 'a prompt keeps it: the agent he gave it to signs in with it')
        for t in ('Reset password is broken', 'password reset', 'pin the tab', 'password: [redacted:secret]'): self.assertEqual(redact.shown(t), t)

    def test_his_title_the_phone_and_the_advisor_carry_no_password(self):
        from taskuary import general, lookout, messengers, remote_assistant
        from taskuary.store import MemoryStore
        s = MemoryStore()
        tid = s.create_task({'Title': general.title_of(self.LINE), 'Summary': self.LINE, 'Kind': 'task', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
        t = s.get_task(tid)
        self.assertNotIn('Hunter2', t['Title']); self.assertIn('Hunter2', t['Summary'])
        self.assertTrue(general.own_title(s, tid, self.LINE), 'still his words as made, so the agent may name it')
        s.update_task(tid, {'Title': 'Chirp: password is Hunter2!x9'}, 'agent')
        self.assertNotIn('Hunter2', s.get_task(tid)['Title'])
        s._exec('UPDATE task SET Title=? WHERE TaskId=?', (self.LINE, tid))          # a title kept from before
        self.assertEqual(s.scrub_titles(), 1); self.assertNotIn('Hunter2', s.get_task(tid)['Title'])
        cid = s.get_connector_by_type('whatsapp')['ConnectorId']
        with mock.patch.object(messengers, 'wa_send') as sent:
            remote_assistant.send(s, 'whatsapp', '15551234567@s.whatsapp.net', f'Open: {self.LINE}', cid, asked=True)
        self.assertTrue(sent.called); self.assertFalse(any('Hunter2' in str(c.args) for c in sent.call_args_list))
        self.assertNotIn('Hunter2', lookout.asked({'type': 'lookout', 'whole': True, 'window': f'TASKS: task{tid} open: {self.LINE}'}))


class SsnAndDateOfBirthTests(unittest.TestCase):
    """The owner, 2026-11-25: "SSN or birthdays are never sent to endpoints, even HIPAA AI". An SSN by its shape or its label, a date of
    birth only by its label - a bare date is a meeting or a deadline. Invented numbers from the never-issued ranges (000, 666, 9xx)."""

    def test_an_ssn_goes_by_its_shape_or_its_label(self):
        for raw, want in [('SSN: 666-12-3456', 'SSN: [redacted:ssn]'), ('ssn 666123456', 'ssn [redacted:ssn]'),
                          ('Social Security Number is 900 12 3456', 'Social Security Number is [redacted:ssn]'),
                          ('my social: 000-11-2222', 'my social: [redacted:ssn]'), ('member 666-12-3456 on file', 'member [redacted:ssn] on file'),
                          ('{"ssn": "900123456"}', '{"ssn": "[redacted:ssn]"}')]:
            self.assertEqual(redact.scrub(raw), want)

    def test_a_date_of_birth_goes_only_where_a_label_names_it(self):
        for raw, want in [('DOB: 01/02/1980', 'DOB: [redacted:date-of-birth]'), ('date of birth 1980-01-02', 'date of birth [redacted:date-of-birth]'),
                          ('Born on March 3, 1980', 'Born on [redacted:date-of-birth]'), ('birthday is 3rd of March', 'birthday is [redacted:date-of-birth]'),
                          ('"dateOfBirth": "1979-12-31"', '"dateOfBirth": "[redacted:date-of-birth]"'), ('D.O.B. 02/14/1975', 'D.O.B. [redacted:date-of-birth]')]:
            self.assertEqual(redact.scrub(raw), want)

    def test_what_only_looks_like_one_stays(self):
        for t in ('Meeting on 01/02/2026', 'due March 3, 2026', 'invoice 2026-11-25', 'call 555-123-4567', 'zip 12345-6789', 'order 123456789',
                  'DOB unknown, call 02/03/2026?', 'born in 1980', 'a social event on May 3', 'revert da8dae0012345', 'ref 666-12-3456-7'):
            self.assertEqual(redact.scrub(t), t)

    def test_his_screen_and_store_keep_the_number_only_what_leaves_loses_it(self):
        from taskuary import concierge
        line = 'Patient DOB 04/05/1961, SSN 666-12-3456 - book the follow-up'
        self.assertEqual(redact.shown(line), line); self.assertEqual(concierge.redact(line), line)
        self.assertEqual(redact.secrets(line), line)
        self.assertEqual(redact.scrub(line), 'Patient DOB [redacted:date-of-birth], SSN [redacted:ssn] - book the follow-up')
        self.assertEqual(redact.scrub(redact.scrub(line)), redact.scrub(line))
        self.assertTrue(redact.holds_placeholder(redact.scrub(line)), 'a reply copying it is refused at the send (outbound)')


if __name__ == '__main__':
    unittest.main()
