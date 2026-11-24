# Ball-by-ball CSV import

One row represents one delivery. Required columns are shown in `import-format.csv`.

- `match_date`: YYYY-MM-DD
- `extra_type`: none, wide, no_ball, bye, leg_bye, penalty
- `dismissal_type`: blank, bowled, caught, lbw, run_out, stumped, hit_wicket, caught_and_bowled, other
- Provide `dismissed_player` and `fielder` where applicable.

This is SPL's own normalized import format, not a claim that CricHeroes exports these exact columns. Map an authorised CricHeroes export/API response into this format. Summary scorecards do not contain enough information to calculate dot balls reliably.
