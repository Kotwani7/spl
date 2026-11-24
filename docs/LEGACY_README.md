# Sindhi Premier League — Full-stack Django website

This project includes a Django backend, SQLite database for local development, responsive mobile navigation, public pages, organiser/admin management, sponsor records, contact enquiry storage, and Season 3 scorecard summaries.

## 1. Windows setup (PowerShell)

Open PowerShell in this project folder:

```powershell
py -m venv .venv
.venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py makemigrations league
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open `http://127.0.0.1:8000/`. Admin: `http://127.0.0.1:8000/django-admin/`.

If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, then activate again.

## 2. Import Season 3 scorecard summaries

The `data/season3.json` file contains the 31 extracted Season 3 scorecard records. After migrations, run:

```powershell
python manage.py import_season_json --file data/season3.json --season 3
```

This imports match summary, result text, innings totals, best batting/bowling highlights and extracted scorecard text. It does NOT create ball-by-ball deliveries, so calculated ball-by-ball leaderboards remain empty until valid delivery data is imported.

## 3. Add Season 2

1. Create `source-pdfs/season2/` and put the extracted PDF files inside it (nested folders are okay).
2. Install the PDF parser: `python -m pip install pypdf`.
3. Convert PDFs:

```powershell
python tools/convert_pdfs.py --input source-pdfs/season2 --season 2 --output data/season2.json
```

4. Inspect `data/season2.json` against the original PDFs.
5. Import into Django:

```powershell
python manage.py import_season_json --file data/season2.json --season 2
```

Do not import a scorecard summary as ball-by-ball data. Results are stored only when extracted from the source.

## 4. Manage the site

Sign in at `/django-admin/`. Add Tournament, Team, Player, Match, Sponsor and Innings records. The Sponsors page is database-driven. Upload sponsor logos through the Sponsor admin form. The organiser page links to Django Admin and supports the existing normalized ball-by-ball CSV importer.

## 5. Contact email and Gmail

The admin/contact address is configured as `vanshkotwani8@gmail.com`. Website contact enquiries are always saved to the database. To send email notifications:
- Enable 2-Step Verification on the Gmail account.
- Generate a Google App Password.
- Put it in `.env` as `EMAIL_HOST_USER=vanshkotwani8@gmail.com` and `EMAIL_HOST_PASSWORD=your-app-password`.
- Never share the App Password, commit `.env`, or put it in frontend code.

No Gmail credentials are embedded or required to run the website locally.

## 6. Mobile navigation

The top navigation collapses into a menu button on mobile. The menu opens as a full-height vertical navigation panel with all main sections and closes after a link is selected.

## 7. Public launch checklist

This package is ready for local setup and testing, not one-click public deployment. Before publishing:
- Use a production PostgreSQL database (not SQLite).
- Set a strong private `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`.
- Configure HTTPS, static/media hosting and backups.
- Deploy using a production WSGI server (e.g. Gunicorn) on a supported host.
- Create the production admin account securely.
- Confirm permission and accuracy for all CricHeroes data and logos.
- Add official registration form URL and confirmed sponsor details.

Do not publish `.env`, database backups, or admin credentials.


## Season 2 archive supplied in this conversation
The uploaded `SPL 2.zip` contains 16 PDFs. All 16 are explicitly labelled **League Matches** in their PDF headers. The ZIP does not include any file labelled Qualifier, Eliminator, Semi Final or Final, so this import classifies all 16 supplied records as League Matches and does not fabricate a playoff bracket or playoff fixtures. If additional playoff PDFs exist, add them to the archive and rerun conversion/import after checking their labels.

The updated `data/season2.json` retains both innings' batter rows, dismissal/status text, batting figures, extras, total, fall of wickets, bowling figures, plus the original extracted text for each match. Some PDF scorecards may contain OCR/text-layout ambiguities; cross-check the displayed rows against the original PDF. The data supplied contains 16 matches, not necessarily the complete Season 2 tournament.


## Updated Season 2 + automatic player registration
The included `data/season2.json` now contains 28 match records (21 League Matches, 4 Quarter Finals, 2 Semi Finals, 1 Final) and full extracted batting/bowling innings for all 28 supplied PDFs. Season 3 roster data is included in `data/season3.json`.

Import both seasons after migrations:
```powershell
python manage.py import_season_json --file data/season2.json --season 2
python manage.py import_season_json --file data/season3.json --season 3
```
The importer creates Player records from playing squads, batting rows and bowling rows, and links them to the relevant team where the scorecard identifies the team. Exact case-insensitive names are reused across seasons; ambiguous spelling variants are not automatically merged. CricHeroes deleted-user placeholders are skipped.

Then open Django Admin → Players to review the imported player records and team links.


## Updated Season 2 + automatic player registration
The included `data/season2.json` now contains 28 match records (21 League Matches, 4 Quarter Finals, 2 Semi Finals, 1 Final) and full extracted batting/bowling innings for all 28 supplied PDFs. Season 3 roster data is included in `data/season3.json`.

