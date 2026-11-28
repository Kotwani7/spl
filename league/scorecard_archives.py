"""Validation helpers for reconciling season JSON against CricHeroes PDFs."""

import copy
import io
import math
import re
import unicodedata
from pathlib import Path

from pypdf import PdfReader


class ScorecardDataError(ValueError):
    """A PDF could not be read as a textual scorecard."""


def _compact(value):
    value = unicodedata.normalize("NFKD", str(value or "")).casefold()
    return re.sub(r"[^a-z0-9]+", "", value)


def _display(value):
    value = unicodedata.normalize("NFKD", str(value or "")).casefold()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value)).strip()


def overs_to_balls(value):
    match = re.fullmatch(r"\s*(\d+)(?:\.(\d))?\s*", str(value or "0"))
    if not match:
        raise ValueError(f"Invalid cricket overs value: {value!r}")
    partial = int(match.group(2) or 0)
    if partial > 5:
        raise ValueError(f"Invalid partial over in cricket overs value: {value!r}")
    return int(match.group(1)) * 6 + partial


def extract_pdf_text(content):
    """Read embedded PDF text in memory; source PDFs are never written to disk."""
    try:
        reader = PdfReader(io.BytesIO(content), strict=False)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ScorecardDataError("encrypted PDF has no usable embedded text")
        text = "\n\f\n".join(page.extract_text() or "" for page in reader.pages)
    except ScorecardDataError:
        raise
    except Exception as exc:
        raise ScorecardDataError(f"PDF text extraction failed: {exc}") from exc

    if len(_compact(text)) < 100:
        raise ScorecardDataError("PDF has no usable embedded text")
    return text


def _close(left, right):
    try:
        return math.isclose(float(left), float(right), rel_tol=0, abs_tol=0.011)
    except (TypeError, ValueError):
        return False


def _row_player(prefix, expected, remaining):
    """Match a PDF row to one exact scorecard name, allowing role suffixes."""
    name_text = re.sub(r"^\s*\d+\s+", "", prefix).strip()
    normalized_prefix = _compact(name_text)
    candidates = [
        (index, row, _compact(row.get("name")))
        for index, row in remaining
        if _compact(row.get("name"))
        and normalized_prefix.startswith(_compact(row.get("name")))
    ]
    if not candidates:
        return None
    longest = max(len(name_key) for _, _, name_key in candidates)
    candidates = [entry for entry in candidates if len(entry[2]) == longest]
    return candidates[0] if len(candidates) == 1 else None


_INNINGS_HEADER = re.compile(
    r"^\s*(?P<team>.+?)\s+(?P<runs>\d+)\s*/\s*(?P<wickets>\d+)\s+"
    r"\((?P<overs>[0-9.]+)\s+Ov\)\s+\((?P<number>\d+(?:st|nd|rd|th))\s+Innings\)",
    re.I,
)
_BATTER_TAIL = re.compile(
    r"(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([0-9.]+)\s*$"
)
_BOWLER_TAIL = re.compile(
    r"([0-9.]+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+"
    r"(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([0-9.]+)\s*$"
)
_EXTRAS = re.compile(r"^\s*Extras:\s*(?:\((.*?)\)\s*)?(\d+)\s*$", re.I)


def _innings_sections(text):
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if _INNINGS_HEADER.search(line)]
    sections = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(lines)
        sections.append((lines[start:end], _INNINGS_HEADER.search(lines[start])))
    return sections


def _parse_extras(lines, expected, filename, issues):
    extras_line = next(
        (line for line in lines if line.strip().casefold().startswith("extras:")),
        None,
    )
    parsed = _EXTRAS.match(extras_line or "")
    if not parsed:
        issues.append("innings extras could not be read")
        return {}

    codes = {
        key.casefold(): int(value)
        for key, value in re.findall(r"([a-z]+)\s+(\d+)", parsed.group(1) or "", re.I)
    }
    codes["total"] = int(parsed.group(2))
    source = {str(key).casefold(): int(value or 0) for key, value in (expected or {}).items()}
    for key in set(codes) | set(source):
        if key == "total":
            if key in source and codes.get(key, 0) != source[key]:
                issues.append(
                    f"innings extras total differs (PDF {codes.get(key, 0)}, JSON {source[key]})"
                )
        elif codes.get(key, 0) != source.get(key, 0):
            issues.append(
                f"innings extra {key} differs (PDF {codes.get(key, 0)}, JSON {source.get(key, 0)})"
            )
    return codes


