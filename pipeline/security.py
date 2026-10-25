"""Remove operational credentials from source errors before logging or exposing health metadata."""
import os
import re
from urllib.parse import quote, quote_plus, urljoin, urlparse

SECRET_VARS = ("AIRNOW_API_KEY", "FIRMS_MAP_KEY", "NEXT_PUBLIC_SUPABASE_ANON_KEY",
               "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "VERCEL_TOKEN", "GH_TOKEN")


def redact(text):
    text = str(text)
    for name in SECRET_VARS:
        value = os.environ.get(name)
        if value:
            for representation in {value, quote(value, safe=""), quote_plus(value)}:
                text = text.replace(representation, "***")
    return re.sub(r"(?i)([?&](?:api_key|map_key|token|access_token|key)=)[^&\s\"']+", r"\1***", text)


def official_link(value, fallback):
    """Only link a provider's records back to that same official HTTPS host."""
    try:
        url = urljoin(fallback, str(value or ""))
        parsed = urlparse(url)
        if parsed.scheme == "https" and parsed.hostname == urlparse(fallback).hostname and not parsed.username and not parsed.password:
            return url
    except ValueError:
        pass
    return fallback
