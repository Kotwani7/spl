# Vercel deployment

Vercel detects this repository as Django from `manage.py` and serves collected static files through its CDN. The root `vercel.json` runs migrations, imports all three season JSON files, and collects static assets during each deployment build.

Connect a Neon Postgres resource to the Vercel project with the free plan and production environment. The Marketplace integration supplies `DATABASE_URL` to the deployment; do not store the connection string in Git. The import command is repeatable and preserves the match IDs already in the season JSON.

Set these Vercel production environment variables: `DEBUG=False`, `SECRET_KEY` (a private key of at least 50 characters), `ALLOWED_HOSTS=.vercel.app`, `CSRF_TRUSTED_ORIGINS=https://*.vercel.app`, and `TRUST_PROXY_HEADERS=True`. Create a new deployment after setting variables so the build imports the seasons into Postgres.

The app database writes persist in Postgres. Vercel Functions do not provide persistent local file storage, so uploaded media needs an external object-storage backend. Vercel's free Hobby plan is limited to personal, non-commercial use; use another plan/host if the league site is commercial.
