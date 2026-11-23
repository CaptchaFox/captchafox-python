"""Verifies tokens of the CaptchaFox widget with siteverify."""

import http.client
import io
import json
import math
import socket
import ssl
import time
from dataclasses import dataclass
from typing import ClassVar
from urllib.parse import SplitResult, urlencode, urlsplit

__all__ = ["CaptchaFoxClient", "Passed", "Rejected", "VerificationUnavailableError"]

_ENDPOINT = "https://api.captchafox.com/siteverify"


@dataclass(frozen=True, kw_only=True)
class Passed:
    """siteverify answered ``"success": true``."""

    passed: ClassVar[bool] = True

    #: The time of the challenge as siteverify sent it, an ISO 8601 timestamp.
    challenge_ts: str | None = None
    #: The hostname of the site where the challenge was solved.
    hostname: str | None = None


@dataclass(frozen=True, kw_only=True)
class Rejected:
    """siteverify answered ``"success": false``, or the token was empty."""

    passed: ClassVar[bool] = False

    #: The error codes of siteverify, such as ``timeout-or-duplicate``, possibly none.
    error_codes: tuple[str, ...]

    # Every object is true by default, so `if client.verify(token):` would let a rejection through.
    def __bool__(self) -> bool:
        return False


class VerificationUnavailableError(Exception):
    """siteverify could not be evaluated: it was not reached, did not answer in time, answered with an HTTP status
    other than 200, or with a body that is no JSON object with a boolean ``success``. Whether the protected request
    passes then is the caller's decision. The message never contains the secret key.
    """


class CaptchaFoxClient:
    """Verifies tokens of the CaptchaFox widget with the secret key of a site. Create it once and reuse it; it is
    thread-safe.
    """

    def __init__(self, secret: str, timeout: float = 5.0) -> None:
        """``timeout`` is how long a verification may take in seconds, from connecting to siteverify to the end of
        its answer.
        """
        if not isinstance(secret, str):
            raise TypeError("the secret key is no string")

        if not secret:
            raise ValueError("the secret key is empty")

        if not (timeout > 0 and math.isfinite(timeout)):
            raise ValueError("the timeout is not a positive number of seconds")

        self._secret = secret
        self._timeout = timeout
        self._endpoint = _ENDPOINT
        self._context = ssl.create_default_context()

    def verify(self, token: str | None, sitekey: str | None = None, remote_ip: str | None = None) -> Passed | Rejected:
        """Verifies a token, issued for ``sitekey`` to a visitor at ``remote_ip``; each of them is sent only when it
        is not ``None`` or empty. An empty or ``None`` token is rejected with ``missing-input-response`` without a
        request.

        :raises VerificationUnavailableError: if siteverify cannot be evaluated
        """
        if not token:
            return Rejected(error_codes=("missing-input-response",))

        endpoint = urlsplit(self._endpoint)
        request = _request(endpoint, self._secret, token, sitekey, remote_ip)
        try:
            body = self._post(endpoint, request)
        except TimeoutError as e:
            raise VerificationUnavailableError(f"siteverify did not answer within {self._timeout} seconds") from e
        except OSError as e:
            raise VerificationUnavailableError("siteverify could not be reached") from e
        except http.client.HTTPException as e:
            raise VerificationUnavailableError("siteverify answered with no valid HTTP response") from e

        return _evaluate(body)

    def _post(self, endpoint: SplitResult, request: memoryview) -> bytes:
        https = endpoint.scheme == "https"
        deadline = time.monotonic() + self._timeout
        sock = _connect(endpoint.hostname, endpoint.port or (443 if https else 80), deadline)
        try:
            if https:
                # The timeout of a socket bounds the whole handshake.
                sock.settimeout(_remaining(deadline))
                sock = self._context.wrap_socket(sock, server_hostname=endpoint.hostname)

            # sendall of a TLS socket gives each of its sends the whole timeout.
            while request:
                sock.settimeout(_remaining(deadline))
                request = request[sock.send(request) :]

            response = http.client.HTTPResponse(_DeadlineReader(sock, deadline), method="POST")
            try:
                response.begin()
                if response.status != 200:
                    raise VerificationUnavailableError(f"siteverify answered with HTTP status {response.status}")

                return response.read()
            finally:
                response.close()
        finally:
            sock.close()


