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

    rows.sort(key=lambda r: int(r["Overall Rank"]))

    # quick sanity output
    for r in rows:
        print(f'{r["Overall Rank"]}. {r["Team"]}')

if __name__ == "__main__":
    main()
