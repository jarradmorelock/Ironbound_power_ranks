import json
from pathlib import Path

STATE_PATH = Path("state.json")

import requests
import os
import csv
import matplotlib.pyplot as plt
from matplotlib import rcParams
import urllib.request
from pathlib import Path

rcParams["font.family"] = "DejaVu Sans"
rcParams["axes.unicode_minus"] = False

CSV_PATH = Path("exports/latest.csv")
SLEEPER_LEAGUE_ID = "1314016187998294016"
URL_PATH = Path("exports/power_ranks_url.txt")
OUT_PATH = Path("exports/power_ranks_message.txt")
IMG_PATH = Path("exports/power_ranks.png")

def post_to_discord(webhook_url: str, content: str, image_path):
    """
    Posts a message + image to Discord via webhook.
    If webhook_url is missing, do nothing (safe for testing).
    """
    if not webhook_url:
        print("DISCORD_WEBHOOK_URL not set; skipping Discord post.")
    return

    data = {"content": content}

    with open(image_path, "rb") as f:
        files = {"file": (image_path.name, f, "image/png")}
        resp = requests.post(webhook_url, data=data, files=files, timeout=30)

    if resp.status_code >= 300:
        raise RuntimeError(f"Discord webhook post failed: {resp.status_code} {resp.text}")

    print("Posted to Discord.") 

def fetch_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "ironbound-power-ranks/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))

def sleeper_records_by_username(league_id: str) -> dict[str, str]:
    users = fetch_json(f"https://api.sleeper.app/v1/league/{league_id}/users")
    rosters = fetch_json(f"https://api.sleeper.app/v1/league/{league_id}/rosters")

    #user_id -> usernames we can match
    id_to_names: dict[str, set[str]] = {}
    for u in users:
        uid = u.get("user_id")
        if not uid:
            continue
        names = set()
        if u.get("username"):
            names.add(str(u["username"]))
        if u.get("display_name"):
            names.add(str(u["display_name"]))
        if names:
            id_to_names[str(uid)] = names

    out: dict[str, str] = {}
    for r in rosters:
        owner_id = r.get("owner_id")
        if not owner_id:
            continue

        settings = r.get("settings") or {}
        w = int(settings.get("wins", 0) or 0)
        l = int(settings.get("losses", 0) or 0)
        t = int(settings.get("ties", 0) or 0)

        rec = f"{w}-{l}-{t}" if t else f"{w}-{l}"

        for name in id_to_names.get(str(owner_id), set()):
            out[name] = rec

    return out

def read_share_url() -> str:
    if URL_PATH.exists():
        txt = URL_PATH.read_text(encoding="utf-8").strip()
        if txt:
            return txt.splitlines()[0].strip()
    return ""

def main():
    records = sleeper_records_by_username(SLEEPER_LEAGUE_ID)
    share_url = read_share_url()
    
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)

        next(reader, None)  # skip title line
        headers = None
        for row in reader:
            if row and any (cell.strip() for cell in row):
                headers = row
                break
        
        if not headers:
            raise RuntimeError("CSV missing header row")

        rows = []
        for r in reader:
            if not r or len(r) != len(headers):
                continue  # skip blanks/footer/malformed
            rows.append(dict(zip(headers, r)))

    if STATE_PATH.exists():
        with STATE_PATH.open("r", encoding="utf-8") as f:
            prev_state = json.load(f)
    else:
        prev_state = {}

    def rank_key(r):
        v = (r.get("Overall Rank") or "").strip()
        return int(v) if v.isdigit() else 10**9
    rows.sort(key=rank_key)
    msg_lines = []
    msg_lines.append("🏆 **Ironbound Sixteen – Dynasty Power Rankings**")
    msg_lines.append("")
    new_state = {}

    # quick sanity output
    table_rows = []
    for r in rows:
        team = r["Team"]
        rank = int(r["Overall Rank"]) if r["Overall Rank"].strip().isdigit() else None

        prev_rank = prev_state.get(team)

        if prev_rank is None:
            delta = "🆕"
        elif rank < prev_rank:
            delta = f"▲{prev_rank - rank}"
        elif rank > prev_rank:
            delta = f"▼{rank - prev_rank}"
        else:
            delta = "—"
        print(f"{rank}. {team} ({delta})")
        owner = (r.get("Owner") or "").strip()
        record = records.get(owner, records.get(owner.lower(), "-"))
        msg_lines.append(f"**{rank}.** {team} ({delta})  '{record}'")
        new_state[team] = rank
        table_rows.append([str(rank), team, str(delta), record])

    # write updated state AFTER the loop
    with STATE_PATH.open("w", encoding="utf-8") as f:
        json.dump(new_state, f, indent=2)
    if share_url:
        msg_lines.append("")
        msg_lines.append(f"Interactive table: {share_url}")
        
    # ---- build PNG stacked bar chart (overall strength) ----
    def to_int(x):
        try:
            return int(float(str(x).replace(",", "").strip()))
        except Exception:
            return 0

    # rows should already be sorted by Overall Rank (rank 1 first)
    teams = [r.get("Team", "").strip() for r in rows]

    # Try common DynastyDaddy column names (covers your CSV + future variations)
    qb = [to_int(r.get("QB Value", 0)) for r in rows]
    rb = [to_int(r.get("RB Value", 0)) for r in rows]
    wr = [to_int(r.get("WR Value", 0)) for r in rows]
    te = [to_int(r.get("TE Value", 0)) for r in rows]

    # Draft capital shows up under different header names sometimes
    dc_key_candidates = ["Draft Capital Value", "Draft Value", "Picks Value", "Draft Capital"]
    draft = [to_int(next((r.get(k) for k in dc_key_candidates if k in r), 0)) for r in rows]

    fig, ax = plt.subplots(figsize=(12, 8))

    # Stacked horizontal bars (rank 1 at top)
    left = [0] * len(rows)
    ax.barh(teams, qb, left=left, label="QB"); left = [l + v for l, v in zip(left, qb)]
    ax.barh(teams, rb, left=left, label="RB"); left = [l + v for l, v in zip(left, rb)]
    ax.barh(teams, wr, left=left, label="WR"); left = [l + v for l, v in zip(left, wr)]
    ax.barh(teams, te, left=left, label="TE"); left = [l + v for l, v in zip(left, te)]
    ax.barh(teams, draft, left=left, label="Draft Capital")

    ax.invert_yaxis()
    ax.set_title("Ironbound Sixteen — Power Rankings (Stacked Value)")
    ax.set_xlabel("Total Value")
    ax.legend(loc="lower right")

    fig.tight_layout()
    fig.savefig(IMG_PATH, dpi=200)
    plt.close(fig)

    discord_webhook = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    share_url = os.getenv("DYNASTY_DADDY_SHARE_URL", "").strip()

    if share_url:
        msg_lines.append("")
        msg_lines.append(f"Interactive table: {share_url}")

    message = "/n".join(msg_lines)
    
    OUT_PATH.write_text("\n".join(msg_lines), encoding="utf-8")

    post_to_discord(discord_webhook, message, IMG_PATH)

if __name__ == "__main__":
    main()
