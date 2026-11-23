## 1.0.0

- Verify CaptchaFox tokens with siteverify: `CaptchaFoxClient.verify` returns `Passed` or `Rejected`, and raises
  `VerificationUnavailableError` when CaptchaFox cannot be reached in time or answers unexpectedly.
- Python 3.11 and later, no runtime dependencies.
