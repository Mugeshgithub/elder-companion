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

-- privacy and access (added 2026-10-22)
ALTER TABLE patients ADD COLUMN IF NOT EXISTS retention_days INT DEFAULT 365;      -- null keeps data until the family deletes it
CREATE TABLE IF NOT EXISTS family_members (
    id         BIGSERIAL PRIMARY KEY,
    patient_id INT NOT NULL REFERENCES patients(id),
    name       TEXT NOT NULL,
    code_hash  TEXT NOT NULL UNIQUE,                                               -- the code is shown once and never stored
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen  TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS audit_log (
    id         BIGSERIAL PRIMARY KEY,
    patient_id INT,
    actor      TEXT NOT NULL,
    action     TEXT NOT NULL,
    detail     TEXT,
    at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS audit_patient_time ON audit_log (patient_id, at DESC);

-- medical documents with sources (added 2026-10-22)
CREATE TABLE IF NOT EXISTS documents (
    id            BIGSERIAL PRIMARY KEY,
    patient_id    INT NOT NULL REFERENCES patients(id),
    filename      TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'processing',   -- processing | ready | failed
    error         TEXT,
    doc_type      TEXT,
    doc_date      DATE,
    author        TEXT,
    named_patient TEXT,                                 -- who the document says it is about
    sha256        TEXT NOT NULL,
    pages         JSONB NOT NULL,                       -- the text of each page, so a quote can be checked
    uploaded_by   TEXT NOT NULL,
    uploaded_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (patient_id, sha256)
);
CREATE TABLE IF NOT EXISTS document_facts (
    id          BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    patient_id  INT NOT NULL,
    kind        TEXT NOT NULL,
    summary     TEXT NOT NULL,
    detail      JSONB,
    page        INT NOT NULL,
    quote       TEXT NOT NULL,
    verified    BOOLEAN NOT NULL,                       -- the quote was found, word for word, on that page
    status      TEXT NOT NULL DEFAULT 'pending',        -- pending | approved | rejected
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    memory_id   BIGINT                                  -- the memory the companion reads, once approved
);
CREATE INDEX IF NOT EXISTS document_facts_doc ON document_facts (document_id);

-- telegram alerts (added 2026-10-22)
CREATE TABLE IF NOT EXISTS notify_targets (
    id         BIGSERIAL PRIMARY KEY,
    patient_id INT NOT NULL REFERENCES patients(id),
    name       TEXT NOT NULL,
    chat_id    BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (patient_id, chat_id)
);
CREATE TABLE IF NOT EXISTS notify_links (
    token_hash TEXT PRIMARY KEY,                -- the link token is shown once and only a hash is kept
    patient_id INT NOT NULL REFERENCES patients(id),
    name       TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);
ALTER TABLE patients ADD COLUMN IF NOT EXISTS notify_words BOOLEAN NOT NULL DEFAULT false;  -- include the person's words in messages
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS reminded_at TIMESTAMPTZ;  -- set when the one reminder for an open serious alert was sent
