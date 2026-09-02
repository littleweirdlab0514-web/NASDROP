#!/usr/bin/env python3
"""Interactive offline account setup for the NASDrop container."""

from __future__ import annotations

import argparse
from getpass import getpass

import backend


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or reset the NASDrop login account.")
    parser.add_argument("command", choices=("set",))
    parser.add_argument("username", help="NASDrop login ID (3-32 letters, numbers, dot, underscore, or hyphen)")
    args = parser.parse_args()

    password = getpass("New NASDrop password: ")
    confirmation = getpass("Confirm password: ")
    if password != confirmation:
        parser.error("passwords do not match")
    username = backend.replace_credentials(args.username, password)
    print(f"NASDrop account '{username}' was saved. Restart the running container before signing in.")


if __name__ == "__main__":
    main()
