-- Stage A persistence schema.
-- Run automatically by docker-entrypoint-initdb.d on first `docker compose up`.

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------- World meta ----------
CREATE TABLE IF NOT EXISTS world_meta (
    id            SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1), -- singleton
    current_tick  INTEGER NOT NULL DEFAULT 0,
    loaded_packs  TEXT[]  NOT NULL DEFAULT '{}',
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO world_meta (id, current_tick) VALUES (1, 0) ON CONFLICT DO NOTHING;

-- ---------- Tiles ----------
CREATE TABLE IF NOT EXISTS tiles (
    tile_id        TEXT PRIMARY KEY,
    display_name   TEXT NOT NULL,
    primary_pack   TEXT NOT NULL,
    tile_type      TEXT NOT NULL,
    description    TEXT DEFAULT '',
    allowed_packs  TEXT[] NOT NULL DEFAULT '{}',
    tension_bias   REAL NOT NULL DEFAULT 0.5,
    event_cooldowns JSONB NOT NULL DEFAULT '{}'::jsonb,
    resident_agents TEXT[] NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_tiles_pack ON tiles (primary_pack);

-- ---------- Agents ----------
CREATE TABLE IF NOT EXISTS agents (
    agent_id             TEXT PRIMARY KEY,
    pack_id              TEXT NOT NULL,
    display_name         TEXT NOT NULL,
    persona_card         TEXT NOT NULL DEFAULT '',
    is_historical_figure BOOLEAN NOT NULL DEFAULT FALSE,
    attributes           JSONB NOT NULL DEFAULT '{}'::jsonb,
    alignment            TEXT NOT NULL DEFAULT 'neutral',
    tags                 TEXT[] NOT NULL DEFAULT '{}',
    life_stage           TEXT NOT NULL DEFAULT 'prime',
    age                  INTEGER NOT NULL DEFAULT 20,
    current_tile         TEXT REFERENCES tiles(tile_id) ON DELETE SET NULL,
    current_goal         TEXT,
    inventory            JSONB NOT NULL DEFAULT '[]'::jsonb,
    state_extra          JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_tick            INTEGER NOT NULL DEFAULT 0,
    created_at_tick      INTEGER NOT NULL DEFAULT 0,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_agents_pack ON agents (pack_id);
CREATE INDEX IF NOT EXISTS idx_agents_tile ON agents (current_tile);
CREATE INDEX IF NOT EXISTS idx_agents_hf ON agents (is_historical_figure) WHERE is_historical_figure;

-- ---------- Relationships (directed) ----------
CREATE TABLE IF NOT EXISTS relationships (
    source_id              TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
    target_id              TEXT NOT NULL,
    affinity               INTEGER NOT NULL DEFAULT 0 CHECK (affinity BETWEEN -100 AND 100),
    kind                   TEXT NOT NULL DEFAULT 'acquaintance',
    last_interaction_tick  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (source_id, target_id)
);
CREATE INDEX IF NOT EXISTS idx_rel_target ON relationships (target_id);
CREATE INDEX IF NOT EXISTS idx_rel_strong ON relationships (source_id) WHERE ABS(affinity) >= 70;

-- ---------- Events (append-only legend log) ----------
CREATE TABLE IF NOT EXISTS events (
    event_id             UUID PRIMARY KEY,
    tick                 INTEGER NOT NULL,
    pack_id              TEXT NOT NULL,
    tile_id              TEXT,
    event_kind           TEXT NOT NULL,
    participants         TEXT[] NOT NULL DEFAULT '{}',
    outcome              TEXT NOT NULL DEFAULT 'neutral',
    stat_changes         JSONB NOT NULL DEFAULT '{}'::jsonb,
    relationship_changes JSONB NOT NULL DEFAULT '[]'::jsonb,
    template_rendering   TEXT NOT NULL DEFAULT '',
    enhanced_rendering   TEXT,
    spotlight_rendering  TEXT,
    importance           REAL NOT NULL DEFAULT 0.0,
    tier_used            SMALLINT NOT NULL DEFAULT 1,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_events_tick ON events (tick DESC);
CREATE INDEX IF NOT EXISTS idx_events_pack_tick ON events (pack_id, tick DESC);
CREATE INDEX IF NOT EXISTS idx_events_participants ON events USING GIN (participants);
CREATE INDEX IF NOT EXISTS idx_events_spotlight ON events (tick DESC) WHERE importance >= 0.6;

-- ---------- Agent episodic memory (vector) ----------
CREATE TABLE IF NOT EXISTS agent_memory (
    memory_id    UUID PRIMARY KEY,
    agent_id     TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
    tick         INTEGER NOT NULL,
    doc          TEXT NOT NULL,
    importance   REAL NOT NULL DEFAULT 0.0,
    kind         TEXT NOT NULL DEFAULT 'raw',  -- raw | reflection | interview
    embedding    vector(1024),                 -- dim for BGE-M3; nullable until embed is backfilled
    metadata     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_memory_agent_tick ON agent_memory (agent_id, tick DESC);
-- HNSW index on embeddings for approximate NN search (only build when data exists)
-- CREATE INDEX IF NOT EXISTS idx_memory_embedding ON agent_memory USING hnsw (embedding vector_cosine_ops);

-- ---------- Router stats (daily budgets & counters) ----------
CREATE TABLE IF NOT EXISTS router_daily_stats (
    day          DATE PRIMARY KEY,
    tier1_calls  INTEGER NOT NULL DEFAULT 0,
    tier2_calls  INTEGER NOT NULL DEFAULT 0,
    tier3_calls  INTEGER NOT NULL DEFAULT 0,
    tier2_tokens INTEGER NOT NULL DEFAULT 0,
    tier3_tokens INTEGER NOT NULL DEFAULT 0,
    downgrades   INTEGER NOT NULL DEFAULT 0
);
