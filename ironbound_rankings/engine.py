"""Deterministic multi-source power-ranking calculation."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from statistics import mean

from .models import (
    LeagueSnapshot,
    LeagueTeam,
    PlayerIdentity,
    RankedTeam,
    RankingResult,
    ValueBook,
)


RECORD_SHARE_OF_SEASON = 0.80
POINTS_SHARE_OF_SEASON = 0.20
GUARDRAIL_MIN_GAMES = 8
GUARDRAIL_WIN_GAP = 4.0
GUARDRAIL_MAX_SCORE_LEAD = 10.0


@dataclass
class _TeamScore:
    team: LeagueTeam
    market: float
    lineup: float
    season: float
    market_points: float
    lineup_points: float
    season_points: float
    score: float
    record_guardrail_applied: bool = False


ELIGIBLE = {
    "QB": {"QB"},
    "RB": {"RB"},
    "WR": {"WR"},
    "TE": {"TE"},
    "FLEX": {"RB", "WR", "TE"},
    "SUPER_FLEX": {"QB", "RB", "WR", "TE"},
}


def rank_league(
    snapshot: LeagueSnapshot,
    players: dict[str, PlayerIdentity],
    books: list[ValueBook],
    previous_ranks: dict[str, int] | None = None,
    generated_at: str = "",
) -> RankingResult:
    previous_ranks = previous_ranks or {}
    dynasty_books = [book for book in books if book.category == "dynasty"]
    lineup_books = [book for book in books if book.category == "lineup"]
    if not dynasty_books or not lineup_books:
        raise ValueError("At least one dynasty and one lineup source are required")

    roster_ids = [team.roster_id for team in snapshot.teams]
    source_totals: dict[str, dict[int, float]] = {}
    source_percentiles: dict[str, dict[int, float]] = {}

    for book in dynasty_books:
        if not _has_roster_coverage(snapshot, book, minimum=0.70):
            continue
        totals = {
            team.roster_id: sum(book.player_values.get(pid, 0) for pid in team.player_ids)
            + sum(_pick_value(book, pick.year, pick.round) for pick in team.picks)
            for team in snapshot.teams
        }
        if max(totals.values(), default=0) <= 0:
            continue
        source_totals[book.name] = totals
        source_percentiles[book.name] = percentile_scores(totals)

    starter_slots = [
        "QB" if slot == "SUPER_FLEX" and not snapshot.is_superflex else slot
        for slot in snapshot.roster_positions
        if slot in ELIGIBLE
    ]
    for book in lineup_books:
        if not _has_roster_coverage(snapshot, book, minimum=0.45):
            continue
        totals = {
            team.roster_id: optimal_lineup_value(
                team.player_ids,
                starter_slots,
                players,
                book.player_values,
            )
            for team in snapshot.teams
        }
        if max(totals.values(), default=0) <= 0:
            continue
        source_totals[book.name] = totals
        source_percentiles[book.name] = percentile_scores(totals)

    usable_dynasty = [book.name for book in dynasty_books if book.name in source_percentiles]
    usable_lineup = [book.name for book in lineup_books if book.name in source_percentiles]
    if not usable_dynasty or not usable_lineup:
        raise ValueError("The available sources did not map enough roster values")

    market_pct = {
        roster_id: mean(source_percentiles[name][roster_id] for name in usable_dynasty)
        for roster_id in roster_ids
    }
    lineup_pct = {
        roster_id: mean(source_percentiles[name][roster_id] for name in usable_lineup)
        for roster_id in roster_ids
    }
    starter_ratings = {
        roster_id: (
            source_totals[usable_lineup[0]][roster_id]
            if len(usable_lineup) == 1
            else lineup_pct[roster_id]
        )
        for roster_id in roster_ids
    }

    completed_games = max((team.games for team in snapshot.teams), default=0)
    has_results = completed_games > 0
    season_pct: dict[int, float] = {}
    if has_results:
        record_pct = percentile_scores(
            {team.roster_id: team.win_percentage for team in snapshot.teams}
        )
        points_pct = percentile_scores(
            {team.roster_id: team.points_for for team in snapshot.teams}
        )
        season_pct = {
            roster_id: (
                record_pct[roster_id] * RECORD_SHARE_OF_SEASON
                + points_pct[roster_id] * POINTS_SHARE_OF_SEASON
            )
            for roster_id in roster_ids
        }
    weights = ranking_weights(completed_games)

    scored: list[_TeamScore] = []
    for team in snapshot.teams:
        rid = team.roster_id
        market_points = market_pct[rid] * weights[0]
        lineup_points = lineup_pct[rid] * weights[1]
        season_points = season_pct.get(rid, 0) * weights[2]
        score = market_points + lineup_points + season_points
        scored.append(
            _TeamScore(
                team=team,
                market=market_pct[rid],
                lineup=lineup_pct[rid],
                season=season_pct.get(rid, 0),
                market_points=market_points,
                lineup_points=lineup_points,
                season_points=season_points,
                score=score,
            )
        )

    record_guardrail_active = completed_games >= GUARDRAIL_MIN_GAMES
    if record_guardrail_active:
        _apply_record_guardrail(scored)
    scored.sort(
        key=lambda item: (
            item.score,
            item.market,
            item.lineup,
            item.team.points_for,
        ),
        reverse=True,
    )

    source_ranks = {
        name: ordinal_ranks(values) for name, values in source_totals.items()
    }
    ranked: list[RankedTeam] = []
    for rank, item in enumerate(scored, start=1):
        team = item.team
        rid = team.roster_id
        ranked.append(
            RankedTeam(
                rank=rank,
                roster_id=rid,
                team_name=team.team_name,
                owner_name=team.owner_name,
                record=team.record,
                points_for=team.points_for,
                score=round(item.score, 1),
                market_percentile=round(item.market, 1),
                lineup_percentile=round(item.lineup, 1),
                season_percentile=(round(season_pct[rid], 1) if has_results else None),
                market_points=round(item.market_points, 2),
                lineup_points=round(item.lineup_points, 2),
                season_points=round(item.season_points, 2),
                starter_rating=round(starter_ratings[rid], 2),
                record_guardrail_applied=item.record_guardrail_applied,
                previous_rank=previous_ranks.get(str(rid)),
                source_ranks={name: ranks[rid] for name, ranks in source_ranks.items()},
            )
        )

    return RankingResult(
        league=snapshot,
        teams=ranked,
        dynasty_sources=usable_dynasty,
        lineup_sources=usable_lineup,
        has_season_results=has_results,
        generated_at=generated_at,
        market_weight=weights[0],
        lineup_weight=weights[1],
        season_weight=weights[2],
        record_guardrail_active=record_guardrail_active,
    )


def ranking_weights(completed_games: int) -> tuple[float, float, float]:
    """Favor win-now starters while results gain influence through the season."""
    if completed_games <= 0:
        return (0.45, 0.55, 0.0)
    if completed_games <= 3:
        return (0.35, 0.45, 0.20)
    if completed_games <= 7:
        return (0.30, 0.40, 0.30)
    return (0.25, 0.35, 0.40)


def _apply_record_guardrail(scored: list[_TeamScore]) -> None:
    """Prevent a clearly worse record from creating an implausibly large lead."""
    by_record = sorted(
        scored,
        key=lambda item: (
            item.team.wins + item.team.ties * 0.5,
            item.team.win_percentage,
        ),
        reverse=True,
    )
    for item in by_record:
        if item.team.games < GUARDRAIL_MIN_GAMES:
            continue
        standing_wins = item.team.wins + item.team.ties * 0.5
        clearly_better = [
            other
            for other in by_record
            if other.team.games >= GUARDRAIL_MIN_GAMES
            and (other.team.wins + other.team.ties * 0.5) - standing_wins
            >= GUARDRAIL_WIN_GAP
        ]
        if not clearly_better:
            continue
        ceiling = min(
            other.score + GUARDRAIL_MAX_SCORE_LEAD for other in clearly_better
        )
        if item.score <= ceiling:
            continue

        target_roster_points = max(0.0, ceiling - item.season_points)
        roster_points = item.market_points + item.lineup_points
        scale = min(1.0, target_roster_points / roster_points) if roster_points else 0.0
        item.market_points *= scale
        item.lineup_points *= scale
        item.score = item.market_points + item.lineup_points + item.season_points
        item.record_guardrail_applied = True


def percentile_scores(values: dict[int, float]) -> dict[int, float]:
    """Return 0-100 relative scores, assigning tied values their average place."""
    if not values:
        return {}
    if len(set(values.values())) == 1:
        return {key: 50.0 for key in values}
    ordered = sorted(values.items(), key=lambda item: item[1])
    result: dict[int, float] = {}
    index = 0
    denominator = max(1, len(ordered) - 1)
    while index < len(ordered):
        end = index
        while end + 1 < len(ordered) and ordered[end + 1][1] == ordered[index][1]:
            end += 1
        average_index = (index + end) / 2
        score = average_index / denominator * 100
        for offset in range(index, end + 1):
            result[ordered[offset][0]] = score
        index = end + 1
    return result


def ordinal_ranks(values: dict[int, float]) -> dict[int, int]:
    ordered = sorted(values.items(), key=lambda item: (-item[1], item[0]))
    return {roster_id: index for index, (roster_id, _) in enumerate(ordered, start=1)}


def optimal_lineup_value(
    player_ids: list[str],
    slots: list[str],
    players: dict[str, PlayerIdentity],
    values: dict[str, float],
) -> float:
    candidates = [
        (pid, players[pid].position, values.get(pid, 0.0))
        for pid in player_ids
        if pid in players and players[pid].position in {"QB", "RB", "WR", "TE"}
    ]
    candidates.sort(key=lambda item: item[2], reverse=True)
    ordered_slots = sorted(slots, key=lambda slot: len(ELIGIBLE[slot]))

    @lru_cache(maxsize=None)
    def solve(slot_index: int, used_mask: int) -> float:
        if slot_index >= len(ordered_slots):
            return 0.0
        slot = ordered_slots[slot_index]
        best = solve(slot_index + 1, used_mask)
        for index, (_pid, position, value) in enumerate(candidates):
            if used_mask & (1 << index) or position not in ELIGIBLE[slot]:
                continue
            best = max(best, value + solve(slot_index + 1, used_mask | (1 << index)))
        return best

    result = solve(0, 0)
    solve.cache_clear()
    return result


def _has_roster_coverage(
    snapshot: LeagueSnapshot, book: ValueBook, *, minimum: float
) -> bool:
    rostered = {
        player_id for team in snapshot.teams for player_id in team.player_ids
    }
    if not rostered:
        return False
    mapped = sum(1 for player_id in rostered if book.player_values.get(player_id, 0) > 0)
    return mapped / len(rostered) >= minimum


def _pick_value(book: ValueBook, year: int, round_number: int) -> float:
    direct = book.pick_values.get((year, "mid", round_number))
    if direct is not None:
        return direct
    same_round = [
        (pick_year, value)
        for (pick_year, tier, pick_round), value in book.pick_values.items()
        if tier == "mid" and pick_round == round_number
    ]
    if not same_round:
        return 0.0
    closest_year, value = min(same_round, key=lambda item: abs(item[0] - year))
    if year > closest_year:
        value *= 0.80 ** (year - closest_year)
    return value
