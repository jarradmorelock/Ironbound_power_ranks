"""Fetch and normalize dynasty/redraft market values."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .http import DataSourceError, HttpClient
from .models import PlayerIdentity, ValueBook


DYNASTY_DADDY_BASE = "https://dynasty-daddy.com/api/v1"
FANTASY_CALC_URL = "https://api.fantasycalc.com/values/current"

MARKETS = (
    (0, "KeepTradeCut", "dynasty"),
    (1, "FantasyCalc", "dynasty"),
    (2, "DynastyProcess", "dynasty"),
    (3, "DynastySuperflex", "dynasty"),
    (4, "KeepTradeCut Redraft", "lineup"),
    (5, "FantasyCalc Redraft", "lineup"),
)


@dataclass
class MarketData:
    players: dict[str, PlayerIdentity]
    books: list[ValueBook]
    warnings: list[str]


def fetch_market_data(
    client: HttpClient,
    *,
    is_superflex: bool,
    num_teams: int,
    ppr: float,
) -> MarketData:
    warnings: list[str] = []
    try:
        market_data = fetch_dynasty_daddy(client, is_superflex=is_superflex)
        warnings.extend(market_data.warnings)
    except DataSourceError as exc:
        warnings.append(f"Dynasty Daddy metadata unavailable: {exc}")
        market_data = MarketData(players={}, books=[], warnings=[])

    dynasty_books = [book for book in market_data.books if book.category == "dynasty"]
    lineup_books = [book for book in market_data.books if book.category == "lineup"]
    players = dict(market_data.players)
    books = list(market_data.books)

    if not dynasty_books or not lineup_books:
        fallback = fetch_fantasy_calc(
            client,
            is_superflex=is_superflex,
            num_teams=num_teams,
            ppr=ppr,
        )
        players.update(fallback.players)
        if not dynasty_books:
            books.extend(book for book in fallback.books if book.category == "dynasty")
            warnings.append("Using direct FantasyCalc dynasty values as a fallback.")
        if not lineup_books:
            books.extend(book for book in fallback.books if book.category == "lineup")
            warnings.append("Using direct FantasyCalc redraft values as a fallback.")

    if not any(book.category == "dynasty" for book in books):
        raise DataSourceError("No dynasty value source was available")
    if not any(book.category == "lineup" for book in books):
        raise DataSourceError("No current-season value source was available")
    return MarketData(players=players, books=books, warnings=warnings)


def fetch_dynasty_daddy(client: HttpClient, *, is_superflex: bool) -> MarketData:
    metadata = client.get_json(f"{DYNASTY_DADDY_BASE}/player/all/today")
    if not isinstance(metadata, list) or len(metadata) < 100:
        raise DataSourceError("Dynasty Daddy returned incomplete player metadata")

    identities_by_name: dict[str, PlayerIdentity] = {}
    sleeper_players: dict[str, PlayerIdentity] = {}
    asset_names: dict[str, str] = {}
    for row in metadata:
        name_id = str(row.get("name_id") or "").strip()
        if not name_id:
            continue
        asset_names[name_id] = str(row.get("full_name") or "").strip()
        sleeper_id = str(row.get("sleeper_id") or "").strip()
        position = str(row.get("position") or "").upper().strip()
        if sleeper_id:
            identity = PlayerIdentity(
                sleeper_id=sleeper_id,
                name_id=name_id,
                full_name=str(row.get("full_name") or name_id),
                position=position,
            )
            identities_by_name[name_id] = identity
            sleeper_players[sleeper_id] = identity

    warnings: list[str] = []
    books: list[ValueBook] = []
    value_field = "sf_trade_value" if is_superflex else "trade_value"
    for market_number, label, category in MARKETS:
        try:
            rows = client.get_json(
                f"{DYNASTY_DADDY_BASE}/player/all/market/{market_number}"
            )
            book = _book_from_dynasty_daddy_rows(
                rows,
                label=label,
                category=category,
                value_field=value_field,
                identities_by_name=identities_by_name,
                asset_names=asset_names,
            )
            books.append(book)
        except DataSourceError as exc:
            warnings.append(f"{label} unavailable: {exc}")

    return MarketData(players=sleeper_players, books=books, warnings=warnings)


def _book_from_dynasty_daddy_rows(
    rows: Any,
    *,
    label: str,
    category: str,
    value_field: str,
    identities_by_name: dict[str, PlayerIdentity],
    asset_names: dict[str, str],
) -> ValueBook:
    if not isinstance(rows, list):
        raise DataSourceError(f"{label} returned an invalid payload")
    book = ValueBook(name=label, category=category)
    for row in rows:
        name_id = str(row.get("name_id") or "").strip()
        value = _number(row.get(value_field))
        if not name_id or value <= 0:
            continue
        identity = identities_by_name.get(name_id)
        if identity:
            book.player_values[identity.sleeper_id] = value
            continue
        pick_key = parse_pick_asset(asset_names.get(name_id, ""))
        if pick_key:
            book.pick_values[pick_key] = value
    if len(book.player_values) < 100:
        raise DataSourceError(f"{label} returned too few mapped players")
    return book


def fetch_fantasy_calc(
    client: HttpClient,
    *,
    is_superflex: bool,
    num_teams: int,
    ppr: float,
) -> MarketData:
    players: dict[str, PlayerIdentity] = {}
    books: list[ValueBook] = []
    for is_dynasty, label, category in (
        (True, "FantasyCalc Direct", "dynasty"),
        (False, "FantasyCalc Redraft Direct", "lineup"),
    ):
        rows = client.get_json(
            FANTASY_CALC_URL,
            params={
                "isDynasty": str(is_dynasty).lower(),
                "numQbs": 2 if is_superflex else 1,
                "numTeams": num_teams,
                "ppr": ppr,
            },
        )
        if not isinstance(rows, list):
            raise DataSourceError(f"{label} returned an invalid payload")
        book = ValueBook(name=label, category=category)
        for row in rows:
            player = row.get("player") or {}
            value = _number(row.get("value"))
            sleeper_id = str(player.get("sleeperId") or "").strip()
            name = str(player.get("name") or "").strip()
            position = str(player.get("position") or "").upper().strip()
            if sleeper_id and value > 0:
                players[sleeper_id] = PlayerIdentity(
                    sleeper_id=sleeper_id,
                    name_id=_name_id(name, position),
                    full_name=name,
                    position=position,
                )
                book.player_values[sleeper_id] = value
            else:
                pick_key = parse_pick_asset(name)
                if pick_key and value > 0:
                    book.pick_values[pick_key] = value
        if len(book.player_values) < 100:
            raise DataSourceError(f"{label} returned too few players")
        books.append(book)
    return MarketData(players=players, books=books, warnings=[])


def parse_pick_asset(name: str) -> tuple[int, str, int] | None:
    """Normalize a market pick such as '2027 Mid 1st' for Sleeper ownership."""
    match = re.search(
        r"\b(20\d{2})\s+(Early|Mid|Late)\s+([1-9])(?:st|nd|rd|th)\b",
        name,
        flags=re.IGNORECASE,
    )
    if match:
        return int(match.group(1)), match.group(2).lower(), int(match.group(3))
    return None


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _name_id(name: str, position: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower()) + position.lower()
