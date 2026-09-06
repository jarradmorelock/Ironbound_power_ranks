"""Render an image-first ranking board for Discord Gallery view."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import unicodedata

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.patheffects as path_effects  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

from .models import LeagueConfig, RankingResult


def render_chart(result: RankingResult, config: LeagueConfig, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    theme = config.theme
    teams = result.teams

    fig, ax = plt.subplots(figsize=(10, 10), dpi=180)
    fig.patch.set_facecolor(theme.background)
    ax.set_facecolor(theme.background)
    fig.subplots_adjust(left=0.34, right=0.94, top=0.79, bottom=0.14)

    y_positions = list(range(len(teams)))
    market = [team.market_points for team in teams]
    lineup = [team.lineup_points for team in teams]
    season = [team.season_points for team in teams]

    ax.barh(y_positions, market, color=theme.market, height=0.60, label="Market")
    ax.barh(
        y_positions,
        lineup,
        left=market,
        color=theme.lineup,
        height=0.60,
        label="Starting lineup",
    )
    if result.has_season_results:
        left = [a + b for a, b in zip(market, lineup)]
        ax.barh(
            y_positions,
            season,
            left=left,
            color=theme.season,
            height=0.60,
            label="Season results (record-led)",
        )

    for y, team in zip(y_positions, teams):
        _draw_component_values(
            ax,
            y=y,
            values=(team.market_points, team.lineup_points, team.season_points),
            has_season_results=result.has_season_results,
            text_color=theme.text,
            outline_color=theme.background,
        )

    labels = [_team_label(team) for team in teams]
    ax.set_yticks(y_positions, labels=labels, fontsize=10.2, color=theme.text)
    ax.invert_yaxis()
    ax.set_xlim(0, 108)
    ax.set_xticks([0, 20, 40, 60, 80, 100])
    ax.tick_params(axis="x", colors=theme.muted, labelsize=8.5, length=0)
    ax.tick_params(axis="y", length=0, pad=12)
    ax.xaxis.grid(True, color=theme.panel, linewidth=1.0, alpha=0.85)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_visible(False)

    for y, team in zip(y_positions, teams):
        ax.text(
            min(105.5, team.score + 1.2),
            y,
            f"{team.score:.1f}",
            va="center",
            ha="left",
            fontsize=9.5,
            fontweight="bold",
            color=theme.text,
        )
        ax.text(
            -2.0,
            y + 0.29,
            f"{team.record}  |  {safe_chart_text(team.owner_name)[:22]}",
            va="top",
            ha="right",
            fontsize=6.9,
            color=theme.muted,
            clip_on=False,
        )

    fig.text(
        0.06,
        0.935,
        config.brand,
        color=theme.text,
        fontsize=34,
        fontweight="black",
        ha="left",
        va="top",
    )
    fig.text(
        0.06,
        0.882,
        "POWER RANKINGS",
        color=theme.accent,
        fontsize=16,
        fontweight="bold",
        ha="left",
        va="top",
    )
    fig.text(
        0.94,
        0.925,
        _issue_label(result),
        color=theme.text,
        fontsize=12,
        fontweight="bold",
        ha="right",
        va="top",
    )
    fig.text(
        0.94,
        0.892,
        f"{config.publication} · {_format_label(result)}",
        color=theme.muted,
        fontsize=8.5,
        ha="right",
        va="top",
    )
    fig.add_artist(
        Rectangle(
            (0.06, 0.842),
            0.88,
            0.004,
            transform=fig.transFigure,
            color=theme.accent,
            linewidth=0,
        )
    )

    legend = ax.legend(
        loc="lower left",
        bbox_to_anchor=(0, -0.14),
        ncol=3,
        frameon=False,
        fontsize=8.5,
    )
    for text in legend.get_texts():
        text.set_color(theme.muted)

    formula = _formula_label(result)
    source_names = result.dynasty_sources + result.lineup_sources
    sources = ", ".join(source_names)
    source_prefix = (
        "Markets: "
        if any("Direct" in source for source in source_names)
        else "Markets via Dynasty Daddy: "
    )
    fig.text(0.06, 0.055, formula, color=theme.text, fontsize=7.8, ha="left")
    fig.text(
        0.06,
        0.031,
        f"{source_prefix}{sources}  |  League data: Sleeper  |  {_generated_label(result)}",
        color=theme.muted,
        fontsize=6.5,
        ha="left",
    )

    fig.savefig(output, facecolor=fig.get_facecolor(), bbox_inches=None)
    plt.close(fig)
    result.output_image = output


def _draw_component_values(
    ax,
    *,
    y: int,
    values: tuple[float, float, float],
    has_season_results: bool,
    text_color: str,
    outline_color: str,
) -> None:
    """Write each non-zero contribution inside its stacked-bar segment."""
    visible_values = values if has_season_results else values[:2]
    left = 0.0
    for value in visible_values:
        if value > 0:
            narrow = value < 3.8
            label = ax.text(
                left + value / 2,
                y,
                f"{value:.1f}",
                va="center",
                ha="center",
                rotation=90 if narrow else 0,
                fontsize=5.8 if narrow else 7.2,
                fontweight="bold",
                color=text_color,
                clip_on=True,
                zorder=4,
            )
            label.set_path_effects(
                [path_effects.withStroke(linewidth=1.8, foreground=outline_color)]
            )
        left += value


def _team_label(team) -> str:
    name = safe_chart_text(team.team_name).strip()
    if len(name) > 27:
        name = name[:26].rstrip() + "…"
    movement = team.movement
    if movement is None:
        marker = "NEW"
    elif movement > 0:
        marker = f"+{movement}"
    elif movement < 0:
        marker = str(movement)
    else:
        marker = "—"
    return f"{team.rank:>2}.  {name}   {marker}"


def safe_chart_text(value: str) -> str:
    """Keep decorative Sleeper names readable with fonts available in Actions."""
    replacements = {
        "卄": "H",
        "🅱️": "B",
        "🅱": "B",
        "™": "",
    }
    for original, replacement in replacements.items():
        value = value.replace(original, replacement)
    normalized = unicodedata.normalize("NFKC", value)
    return normalized.encode("ascii", "ignore").decode("ascii").strip()


def _issue_label(result: RankingResult) -> str:
    if result.league.week > 0:
        return f"WEEK {result.league.week} · {result.league.season}"
    return f"PRESEASON · {result.league.season}"


def _generated_label(result: RankingResult) -> str:
    try:
        value = datetime.fromisoformat(result.generated_at)
        return value.strftime("%b %-d, %Y %-I:%M %p ET")
    except (TypeError, ValueError):
        return result.generated_at


def _format_label(result: RankingResult) -> str:
    return "SUPERFLEX" if result.league.is_superflex else "1QB"


def _formula_label(result: RankingResult) -> str:
    market = _percent(result.market_weight)
    lineup = _percent(result.lineup_weight)
    season = _percent(result.season_weight)
    if not result.has_season_results:
        return f"{market} market consensus  |  {lineup} starting lineup  |  preseason"
    guardrail = "  |  4+ win-gap guardrail" if result.record_guardrail_active else ""
    return (
        f"{market} market  |  {lineup} lineup  |  {season} season "
        f"(80% record / 20% points){guardrail}"
    )


def _percent(weight: float) -> str:
    return f"{weight * 100:g}%"
