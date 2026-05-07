#!/usr/bin/env python3
import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a test email using Django settings.")
    parser.add_argument("--to", required=True, help="Recipient email address")
    parser.add_argument(
        "--subject",
        default="Forma test email",
        help="Email subject (default: Forma test email)",
    )
    parser.add_argument(
        "--message",
        default="This is a test email from Forma.",
        help="Email body text",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "forma_project.settings")

    import django

    django.setup()

    from django.conf import settings
    from django.core.mail import send_mail

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "") or getattr(settings, "EMAIL_HOST_USER", "")
    if not from_email:
        print("No sender configured. Set PERSONAL_DEFAULT_FROM_EMAIL or EMAIL_HOST_USER.")
        return 1

    try:
        sent = send_mail(
            subject=args.subject,
            message=args.message,
            from_email=from_email,
            recipient_list=[args.to],
            fail_silently=False,
        )
    except Exception as exc:
        print(f"Failed to send email: {exc}")
        return 1

    if sent == 1:
        print(f"Test email sent to {args.to} from {from_email}")
        return 0

    print("No email was sent.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
