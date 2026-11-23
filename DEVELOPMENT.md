# Development

## Requirements

Python 3.11 or later and `make`. The tests need nothing beyond the standard library. `make build` needs the package
`build` (`python3 -m pip install build`). Set `PYTHON` to run with another interpreter, such as
`make test PYTHON=python3.11`.

## Build

```bash
make build
```

writes the sdist and the wheel to `dist/`.

## Test

| Command | Runs |
|---|---|
| `make test` | The tests against a local siteverify server, including every case of `tests/__fixtures__/siteverify-cases.json`, and the check that the library needs only the standard library at runtime. Needs no network. CI runs it on Python 3.11, 3.12, 3.13, 3.14 and 3.15 for every push to `main` and every pull request. |
| `make test-live` | The test against `https://api.captchafox.com/siteverify` with the public test keys. Needs the network. |
