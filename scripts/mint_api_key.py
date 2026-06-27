"""Mint an API key for a user. Run on the server where flowdrip_app imports.

Usage: python scripts/mint_api_key.py <email> [label]
Prints the plaintext key ONCE — store it now, only its hash is kept.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import flowdrip_app as fa


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/mint_api_key.py <email> [label]")
        raise SystemExit(2)
    email = sys.argv[1]
    label = sys.argv[2] if len(sys.argv) > 2 else ""
    key = fa._mint_api_key(email, label=label)
    print(f"API key for {email} (label={label or '-'}):")
    print(key)
    print("Store this now — only its hash is kept on the server.")


if __name__ == "__main__":
    main()
