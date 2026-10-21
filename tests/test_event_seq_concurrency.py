"""Concurrency test for append_event() seq numbering (issue #98).

Verifies that concurrent workers calling append_event() simultaneously
do not produce duplicate sequence numbers due to TOCTOU race conditions.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from devagent.session import store


def test_concurrent_append_event_distinct_seq(tmp_path: Path) -> None:
    db = tmp_path / "test_events.db"
    store.init_schema(db_path=db)
    session_id = "test-concurrent-session"

    store.create_session(session_id, project="test", db_path=db)

    num_events = 24

    def worker(i: int) -> int:
        return store.append_event(
            session_id=session_id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"Message {i}",
            db_path=db,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        seqs = list(pool.map(worker, range(num_events)))

    # Every seq must be unique
    assert len(seqs) == len(set(seqs)) == num_events
    # Seqs must span 0 through num_events - 1 without gaps
    assert sorted(seqs) == list(range(num_events))

    # Verify rows stored in database match in order
    events = store.get_events(session_id, db_path=db)
    stored_seqs = [e["seq"] for e in events]
    assert stored_seqs == list(range(num_events))
