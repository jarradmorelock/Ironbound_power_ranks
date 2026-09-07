"""Create image-backed Discord Forum posts."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .http import HttpClient
from .models import LeagueConfig, RankingResult


def build_message(result: RankingResult, config: LeagueConfig) -> tuple[str, str]:
    period = (
        f"Week {result.league.week}"
        if result.league.week > 0
        else f"{result.league.season} Preseason"
    )
    thread_name = f"{config.brand.title()} Power Rankings — {period}"
    lines = [
        f"# {config.brand} POWER RANKINGS",
        f"**{period} · {config.publication} · {_format_label(result)}**",
        "",
    ]
    for team in result.teams:
        movement = _movement(team.movement)
        forecast = ""
        if team.make_playoffs_pct is not None:
            forecast = (
                f" · PO {team.make_playoffs_pct:.0f}%"
                f" · TITLE {(team.win_championship_pct or 0):.0f}%"
            )
        lines.append(
            f"**{team.rank}. {escape_discord(team.team_name)}** — "
            f"{team.record} · {team.score:.1f} {movement}{forecast}".rstrip()
        )
    source_names = result.dynasty_sources + result.lineup_sources
    source_prefix = "Sources: "
    lines.extend(
        [
            "",
            _formula_line(result),
            (
                f"-# {source_prefix}"
                f"{', '.join(source_names)} · League data: Sleeper"
            ),
        ]
    )
    if result.forecast_simulations:
        lines.append(
            f"-# Forecast: {result.forecast_model} · "
            f"{result.forecast_simulations:,} simulations · Sleeper schedule/settings"
        )
    content = "\n".join(lines)
    if len(content) > 2000:
        raise ValueError("Discord message exceeded 2,000 characters")
    return thread_name[:100], content


def post_forum_ranking(
    client: HttpClient,
    *,
    webhook_url: str,
    result: RankingResult,
    config: LeagueConfig,
    image_path: Path,
    playoff_image_path: Path | None,
    tag_ids: list[str],
) -> dict:
    if not webhook_url.startswith(("https://discord.com/api/webhooks/", "https://canary.discord.com/api/webhooks/")):
        raise ValueError(f"{config.webhook_env} is not a Discord webhook URL")
    thread_name, content = build_message(result, config)
    filename = f"{config.key}-power-rankings.png"
    attachments = [
        {
            "id": 0,
            "filename": filename,
            "description": f"{config.brand} {thread_name} bar chart",
        }
    ]
    files = {"files[0]": (filename, image_path.read_bytes(), "image/png")}
    if playoff_image_path and playoff_image_path.exists():
        playoff_filename = f"{config.key}-playoff-forecast.png"
        attachments.append(
            {
                "id": 1,
                "filename": playoff_filename,
                "description": f"{config.brand} playoff forecast chart",
            }
        )
        files["files[1]"] = (
            playoff_filename,
            playoff_image_path.read_bytes(),
            "image/png",
        )
    payload = {
        "thread_name": thread_name,
        "content": content,
        "allowed_mentions": {"parse": []},
        "attachments": attachments,
    }
    if tag_ids:
        payload["applied_tags"] = tag_ids[:5]
    return client.post_multipart(
        _with_wait(webhook_url),
        data={"payload_json": json.dumps(payload)},
        files=files,
    )


def parse_tag_ids(raw: str) -> list[str]:
    raw = raw.strip()
    if not raw:
        return []
    try:
        values = json.loads(raw)
        if isinstance(values, list):
            candidates = values
        else:
            candidates = [raw]
    except json.JSONDecodeError:
        candidates = raw.split(",")
    return [str(value).strip() for value in candidates if str(value).strip().isdigit()]


def escape_discord(value: str) -> str:
    for character in ("\\", "*", "_", "~", "`", "|"):
        value = value.replace(character, f"\\{character}")
    return value.replace("@", "＠")


def _movement(movement: int | None) -> str:
    if movement is None:
        return "NEW"
    if movement > 0:
        return f"▲{movement}"
    if movement < 0:
        return f"▼{abs(movement)}"
    return "—"


def _with_wait(url: str) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["wait"] = "true"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def _format_label(result: RankingResult) -> str:
    return "SUPERFLEX" if result.league.is_superflex else "1QB"


def _formula_line(result: RankingResult) -> str:
    market = f"{result.market_weight * 100:g}%"
    lineup = f"{result.lineup_weight * 100:g}%"
    if not result.has_season_results:
        return f"-# Preseason index: market consensus {market} · ADP starters {lineup}"
    season = f"{result.season_weight * 100:g}%"
    guardrail = " · 4+ win-gap guardrail active" if result.record_guardrail_active else ""
    return (
        f"-# Index: market {market} · ROS starters {lineup} · season {season} "
        f"(80% record / 20% points){guardrail}"
    )
