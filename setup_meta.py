"""Interactive Meta setup. Standard library only.

Prompts for Page ID + access token, verifies them via token_check, and ONLY
saves to .env if the token PASSES. Existing .env keys are preserved.

  python setup_meta.py
"""
from __future__ import annotations

import sys

import config
import token_check


def _write_env(updates: dict) -> None:
    env = config.ROOT / ".env"
    lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
    keys = set(updates)
    out, seen = [], set()
    for ln in lines:
        if "=" in ln and not ln.strip().startswith("#"):
            k = ln.split("=", 1)[0].strip()
            if k in keys:
                out.append(f"{k}={updates[k]}")
                seen.add(k)
                continue
        out.append(ln)
    for k in keys - seen:
        out.append(f"{k}={updates[k]}")
    env.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> int:
    print("=== Auriga · Meta Page setup ===")
    page_id = input("Facebook Page ID: ").strip()
    token = input("Page access token (long-lived): ").strip()
    if not page_id or not token:
        print("Both Page ID and token are required. Nothing saved.")
        return 1

    print("\nVerifying with Meta Graph API ...")
    res = token_check.verify(token, page_id)
    print(token_check.render(res))

    if not res["passed"]:
        print("\n❌ Token did NOT pass — refusing to save invalid credentials.")
        print("   Fix the issues above and re-run `python setup_meta.py`.")
        return 1

    _write_env({"FACEBOOK_PAGE_ID": page_id, "FACEBOOK_ACCESS_TOKEN": token,
                "DRY_RUN": "false"})
    print("\n✅ Verified and saved to .env (DRY_RUN=false). You're ready to publish.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