def _validate_batting(lines, source_rows, filename, issues):
    remaining = list(enumerate(source_rows or []))
    ordered = []
    for line in lines[1:]:
        if line.strip().casefold().startswith("extras:"):
            break
        parsed = _BATTER_TAIL.search(line)
        if not parsed:
            continue
        matched = _row_player(line[:parsed.start()], source_rows or [], remaining)
        if matched is None:
            issues.append("a batting row could not be matched to one player name")
            continue
        index, row, _ = matched
        remaining = [entry for entry in remaining if entry[0] != index]
        runs, balls, minutes, fours, sixes, strike_rate = parsed.groups()
        facts = (int(runs), int(balls), int(minutes), int(fours), int(sixes), float(strike_rate))
        source_facts = (
            int(row.get("runs") or 0),
            int(row.get("balls") or 0),
            int(row.get("minutes") or 0),
            int(row.get("fours") or 0),
            int(row.get("sixes") or 0),
            float(row.get("strike_rate") or 0),
        )
        if facts[:5] != source_facts[:5] or not _close(facts[5], source_facts[5]):
            issues.append(f"batting figures differ for {row.get('name', 'unknown player')}")
        batter = copy.deepcopy(row)
        batter["position"] = len(ordered) + 1
        ordered.append(batter)

    if remaining:
        names = ", ".join(str(row.get("name", "unknown player")) for _, row in remaining)
        issues.append(f"batting players are absent from PDF rows: {names}")
    if len(ordered) != len(source_rows or []):
        issues.append("PDF batting row count differs from JSON")
    return ordered


def _validate_bowling(lines, source_rows, issues):
    remaining = list(enumerate(source_rows or []))
    ordered = []
    in_bowling = False
    for line in lines:
        if "No Bowler" in line:
            in_bowling = True
            continue
        if not in_bowling:
            continue
        parsed = _BOWLER_TAIL.search(line)
        if not parsed:
            continue
        matched = _row_player(line[:parsed.start()], source_rows or [], remaining)
        if matched is None:
            issues.append("a bowling row could not be matched to one player name")
            continue
        index, row, _ = matched
        remaining = [entry for entry in remaining if entry[0] != index]
        overs, maidens, runs, wickets, dots, fours, sixes, wides, no_balls, economy = parsed.groups()
        facts = (
            overs_to_balls(overs),
            int(maidens),
            int(runs),
            int(wickets),
            int(dots),
            int(fours),
            int(sixes),
            int(wides),
            int(no_balls),
            float(economy),
        )
        source_facts = (
            overs_to_balls(row.get("overs")),
            int(row.get("maidens") or 0),
            int(row.get("runs") or 0),
            int(row.get("wickets") or 0),
            int(row.get("dot_balls") or 0),
            int(row.get("fours_conceded") or 0),
            int(row.get("sixes_conceded") or 0),
            int(row.get("wides") or 0),
            int(row.get("no_balls") or 0),
            float(row.get("economy") or 0),
        )
        if facts[:9] != source_facts[:9] or not _close(facts[9], source_facts[9]):
            issues.append(f"bowling figures differ for {row.get('name', 'unknown player')}")
        bowler = copy.deepcopy(row)
        bowler["position"] = len(ordered) + 1
        ordered.append(bowler)

    if remaining:
        names = ", ".join(str(row.get("name", "unknown player")) for _, row in remaining)
        issues.append(f"bowlers are absent from PDF rows: {names}")
    if len(ordered) != len(source_rows or []):
        issues.append("PDF bowling row count differs from JSON")
    return ordered


def _match_facts(text):
    flat = " ".join(text.split())
    header = re.search(
        r"\bMatch\s+Details\s+Match\s+(.+?)\s+vs\s+(.+?)\s+"
        r"Ground\s+(.+?)\s+Date\s+(\d{4}-\d{2}-\d{2})\b",
        flat,
        re.I,
    )
    if not header:
        return {}, ["match header, teams, venue, or date could not be read"]

    facts = {
        "teamA": header.group(1).strip(),
        "teamB": header.group(2).strip(),
        "ground": header.group(3).strip(),
        "date": header.group(4),
    }
    toss = re.search(r"\bToss\s+(.+?)\s+Total\s+", flat, re.I)
    facts["toss"] = toss.group(1).strip() if toss else ""

    best_index = flat.casefold().find("best performances")
    result_marker = flat.casefold().rfind("result", 0, best_index if best_index >= 0 else None)
    facts["result"] = (
        flat[result_marker + len("result"):best_index].strip(" :\t")
        if result_marker >= 0 and best_index >= 0
        else ""
    )

    title = next(
        (line for line in text.splitlines() if "SINDHI PREMIER LEAGUE" in line.upper()),
        "",
    )
    stage = re.search(r"\(([^()]*)\)", title)
    facts["stage"] = stage.group(1).strip() if stage else ""

    total_start = flat.casefold().find("total")
    total_end = flat.casefold().rfind("result", 0, best_index if best_index >= 0 else None)
    total_text = flat[total_start + len("total"):total_end] if 0 <= total_start < total_end else ""
    facts["totals"] = {
        _compact(team): (int(runs), int(wickets), overs)
        for team, runs, wickets, overs in re.findall(
            r"(.+?)\s+(\d+)\s*/\s*(\d+)\s+\(([0-9.]+)\s+Ov\)",
            total_text,
            re.I,
        )
    }
    return facts, []


