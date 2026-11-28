# Historical scorecard import

The season JSON files in `data/` retain the existing CricHeroes match IDs and source facts. `import_scorecard_archives` checks each PDF in its explicitly named season ZIP against that JSON before writing anything. It reads embedded PDF text in memory and stores the filename and extracted text, not the PDF file.

From the Django project directory, run:

```powershell
.\.venv\Scripts\python.exe manage.py import_scorecard_archives `
  --season-1-archive "C:\Users\VANSH\Downloads\spl scorecards\spl1.zip" `
  --season-2-archive "C:\Users\VANSH\Downloads\spl scorecards\SPL2.zip" `
  --season-3-archive "C:\Users\VANSH\Downloads\spl scorecards\SPL3 scorecards.zip"
```

Each archive is mapped to its numbered season by its named option. The command matches `Scorecard_<CricHeroes ID>.pdf` to that season's JSON record, checks match details, innings totals, batting and bowling figures, and extras, then imports only verified matches. A PDF/JSON conflict is logged with the PDF filename and that match is skipped for review. A result omitted from JSON is recovered only when it is explicit in the PDF text.

Matches, teams, and players are reused by their existing identifiers or exact names. Repeated runs update existing match records and player statistics, add missing innings aggregates, and preserve existing database IDs and supplemental scorecard fields. The command does not delete matches, players, statistics, deliveries, or unrelated rows.

## Free Render deployment

The repository's `render.yaml` uses Render's free web-service plan and expects a free external PostgreSQL database through the `DATABASE_URL` environment variable. Create the database first, add its connection string in the Render service's Environment settings (never commit it), then deploy. The build runs migrations and imports all three committed season JSON files. The JSON imports are idempotent, so redeploys do not duplicate matches or player statistics. The PDF ZIPs do not need to be copied to the web server.

Render's free web service sleeps after 15 minutes without traffic and can take about a minute to wake. Its local filesystem is ephemeral, so uploaded media files are not durable. Use external object storage if uploaded files need to persist. Season 3's two results that were blank in the source JSON are included because the PDFs explicitly state them.
