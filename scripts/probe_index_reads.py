"""Fixed-size synthetic probe; emits metadata only, no user storage or models."""

import json
from pathlib import Path
import sys
import tempfile
import time
from uuid import uuid4

import chromadb

from ragdb.domain.models import Chunk
from ragdb.infrastructure.vectorstore import ChromaVectorStore


def run(root: Path, trials: int = 24, reopen_writer: bool = False):
    observations = []
    started = time.monotonic()
    for trial in range(trials):
        directory = root / str(trial)
        collections = [uuid4() for _ in range(4)]
        chunks = [Chunk(
            id=f"{cid}-{n}", collection_id=cid, source_id=uuid4(),
            source_content_hash="a" * 64, generation=1, ordinal=n,
            text="synthetic", normalized_text="synthetic",
        ) for cid in collections for n in range(2)]
        failed_collections = []
        with ChromaVectorStore(directory, operation_scoped=reopen_writer) as old, ChromaVectorStore(directory, "a" * 64) as writer:
            target = writer
            old.upsert(chunks, [[0.1, 0.2] for _ in chunks])
            for chunk in chunks:
                target.upsert([chunk], [[0.1, 0.2, 0.3]])
                assert target.has_chunks(chunk.collection_id, [chunk.id])
            if reopen_writer:
                writer.close()
                target = ChromaVectorStore(directory, "a" * 64)
            for ordinal, cid in enumerate(collections):
                errors = []
                query_started = time.monotonic()
                recovered = False
                # Observation window, not a product retry policy. Always bounded.
                for attempt in range(11):
                    try:
                        assert target.search(cid, [0.1, 0.2, 0.3], 1)
                        recovered = True
                        break
                    except Exception as exc:
                        cause = exc
                        while cause.__cause__ is not None:
                            cause = cause.__cause__
                        errors.append({"type": type(cause).__name__,
                                       "nothing_on_disk": "Nothing found on disk" in str(cause)})
                        if attempt < 10:
                            time.sleep(0.02)
                observations.append({"trial": trial, "collection": ordinal, "errors": errors,
                                     "readable": recovered, "seconds": round(time.monotonic() - query_started, 4)})
                if not recovered:
                    failed_collections.append((cid, observations[-1]))
            if reopen_writer:
                target.close()
        if failed_collections:
            # Distinguish the open system's state from a fresh reader replaying WAL.
            with ChromaVectorStore(directory, "a" * 64) as reopened:
                for cid, observation in failed_collections:
                    try:
                        observation["readable_after_close"] = bool(reopened.search(cid, [0.1, 0.2, 0.3], 1))
                    except Exception:
                        observation["readable_after_close"] = False
    return {"python": sys.version.split()[0], "chroma": chromadb.__version__, "trials": trials,
            "reopen_writer": reopen_writer,
            "queries": len(observations), "first_read_failures": sum(bool(o["errors"]) for o in observations),
            "unrecovered": sum(not o["readable"] for o in observations),
            "seconds": round(time.monotonic() - started, 2),
            "failures": [o for o in observations if o["errors"]]}


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="ragdb-index-probe-") as directory:
        print(json.dumps(run(Path(directory), int(sys.argv[1]) if len(sys.argv) > 1 else 24,
                             "--reopen-writer" in sys.argv), indent=2))
