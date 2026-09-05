# Ironbound Power Rankings

An image-first weekly publisher for the two Ironbound dynasty leagues. Every Saturday at noon in New York, it rebuilds both leagues from live market and Sleeper data, creates a separate branded bar chart for each league, and opens a new post in the correct Discord Forum.

The two publishers share one tested ranking engine, but run as isolated league operations. If one league or webhook fails, the other league is still attempted and any successful publication state is preserved.

## What it publishes

- **IRONBOUND** to the `ironbound weekly` Forum.
- **UNBOUND** to the `unbound weekly` Forum.
- A Gallery-friendly 1800×1800 PNG ranking board.
- A numbered text ranking with each team's live Sleeper record, index score, and week-over-week movement.
- A new Forum thread each week, with optional Forum tags.

The two images deliberately use different visual systems: forged black/brass/crimson for the flagship and broken-chain teal/violet/orange for the free league.

Both Ironbound leagues are **1QB**. Sleeper displays the single quarterback position as `SUPER_FLEX`, but the publisher deliberately treats that slot as QB-only and requests 1QB market values. It does not interpret either league as a true superflex format.

## Live inputs

| Layer | Sources |
| --- | --- |
| Dynasty market consensus | KeepTradeCut, FantasyCalc, DynastyProcess, and DynastySuperflex values supplied through Dynasty Daddy's live market service |
| Starting-lineup strength | KeepTradeCut Redraft and FantasyCalc Redraft values supplied through Dynasty Daddy |
| League truth | Sleeper league format, rosters, traded future picks, records, and points scored |
| Outage fallback | FantasyCalc's direct current dynasty and redraft feeds |

The publisher does not scrape KeepTradeCut. It consumes Dynasty Daddy's consolidated public market response and publishes only derived team-level scores, with source attribution in every image and post.

## Ranking formula

The balance moves toward real results as the season becomes meaningful:

| Completed games | Market consensus | Starting lineup | Season performance |
| --- | ---: | ---: | ---: |
| Preseason | 62.5% | 37.5% | — |
| 1–3 | 50% | 30% | 20% |
| 4–7 | 45% | 25% | 30% |
| 8+ | 35% | 25% | 40% |

- **Market consensus** values each team's complete roster and its actual ownership of the next three rookie-pick classes, averaged across every available dynasty source.
- **Starting-lineup strength** finds the best legal lineup for the league's real Sleeper positions, averaged across the two current-season markets.
- **Season performance** is 80% record and 20% points scored, so wins lead the in-season calculation without making points-for irrelevant.

Beginning after eight completed games, a record guardrail handles extreme disagreements: a team four or more wins behind another team cannot lead it by more than 10 index points. Thus a market-rich 7–7 roster can still rate above a 12–2 contender, but it cannot sit 20 or 30 points clear of it.

Every source is converted to a league-relative percentile before averaging, so a provider with a larger numeric scale cannot overpower the others.

Future picks follow Dynasty Daddy's conservative convention: an unresolved future slot is valued as a mid pick. Traded-pick ownership comes directly from Sleeper.

## GitHub setup

Add these two repository **secrets** under **Settings → Secrets and variables → Actions**:

| Secret | Destination |
| --- | --- |
| `MAIN_IRONBOUND_WEEKLY_WEBHOOK` | Webhook created inside the `ironbound weekly` Forum |
| `FREE_IRONBOUND_WEEKLY_WEBHOOK` | Webhook created inside the `unbound weekly` Forum |

Do not reuse a webhook from a news, transaction, trade, or ordinary text channel. Incoming webhooks are tied to their destination channel.

If either Forum requires a tag, add a repository **variable** containing a JSON list or comma-separated tag IDs:

- `MAIN_IRONBOUND_WEEKLY_TAG_IDS`
- `FREE_IRONBOUND_WEEKLY_TAG_IDS`

Example value:

```text
["123456789012345678"]
```

Keep **Settings → Actions → General → Workflow permissions** on GitHub's safer read-only default. The checked-in workflow explicitly requests only `contents: write`, which it needs to save the two small state files used for movement arrows and duplicate-post protection; every unspecified permission remains disabled.

## Schedule and safety

The workflow is triggered at 12:07 p.m. or 1:07 p.m. Eastern, covering both possible UTC equivalents of Saturday noon while avoiding GitHub's busiest scheduling minute. GitHub passes the exact trigger expression to the publisher, and a New York daylight/standard-time guard permits only the trigger corresponding to 12:07 p.m. to publish. Because the guard checks the intended trigger instead of the runner's eventual start time, an ordinary GitHub scheduling delay cannot suppress the post.

Manual runs default to **Dry run: true**. A dry run fetches real data, builds both complete preview packages, and uploads them as a GitHub Actions artifact without contacting Discord or changing state.

For a manual live run:

1. Open **Actions → Publish Power Rankings → Run workflow**.
2. Choose `all`, `main`, or `free`.
3. Uncheck **Preview only**.
4. Leave **Allow a second live post** unchecked unless replacing a deleted or bad same-week post.

The saved `last_published_key` prevents an accidental second post for the same Sleeper week. The `force_post` option is the deliberate escape hatch.

## Local preview

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m ironbound_rankings --league all
```

Preview files appear under `exports/main/` and `exports/free/`. They are ignored by Git; the workflow keeps each run's previews as downloadable artifacts.

## Repository map

```text
ironbound_rankings/
  sources.py      Dynasty Daddy markets and FantasyCalc fallback
  sleeper.py      rosters, format, records, and pick ownership
  engine.py       source normalization, legal lineups, final index
  render.py       the two Gallery chart designs
  discord.py      safe Forum webhook payloads
  publisher.py    independent league orchestration and previews
leagues.json      non-secret league IDs, brands, and themes
state/            last successful rank order and publication key
tests/            deterministic unit coverage
```

Sleeper and market access are read-only. Discord is contacted only when `--publish` is explicitly supplied or by the guarded weekly schedule.
