"""Refresh the Instagram token and write the new one to $GITHUB_OUTPUT (masked)."""
import os

from stockreels import instagram

token, expires_in = instagram.refresh_token()
print(f"::add-mask::{token}")
print(f"[instagram] token refreshed, valid for {int(expires_in or 0) // 86400} more days")
with open(os.environ["GITHUB_OUTPUT"], "a") as f:
    f.write(f"token={token}\n")
