import os
from typing import Any

import requests

DEFAULT_TIMEOUT = 15.0
DEFAULT_VERIFY = os.getenv("DY_REQUEST_VERIFY", "false").strip().lower() in {"1", "true", "yes", "on"}


def get_proxy_config() -> dict[str, str] | None:
    proxy = os.getenv("DY_PROXY") or os.getenv("ALL_PROXY") or os.getenv("all_proxy")
    http_proxy = os.getenv("DY_HTTP_PROXY") or os.getenv("HTTP_PROXY") or os.getenv("http_proxy") or proxy
    https_proxy = os.getenv("DY_HTTPS_PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or proxy
    proxies = {}
    if http_proxy:
        proxies["http"] = http_proxy
    if https_proxy:
        proxies["https"] = https_proxy
    return proxies or None


def get_default_request_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "timeout": DEFAULT_TIMEOUT,
        "verify": DEFAULT_VERIFY,
    }
    proxies = get_proxy_config()
    if proxies:
        kwargs["proxies"] = proxies
    return kwargs


_original_request = requests.sessions.Session.request
_patched = False


def patch_requests() -> None:
    global _patched
    if _patched:
        return

    def _request_with_defaults(self, method, url, **kwargs):
        defaults = get_default_request_kwargs()
        for key, value in defaults.items():
            kwargs.setdefault(key, value)
        return _original_request(self, method, url, **kwargs)

    requests.sessions.Session.request = _request_with_defaults
    _patched = True


patch_requests()
