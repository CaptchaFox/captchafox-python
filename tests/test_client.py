"""What the specification's cases leave out."""

import ast
import socket
import sys
import time
import tomllib
import unittest
from pathlib import Path
from unittest import mock

import captchafox
from captchafox import CaptchaFoxClient, Passed, Rejected, VerificationUnavailableError

from .local_siteverify import LocalSiteverify
from .support import bounded, formatted, raised

SECRET = "ok_11111111000000001111111100000000"
ROOT = Path(__file__).parent.parent


def client_of(server: LocalSiteverify, timeout: float = 2.0) -> CaptchaFoxClient:
    client = CaptchaFoxClient(SECRET, timeout)
    client._endpoint = server.endpoint
    return client


class CaptchaFoxClientTest(unittest.TestCase):
    def test_fields_arrive_unchanged_whatever_their_characters(self) -> None:
        with LocalSiteverify.answering(200, '{"success":true}') as server:
            secret = "ok_a+b&c=d %ä"
            token = "t+&=/?#% ä€"
            client = CaptchaFoxClient(secret, 2.0)
            client._endpoint = server.endpoint
            client.verify(token, "sk_1", "2001:db8::1")

            expected = {"secret": secret, "response": token, "sitekey": "sk_1", "remoteIp": "2001:db8::1"}
            self.assertEqual(expected, server.requests[0].form)
            self.assertEqual("/siteverify", server.requests[0].path)

    def test_strings_that_utf8_cannot_encode_are_sent_with_a_replacement(self) -> None:
        with LocalSiteverify.answering(200, '{"success":true}') as server:
            verification = client_of(server).verify("t\udcff", "sk_\ud800", "203.0.113.7\udfff")

            self.assertIsInstance(verification, Passed)
            expected = {"secret": SECRET, "response": "t?", "sitekey": "sk_?", "remoteIp": "203.0.113.7?"}
            self.assertEqual(expected, server.requests[0].form)

    def test_a_none_token_is_rejected_without_a_request(self) -> None:
        with LocalSiteverify.answering(200, '{"success":true}') as server:
            verification = client_of(server).verify(None)

            self.assertEqual(Rejected(error_codes=("missing-input-response",)), verification)
            self.assertEqual([], server.requests)

    def test_a_repeated_success_cannot_be_evaluated(self) -> None:
        with self.assertRaises(VerificationUnavailableError):
            captchafox._evaluate(b'{"success":false,"success":true}')

    # json of older Pythons raises RecursionError on it, json of newer ones parses it; either is an outcome.
    def test_a_deeply_nested_body_is_evaluated_or_cannot_be_evaluated(self) -> None:
        body = b'{"success":true,"x":' + b"[" * 100_000 + b"]" * 100_000 + b"}"

        try:
            verification = captchafox._evaluate(body)
        except VerificationUnavailableError:
            return

        self.assertIsInstance(verification, Passed)

    def test_constants_that_are_no_json_cannot_be_evaluated(self) -> None:
        for body in (b'{"success":true,"x":NaN}', b'{"success":true,"x":-Infinity}'):
            with self.subTest(body), self.assertRaises(VerificationUnavailableError):
                captchafox._evaluate(body)

    def test_a_body_that_is_no_utf8_cannot_be_evaluated(self) -> None:
        with self.assertRaises(VerificationUnavailableError):
            captchafox._evaluate('{"success":true,"hostname":"ä"}'.encode("latin-1"))

    def test_the_default_timeout_is_five_seconds(self) -> None:
        self.assertEqual(5.0, CaptchaFoxClient(SECRET)._timeout)

    def test_the_timeout_ends_an_answer_that_never_completes_and_closes_the_connection(self) -> None:
        with LocalSiteverify.trickling(200, '{"success":true') as server:
            client = client_of(server, timeout=1.0)
            start = time.monotonic()

            with self.assertRaises(VerificationUnavailableError):
                bounded(lambda: client.verify("token"), 10)
            elapsed = time.monotonic() - start
            self.assertLess(elapsed, 3, f"the verification took {elapsed:.1f} s")

            # The server notices the closed connection when it writes its next space.
            limit = time.monotonic() + 5
            while server.broken_at is None and time.monotonic() < limit:
                time.sleep(0.05)
            self.assertIsNotNone(server.broken_at, "the connection is still open")

    def test_the_addresses_of_siteverify_share_the_timeout(self) -> None:
        class Unanswered:
            """A socket whose connect is never answered, so that it waits for its timeout."""

            def __init__(self, *args: object) -> None:
                self._timeout = None

            def settimeout(self, timeout: float) -> None:
                self._timeout = timeout

            def connect(self, address: object) -> None:
                time.sleep(self._timeout)
                raise TimeoutError("timed out")

            def close(self) -> None:
                pass

        addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (f"192.0.2.{n}", 443)) for n in range(1, 4)]
        client = CaptchaFoxClient(SECRET, 0.5)
        start = time.monotonic()

        with mock.patch("socket.getaddrinfo", return_value=addresses), mock.patch("socket.socket", Unanswered):
            with self.assertRaises(VerificationUnavailableError):
                bounded(lambda: client.verify("token"), 10)
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 1, f"the verification took {elapsed:.1f} s")

    def test_the_secret_key_is_not_in_the_representation(self) -> None:
        client = CaptchaFoxClient(SECRET)

        self.assertNotIn(SECRET, repr(client))
        self.assertNotIn(SECRET, str(client))

    def test_nothing_is_logged(self) -> None:
        with LocalSiteverify.answering(500, "") as server, self.assertNoLogs(level="DEBUG"):
            with self.assertRaises(VerificationUnavailableError):
                client_of(server).verify("token")

    def test_an_empty_secret_key_or_no_positive_timeout_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            CaptchaFoxClient("")
        with self.assertRaises(TypeError):
            CaptchaFoxClient(None)
        for timeout in (0, -1, float("nan"), float("inf")):
            with self.subTest(timeout), self.assertRaises(ValueError):
                CaptchaFoxClient(SECRET, timeout)


