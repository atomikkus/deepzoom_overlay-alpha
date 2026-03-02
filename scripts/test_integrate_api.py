"""Test connection to the integrated external API (login + optional pathology_image/all)."""
import asyncio
import json
import os
import sys
from pathlib import Path

# Project root
ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "integrate_config.json"


def load_config():
    out = {
        "base_url": os.getenv("EXTERNAL_API_BASE_URL", "").strip().rstrip("/"),
        "email": os.getenv("EXTERNAL_API_EMAIL", "").strip(),
        "password": os.getenv("EXTERNAL_API_PASSWORD", "").strip(),
    }
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            for k in ("base_url", "email", "password"):
                if isinstance(data.get(k), str):
                    out[k] = data[k].strip()
            if out["base_url"]:
                out["base_url"] = out["base_url"].rstrip("/")
        except Exception as e:
            print(f"Warning: Could not load {CONFIG_PATH}: {e}")
    if os.getenv("EXTERNAL_API_BASE_URL"):
        out["base_url"] = os.getenv("EXTERNAL_API_BASE_URL", "").strip().rstrip("/")
    if os.getenv("EXTERNAL_API_EMAIL"):
        out["email"] = os.getenv("EXTERNAL_API_EMAIL", "").strip()
    if os.getenv("EXTERNAL_API_PASSWORD"):
        out["password"] = os.getenv("EXTERNAL_API_PASSWORD", "").strip()
    return out


async def main():
    try:
        import httpx
    except ImportError:
        print("FAIL: httpx not installed. Run: pip install httpx")
        sys.exit(1)

    cfg = load_config()
    base = cfg.get("base_url") or ""
    email = cfg.get("email") or ""
    password = cfg.get("password") or ""

    if not base or not email:
        print("FAIL: External API not configured. Set base_url and email in integrate_config.json or env.")
        sys.exit(1)

    print(f"Testing connection to {base} ...")
    print("1. POST /user/login ...")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                f"{base}/user/login",
                json={"email": email, "password": password},
            )
            r.raise_for_status()
            data = r.json()
    except httpx.ConnectError as e:
        print(f"   FAIL: Could not connect to {base}")
        print(f"   Error: {e}")
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"   FAIL: HTTP {e.response.status_code}")
        try:
            body = e.response.json()
            print(f"   Response: {body}")
        except Exception:
            print(f"   Body: {e.response.text[:500]}")
        sys.exit(1)
    except Exception as e:
        print(f"   FAIL: {e}")
        sys.exit(1)

    payload = data.get("payLoad") or data.get("payload")
    if not isinstance(payload, dict) or not payload.get("authToken"):
        print("   FAIL: Response missing payLoad.authToken")
        sys.exit(1)

    token = payload["authToken"]
    print(f"   OK: Login successful (authToken: {token[:12]}...)")

    # Optional: test pathology_image/all if sample IDs are available
    patient_id = os.getenv("TEST_PATIENT_ID", "a1ce9f01-218d-4505-9906-957549121805")
    event_id = os.getenv("TEST_EVENT_ID", "189704")
    slide_id = os.getenv("TEST_SLIDE_ID", "B1")
    print(f"2. GET /pathology_image/all?patient_id=...&event_id=...&slide_id=... ...")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{base}/pathology_image/all",
                params={"patient_id": patient_id, "event_id": event_id, "slide_id": slide_id},
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            data2 = r.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            print(f"   OK: Endpoint reachable (404 = no images for this patient/event; try other IDs)")
        else:
            print(f"   FAIL: HTTP {e.response.status_code} - {e.response.text[:300]}")
            sys.exit(1)
    except Exception as e:
        print(f"   FAIL: {e}")
        sys.exit(1)

    payload2 = data2.get("payLoad") or data2.get("payload")
    blocks = (payload2 or {}).get("blocks") if isinstance(payload2, dict) else None
    if blocks is not None:
        n = sum(len(b.get("slides") or []) for b in blocks)
        print(f"   OK: pathology_image/all returned {len(blocks)} block(s), {n} slide(s)")
    else:
        print("   OK: pathology_image/all responded (no blocks in payload)")

    print("Connection to integrated API is good.")


if __name__ == "__main__":
    asyncio.run(main())
