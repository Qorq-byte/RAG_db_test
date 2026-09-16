# RAG Personal Knowledge Base Design

## 1. Purpose

Build a Python-first personal knowledge base for artificial-intelligence study. The first phase focuses on local ingestion, indexing, management, and traceable retrieval. LLM-generated answers and a desktop UI are deliberately deferred until the retrieval foundation is stable.

The project runs primarily on Windows with Python 3.11.15, uses `uv` for environment and dependency management, and lives at `D:\python\RAG_db_test`.

## 2. Scope

### Phase 1

- Manage multiple isolated knowledge collections, such as courses, papers, and code projects.
- Ingest PDF, Markdown, plain text, Word, PowerPoint, source code, configuration files, pasted text, directories, websites, and public GitHub repositories.
- Watch selected directories and synchronize file additions, updates, moves, and deletions.
- Detect scanned PDFs and offer optional OCR instead of requiring OCR dependencies by default.
- Generate embeddings locally or through a cloud provider selected in configuration.
- Persist vectors in ChromaDB and source catalog, task state, logs, and keyword indexes in SQLite.
- Search with vector and keyword retrieval, reciprocal-rank fusion, metadata filters, and optional reranking.
- Return original text and complete source attribution, including document path or URL, page or slide, metadata, retrieval method, and scores.
- Provide a Chinese-first subcommand CLI.

### Deferred to Phase 2

- LLM question answering and conversational memory.
- Summaries, outlines, study notes, quizzes, and flashcards.
- Native desktop application.

The Phase 1 interfaces must allow these capabilities to be added without replacing the ingestion or retrieval core.

## 3. Architecture

Use a modular monolith. Each module has a narrow responsibility and communicates through project-owned interfaces.

```text
CLI
  -> application services
       -> collection management
       -> ingestion and synchronization
       -> search
       -> index maintenance
  -> core services
       -> parsers
       -> chunkers
       -> embedding providers
       -> keyword and vector retrieval
       -> fusion and reranking
  -> infrastructure adapters
       -> ChromaDB
       -> SQLite/FTS5
       -> filesystem watcher
       -> web crawler
       -> public GitHub importer
```

The core must not depend on the CLI. Future desktop and API layers will call the same application services. Third-party frameworks, if used, remain behind adapters so project behavior is not tied to one orchestration framework.

## 4. Data Model

Each collection has independent source records and indexes. A normalized source record includes:

- Stable source identifier and collection identifier.
- Source type, title, path or URL, and content hash.
- Import and last-update timestamps.
- Processing status and latest task result.
- User metadata such as tags, course, author, and topic.
- Parser and embedding configuration used to build the index.

Each chunk includes:

- Stable chunk identifier and parent source identifier.
- Original text and normalized text.
- Heading hierarchy or code symbol context when available.
- Page, slide, line range, repository path, or webpage locator.
- File type, language, tags, and source metadata.
- Vector and keyword index linkage.

API keys and secrets never enter stored source metadata or logs.

## 5. Ingestion Pipeline

```text
source input
  -> validation and source-specific parsing
  -> normalized document and metadata
  -> content-hash duplicate/version check
  -> structure-aware chunking
  -> local or cloud embedding
  -> ChromaDB and SQLite index update
  -> task record and operation log
```

Supported entry points are individual files, directories, pasted text, watched directories, website URLs, and public GitHub URLs.

Unchanged content is skipped. Changed content replaces only that source's chunks after the new index data has been built successfully. Removing or moving a watched source automatically removes stale index entries and records the action.

Web crawling is conservative by default: same-domain only, honors `robots.txt`, enforces rate and page limits, and requires explicit depth and scope. Public GitHub imports exclude binary files, generated/build directories, dependency directories, and files above a configurable size limit.

PDFs use their text layer by default. If insufficient text is detected, the task reports that OCR is needed and can rerun with optional OCR support.

## 6. Retrieval Pipeline

