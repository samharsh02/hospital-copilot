from .base import *  # noqa: F401, F403

SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=False)  # noqa: F405
SECURE_HSTS_SECONDS = 31536000
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=False)  # noqa: F405
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=False)  # noqa: F405

try:
    import sentry_sdk
    _sentry_dsn = env("SENTRY_DSN", default="")  # noqa: F405
    if _sentry_dsn:
        sentry_sdk.init(dsn=_sentry_dsn, traces_sample_rate=0.2)
except ImportError:
    pass
