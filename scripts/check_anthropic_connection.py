#!/usr/bin/env python3
"""Check TLS + network path to Anthropic (same SSL setup as the bot).

Run from repo root with venv active:
  PYTHONPATH=. python3 scripts/check_anthropic_connection.py

Optional: one token API smoke test (small cost):
  CHECK_ANTHROPIC_MESSAGE=1 PYTHONPATH=. python3 scripts/check_anthropic_connection.py
"""
from __future__ import annotations

import os
import socket
import sys

# Repo root on path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _print_tls_intercept_hint(host: str) -> None:
    """Best-effort: detect TLS inspection (e.g. Umbrella) via openssl."""
    import subprocess

    try:
        proc = subprocess.run(
            [
                "openssl",
                "s_client",
                "-connect",
                f"{host}:443",
                "-servername",
                host,
            ],
            input=b"",
            capture_output=True,
            timeout=15,
            check=False,
        )
        blob = (proc.stdout or b"") + (proc.stderr or b"")
        if b"Umbrella" in blob or b"Cisco" in blob and b"SubCA" in blob:
            print("Detected Cisco Umbrella / similar intercept on this network (openssl trace).")
    except Exception:
        pass


def main() -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv(os.path.join(_ROOT, ".env"))
    except ImportError:
        pass

    print("Python:", sys.version.replace("\n", " "))
    try:
        import ssl

        print("ssl:", getattr(ssl, "OPENSSL_VERSION", "unknown"))
    except Exception:
        pass

    key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not key:
        print("ERROR: ANTHROPIC_API_KEY is not set (load .env or export it).")
        return 1

    host = "api.anthropic.com"
    try:
        ips = socket.gethostbyname_ex(host)[2]
        print(f"DNS {host} -> {ips}")
    except OSError as e:
        print(f"ERROR: DNS resolution failed: {e}")
        return 1

    import httpx

    from src.brain.claude_client import _client, _ssl_context_for_anthropic

    ctx = _ssl_context_for_anthropic()
    try:
        r = httpx.get(f"https://{host}/", verify=ctx, timeout=30.0)
        print(f"TLS + GET https://{host}/ -> HTTP {r.status_code}")
    except Exception as e:
        print(f"ERROR: TLS/HTTP to {host} failed: {type(e).__name__}: {e}")
        c = getattr(e, "__cause__", None)
        if c:
            print(f"  cause: {type(c).__name__}: {c}")
        print()
        print("If you are on office Wi‑Fi / Cisco Umbrella / corporate filter:")
        print("  Your network decrypts HTTPS and re-signs with a company CA. certifi cannot trust that.")
        print("  Fix: ask IT for the root CA .pem, then:")
        print('    export SSL_CERT_FILE="/path/to/combined.pem"')
        print("  where combined.pem = certifi bundle + org root (concatenate both files).")
        print("  Or use a hotspot / network without SSL inspection, or whitelist api.anthropic.com.")
        print()
        _print_tls_intercept_hint(host)
        print("Other hints: pip install certifi | Homebrew Python 3.12+")
        return 1

    if os.environ.get("CHECK_ANTHROPIC_MESSAGE", "").strip() not in ("1", "true", "yes"):
        print("OK (no Messages API call). Set CHECK_ANTHROPIC_MESSAGE=1 for a tiny API test.")
        return 0

    try:
        client = _client()
        from src.utils.config import load_settings

        model = str(load_settings().get("claude", {}).get("model", "claude-opus-4-20250514"))
        msg = client.messages.create(
            model=model,
            max_tokens=1,
            messages=[{"role": "user", "content": "ping"}],
        )
        print(f"Messages API OK (model={model}, stop_reason={getattr(msg, 'stop_reason', '')})")
    except Exception as e:
        print(f"ERROR: Messages API: {type(e).__name__}: {e}")
        c = getattr(e, "__cause__", None)
        if c:
            print(f"  cause: {type(c).__name__}: {c}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
