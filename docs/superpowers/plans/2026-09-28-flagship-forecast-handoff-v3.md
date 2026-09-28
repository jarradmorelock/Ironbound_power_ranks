# Flagship Forecast Handoff v3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Power Rankings engine the single authority for ranking-component explanation, remaining-schedule strength, and simulated weekly matchup lines based on projected-optimal legal lineups.

**Architecture:** Keep all model calculations in `Ironbound_power_ranks`; Editorial Desk only consumes the resulting handoff. Extend the existing Sleeper snapshot with scoring settings and fetch next-week player projections, then compute projected-optimal legal lineups once before simulation. Add schedule-strength and weekly-matchup forecast blocks to `RankingResult` and serialize them through the v3 handoff.

**Tech Stack:** Python 3.11+, Sleeper public API, existing deterministic ranking/Monte Carlo code, unittest.

**Spec:** User-approved flagship publication audit and 2026-09-28 implementation direction in project conversation.

## Global Constraints

- Ironbound and Unbound remain 1QB for weekly lineup optimization even if a SUPER_FLEX roster slot exists only as an anti-hoarding mechanism.
- Ranking movement and rendered ranking/playoff assets remain owned by this repository.
- Weekly matchup lines must use projected-optimal legal lineups, never submitted current starters.
- The optimal lineup is chosen once from pregame projections, not re-optimized inside each simulation.
- Weekly matchup simulations are deterministic for the same league/week/input data.
- Editorial Desk must receive model inputs/components, not reverse-engineer rendered charts.

## Review Focus

- Projection payloads with only a precomputed `pts` value still produce usable player means.
- Custom Sleeper scoring settings are applied when component projection stats are available.
- Missing projections do not silently promote zero-value players into optimal lineups when alternatives exist.
- Remaining-schedule strength excludes completed weeks and playoff weeks.
- A lineup cannot use the same player in two slots.

---

### Task 1: Ranking component and schedule-strength handoff

**Files:**
- Modify: `ironbound_rankings/models.py`
- Modify: `ironbound_rankings/forecast.py`
- Modify: `ironbound_rankings/handoff.py`
- Test: `tests/test_forecast.py`
- Test: `tests/test_handoff.py`

**Interfaces:**
- Produces: `RankingResult.remaining_schedule_strength: list[dict]`
- Produces: handoff `official_power_rankings[].components`
- Produces: handoff `remaining_schedule_strength`

- [ ] Write failing tests for weighted component details and remaining opponent index/rank.
- [ ] Run the PR test suite and confirm failures reflect missing fields.
- [ ] Implement deterministic schedule-strength attachment from current Power Board scores.
- [ ] Serialize component percentiles/weighted points/weights and schedule strength.
- [ ] Run full regression suite.

### Task 2: Projected-optimal weekly matchup simulation

**Files:**
- Modify: `ironbound_rankings/models.py`
- Modify: `ironbound_rankings/sleeper.py`
- Modify: `ironbound_rankings/forecast.py`
- Modify: `ironbound_rankings/publisher.py`
- Modify: `ironbound_rankings/handoff.py`
- Test: `tests/test_forecast.py`
- Test: `tests/test_integration_units.py`
- Test: `tests/test_handoff.py`

**Interfaces:**
- Consumes: Sleeper next-week projection payload and league scoring settings.
- Produces: `RankingResult.weekly_matchup_forecast: list[dict]`
- Produces: handoff `weekly_matchup_forecast` with projected scores, spread, total, win probability, optimal-lineup player IDs, simulation count, and model label.

- [ ] Write failing tests proving projected-optimal lineup selection and deterministic simulations.
- [ ] Run tests and confirm the feature is absent.
- [ ] Add scoring-settings capture and projection fetching.
- [ ] Implement projected fantasy means, optimal legal lineup selection, and 10,000 deterministic simulations per matchup.
- [ ] Wire the forecast into publisher and handoff.
- [ ] Run full regression suite.

### Task 3: Documentation and contract version

**Files:**
- Modify: `README.md`
- Modify: `ironbound_rankings/handoff.py`
- Test: `tests/test_handoff.py`

**Interfaces:**
- Produces: handoff schema v3 semantics for Editorial Desk.

- [ ] Add contract assertions for schema v3 and model ownership.
- [ ] Document the new fields and the no-reoptimization-inside-simulation rule.
- [ ] Run full regression suite.
