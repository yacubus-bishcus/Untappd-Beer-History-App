# Untappd Beer History Web

A responsive Next.js 16 app that turns the desktop exporter’s `my_beers.csv` into a private, searchable beer archive.

## Stack

- Next.js App Router and React 19
- Supabase Auth, Postgres, and Row Level Security
- Vercel hosting
- Papa Parse for standards-compliant CSV ingestion

Vercel hosts the web app. Supabase hosts the Postgres database and authentication service.

## Local Development

Create `.env.local` from `.env.example` and provide the Supabase project URL and publishable key. Never put a Supabase secret key or service-role key in a `NEXT_PUBLIC_` variable.

```bash
npm install
npm run dev
```

Open `http://localhost:3000`.

## Database

Migrations live in `../supabase/migrations`. The schema stores one row per imported check-in and uses `user_id` ownership policies for select, insert, update, and delete. Anonymous table access is explicitly revoked.

Apply migrations through the Supabase CLI or the connected Supabase project, then run the security advisor before deployment.

## CSV Import

The import endpoint accepts the CSV written by the Python desktop app. Required columns are:

- `Beer Name`
- `Producer`
- `Consumed Location`
- `Lat`
- `Long`
- `Beer Type`
- `My Rating`
- `Global Rating`
- `Recent Date`

`Total Checkins` is optional for compatibility with older exports. Imports are capped at 5 MB and upsert in batches of 500.

## Verification

```bash
npm run lint
npm run build
```

The production deployment is [untappd-beer-history.vercel.app](https://untappd-beer-history.vercel.app).