class _DeadlineReader(io.RawIOBase):
    """Reads a response from a socket until a deadline. The timeout of a socket bounds each read alone, so an answer
    that trickles in would never time out.
    """

    def __init__(self, sock: socket.socket, deadline: float) -> None:
        super().__init__()
        self._sock = sock
        self._deadline = deadline

    # http.client.HTTPResponse reads through sock.makefile("rb").
    def makefile(self, mode: str) -> io.BufferedReader:
        return io.BufferedReader(self)

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        self._sock.settimeout(_remaining(self._deadline))
        return self._sock.recv_into(buffer)


# Error trackers and tracebacks with locals show the locals of the frames an exception passes, so the request, which
# holds the secret key, is built here, before the network is used, and kept as a memoryview, whose representation
# leaves its bytes out.
def _request(endpoint: SplitResult, secret: str, token: str, sitekey: str | None, remote_ip: str | None) -> memoryview:
    fields = {"secret": secret, "response": token}
    if sitekey:
        fields["sitekey"] = sitekey
    if remote_ip:
        fields["remoteIp"] = remote_ip
    # A string that UTF-8 cannot encode, such as a lone surrogate from a JSON body, is sent with "?" in its place
    # instead of failing the verification.
    form = urlencode(fields, encoding="utf-8", errors="replace").encode("ascii")

    head = (
        f"POST {endpoint.path} HTTP/1.1\r\n"
        f"Host: {endpoint.netloc}\r\n"
        "User-Agent: captchafox-python\r\n"
        "Content-Type: application/x-www-form-urlencoded\r\n"
        f"Content-Length: {len(form)}\r\n"
        "Connection: close\r\n"
        "\r\n"
    )
    return memoryview(head.encode("ascii") + form)


def _connect(host: str, port: int, deadline: float) -> socket.socket:
    # socket.create_connection gives each address the whole timeout; here all addresses share it.
    error = None
    for family, kind, proto, _, address in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM):
        sock = socket.socket(family, kind, proto)
        try:
            sock.settimeout(_remaining(deadline))
            sock.connect(address)
            return sock
        except OSError as e:
            sock.close()
            error = e

    raise error


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("the timeout of the verification passed")

    return remaining


def _evaluate(body: bytes) -> Passed | Rejected:
    try:
        answer = json.loads(body.decode("utf-8"), object_pairs_hook=_object, parse_constant=_no_constant)
    except (ValueError, RecursionError) as e:
        raise VerificationUnavailableError("siteverify answered with a body that is no JSON") from e

    if not isinstance(answer, dict):
        raise VerificationUnavailableError("siteverify answered with JSON that is no object")

    success = answer.get("success")
    if not isinstance(success, bool):
        raise VerificationUnavailableError("siteverify answered without a boolean success")

    if success:
        return Passed(challenge_ts=_string(answer.get("challenge_ts")), hostname=_string(answer.get("hostname")))
    else:
        return Rejected(error_codes=_strings(answer.get("error-codes")))


# A repeated name, such as "success" twice, has no defined meaning, so the answer is malformed.
def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    members = dict(pairs)
    if len(members) != len(pairs):
        raise ValueError("a member name is repeated")

    return members


# json accepts NaN, Infinity and -Infinity, which are no JSON.
def _no_constant(name: str) -> object:
    raise ValueError(f"{name} is no JSON")


def _string(value: object) -> str | None:
    return value if isinstance(value, str) else None


# A rejection stays a rejection when its error codes are malformed; only the entries that are strings are kept.
def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()

    return tuple(element for element in value if isinstance(element, str))
