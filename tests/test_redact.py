"""Credentials that arrive in the mail must not leave in a prompt.

A colleague pastes an API key into an email; triage reads that mail, the coder is handed the
thread verbatim (`agents.task_context` writes `BodyText` straight into the prompt), and the key
is now in a request to Anthropic, OpenAI or Azure. The leak is on the way OUT, on the very first
prompt - long before any transcript is stored.

So the message row keeps the owner's mail intact (it is their inbox; a portal code emailed by a
vendor has to stay readable) and the scrub happens at the three doors a prompt can leave by.

The one rule that is easy to get wrong: a git SHA is 40 hex characters. A catch-all
"long hex string" pattern blanks out every commit hash in a coder prompt - which is what the
chat scrub did until it came here. Entropy only counts when the line says it holds a secret.
"""
import unittest

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
    """Over-redaction is a bug too: the coder reads these."""

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


if __name__ == '__main__':
    unittest.main()
