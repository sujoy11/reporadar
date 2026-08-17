-- RepoRadar Supabase schema (run once in Supabase SQL editor)
CREATE TABLE IF NOT EXISTS search_cache (
  query TEXT PRIMARY KEY,
  results JSONB,
  cached_at TIMESTAMP DEFAULT now(),
  expires_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS verified_repos (
  id SERIAL PRIMARY KEY,
  owner TEXT,
  name TEXT,
  verdict TEXT,
  summary TEXT,
  ai_provider TEXT,
  verified_at TIMESTAMPTZ DEFAULT now(),
  github_stars_at_time INT,
  UNIQUE(owner, name)
);

-- Migration for existing tables: ensure verified_at exists as timestamptz.
-- Safe to re-run (IF NOT EXISTS / no-op when already present).
ALTER TABLE IF EXISTS verified_repos
  ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ DEFAULT now();

CREATE TABLE IF NOT EXISTS saved_repos (
  id SERIAL PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id),
  owner TEXT,
  name TEXT,
  saved_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS keepalive_log (
  id SERIAL PRIMARY KEY,
  pinged_at TIMESTAMP DEFAULT now()
);

-- Natural-language search cache (NL query -> GitHub qualifier variants + AI ranking)
CREATE TABLE IF NOT EXISTS nl_query_cache (
  raw_query TEXT PRIMARY KEY,
  query_variants JSONB,
  ranked_order JSONB,
  cached_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_search_cache_expires ON search_cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_verified_owner_name ON verified_repos(owner, name);


-- ============================================================
-- MIGRATION: Add AI verdict sub-fields to verified_repos.
-- The original table only has 8 columns (id, owner, name, verdict,
-- summary, ai_provider, verified_at, github_stars_at_time).
-- Until this migration is applied, the app stores structured AI
-- fields inside the summary TEXT column as JSON and recovers them
-- on read (see lib/supabase_client.py::_backfill_from_summary).
-- Run this in the Supabase SQL editor to add dedicated columns.
-- ============================================================
ALTER TABLE IF EXISTS verified_repos ADD COLUMN IF NOT EXISTS maintained TEXT;
ALTER TABLE IF EXISTS verified_repos ADD COLUMN IF NOT EXISTS maturity TEXT;
ALTER TABLE IF EXISTS verified_repos ADD COLUMN IF NOT EXISTS community TEXT;
ALTER TABLE IF EXISTS verified_repos ADD COLUMN IF NOT EXISTS docs TEXT;
ALTER TABLE IF EXISTS verified_repos ADD COLUMN IF NOT EXISTS setup TEXT;
ALTER TABLE IF EXISTS verified_repos ADD COLUMN IF NOT EXISTS reasoning TEXT;
ALTER TABLE IF EXISTS verified_repos ADD COLUMN IF NOT EXISTS model TEXT;