Import both seasons after migrations:
```powershell
python manage.py import_season_json --file data/season2.json --season 2
python manage.py import_season_json --file data/season3.json --season 3
```
The importer creates Player records from playing squads, batting rows and bowling rows, and links them to the relevant team where the scorecard identifies the team. Exact case-insensitive names are reused across seasons; ambiguous spelling variants are not automatically merged. CricHeroes deleted-user placeholders are skipped.

Then open Django Admin → Players to review the imported player records and team links.

Windows shortcut: after installing requirements and creating `.env`, double-click `IMPORT-SEASONS.bat` from the project folder to run migrations and import both Season 2 and Season 3.


## Complete Season 2 and Season 3 scorecards

This package includes full scorecard JSON extracted from the supplied CricHeroes PDFs:
- Season 2: 28 matches (21 league, 4 quarter-final, 2 semi-final, 1 final).
- Season 3: 31 matches (24 league, 4 quarter-final, 2 semi-final, 1 final).
- Both seasons include two innings per match with batting rows, bowling rows, extras, to-bat lists, fall-of-wickets text, squad lists and original extracted PDF text.
- `PlayerMatchStat` is the scorecard-level aggregate used by player profiles and leaderboards. It does not create ball-by-ball `Delivery` records.
- The importer reuses case-insensitive exact player names and refreshes match/player statistics on re-import. Nicknames and spelling variants are not fuzzy-merged automatically; review the Players admin list for aliases that may need manual consolidation.
- Bowling overs are aggregated as cricket overs notation (balls, not decimal fractions).

### Import / update after extracting this ZIP

Activate the project virtual environment, then run:

```powershell
python -m pip install -r requirements.txt
python manage.py makemigrations league
python manage.py migrate
python manage.py import_season_json --file data/season2.json --season 2
python manage.py import_season_json --file data/season3.json --season 3
python manage.py runserver
```

Existing matches are updated by their CricHeroes match IDs. Back up your `db.sqlite3` before importing if it already contains manual edits. Do not delete your database to apply these updates.


## Season 1 (2024) scorecard archive integration

The Season 1 source archive is stored in `data/season1_pdfs/` and its structured import file is `data/season1.json`.

The archive contains 15 CricHeroes matches (12 league matches, 2 semi-finals and 1 final) from 3–5 May 2024. It includes the match totals, both innings' batting and bowling tables, extras, fall of wickets, yet-to-bat lists, and playing squads where shown in the PDFs. It does **not** contain ball-by-ball delivery data.

Before importing, back up your existing `db.sqlite3` file. Then, from the folder containing `manage.py`, run:

```powershell
python manage.py check
python manage.py import_season_json --file data/season1.json --season 1
```

The importer creates/updates Season 1 tournament, teams, players, match records and aggregate player-match statistics. It stores the full innings scorecards in `Match.full_scorecard`, which are rendered by the existing match-detail page. The Teams, Matches, Players, Player Profiles and Leaderboards pages already query the shared database and will therefore include Season 1; use the season filters to view it.

The importer is safe to re-run for the same Season 1 match IDs: it updates those match records and rebuilds their player-match aggregate rows. Do not use it with Season 2 or Season 3 unless you intentionally want to refresh those seasons' imported statistics.

### Data review notes

The supplied PDFs use both `Sushils Worrios` and `Sushils Warriors`, and both `Haresh Super Kings` and `Harsh Super Kings`. These have been preserved as written in the source files rather than automatically merged. Confirm whether each pair is a spelling variation before consolidating team identities. No Season 1 sponsor details were included in the supplied archive.


## Latest website enhancements

- Leaderboards now include MVP points (1 per run, +7 per four, +9 per six, +25 per wicket), most runs, most wickets, most dot balls, appearances, and best fielder. Each board initially shows 10 players and reveals the next 10 independently.
- Best-fielder points count one recorded catch/caught-and-bowled or run-out fielder attribution as one dismissal. Historical CricHeroes aggregate scorecards do not provide individual fielder attribution, so historical fielding rankings remain empty until ball-by-ball fielding records are entered.
- Match Centre includes a live-match area and organiser-only Start Match flow. Staff users can start a fixture, record deliveries, mark dismissals/fielders, begin the second innings, and finish the match. Public visitors can view live scores and recent deliveries.
- Team cards link to a team squad page listing players with recorded appearances for that team in that season.

### Organiser live scoring

1. Sign in to `/django-admin/` with a staff account.
2. Open `/matches/` and choose **Start a match**.
3. Select a season and two teams. Team A bats first.
4. Record each delivery in the live scoring panel. For catches and run-outs, select the fielder so the Best Fielder table can count it.
5. Use **End innings / Start next** after the first innings, then **Finish match** when scoring is complete.

The live scoring interface records ball-by-ball data in the existing `Innings` and `Delivery` tables. It does not infer historical ball-by-ball records from the aggregate imported scorecards.
