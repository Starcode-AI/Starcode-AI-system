import argparse
import getpass
import sys

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select

from app.db import SessionLocal, init_db
from app.models import Role, User
from app.security import hash_password


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a LocalAI Control administrator")
    parser.add_argument("--email", help="Administrator email")
    parser.add_argument("--name", default="Administrator", help="Display name")
    args = parser.parse_args()
    email = args.email or input("Administrator email: ").strip()
    try:
        email = validate_email(email, check_deliverability=False).normalized.lower()
    except EmailNotValidError as exc:
        print(f"Invalid email: {exc}", file=sys.stderr)
        return 2
    password = getpass.getpass("Password (at least 12 characters): ")
    confirmation = getpass.getpass("Repeat password: ")
    if password != confirmation or len(password) < 12:
        print("Passwords do not match or are shorter than 12 characters.", file=sys.stderr)
        return 2
    init_db()
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == email)):
            print("A user with this email already exists.", file=sys.stderr)
            return 1
        db.add(
            User(
                email=email,
                display_name=args.name[:80],
                password_hash=hash_password(password),
                role=Role.system_administrator,
            )
        )
        db.commit()
    print("Administrator created successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
