-- Verifiable Guidance Layer — schema
--
-- Read this file top to bottom and you have the data model. It is a property graph
-- expressed relationally: CONCEPTS are stable identities, NODES are their dated
-- versions, EDGES are typed relationships between concepts, and every row records
-- the RELEASE that created it (and, if later removed, the release that retired it).
--
-- Two ideas do most of the work:
--
--   1. "In force" is computed, never stored. The version of a concept in force on a
--      date is the visible version with the greatest effective date on or before it.
--      Adding a newer version in a later release automatically closes the previous
--      one in that release — and leaves earlier releases byte-identical.
--
--   2. A release is a watermark. A row is visible in release R when
--      created_release <= R and (retired_release is null or retired_release > R).
--      Pin an answer to a release and it reproduces forever.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS releases (
    id          integer PRIMARY KEY,
    label       text NOT NULL,
    changelog   text NOT NULL DEFAULT '',
    created_by  text NOT NULL DEFAULT 'seed',
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS jurisdictions (
    code  text PRIMARY KEY,          -- GLOBAL, JN, JS
    name  text NOT NULL
);

-- A published instrument: an edition, a guidance statement, a ruling, an amendment,
-- an adoption notice, a practice note. Its prose lives in data/sources/.
CREATE TABLE IF NOT EXISTS documents (
    id               text PRIMARY KEY,        -- doc:E2025
    title            text NOT NULL,
    tier             text NOT NULL CHECK (tier IN ('authoritative','interpretive','practitioner')),
    published_on     date,
    effective_from   date,                    -- GLOBAL effective date
    body_path        text,                    -- relative to data/
    created_release  integer NOT NULL REFERENCES releases(id),
    retired_release  integer REFERENCES releases(id)
);

-- Jurisdiction-specific adoption of a document. Absent a row, a document is in force
-- in every jurisdiction from its own effective_from.
CREATE TABLE IF NOT EXISTS adoptions (
    document_id      text NOT NULL REFERENCES documents(id),
    jurisdiction     text NOT NULL REFERENCES jurisdictions(code),
    effective_from   date NOT NULL,
    source_doc       text REFERENCES documents(id),   -- the adoption notice (provenance)
    created_release  integer NOT NULL REFERENCES releases(id),
    retired_release  integer REFERENCES releases(id),
    PRIMARY KEY (document_id, jurisdiction, created_release)
);

-- A stable identity that survives editions and renumbering. A concept with no
-- published versions is a KNOWN GAP: something the graph knows is relevant but does
-- not hold. That distinction — known gap vs. unknown gap — is the whole point.
CREATE TABLE IF NOT EXISTS concepts (
    concept_id       text PRIMARY KEY,        -- prov:composite-inclusion-timing
    kind             text NOT NULL CHECK (kind IN ('provision','definition','guidance','ruling','practice_note')),
    title            text NOT NULL,
    created_release  integer NOT NULL REFERENCES releases(id)
);

-- A dated version of a concept: the unit the resolver selects and the verifier cites.
CREATE TABLE IF NOT EXISTS nodes (
    version_id         text PRIMARY KEY,      -- prov:composite-inclusion-timing@E2025
    concept_id         text NOT NULL REFERENCES concepts(concept_id),
    display_ref        text,                  -- 3.A.6 — what a human sees; never an identity
    tier               text NOT NULL CHECK (tier IN ('authoritative','interpretive','practitioner')),
    obligation         text NOT NULL CHECK (obligation IN ('must','should','definition','n/a')),
    text               text NOT NULL,
    parameters         jsonb NOT NULL DEFAULT '{}'::jsonb,   -- machine-checkable values
    source_doc         text NOT NULL REFERENCES documents(id),
    effective_from     date NOT NULL,         -- GLOBAL; jurisdictional adoption may delay it
    effective_to       date,                  -- only for explicit withdrawal; null = open
    jurisdiction_scope text REFERENCES jurisdictions(code),  -- null = everywhere
    created_release    integer NOT NULL REFERENCES releases(id),
    retired_release    integer REFERENCES releases(id),
    embedding          vector(256)
);
CREATE INDEX IF NOT EXISTS nodes_concept_idx ON nodes (concept_id, effective_from);
CREATE INDEX IF NOT EXISTS nodes_fts_idx ON nodes
    USING gin (to_tsvector('english', coalesce(display_ref,'') || ' ' || text));

-- Typed relationships between concepts. Versions are chosen by date at query time,
-- so an edge never has to be re-asserted when an edition changes.
--
--   DEPENDS_ON_DEFINITION  clause -> definition   the clause's meaning depends on it
--   REFERENCES             any    -> any          explicit cross-reference in the text
--   INTERPRETED_BY         clause -> guidance      interpretive material that applies
--   CARVED_OUT_BY          clause -> ruling        an exception that modifies effect
--   ANNOTATED_BY           clause -> practice_note practitioner-tier note
--
-- Supersession and amendment are not edges: they are derived from version
-- chronology and from each version's source document.
CREATE TABLE IF NOT EXISTS edges (
    id               serial PRIMARY KEY,
    kind             text NOT NULL CHECK (kind IN
                        ('DEPENDS_ON_DEFINITION','REFERENCES','INTERPRETED_BY','CARVED_OUT_BY','ANNOTATED_BY')),
    from_concept     text NOT NULL REFERENCES concepts(concept_id),
    to_concept       text NOT NULL REFERENCES concepts(concept_id),
    -- provenance: nothing links two concepts without someone accountable for it
    asserted_by      text NOT NULL,
    basis            text NOT NULL CHECK (basis IN ('source_text','editorial','proposal')),
    source_passage   text,
    reviewed_by      text,
    created_release  integer NOT NULL REFERENCES releases(id),
    retired_release  integer REFERENCES releases(id)
);
CREATE INDEX IF NOT EXISTS edges_from_idx ON edges (from_concept);
CREATE INDEX IF NOT EXISTS edges_to_idx ON edges (to_concept);

-- Prose chunks of the source documents: what the NAIVE baseline retrieves over.
-- Same documents as the graph, so the comparison is fair.
CREATE TABLE IF NOT EXISTS chunks (
    id               serial PRIMARY KEY,
    document_id      text NOT NULL REFERENCES documents(id),
    ordinal          integer NOT NULL,
    heading          text,
    text             text NOT NULL,
    created_release  integer NOT NULL REFERENCES releases(id),
    retired_release  integer REFERENCES releases(id),
    embedding        vector(256)
);
CREATE INDEX IF NOT EXISTS chunks_fts_idx ON chunks
    USING gin (to_tsvector('english', coalesce(heading,'') || ' ' || text));

-- A proposed change to the published graph, awaiting editorial decision. The bundle
-- holds the documents, concepts, nodes, edges and adoptions it would add.
CREATE TABLE IF NOT EXISTS proposals (
    id               text PRIMARY KEY,
    title            text NOT NULL,
    kind             text NOT NULL CHECK (kind IN ('new_source','amendment','correction','practice_note')),
    submitted_by     text NOT NULL,
    submitted_role   text NOT NULL,
    basis            text NOT NULL,
    rationale        text NOT NULL,
    bundle           jsonb NOT NULL,
    status           text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
    decided_by       text,
    decision_note    text,
    release_id       integer REFERENCES releases(id),
    submitted_at     timestamptz NOT NULL DEFAULT now(),
    decided_at       timestamptz
);

-- Every answer the system gives, pinned to the release it was answered under.
CREATE TABLE IF NOT EXISTS answers (
    id               serial PRIMARY KEY,
    asked_at         timestamptz NOT NULL DEFAULT now(),
    question         text NOT NULL,
    frame            jsonb NOT NULL,
    jurisdiction     text,
    as_of            date,
    release_id       integer NOT NULL REFERENCES releases(id),
    outcome          text NOT NULL,
    claims           jsonb NOT NULL,
    flags            jsonb NOT NULL,
    packet           jsonb NOT NULL,
    composer_model   text,
    verification     jsonb NOT NULL
);

-- Answers that were issued to a client. Staleness is computed against the current
-- release, never stored: the system can always say when and why one went stale.
CREATE TABLE IF NOT EXISTS issued_answers (
    id               text PRIMARY KEY,         -- ia:IA-0001
    client_name      text NOT NULL,
    client_ref       text NOT NULL,
    issued_on        date NOT NULL,
    jurisdiction     text NOT NULL REFERENCES jurisdictions(code),
    as_of            date NOT NULL,
    release_id       integer NOT NULL REFERENCES releases(id),
    question         text NOT NULL,
    outcome          text NOT NULL,
    answer_text      text NOT NULL,
    cited_versions   text[] NOT NULL
);
