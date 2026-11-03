# Test only: ops/test.sh mounts this into the test container's venv when FAKE_DATE is set (YYYY-MM-DDTHH:MM, UTC),
# so every datetime.now(), today() and utcnow() in Hermes and its plugins runs from that moment.
# Python imports sitecustomize at startup, before any `from datetime import datetime`.
import os

FAKE = os.environ.get("FAKE_DATE")
if FAKE:
    import datetime as _dt

    _real = _dt.datetime
    _shift = _real.fromisoformat(FAKE).replace(tzinfo=_dt.timezone.utc) - _real.now(_dt.timezone.utc)

    class _Shifted(_real):
        @classmethod
        def now(cls, tz=None):
            return _real.now(tz) + _shift

        @classmethod
        def today(cls):
            return _real.today() + _shift

        @classmethod
        def utcnow(cls):
            return _real.utcnow() + _shift

    _dt.datetime = _Shifted
