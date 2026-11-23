import threading
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

T = TypeVar("T")
TESTS = Path(__file__).parent


def bounded(call: Callable[[], T], seconds: float) -> T:
    """Runs the call and fails when it takes longer, instead of letting a timeout that does not take effect hang."""
    outcome: list = []

    def run() -> None:
        try:
            outcome.append((True, call()))
        except BaseException as e:
            outcome.append((False, e))

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(seconds)
    if not outcome:
        raise AssertionError(f"the call did not end within {seconds} seconds")

    returned, value = outcome[0]
    if not returned:
        raise value
    return value


def raised(call: Callable[[], object]) -> BaseException:
    """The exception the call raises, with the locals of its frames, which assertRaises clears."""
    try:
        call()
    except BaseException as e:
        return e
    raise AssertionError("the call raised no exception")


def formatted(error: BaseException) -> str:
    """The exception as logs and error trackers show it: the messages and representations of the exception and its
    causes, and the locals of every frame outside the tests that their tracebacks keep.
    """
    texts = ["".join(traceback.format_exception(error))]
    seen: set[int] = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        texts.append(repr(error))
        texts.append(repr(error.args))
        for frame in traceback.TracebackException(type(error), error, error.__traceback__, capture_locals=True).stack:
            if Path(frame.filename).parent != TESTS:
                texts.extend(f"{frame.name}: {name} = {value}" for name, value in (frame.locals or {}).items())
        error = error.__cause__ or error.__context__
    return "\n".join(texts)