def validate_scorecard_record(record, text, filename):
    """Return a PDF-verified row, issues, and fields recovered from PDF text."""
    row = copy.deepcopy(record)
    issues = []
    recovered = []
    filename = Path(filename).name
    file_id = re.fullmatch(r"Scorecard_(\d+)\.pdf", filename, re.I)
    if not file_id or str(row.get("id") or "") != file_id.group(1):
        issues.append("PDF filename ID does not match the season JSON record ID")
    if len(_compact(text)) < 100:
        issues.append("PDF has no usable embedded text")
    facts, fact_issues = _match_facts(text)
    issues.extend(fact_issues)
    if issues:
        return None, issues, recovered

    for field in ("teamA", "teamB", "date", "ground", "toss", "stage"):
        expected = row.get(field)
        actual = facts.get(field)
        if expected and actual and _display(expected) != _display(actual):
            issues.append(f"{field} differs between PDF and JSON")
        elif not expected and actual:
            row[field] = actual
            recovered.append(field)

    pdf_result = facts.get("result") or ""
    source_result = str(row.get("result") or "").strip()
    if source_result and pdf_result and _display(source_result) != _display(pdf_result):
        issues.append("result differs between PDF and JSON")
    elif not source_result and pdf_result:
        row["result"] = pdf_result
        recovered.append("result")
    elif not pdf_result:
        issues.append("result could not be read from PDF")

    expected_innings = row.get("innings") or []
    if len(facts.get("totals", {})) != len(expected_innings):
        issues.append("match summary innings totals could not be fully read")
    for innings in expected_innings:
        summary = facts.get("totals", {}).get(_compact(innings.get("team")))
        if summary is None:
            issues.append(f"match summary is missing {innings.get('team', 'an innings team')}")
            continue
        pdf_runs, pdf_wickets, pdf_overs = summary
        try:
            same_total = (
                pdf_runs == int(innings.get("runs") or 0)
                and pdf_wickets == int(innings.get("wickets") or 0)
                and overs_to_balls(pdf_overs) == overs_to_balls(innings.get("overs"))
            )
        except (TypeError, ValueError):
            same_total = False
        if not same_total:
            issues.append(f"innings total differs for {innings.get('team', 'unknown team')}")

    sections = _innings_sections(text)
    if len(sections) != len(expected_innings):
        issues.append("innings count differs between PDF and JSON")

    updated_innings = []
    sections_by_team = {_compact(header.group("team")): lines for lines, header in sections}
    if len(sections_by_team) != len(sections):
        issues.append("PDF innings team names are ambiguous")

    for innings in expected_innings:
        team_key = _compact(innings.get("team"))
        section = sections_by_team.get(team_key)
        if section is None:
            issues.append(f"PDF innings section is missing {innings.get('team', 'unknown team')}")
            continue
        header = _INNINGS_HEADER.search(section[0])
        if not header:
            issues.append(f"PDF innings header is unreadable for {innings.get('team', 'unknown team')}")
            continue
        if (
            int(header.group("runs")) != int(innings.get("runs") or 0)
            or int(header.group("wickets")) != int(innings.get("wickets") or 0)
            or overs_to_balls(header.group("overs")) != overs_to_balls(innings.get("overs"))
        ):
            issues.append(f"innings header differs for {innings.get('team', 'unknown team')}")

        batting = _validate_batting(section, innings.get("batting", []), filename, issues)
        bowling = _validate_bowling(section, innings.get("bowling", []), issues)
        extras = _parse_extras(section, innings.get("extras", {}), filename, issues)
        refreshed = copy.deepcopy(innings)
        refreshed["batting"] = batting
        refreshed["bowling"] = bowling
        refreshed["extras"] = extras
        updated_innings.append(refreshed)

    if not issues:
        row["innings"] = updated_innings
        row["sourcePdf"] = filename
        if not row.get("scorecardText"):
            row["scorecardText"] = text
            recovered.append("scorecardText")
        return row, [], recovered
    return None, issues, recovered
