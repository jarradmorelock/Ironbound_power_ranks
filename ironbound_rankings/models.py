"""Shared data structures for the ranking pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Theme:
    background: str
    panel: str
    text: str
    muted: str
    market: str
    lineup: str
    season: str
    accent: str


@dataclass(frozen=True)
class LeagueConfig:
    key: str
    league_id: str
    brand: str
    publication: str
    quarterback_mode: str
    webhook_env: str
    tags_env: str
    theme: Theme


@dataclass(frozen=True)
class PlayerIdentity:
    sleeper_id: str
    name_id: str
    full_name: str
    position: str


@dataclass
class ValueBook:
    name: str
    category: str
    player_values: dict[str, float] = field(default_factory=dict)
    pick_values: dict[tuple[int, str, int], float] = field(default_factory=dict)


@dataclass(frozen=True)
class DraftPick:
    year: int
    round: int
    original_roster_id: int


@dataclass
class LeagueTeam:
    roster_id: int
    owner_id: str
    team_name: str
    owner_name: str
    player_ids: list[str]
    picks: list[DraftPick]
    wins: int
    losses: int
    ties: int
    points_for: float

    @property
    def games(self) -> int:
        return self.wins + self.losses + self.ties

    @property
    def record(self) -> str:
        if self.ties:
            return f"{self.wins}-{self.losses}-{self.ties}"
        return f"{self.wins}-{self.losses}"

    @property
    def win_percentage(self) -> float:
        if not self.games:
            return 0.5
        return (self.wins + self.ties * 0.5) / self.games


@dataclass
class LeagueSnapshot:
    league_id: str
    league_name: str
    season: int
    week: int
    is_superflex: bool
    ppr: float
    roster_positions: list[str]
    teams: list[LeagueTeam]


@dataclass
class RankedTeam:
    rank: int
    roster_id: int
    team_name: str
    owner_name: str
    record: str
    points_for: float
    score: float
    market_percentile: float
    lineup_percentile: float
    season_percentile: float | None
    market_points: float
    lineup_points: float
    season_points: float
    record_guardrail_applied: bool = False
    previous_rank: int | None = None
    source_ranks: dict[str, int] = field(default_factory=dict)

    @property
    def movement(self) -> int | None:
        if self.previous_rank is None:
            return None
        return self.previous_rank - self.rank


@dataclass
class RankingResult:
    league: LeagueSnapshot
    teams: list[RankedTeam]
    dynasty_sources: list[str]
    lineup_sources: list[str]
    has_season_results: bool
    generated_at: str
    market_weight: float
    lineup_weight: float
    season_weight: float
    record_guardrail_active: bool
    output_image: Path | None = None
