"""Convert CricHeroes PDF scorecards to SPL archive JSON (summary-level, not ball-by-ball)."""
import argparse, json, re
from pathlib import Path
from pypdf import PdfReader

def clean_lines(text):
    return [re.sub(r"\s+", " ", x).strip() for x in text.splitlines() if x.strip() and x.strip() != "\xa0"]

def parse(path, season):
    text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    lines = clean_lines(text)
    joined = "\n".join(lines)
    title = next((x for x in lines if "SINDHI PREMIER LEAGUE SEASON" in x.upper()), "")
    stage_match = re.search(r"\(([^()]*)\)", title)
    stage = stage_match.group(1).strip() if stage_match else "Match"

    # CricHeroes exports may label the result line differently or split it across lines.
    result = ""
    for i, line in enumerate(lines):
        m = re.match(r"^Result\s*:?\s*(.*)$", line, flags=re.I)
        if m:
            candidate = m.group(1).strip()
            if not candidate and i + 1 < len(lines):
                candidate = lines[i + 1].strip()
            if candidate and not re.match(r"^(Toss|Total|Best Performances)", candidate, re.I):
                result = candidate
                break
    # Fallback: detect common result wording anywhere in the extracted text.
    if not result:
        m = re.search(r"([A-Z][A-Z0-9 '&().-]{2,}?\s+(?:won by|tied| ಪಂದ್ಯ|lost by)\s+[^\\n]+)", joined, re.I)
        if m: result = m.group(1).strip()

    dm = re.search(r"Date\s+(\d{4}-\d{2}-\d{2})", joined, re.I)
    date = dm.group(1) if dm else ""
    idx = next((i for i,x in enumerate(lines) if re.match(r"^Match\s+.+\s+vs\s*$", x, re.I)), None)
    team_a = team_b = ""
    if idx is not None:
        team_a = re.sub(r"^Match\s+", "", lines[idx], flags=re.I).replace(" vs","").strip()
        if idx+1 < len(lines): team_b = lines[idx+1].strip()
    else:
        m = re.search(r"Match\s+(.+?)\s+vs\s+(.+)", joined, re.I)
        if m: team_a, team_b = m.group(1).strip(), m.group(2).splitlines()[0].strip()

    ground = ""
    gi = next((i for i,x in enumerate(lines) if x.startswith("Ground ")), None)
    if gi is not None:
        ground = lines[gi][7:]
        if gi+1 < len(lines) and not lines[gi+1].startswith(("Date","Match Result","Toss")):
            ground += ", " + lines[gi+1]
    toss = next((re.sub(r"^Toss\s*", "", x, flags=re.I) for x in lines if re.match(r"^Toss\s+",x,re.I)), "")
    totals=[]
    for x in lines:
        m=re.match(r"Total\s+(.+?)\s+(\d+/\d+)\s+\(([\d.]+)\s+Ov\)",x,re.I)
        if m: totals.append({"team":m.group(1).strip(),"score":m.group(2),"overs":m.group(3)})
    batters=[]; bowlers=[]
    bi=next((i for i,x in enumerate(lines) if x.startswith("Best Performances - Batsmen")),None)
    bo=next((i for i,x in enumerate(lines) if x.startswith("Best Performances - Bowlers")),None)
    if bi is not None and bo is not None:
        for x in lines[bi+1:bo]:
            m=re.match(r"(.+?)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([\d.]+)$",x)
            if m: batters.append({"name":m.group(1),"runs":int(m.group(2)),"balls":int(m.group(3)),"fours":int(m.group(4)),"sixes":int(m.group(5)),"strike_rate":float(m.group(6))})
        for x in lines[bo+1:]:
            if x.startswith("Match Officials"): break
            m=re.match(r"(.+?)\s+([\d.]+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([\d.]+)$",x)
            if m: bowlers.append({"name":m.group(1),"overs":m.group(2),"maidens":int(m.group(3)),"runs":int(m.group(4)),"wickets":int(m.group(5)),"economy":float(m.group(6))})
    return {"id":path.stem,"season":season,"stage":stage,"date":date,"teamA":team_a,"teamB":team_b,"ground":ground,"toss":toss,"result":result,"totals":totals,"bestBatters":batters,"bestBowlers":bowlers,"scorecardText":text.strip(),"sourcePdf":path.name}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True); p.add_argument("--season",required=True,type=int,choices=[1,2,3]); p.add_argument("--output",required=True)
    a=p.parse_args()
    files=sorted(Path(a.input).rglob("*.pdf"))
    if not files: raise SystemExit(f"No PDF files found in {a.input} (including subfolders)")
    records=[parse(f,a.season) for f in files]
    out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding="utf-8")
    missing=[r["sourcePdf"] for r in records if not r["result"]]
    print(f"Converted {len(records)} PDFs to {out}")
    if missing: print("Result not extracted from:", ", ".join(missing))
    print("Review these records against the original PDFs. This converter does not create ball-by-ball data.")
if __name__=="__main__": main()
