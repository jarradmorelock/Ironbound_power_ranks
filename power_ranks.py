import json
from pathlib import Path

STATE_PATH = Path("state.json")

import csv
from pathlib import Path

CSV_PATH = Path("exports/latest.csv")

def main():
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

    rows.sort(key=lambda r: int(r["Overall Rank"]))
    new_state = {}

    # quick sanity output
    for r in rows:
        team = r["Team"]
        rank = int(r["Overall Rank"])

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
    new_state[team] = rank


    with STATE_PATH.open("w", encoding="utf-8") as f:
      json.dump(new_state, f, indent=2)  

if __name__ == "__main__": 
    main()
