# CaptchaFox for Python

Official [CaptchaFox](https://captchafox.com) integration for Python. It verifies the answers of the widget with
CaptchaFox.

## Compatibility

| Python | Library |
|---|---|
| 3.11, 3.12, 3.13, 3.14, 3.15 | 1.x |

Python 3.10 and older are not supported: pip does not install the library there.

## Installation

```bash
pip install captchafox-python
```

Or add `captchafox-python` to the dependencies of your project. The library needs nothing but the standard library,
so without pip, unpack the folder `captchafox` from `captchafox_python-<version>-py3-none-any.whl` of the
[releases](https://github.com/CaptchaFox/captchafox-python/releases), a ZIP archive, into a directory on your
`sys.path`.

## Configuration

### Get your keys

In the [CaptchaFox portal](https://portal.captchafox.com), open your website under **Sites > Site Details** and copy
the **site key** and the **secret key**.

### Set up the library

Create a `CaptchaFoxClient` once with the secret key of your site and reuse it; it is thread-safe. Keep the secret key
in your configuration or environment, not in source code:

```python
import os

from captchafox import CaptchaFoxClient

client = CaptchaFoxClient(os.environ["CAPTCHAFOX_SECRET"])
```

### Options

| Option | Default | Meaning |
|---|---|---|
| `timeout` | 5 seconds | How long a verification may take, from connecting to CaptchaFox to the end of its answer: `CaptchaFoxClient(secret, timeout=3)`. Looking up the address of CaptchaFox comes before and is bounded by the system's resolver. |

## Usage

The widget adds the token to the form as the POST parameter `cf-captcha-response`. Verify it on the server before
the form is processed, here in a Flask view:

```python
from captchafox import VerificationUnavailableError

token = request.form.get("cf-captcha-response")
try:
    verification = client.verify(token, SITE_KEY, request.remote_addr)
    if not verification.passed:
        ...  # Reject the form.
except VerificationUnavailableError:
    ...  # CaptchaFox gave no usable answer: decide whether the form passes.
```

`verify(token)` sends the token alone; `verify(token, sitekey, remote_ip)` also sends the site key the token was
issued for and the visitor's IP address, each only when it is not `None` or empty.

A verification has one of three outcomes:

- `Passed`: CaptchaFox accepted the token. `challenge_ts` and `hostname` hold the time of the challenge and the
  hostname of the site, where CaptchaFox sent them.
- `Rejected`: CaptchaFox rejected the token; `error_codes` holds its error codes, such as `timeout-or-duplicate`,
  possibly none. An empty or missing token is rejected with `missing-input-response` without asking CaptchaFox.
- `VerificationUnavailableError`: CaptchaFox gave no usable answer; see
  [If CaptchaFox is unreachable](#if-captchafox-is-unreachable).

## Operation

### If CaptchaFox is unreachable

When CaptchaFox cannot be reached, does not complete its answer within the timeout, answers with an HTTP status other
than 200, or with a body that is no valid answer, `verify` raises `VerificationUnavailableError`. Your code decides
whether the form passes then: letting it through keeps your forms available during an outage, rejecting it keeps them
protected. Tokens that CaptchaFox rejects are always `Rejected`.

### Log

The library logs nothing. The messages of its exceptions never contain the secret key.

### Visitor IP

The visitor's IP address is sent only when you pass it as `remote_ip`. Behind a reverse proxy or load balancer, pass
the visitor's address that the proxy forwards, not the address of the proxy.

### Privacy

CaptchaFox is operated by Scoria Labs GmbH, Germany. How CaptchaFox processes data and how to get a data processing
agreement is described in the [CaptchaFox Privacy Center](https://captchafox.com/privacy). A suggested paragraph for
your privacy policy is on the [GDPR page](https://captchafox.com/privacy/gdpr).

## License

Apache-2.0. See [LICENSE](LICENSE).
