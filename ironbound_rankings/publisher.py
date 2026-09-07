"""Orchestrate ranking, rendering, previews, and independent Forum publishing."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import ROOT, load_leagues
from .discord import build_message, parse_tag_ids, post_forum_ranking
from .engine import rank_league
from .forecast import attach_playoff_forecast
from .http import HttpClient
from .models import LeagueConfig, RankingResult
from .render import render_chart, render_playoff_chart
from .sleeper import fetch_league_snapshot
from .sources import MarketData, fetch_market_data
from .state import load_state, save_state


EASTERN = ZoneInfo("America/New_York")


def run(
    *,
    league_selection: str,
    publish: bool,
    force: bool,
    scheduled: bool,
    scheduled_cron: str | None = None,
) -> int:
    now = datetime.now(EASTERN)
    if scheduled and not is_noon_eastern_schedule(now, scheduled_cron):
        trigger = scheduled_cron or "unknown"
        print(
            f"Schedule guard: trigger {trigger!r} is not this week's noon "
            f"Eastern schedule ({now:%A %-I:%M %p %Z}); nothing to publish."
        )
        return 0

    configs = load_leagues()
    selected = list(configs.values()) if league_selection == "all" else [configs[league_selection]]
    client = HttpClient()
    market_cache: dict[tuple[bool, int, float, str], MarketData] = {}
    failures: list[str] = []

    for config in selected:
        try:
            print(f"\n[{config.key}] Loading Sleeper league {config.league_id}...")
            snapshot = fetch_league_snapshot(client, config)
            completed_games = max((team.games for team in snapshot.teams), default=0)
            starter_metric = "ros" if completed_games else "adp"
            cache_key = (
                snapshot.is_superflex,
                len(snapshot.teams),
                snapshot.ppr,
                starter_metric,
            )
            if cache_key not in market_cache:
                market_cache[cache_key] = fetch_market_data(
                    client,
                    is_superflex=snapshot.is_superflex,
                    num_teams=len(snapshot.teams),
                    ppr=snapshot.ppr,
                    starter_metric=starter_metric,
                )
            market_data = market_cache[cache_key]
            for warning in market_data.warnings:
                print(f"[{config.key}] Warning: {warning}")
            outcome = publish_league(
                client=client,
                config=config,
                market_data=market_data,
                snapshot=snapshot,
                now=now,
                publish=publish,
                force=force,
            )
            print(f"[{config.key}] {outcome}")
        except Exception as exc:  # isolate one league from the other
            failures.append(config.key)
            print(f"[{config.key}] FAILED: {exc}")

    if failures:
        print(f"Completed with failures: {', '.join(failures)}")
        return 1
    return 0


def is_noon_eastern_schedule(now: datetime, scheduled_cron: str | None) -> bool:
    """Accept the DST-correct noon trigger even when GitHub starts it late."""
    if now.weekday() != 5:
        return False

    # Local/manual compatibility: without GitHub's trigger expression, retain
    # the strict Saturday-noon check.
    if not scheduled_cron:
        return now.hour == 12

    offset = now.utcoffset()
    if offset is None:
        return False
    noon_utc_hour = (12 - int(offset.total_seconds() // 3600)) % 24
    return scheduled_cron.strip() == f"7 {noon_utc_hour} * * 6"


def publish_league(
    *,
    client: HttpClient,
    config: LeagueConfig,
    market_data: MarketData,
    snapshot,
    now: datetime,
    publish: bool,
    force: bool,
) -> str:
    state_path = ROOT / "state" / f"{config.key}.json"
    state = load_state(state_path)
    previous_ranks = state.get("rank_by_roster_id") or {}
    generated_at = now.isoformat(timespec="seconds")
    result = rank_league(
        snapshot,
        market_data.players,
        market_data.books,
        previous_ranks=previous_ranks,
        generated_at=generated_at,
    )
    attach_playoff_forecast(result)
    post_key = _post_key(result, now)
    output_dir = ROOT / "exports" / config.key
    image_path = output_dir / "latest.png"
    playoff_image_path = output_dir / "latest-playoffs.png"
    render_chart(result, config, image_path)
    render_playoff_chart(result, config, playoff_image_path)
    _write_preview(result, config, output_dir)

    if not publish:
        return (
            "Dry run complete: "
            f"{image_path.relative_to(ROOT)} and "
            f"{playoff_image_path.relative_to(ROOT)}"
        )
    if state.get("last_published_key") == post_key and not force:
        return f"Already published {post_key}; skipped duplicate."

    webhook_url = (os.getenv(config.webhook_env) or "").strip()
    if not webhook_url:
        raise ValueError(f"GitHub secret {config.webhook_env} is not configured")
    tag_ids = parse_tag_ids(os.getenv(config.tags_env) or "")
    response = post_forum_ranking(
        client,
        webhook_url=webhook_url,
        result=result,
        config=config,
        image_path=image_path,
        playoff_image_path=playoff_image_path,
        tag_ids=tag_ids,
    )
    save_state(state_path, result, post_key)
    thread_id = response.get("channel_id") or response.get("id") or "created"
    return f"Published {post_key} to a new Forum thread ({thread_id})."


def _write_preview(result: RankingResult, config: LeagueConfig, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    thread_name, message = build_message(result, config)
    (output_dir / "latest.txt").write_text(
        f"THREAD: {thread_name}\n\n{message}\n", encoding="utf-8"
    )
    payload = {
        "league": {
            "id": result.league.league_id,
            "name": result.league.league_name,
            "season": result.league.season,
            "week": result.league.week,
            "format": "superflex" if result.league.is_superflex else "1QB",
        },
        "generated_at": result.generated_at,
        "dynasty_sources": result.dynasty_sources,
        "lineup_sources": result.lineup_sources,
        "has_season_results": result.has_season_results,
        "forecast_simulations": result.forecast_simulations,
        "forecast_model": result.forecast_model,
        "teams": [asdict(team) for team in result.teams],
    }
    (output_dir / "latest.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _post_key(result: RankingResult, now: datetime) -> str:
    if result.league.week > 0:
        return f"{result.league.season}-week-{result.league.week}"
    return f"{result.league.season}-preseason-{now:%Y-%m-%d}"