```text
query
  -> ChromaDB semantic candidates
  -> SQLite FTS5 keyword candidates
  -> deduplication and reciprocal-rank fusion
  -> optional lightweight reranker
  -> filters, formatting, and source attribution
```

Hybrid retrieval is the default because AI study material combines conceptual language with exact paper names, model names, formulas, and identifiers. Reranking is disabled by default for low-resource CPU machines and can be enabled per collection or query.

Search supports filters for collection, source type, tags, course, author, date, and origin. Results include highlighted original text, source path or URL, page/slide/code location, semantic score, keyword score, retrieval route, fusion rank, and reranker score when applicable.

## 7. CLI and Configuration

The executable command is `ragdb`. Planned command groups are:

```text
ragdb init
ragdb collection create|list|delete|info
ragdb ingest file|directory|text
ragdb crawl
ragdb repo
ragdb watch start|status|stop
ragdb search
ragdb source list|show|delete
ragdb reindex
ragdb doctor
```

Source and search operations require an explicit collection. Destructive collection and bulk-cleanup operations require confirmation. Batch operations show progress and summarize successes, skips, updates, and failures.

`config.toml` stores non-secret settings such as database paths, embedding provider, chunking, retrieval, crawling, and reranking. `.env` stores cloud credentials. Database files, caches, downloaded working copies, and logs live under `.data/` by default and are excluded from Git.

CLI output is Chinese-first. Diagnostic logs retain technical details needed for troubleshooting.

## 8. Failure Handling

- A failed source does not stop the rest of a batch.
- Network ingestion applies timeouts, rate limits, bounded retries, and hard page limits.
- Parsed data may be retained as task state when embedding is temporarily unavailable, allowing indexing to resume.
- Updates build replacement index data before removing the previous valid version.
- Every ingestion task records success, skipped, updated, and failed items with actionable reasons.
- Sensitive environment values are redacted from logs and errors.
- A collection detects embedding or index-schema changes and requires an explicit rebuild.
- `ragdb doctor` checks configuration, storage, model availability, optional OCR, and network-ingestion prerequisites.

## 9. Verification

Phase 1 does not require CI, Docker, or a coverage target. It still includes focused automated verification for high-risk behavior:

- Content hashing, duplicate skipping, incremental replacement, and deletion synchronization.
- Representative parser samples and metadata/location preservation.
- Vector, keyword, fusion, filtering, and optional reranking behavior.
- End-to-end ingestion and search against temporary ChromaDB and SQLite stores.
- Windows paths, Chinese filenames, and text encoding.

## 10. Delivery Workflow

Development uses one feature branch and pull request for each independently verifiable milestone:

1. `feature/project-bootstrap`: initialize `uv`, package layout, configuration, CLI, logging, and ignore rules.
2. `feature/collections-storage`: collections, SQLite catalog, ChromaDB persistence, and metadata contracts.
3. `feature/document-ingestion`: local parsers, chunking, hashing, and manual text.
4. `feature/embeddings-indexing`: local/cloud embedding adapters, batching, updates, and recovery.
5. `feature/hybrid-search`: semantic and keyword retrieval, RRF, filters, attribution, and reranking hook.
6. `feature/web-github-import`: bounded website crawling and public GitHub repository ingestion.
7. `feature/watch-management`: directory watching, deletion sync, source management, rebuilds, and task logs.
8. `feature/cli-polish`: Chinese UX, progress, diagnostics, sample configuration, focused tests, and README.

Each branch is locally verified before commit and push, then merged through a pull request.

## 11. Phase 1 Acceptance Criteria

Phase 1 is complete when a Windows user can:

- Install and run the project with Python 3.11 and `uv`.
- Create and manage multiple independent collections.
- Import every agreed source type and inspect source/task status.
- Re-import without duplicating unchanged content and synchronize watched deletions.
- Choose a configured local or cloud embedding provider.
- Search one collection with hybrid retrieval and optional reranking.
- Filter results and inspect complete, accurate source locations and retrieval scores.
- Diagnose configuration or dependency failures with clear CLI output.
