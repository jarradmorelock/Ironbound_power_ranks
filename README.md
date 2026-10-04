# Ironbound Power Rankings

An image-first weekly publisher for the two Ironbound dynasty leagues. Every Saturday at noon in New York, it rebuilds both leagues from live market and Sleeper data, creates a separate branded bar chart for each league, and opens a new post in the correct Discord Forum. Every Tuesday at 11:07 a.m. Eastern, it rebuilds a magazine-ready copy from the latest records and emails all four graphics to the publications inbox.

The two publishers share one tested ranking engine, but run as isolated league operations. If one league or webhook fails, the other league is still attempted and any successful publication state is preserved.

## What it publishes

- **IRONBOUND** to the `ironbound weekly` Forum.
- **UNBOUND** to the `unbound weekly` Forum.
- Two Gallery-friendly 1800×1800 PNGs: the power-ranking board and a playoff forecast.
- Image-first Forum posts with concise formula and source context; team details stay in the graphics.
- A new Forum thread each week, with optional Forum tags.
- One Tuesday email containing both leagues' power-ranking and playoff-forecast graphics.

The two images deliberately use different visual systems: forged black/brass/crimson for the flagship and broken-chain teal/violet/orange for the free league.

Both Ironbound leagues are **1QB**. Sleeper displays the single quarterback position as `SUPER_FLEX`, but the publisher deliberately treats that slot as QB-only and requests 1QB market values. It does not interpret either league as a true superflex format.

## Live inputs

| Layer | Sources |
| --- | --- |
| Dynasty market consensus | KeepTradeCut, FantasyCalc, DynastyProcess, and DynastySuperflex values supplied through Dynasty Daddy's live market service |
| Starting-lineup strength | Dynasty Daddy's aggregate ADP before results exist, then its rest-of-season rankings once games have been played |
| League truth | Sleeper league format, rosters, schedule, divisions, playoff settings, traded future picks, records, and points scored |
| Outage fallback | FantasyCalc's direct current dynasty and redraft feeds |

The publisher does not scrape KeepTradeCut. It consumes Dynasty Daddy's consolidated public market response and publishes only derived team-level scores, with source attribution in every image and post.

## Ranking formula

The balance moves toward real results every completed NFL week:

| Completed NFL weeks | Market consensus | ROS scoring | Season performance |
| ---: | ---: | ---: | ---: |
| Preseason | 45.0% | 55.0% | — |
| 1 | 35.0% | 45.0% | 20.0% |
| 2 | 33.6% | 43.6% | 22.9% |
| 3 | 32.1% | 42.1% | 25.7% |
| 4 | 30.7% | 40.7% | 28.6% |
| 5 | 29.3% | 39.3% | 31.4% |
| 6 | 27.9% | 37.9% | 34.3% |
| 7 | 26.4% | 36.4% | 37.1% |
| 8+ | 25.0% | 35.0% | 40.0% |

- **Market consensus** is unchanged for the dynasty leagues: it values each team's complete roster and actual ownership of the next three rookie-pick classes, averaged across every available dynasty source.
- **ROS scoring** is projection-based. For each available remaining fantasy week through Week 17, Sleeper player projections are rescored with that league's actual offensive scoring settings, the best legal lineup is selected independently for that week, and those weekly team totals are averaged. This lets byes, depth, projected role changes, and league-specific scoring matter without awarding points merely for sitting on the bench. Taxi players are excluded until activated; reserve players can contribute in a future week when the provider projects them to play.
- **Season performance** remains 80% record and 20% points scored.

If remaining-week projection coverage is unavailable, the engine falls back to its prior Dynasty Daddy/FantasyCalc starter-ranking method rather than converting missing projections to zero.

The win-now share—ROS scoring plus season performance—grows from 55% in the preseason to 75% after eight completed NFL weeks. Long-term dynasty value remains meaningful without allowing bench depth and future picks to dominate a weekly power ranking.

Beginning after eight completed NFL weeks, a record guardrail handles extreme disagreements: a team four or more wins behind another team cannot lead it by more than 10 index points. Thus a market-rich 7–7 roster can still rate above a 12–2 contender, but it cannot sit 20 or 30 points clear of it.

Every source is converted to a league-relative percentile before averaging, so a provider with a larger numeric scale cannot overpower the others.

Future picks follow Dynasty Daddy's conservative convention: an unresolved future slot is valued as a mid pick. Traded-pick ownership comes directly from Sleeper.

## Playoff forecast

The second Gallery image is rebuilt automatically every week. It runs 10,000 deterministic simulations using each league's real Sleeper schedule, four divisions, seven playoff berths, and first-round bye structure. It reports projected record, make-playoffs odds, division odds, bye odds, and championship odds for every team.

The matchup probabilities use the same ROS scoring strength signal as the power rankings when remaining-week projection coverage is available. After completed games exist, prior Sleeper results make a modest Elo adjustment before the remaining schedule is simulated. The calculation runs inside this publisher because Dynasty Daddy's playoff calculator is computed in the browser rather than exposed as a weekly downloadable value.

## GitHub setup

Add these repository **secrets** under **Settings → Secrets and variables → Actions**:

| Secret | Destination |
| --- | --- |
| `MAIN_IRONBOUND_WEEKLY_WEBHOOK` | Webhook created inside the `ironbound weekly` Forum |
| `FREE_IRONBOUND_WEEKLY_WEBHOOK` | Webhook created inside the `unbound weekly` Forum |
| `PUBLICATIONS_EMAIL_FROM` | Dedicated Gmail sender address |
| `PUBLICATIONS_EMAIL_TO` | Publications inbox; multiple addresses may be comma-separated |
| `PUBLICATIONS_EMAIL_APP_PASSWORD` | Google app password for the dedicated sender account |

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

