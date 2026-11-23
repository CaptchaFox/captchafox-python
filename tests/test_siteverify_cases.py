"""Runs every case of the siteverify specification against a local siteverify."""

import json
import unittest
from pathlib import Path

import captchafox
from captchafox import CaptchaFoxClient, Passed, Rejected, VerificationUnavailableError

from .local_siteverify import LocalSiteverify, refusing_endpoint
from .support import bounded, formatted, raised

SPECIFICATION = json.loads((Path(__file__).parent / "__fixtures__" / "siteverify-cases.json").read_text("utf-8"))
TIMEOUT = 5.0
# Short, so that the cases of a siteverify that stops answering end quickly.
SILENCE_TIMEOUT = 1.0
CASE_BOUND = 10.0


class SiteverifyCasesTest(unittest.TestCase):
    def test_every_case(self) -> None:
        for case in SPECIFICATION["cases"]:
            with self.subTest(case["name"]):
                self._run(case)

    def test_the_endpoint_is_the_one_of_the_specification(self) -> None:
        self.assertEqual(SPECIFICATION["endpoint"], captchafox._ENDPOINT)

    def _run(self, case: dict) -> None:
        given = case["input"]
        answer = case["answer"]
        secret = given["secret"]

        server = None
        timeout = TIMEOUT
        if answer is None:
            server = LocalSiteverify.answering(500, "")
            endpoint = server.endpoint
        elif "error" not in answer:
            server = LocalSiteverify.answering(answer["status"], answer["body"])
            endpoint = server.endpoint
        else:
            match answer["error"]:
                case "timeout":
                    server = LocalSiteverify.silent()
                    endpoint = server.endpoint
                    timeout = SILENCE_TIMEOUT
                case "stall":
                    server = LocalSiteverify.stalling(answer["status"], answer["body"])
                    endpoint = server.endpoint
                    timeout = SILENCE_TIMEOUT
                case "connection":
                    endpoint = refusing_endpoint()
                case error:
                    raise ValueError(f"unknown answer error {error}")

        try:
            client = CaptchaFoxClient(secret, timeout)
            client._endpoint = endpoint

            def call() -> Passed | Rejected:
                return client.verify(given["response"], given.get("sitekey"), given.get("remoteIp"))

            self._expect_outcome(case["expect"], secret, call)
            self._expect_request(case["request"], server)
        finally:
            if server is not None:
                server.close()

    def _expect_outcome(self, expect: dict, secret: str, call) -> None:
        match expect["outcome"]:
            case "passed":
                verification = bounded(call, CASE_BOUND)
                self.assertIsInstance(verification, Passed)
                self.assertTrue(verification.passed)
                self.assertTrue(verification)
                self.assertEqual(expect.get("challengeTs"), verification.challenge_ts)
                self.assertEqual(expect.get("hostname"), verification.hostname)
            case "rejected":
                verification = bounded(call, CASE_BOUND)
                self.assertIsInstance(verification, Rejected)
                self.assertFalse(verification.passed)
                self.assertFalse(verification)
                self.assertEqual(tuple(expect["errorCodes"]), verification.error_codes)
            case "unavailable":
                error = raised(lambda: bounded(call, CASE_BOUND))
                self.assertIsInstance(error, VerificationUnavailableError)
                self.assertNotIn(secret, formatted(error))
            case outcome:
                self.fail(f"unknown outcome {outcome}")

    def _expect_request(self, request: dict | None, server: LocalSiteverify | None) -> None:
        if request is None:
            if server is not None:
                self.assertEqual([], server.requests, "no request arrives")
            return

        self.assertEqual(1, len(server.requests), "one request arrives")
        received = server.requests[0]
        self.assertEqual("POST", received.method)
        self.assertEqual("/siteverify", received.path)
        self.assertEqual("application/x-www-form-urlencoded", received.content_type)
        self.assertEqual(request, received.form)