class RuntimeTest(unittest.TestCase):
    def test_the_library_needs_only_the_standard_library(self) -> None:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]
        self.assertEqual([], project.get("dependencies", []))
        self.assertEqual({}, project.get("optional-dependencies", {}))

        for source in (ROOT / "src" / "captchafox").rglob("*.py"):
            for node in ast.walk(ast.parse(source.read_text("utf-8"))):
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    modules = [node.module]
                else:
                    continue
                for module in modules:
                    self.assertIn(module.partition(".")[0], sys.stdlib_module_names, f"{source.name} imports {module}")


class AnswersTest(unittest.TestCase):
    """Answers of siteverify that the specification's cases leave out."""

    def assert_unavailable(self, server: LocalSiteverify) -> None:
        error = raised(lambda: bounded(lambda: client_of(server).verify("token"), 10))
        self.assertIsInstance(error, VerificationUnavailableError)
        self.assertNotIn(SECRET, formatted(error))

    def test_a_success_with_a_status_other_than_200_cannot_be_evaluated(self) -> None:
        for status in (201, 204, 302):
            with self.subTest(status), LocalSiteverify.answering(status, '{"success":true}') as server:
                self.assert_unavailable(server)

    def test_an_answer_that_is_no_valid_http_cannot_be_evaluated(self) -> None:
        answers = {
            "a status line that is no HTTP": "garbage\r\n\r\n",
            "a body shorter than its Content-Length": 'HTTP/1.1 200 OK\r\nContent-Length: 40\r\n\r\n{"success":true}',
            "a chunk size that is no number": 'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\nzz\r\n{"success":true}\r\n0\r\n\r\n',
        }
        for name, answer in answers.items():
            with self.subTest(name), LocalSiteverify.raw(answer) as server:
                self.assert_unavailable(server)

    def test_a_chunked_success_passes(self) -> None:
        answer = 'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\na\r\n{"success"\r\n6\r\n:true}\r\n0\r\n\r\n'

        with LocalSiteverify.raw(answer) as server:
            self.assertIsInstance(client_of(server).verify("token"), Passed)
