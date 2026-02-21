CREATE TABLE IF NOT EXISTS convo_turns (
  id BIGSERIAL PRIMARY KEY,
  convo_id TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  ts TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS memory_facts (
  id BIGSERIAL PRIMARY KEY,
  subject TEXT NOT NULL,
  predicate TEXT NOT NULL,
  object_text TEXT NOT NULL,
  truth_value TEXT NOT NULL CHECK (truth_value IN ('true','false','conditional','unknown')),
  condition_text TEXT,
  valid_from TIMESTAMPTZ,
  valid_to TIMESTAMPTZ,
  confidence REAL NOT NULL,
  source_turn_id BIGINT NOT NULL REFERENCES convo_turns(id),
  extractor_version TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  embedding VECTOR(1536)
);

CREATE INDEX IF NOT EXISTS memory_facts_embedding_hnsw_idx
ON memory_facts USING hnsw (embedding vector_cosine_ops);

ALTER TABLE memory_facts
ADD COLUMN IF NOT EXISTS fts tsvector GENERATED ALWAYS AS (
  to_tsvector('english',
    coalesce(subject, '') || ' ' || coalesce(predicate, '') || ' ' || coalesce(object_text, '')
  )
) STORED;

CREATE INDEX IF NOT EXISTS memory_facts_fts_idx ON memory_facts USING GIN (fts);
