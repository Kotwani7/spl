#!/bin/sh
set -eu

python manage.py migrate --noinput
python manage.py import_season_json --file data/season1.json --season 1
python manage.py import_season_json --file data/season2.json --season 2
python manage.py import_season_json --file data/season3.json --season 3
python manage.py collectstatic --no-input
