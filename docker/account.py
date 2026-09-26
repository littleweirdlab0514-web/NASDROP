#!/usr/bin/env python3
"""Interactive offline account setup for the NASDrop container."""

from __future__ import annotations

import argparse
from getpass import getpass
import os

# Import only the credential helpers. The container entrypoint runs this command
# before the server, so starting a dispatcher here could claim and mutate a
# queued download just before the real server loads it.
os.environ["NAS_PORTAL_ACCOUNT_COMMAND"] = "1"
import backend


def main() -> None:
    parser = argparse.ArgumentParser(description="Create, bootstrap, or reset the NASDrop login account.")
    parser.add_argument("command", choices=("bootstrap", "set"))
    parser.add_argument("username", nargs="?", help="NASDrop login ID (3-32 letters, numbers, dot, underscore, or hyphen)")
    args = parser.parse_args()

    if args.command == "bootstrap":
        if args.username is not None:
            parser.error("bootstrap does not accept a username")
        created = backend.create_docker_bootstrap_credentials()
        migrated = backend.enforce_docker_default_password_change()
        if created or migrated:
            print("NASDrop temporary account nasdrop / nasdrop is active. Change its ID and password immediately after signing in.")
        return
    if not args.username:
        parser.error("set requires a username")

    password = getpass("New NASDrop password: ")
    confirmation = getpass("Confirm password: ")
    if password != confirmation:
        parser.error("passwords do not match")
    username = backend.replace_credentials(args.username, password)
    print(f"NASDrop account '{username}' was saved. Restart the running container before signing in.")


if __name__ == "__main__":
    main()
