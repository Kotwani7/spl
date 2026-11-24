
import re
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import transaction
from league.models import Match

updated = []
skipped = []

normalize = lambda name: re.sub(
    r"[^a-z0-9]",
    "",
    name.casefold()
)

with transaction.atomic():

    matches = Match.objects.filter(
        tournament__season__in=[2, 3],
        winner__isnull=True
    ).select_related(
        "team_a",
        "team_b",
        "tournament"
    )

    for match in matches:

        result = (match.result_text or "").strip()

        found = re.match(
            r"^(.+?)\s+won\s+by\s+\d+\s+(?:runs?|wickets?)\s*$",
            result,
            re.IGNORECASE
        )

        if not found:
            skipped.append((match.pk, result, "Unrecognised result"))
            continue

        winner_name = found.group(1).strip()

        if normalize(winner_name) == normalize(match.team_a.name):
            winner = match.team_a

        elif normalize(winner_name) == normalize(match.team_b.name):
            winner = match.team_b

        else:
            skipped.append((
                match.pk,
                result,
                "Winner does not match either participating team"
            ))
            continue

        match.winner = winner
        match.save(update_fields=["winner"])

        updated.append((match.pk, winner.name, result))


print("\nUPDATED:", len(updated))
print("SKIPPED:", len(skipped))

print("\nUPDATED MATCHES:")
for item in updated:
    print(item)

print("\nSKIPPED MATCHES:")
for item in skipped:
    print(item)
