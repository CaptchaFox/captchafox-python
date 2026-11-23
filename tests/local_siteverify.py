import socket
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl


@dataclass(frozen=True)
class Received:
    method: str
    path: str
    content_type: str | None
    form: dict[str, str]


class LocalSiteverify:
    """A siteverify on the loopback interface that records every request it receives."""

    def __init__(self, mode: str, status: int = 0, body: str = "") -> None:
        self.requests: list[Received] = []
        # When a trickling server found the connection closed, by time.monotonic(); None while it is open.
        self.broken_at: float | None = None
        self._closed = threading.Event()
        site = self

        class Handler(BaseHTTPRequestHandler):
            # Chunked bodies, which the stalling and trickling modes send, need HTTP/1.1.
            protocol_version = "HTTP/1.1"

            def do_POST(self) -> None:
                site.requests.append(self._receive())
                match mode:
                    case "answer":
                        payload = body.encode()
                        self.send_response(status)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Content-Length", str(len(payload)))
                        self.end_headers()
                        self.wfile.write(payload)
                    case "raw":
                        self.wfile.write(body.encode())
                        self.close_connection = True
                    case "silent":
                        site._closed.wait()
                    case "stall":
                        self._send_part()
                        site._closed.wait()
                    case "trickle":
                        self._send_part()
                        site._trickle(self.wfile)
                    case _:
                        raise ValueError(f"unknown mode {mode}")

            def _receive(self) -> Received:
                length = int(self.headers.get("Content-Length", "0"))
                pairs = parse_qsl(self.rfile.read(length).decode(), keep_blank_values=True, strict_parsing=length > 0)
                form = dict(pairs)
                if len(form) != len(pairs):
                    raise ValueError("a field was sent twice")
                return Received(self.command, self.path, self.headers.get("Content-Type"), form)

            def _send_part(self) -> None:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                self.wfile.write(_chunk(body.encode()))
                self.wfile.flush()

            def log_message(self, format: str, *args: object) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, args=(0.05,), daemon=True).start()

    @classmethod
    def answering(cls, status: int, body: str) -> "LocalSiteverify":
        return cls("answer", status, body)

    @classmethod
    def raw(cls, answer: str) -> "LocalSiteverify":
        """Sends the answer as it is, status line and headers included, then closes the connection."""
        return cls("raw", body=answer)

    @classmethod
    def silent(cls) -> "LocalSiteverify":
        """Receives requests and never answers them while it runs."""
        return cls("silent")

    @classmethod
    def stalling(cls, status: int, start: str) -> "LocalSiteverify":
        """Sends the status, the headers and the start of a body, then nothing more while it runs."""
        return cls("stall", status, start)

    @classmethod
    def trickling(cls, status: int, start: str) -> "LocalSiteverify":
        """Sends the status, the headers and the start of a body, then a space every 100 ms until the client goes."""
        return cls("trickle", status, start)

    @property
    def endpoint(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}/siteverify"

    def close(self) -> None:
        self._closed.set()
        self._server.shutdown()
        self._server.server_close()

    def __enter__(self) -> "LocalSiteverify":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _trickle(self, out) -> None:
        try:
            while not self._closed.wait(0.1):
                out.write(_chunk(b" "))
                out.flush()
        except OSError:
            self.broken_at = time.monotonic()


def refusing_endpoint() -> str:
    """An endpoint at a port of the loopback interface where nothing listens."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}/siteverify"


def _chunk(data: bytes) -> bytes:
    return f"{len(data):x}\r\n".encode() + data + b"\r\n"
