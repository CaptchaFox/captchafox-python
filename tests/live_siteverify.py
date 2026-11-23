"""Verifies the public test keys against CaptchaFox's siteverify; needs the network. Its name keeps it out of the
suite: `make test-live` runs it.
"""

import unittest

from captchafox import CaptchaFoxClient, Passed, Rejected

PASSING_SECRET = "ok_11111111000000001111111100000000"
FAILING_SECRET = "ok_FFFFFFFF00000000FFFFFFFF00000000"
SITEKEY = "sk_11111111000000001111111100000000"
TOKEN = "11111111000000001111111100000000"


class LiveSiteverifyTest(unittest.TestCase):
    def test_the_test_key_passes(self) -> None:
        self.assertIsInstance(CaptchaFoxClient(PASSING_SECRET).verify(TOKEN), Passed)

    def test_the_test_key_passes_with_sitekey_and_remote_ip(self) -> None:
        self.assertIsInstance(CaptchaFoxClient(PASSING_SECRET).verify(TOKEN, SITEKEY, "203.0.113.7"), Passed)

    def test_the_failing_test_key_is_rejected(self) -> None:
        verification = CaptchaFoxClient(FAILING_SECRET).verify(TOKEN)

        self.assertIsInstance(verification, Rejected)
        self.assertEqual(("timeout-or-duplicate",), verification.error_codes)
