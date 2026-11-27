import argparse
import sys

from backend.app.config import get_settings
from backend.app.database import LocalDevSQLiteRepository, get_repository


def main() -> None:
    parser = argparse.ArgumentParser(description="LifeLink administrative CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    promote_cmd = subparsers.add_parser("create-admin", help="Promote an existing user to admin (Local Dev Mode)")
    promote_cmd.add_argument("--email", required=True, help="Registered email address of the user")

    args = parser.parse_args()
    settings = get_settings()
    repo = get_repository(settings)

    if args.command == "create-admin":
        if not isinstance(repo, LocalDevSQLiteRepository):
            print("In Supabase mode, promote admins directly via Supabase SQL Editor.")
            sys.exit(1)
        updated = repo.promote_to_admin_cli(args.email)
        if not updated:
            print(f"No user found with email: {args.email}")
            sys.exit(1)
        print(f"Promoted {updated['full_name']} ({updated['email']}) to admin.")


if __name__ == "__main__":
    main()
