"""Convert Season 1 CricHeroes PDFs into the SPL full-scorecard JSON format."""
import argparse
import json
import re
from pathlib import Path
import fitz


def lines_from_page(page):
    return [re.sub(r"\s+", " ", x).strip() for x in page.get_text().splitlines()
            if x.strip() and x.strip() != "\xa0"]


def parse_innings_page(page):
    lines = lines_from_page(page)
    head_i = next(i for i, x in enumerate(lines)
                  if re.search(r"\d+/\d+\s+\([\d.]+\s+Ov\)", x))
    header = lines[head_i]
    m = re.match(r"(.+?)\s+(\d+)/(\d+)\s+\(([\d.]+)\s+Ov\)", header)
    if not m:
        raise ValueError(f"Could not parse innings header: {header}")
    team, runs, wickets, overs = m.group(1).strip(), int(m.group(2)), int(m.group(3)), m.group(4)
    bat_h = lines.index("Batsman")
    bowl_h = lines.index("Bowler")
    batting = []
    i = bat_h + 1
    while i < bowl_h:
        if re.fullmatch(r"\d+", lines[i]) and i + 8 < bowl_h:
            name, status = lines[i + 1], lines[i + 2]
            vals = lines[i + 3:i + 9]
            try:
                r, b, mins, fours, sixes = map(int, vals[:5])
                sr = float(vals[5])
                batting.append({"name": name, "status": status, "runs": r, "balls": b,
                                "minutes": mins, "fours": fours, "sixes": sixes,
                                "strike_rate": sr})
                i += 9
                continue
            except (ValueError, IndexError):
                pass
        i += 1

    extras = {}
    for j, line in enumerate(lines[:bowl_h]):
        if line.startswith("Extras:"):
            for key, value in re.findall(r"(b|lb|wd|nb|pen)\s+(\d+)", line, re.I):
                extras[key.lower()] = int(value)
            if j + 1 < len(lines) and re.fullmatch(r"\d+", lines[j + 1]):
                extras["total"] = int(lines[j + 1])
            break

    fall = ""
    for j, line in enumerate(lines):
        if line == "Fall of Wickets":
            parts = []
            k = j + 1
            while k < len(lines) and not lines[k].startswith("No "):
                parts.append(lines[k])
                k += 1
            fall = " ".join(parts)
            break

    to_bat = []
    for line in lines:
        if line.startswith("To Bat:"):
            to_bat = [x.strip() for x in line.split(":", 1)[1].split(",") if x.strip()]
            break

    bowling = []
    i = bowl_h + 1
    while i < len(lines):
        if re.fullmatch(r"\d+", lines[i]) and i + 11 < len(lines):
            name, vals = lines[i + 1], lines[i + 2:i + 12]
            try:
                ov = vals[0]
                maidens, conceded, wkts, dots, fours, sixes, wides, no_balls = map(int, vals[1:9])
                economy = float(vals[9])
                bowling.append({"name": name, "overs": ov, "maidens": maidens,
                                "runs": conceded, "wickets": wkts, "dot_balls": dots,
                                "fours_conceded": fours, "sixes_conceded": sixes,
                                "wides": wides, "no_balls": no_balls, "economy": economy})
                i += 12
                continue
            except (ValueError, IndexError):
                pass
        i += 1
    return {"team": team, "runs": runs, "wickets": wickets, "overs": overs,
            "batting": batting, "bowling": bowling, "extras": extras,
            "to_bat": to_bat, "fall_of_wickets": fall}


def parse_squads(page):
    lines = lines_from_page(page)
    try:
        ix = lines.index("Playing Squad")
        team_a, team_b = lines[ix + 1], lines[ix + 2]
    except (ValueError, IndexError):
        return []
    squads = {team_a: [], team_b: []}
    i = ix + 3
    while i + 2 < len(lines):
        if re.fullmatch(r"\d{1,2}", lines[i]):
            squads[team_a].append(lines[i + 1])
            squads[team_b].append(lines[i + 2])
            i += 3
        else:
            i += 1
    return [{"team": team, "players": players} for team, players in squads.items()]


def parse_pdf(path):
    doc = fitz.open(path)
    page1 = lines_from_page(doc[0])
    mi = page1.index("Match")
    team_a = page1[mi + 1].replace(" vs", "").strip()
    team_b = page1[mi + 2].strip()
    gi = page1.index("Ground")
    ground = page1[gi + 1] + ", " + page1[gi + 2]
    di = page1.index("Date")
    date_match = re.search(r"\d{4}-\d{2}-\d{2}", page1[di + 1])
    if not date_match:
        raise ValueError(f"Date missing in {path.name}")
    stage = next((x[x.find("(") + 1:x.rfind(")")] for x in page1
                  if x.startswith("SINDHI PREMIER LEAGUE") and "(" in x), "Match")
    toss = next((x for x in page1 if " opt to " in x), "")
    result = ""
    if "Result" in page1 and page1.index("Result") + 1 < len(page1):
        result = page1[page1.index("Result") + 1]

    totals, best_batters, best_bowlers = [], [], []
    for line in page1:
        m = re.match(r"(.+?)\s+(\d+/\d+)\s+\(([\d.]+)\s+Ov\)", line)
        if m:
            totals.append({"team": m.group(1), "score": m.group(2), "overs": m.group(3)})

    try:
        bi, bo = page1.index("Best Performances - Batsmen"), page1.index("Best Performances - Bowlers")
        j = bi + 1
        while j + 5 < bo:
            try:
                best_batters.append({"name": page1[j], "runs": int(page1[j+1]),
                                     "balls": int(page1[j+2]), "fours": int(page1[j+3]),
                                     "sixes": int(page1[j+4]), "strike_rate": float(page1[j+5])})
                j += 6
            except ValueError:
                j += 1
        end = next((k for k in range(bo + 1, len(page1)) if page1[k] == "Match Officials"), len(page1))
        j = bo + 1
        while j + 5 < end:
            try:
                best_bowlers.append({"name": page1[j], "overs": page1[j+1],
                                     "maidens": int(page1[j+2]), "runs": int(page1[j+3]),
                                     "wickets": int(page1[j+4]), "economy": float(page1[j+5])})
                j += 6
            except ValueError:
                j += 1
    except ValueError:
        pass

    innings = [parse_innings_page(doc[2]), parse_innings_page(doc[3])]
    return {"id": path.stem.replace("Scorecard_", ""), "season": 1, "stage": stage,
            "date": date_match.group(0), "teamA": team_a, "teamB": team_b,
            "ground": ground, "toss": toss, "result": result, "totals": totals,
            "bestBatters": best_batters, "bestBowlers": best_bowlers,
            "scorecardText": "\n".join(page.get_text() for page in doc),
            "sourcePdf": path.name, "innings": innings, "squads": parse_squads(doc[1])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    files = sorted(Path(args.input).glob("*.pdf"))
    if not files:
        raise SystemExit("No PDFs found.")
    rows = [parse_pdf(path) for path in files]
    Path(args.output).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Converted {len(rows)} PDFs. Review the JSON before importing; this is scorecard data, not ball-by-ball data.")


if __name__ == "__main__":
    main()
