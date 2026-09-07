"""Build and send the Tuesday magazine email package."""

from __future__ import annotations

import json
import os
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Iterable

from .config import ROOT
from .models import LeagueConfig


SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def send_power_rankings_email(
    configs: Iterable[LeagueConfig],
    *,
    generated_at: datetime,
    root: Path = ROOT,
) -> str:
    """Send every selected league's two graphics in one magazine-ready email."""
    sender = _required_env("PUBLICATIONS_EMAIL_FROM")
    recipients = parse_recipients(_required_env("PUBLICATIONS_EMAIL_TO"))
    password = _required_env("PUBLICATIONS_EMAIL_APP_PASSWORD").replace(" ", "")
    message = build_power_rankings_email(
        configs,
        sender=sender,
        recipients=recipients,
        generated_at=generated_at,
        root=root,
    )

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as smtp:
        smtp.login(sender, password)
        smtp.send_message(message)

    attachment_count = sum(1 for _ in message.iter_attachments())
    return (
        f"Email sent to {len(recipients)} recipient(s) with "
        f"{attachment_count} attachment(s)."
    )


def build_power_rankings_email(
    configs: Iterable[LeagueConfig],
    *,
    sender: str,
    recipients: list[str],
    generated_at: datetime,
    root: Path = ROOT,
) -> EmailMessage:
    configs = list(configs)
    if not configs:
        raise ValueError("At least one league is required for email delivery")
    if not recipients:
        raise ValueError("PUBLICATIONS_EMAIL_TO does not contain a recipient")

    period = _email_period(root / "exports" / configs[0].key / "latest.json")
    message = EmailMessage()
    message["Subject"] = f"Ironbound Power Rankings — {period} — Tuesday Edition"
    message["From"] = f"Ironbound Publications <{sender}>"
    message["To"] = ", ".join(recipients)
    message.set_content(
        "Your Tuesday Ironbound Power Rankings package is attached and ready "
        "for the weekly magazines.\n\n"
        "Included for each league:\n"
        "- Power rankings\n"
        "- Playoff forecast\n\n"
        "The charts were rebuilt from the latest Sleeper records, rosters, and "
        "schedule plus the current ranking feeds. Both Ironbound leagues are "
        "evaluated as 1QB.\n\n"
        f"Generated {generated_at:%A, %B %-d, %Y at %-I:%M %p %Z}.\n"
    )

    period_slug = period.lower().replace(" ", "-")
    for config in configs:
        output_dir = root / "exports" / config.key
        attachments = (
            (
                output_dir / "latest.png",
                f"{config.key}-power-rankings-{period_slug}.png",
            ),
            (
                output_dir / "latest-playoffs.png",
                f"{config.key}-playoff-forecast-{period_slug}.png",
            ),
        )
        for path, filename in attachments:
            if not path.is_file():
                raise FileNotFoundError(f"Email attachment was not generated: {path}")
            message.add_attachment(
                path.read_bytes(),
                maintype="image",
                subtype="png",
                filename=filename,
            )
    return message


def parse_recipients(raw: str) -> list[str]:
    """Accept one address or a comma/semicolon-separated distribution list."""
    normalized = raw.replace(";", ",")
    return [address.strip() for address in normalized.split(",") if address.strip()]


def _email_period(preview_path: Path) -> str:
    if not preview_path.is_file():
        raise FileNotFoundError(f"Email metadata was not generated: {preview_path}")
    payload = json.loads(preview_path.read_text(encoding="utf-8"))
    league = payload["league"]
    week = int(league.get("week") or 0)
    if week > 0:
        return f"Week {week}"
    return f"{league['season']} Preseason"


def _required_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise ValueError(f"GitHub secret {name} is not configured")
    if "\n" in value or "\r" in value:
        raise ValueError(f"GitHub secret {name} contains an invalid line break")
    return value
