import csv
from pathlib import Path

CSV_PATH = Path("exports/latest.csv")

def main():
    rows = []
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    # sort by overall rank (ascending)
    rows.sort(key=lambda r: int(r["Overall Rank"]))

    lines = []
    lines.append("🏆 **Ironbound Sixteen – Dynasty Power Rankings**")
    lines.append("_Tuesday Update_")
    lines.append("")

    for r in rows:
        team = r["Team"]
        rank = r["Overall Rank"]
        value = r.get("Overall Value", "")
        lines.append(f"**#{rank}** — {team}")

    msg = "\n".join(lines)
    print(msg)

if __name__ == "__main__":
    main()