The Discord workflow carries both possible UTC equivalents of Saturday noon while avoiding GitHub's busiest scheduling minute. GitHub passes the exact trigger expression to the publisher, and a New York daylight/standard-time guard permits only the trigger corresponding to 12:07 p.m. Eastern to publish. Because the guard checks the intended trigger instead of the runner's eventual start time, an ordinary GitHub scheduling delay cannot suppress the post.

The separate email workflow uses the same daylight/standard-time protection to send only at 11:07 a.m. Eastern each Tuesday. It rebuilds the graphics from the latest Sleeper records, emails them through the publications Gmail account, and uploads the package as a workflow artifact. It never contacts Discord.

Rank movement follows one continuous publication timeline. Tuesday compares with the preceding Saturday; the next Saturday compares with Tuesday. Thus a team ranked second on Tuesday and fourth on Saturday displays a two-place drop. Discord and email keep separate duplicate-delivery keys, so sharing the rank history cannot accidentally suppress either publication.

Manual runs default to **Dry run: true**. A dry run fetches real data, builds both complete preview packages, and uploads them as a GitHub Actions artifact without contacting Discord or changing state.

For a manual live run:

1. Open **Actions → Publish Power Rankings → Run workflow**.
2. Choose `all`, `main`, or `free`.
3. Uncheck **Preview only**.
4. Leave **Allow a second live post** unchecked unless replacing a deleted or bad same-week post.

The saved `last_published_key` prevents an accidental second post for the same Sleeper week. The `force_post` option is the deliberate escape hatch.

For a manual email test, open **Actions → Email Power Rankings → Run workflow**, choose `all`, and check **Send the real email**. Manual runs default to preview-only and do not replace the official Tuesday history.

## Editorial Desk publication handoff

The Power Rankings engine is the single authority for ranking order,
previous-rank comparison, and movement. Tuesday's ranking build reads the shared
publication history left by the preceding Saturday publication, so the movement
shown in the Tuesday magazine package is the same movement generated by this
engine. Editorial Desk must not recalculate it.

Each successful Tuesday handoff contains explicit cycle metadata:
`ranking_week` is the upcoming Sleeper week shown on the chart, while
`results_through_week` is the completed week whose magazine is being built.
For example, the Tuesday after Week 2 produces a Week 3 ranking graphic with
`results_through_week: 2`.

It also contains:

- current rank, previous rank, movement, composite score, and the underlying market / rest-of-season scoring / season-results components for every team;
- projected record and playoff/division/bye/final/championship probabilities;
- remaining-schedule strength derived from the current Power Board index, including the opponent-by-opponent index trail, average opponent index, difficulty rank, and display grade;
- a weekly matchup forecast built from projected-optimal legal lineups, with projected scores, simulation-derived spread and over/under, win probability, selected player IDs, and model metadata;
- the exact rendered Power Rankings PNG; and
- the exact rendered Playoff Forecast PNG.

The weekly matchup model never uses the lineup a manager happens to have submitted when the ranking run occurs. It chooses each team's best legal lineup from the pregame Sleeper projections exactly once, then holds those players fixed through 10,000 deterministic simulations. It does not re-optimize inside each simulated outcome, so managers are not granted perfect hindsight. Ironbound and Unbound remain 1QB for this optimization, including the Sleeper `SUPER_FLEX` anti-hoarding slot.

The Power Rankings engine also owns remaining-schedule difficulty because that feature is explicitly defined by the current Power Board index. Editorial Desk receives the result and may explain it, but must not independently recalculate it.

The PNGs are copied into `handoff/assets/` and described in the JSON manifest
with filename, SHA-256 checksum, media type, generated time, and the policy
`use supplied graphic unchanged`. Editorial Desk consumes these assets as
publication-ready graphics rather than redrawing them.

## Local preview

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m ironbound_rankings --league all
```

Preview files appear under `exports/main/` and `exports/free/`, including `latest.png` and `latest-playoffs.png`. They are ignored by Git; the workflow keeps each run's previews as downloadable artifacts.

## Repository map

```text
ironbound_rankings/
  sources.py      Dynasty Daddy markets and FantasyCalc fallback
  sleeper.py      rosters, schedule, records, settings, and pick ownership
  engine.py       source normalization, legal lineups, final index
  forecast.py     Elo adjustment and 10,000 playoff simulations
  weekly_forecast.py  remaining-schedule strength and projected-optimal weekly lines/totals
  render.py       power-ranking and playoff Gallery charts
  discord.py      safe Forum webhook payloads
  mailer.py       Tuesday Gmail package and attachments
  publisher.py    independent league orchestration and previews
leagues.json      non-secret league IDs, brands, and themes
state/            shared cross-publication rank history and delivery keys
tests/            deterministic unit coverage
```

Sleeper and market access are read-only. Discord is contacted only when `--publish` is explicitly supplied or by the guarded weekly schedule.

Weekly forecast legality excludes Sleeper reserve/taxi players and currently
out, inactive, IR, PUP, or suspended players, without removing those assets from
dynasty rankings. Questionable/doubtful players remain projection candidates.
If current availability cannot be fetched, the weekly forecast is omitted
rather than represented as verified. The lineup optimizer processes each player
once and searches occupied starter slots, so deep dynasty benches stay tractable.
The handoff records the projection fetch time and explicitly labels positional
volatility as an experimental independent-player heuristic, not a calibrated
historical or correlated game model.
