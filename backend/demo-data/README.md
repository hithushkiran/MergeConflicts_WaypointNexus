# Synthetic development data

These small CSV files contain invented, clearly marked demo records for local development only. They are not official competition data and must not be used for competition results, operational decisions, or submissions.

When `APP_ENV=development` and the Git-ignored `local-data/` official CSV pair is absent, the Compose API uses this dataset to provide a working demo login and store order workflow. If either official CSV is present without the other, seeding fails rather than silently mixing datasets.
