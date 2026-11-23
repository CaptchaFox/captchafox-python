"""Uses the library as an integrator does, by its public names only: a name that goes or changes fails here."""

import unittest

import captchafox
from captchafox import CaptchaFoxClient, Passed, Rejected, VerificationUnavailableError

SECRET = "ok_11111111000000001111111100000000"
SITEKEY = "sk_11111111000000001111111100000000"


def describe(verification: Passed | Rejected) -> str:
    match verification:
        case Passed(challenge_ts=challenge_ts, hostname=hostname):
            return f"passed: {challenge_ts or ''} {hostname or ''}"
        case Rejected(error_codes=error_codes):
            return f"rejected: {','.join(error_codes)}"


class PublicInterfaceTest(unittest.TestCase):
    def test_the_public_names(self) -> None:
        self.assertEqual(
            {"CaptchaFoxClient", "Passed", "Rejected", "VerificationUnavailableError"}, set(captchafox.__all__)
        )
        self.assertTrue(issubclass(VerificationUnavailableError, Exception))

    # An empty token is rejected without a request, so no network is needed.
    def test_every_public_member_is_reachable(self) -> None:
        client = CaptchaFoxClient(SECRET)
        with_timeout = CaptchaFoxClient(SECRET, timeout=3)

        self.assertEqual("rejected: missing-input-response", describe(client.verify("")))
        self.assertEqual("rejected: missing-input-response", describe(client.verify(None)))
        verification = with_timeout.verify("", sitekey=SITEKEY, remote_ip="203.0.113.7")
        self.assertEqual("rejected: missing-input-response", describe(verification))
        self.assertFalse(verification.passed)
        self.assertFalse(verification)

    def test_outcomes_can_be_built_for_the_integrators_own_tests(self) -> None:
        passed = Passed(challenge_ts="2026-10-20T10:00:00Z", hostname="example.com")
        rejected = Rejected(error_codes=("timeout-or-duplicate",))

        self.assertEqual("passed: 2026-10-20T10:00:00Z example.com", describe(passed))
        self.assertTrue(passed.passed)
        self.assertTrue(passed)
        self.assertEqual("passed:  ", describe(Passed()))
        self.assertEqual("rejected: timeout-or-duplicate", describe(rejected))
