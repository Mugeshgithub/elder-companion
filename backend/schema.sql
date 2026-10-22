CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS patients (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    timezone    TEXT NOT NULL DEFAULT 'Europe/Paris',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS memories (
    id          BIGSERIAL PRIMARY KEY,
    patient_id  INT NOT NULL REFERENCES patients(id),
    content     TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT 'conversation', -- conversation | medication | family | routine | mood
    mood        TEXT,
    embedding   vector(1024),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS memories_patient_time ON memories (patient_id, created_at DESC);
CREATE INDEX IF NOT EXISTS memories_embedding ON memories USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS alerts (
    id          BIGSERIAL PRIMARY KEY,
    patient_id  INT NOT NULL REFERENCES patients(id),
    kind        TEXT NOT NULL,   -- missed_medication | inactivity | confusion | distress
    detail      TEXT,
    resolved    BOOLEAN NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- family setup (added 2026-10-22)
ALTER TABLE patients ADD COLUMN IF NOT EXISTS profile TEXT;
ALTER TABLE patients ADD COLUMN IF NOT EXISTS setup JSONB;                       -- the form the family filled in
ALTER TABLE patients ADD COLUMN IF NOT EXISTS intro_done BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE patients ADD COLUMN IF NOT EXISTS checkin_seconds INT;               -- null means the server default
ALTER TABLE memories ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'person';  -- person | family

-- family features (added 2026-10-22)
ALTER TABLE patients ADD COLUMN IF NOT EXISTS consent JSONB;                       -- {by, basis, at}
ALTER TABLE patients ADD COLUMN IF NOT EXISTS paused BOOLEAN NOT NULL DEFAULT false;
CREATE TABLE IF NOT EXISTS family_messages (
    id           BIGSERIAL PRIMARY KEY,
    patient_id   INT NOT NULL REFERENCES patients(id),
    from_name    TEXT NOT NULL,
    text         TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivered_at TIMESTAMPTZ                                                       -- null until the companion has said it
);
CREATE INDEX IF NOT EXISTS family_messages_waiting ON family_messages (patient_id) WHERE delivered_at IS NULL;
