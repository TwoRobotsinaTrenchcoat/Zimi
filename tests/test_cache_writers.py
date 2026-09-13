"""Two threads changing the metadata cache must not erase each other.

Four places read that file, change part of it, and write the whole thing back:
the shape worker, the provenance walk, and registering or unregistering a
single ZIM. They run on different threads — the provenance one from whichever
request asked for it — so without a lock the second save is built on a copy
taken before the first, and the first's work is simply gone.

Losing a shape is not cosmetic. The shape worker re-measures anything without
one, and measuring walks every entry in the file; on a 40 GB Wikipedia that is
minutes of the global libzim lock, every quarter of an hour, forever. Eric
heard it as the NAS cranking, and saw it as Manage → Creator never finishing,
because that walk starves the request that would have answered it.

The collision is FORCED, not raced. Racing the two writers in a loop does not
reproduce it — the window is microseconds and the save is atomic — so a test
written that way passes with the lock removed and is worth nothing. This one
holds the first writer's read-modify-write open and runs the second inside it.
Verified to fail with the lock removed; that is the only reason to trust it.

Run: pytest tests/test_cache_writers.py -v
"""

import json
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import zimi.server as _srv  # noqa: E402

ROUNDS = 60


@pytest.fixture
def library(tmp_path, monkeypatch):
    """Two ZIMs, a real cache file on disk, and the live list beside it."""
    monkeypatch.setattr(_srv, "ZIM_DIR", str(tmp_path))
    monkeypatch.setattr(_srv, "ZIMI_DATA_DIR", str(tmp_path))
    entries = [
        {"name": "alpha", "file": "alpha.zim", "size_bytes": 10, "mtime": 1},
        {"name": "beta", "file": "beta.zim", "size_bytes": 20, "mtime": 2},
    ]
    monkeypatch.setattr(_srv, "_zim_list_cache", entries)
    _srv._save_disk_cache(
        {
            "alpha.zim": {"name": "alpha", "mtime": 1, "size": 10},
            "beta.zim": {"name": "beta", "mtime": 2, "size": 20},
        }
    )
    return entries


def _on_disk():
    return _srv._load_disk_cache() or {}


def test_one_writer_cannot_erase_another(library):
    """The exact collision, forced rather than raced.

    Racing the two writers in a loop does not reproduce it — the window is a
    few microseconds and the save is atomic — so a test written that way passes
    with the lock removed and is worth nothing. This one holds the first
    writer's read-modify-write open and runs the second one inside it.

    With the lock the second writer waits, then builds on what the first saved,
    and both changes survive. Without it the second writer loads the copy from
    before the first saved, and whichever finishes last silently erases the
    other.
    """
    loaded = threading.Event()
    release = threading.Event()

    def slow_shape(disk):
        disk["alpha.zim"]["shape"] = {"entries": 7}
        loaded.set()
        release.wait(5)
        return True

    first = threading.Thread(target=lambda: _srv._update_disk_cache(slow_shape))
    first.start()
    assert loaded.wait(5), "the first writer never started"

    finished = threading.Event()

    def provenance():
        _srv.kind_store(
            {
                "alpha": {
                    "file": "alpha.zim",
                    "sig": ["alpha.zim", 10],
                    "kind": {"mode": "page"},
                }
            }
        )
        finished.set()

    second = threading.Thread(target=provenance)
    second.start()
    # The lock is what makes this true: the second writer cannot get in while
    # the first is mid-cycle.
    held_off = not finished.wait(1.0)

    release.set()
    first.join(5)
    assert finished.wait(5), "the second writer never completed"
    second.join(5)

    assert held_off, "the second writer read the cache while the first held it"
    disk = _on_disk()
    assert disk["alpha.zim"].get("shape") == {"entries": 7}, "the shape was erased"
    assert "zimi_kind" in disk["alpha.zim"], "the provenance record was erased"


def test_a_none_kind_is_still_a_remembered_answer(library):
    """Most ZIMs were published by somebody else, and that is exactly the
    answer worth keeping — otherwise every restart reopens them all."""
    _srv.kind_store(
        {"beta": {"file": "beta.zim", "sig": ["beta.zim", 20], "kind": None}}
    )
    record = _on_disk()["beta.zim"]["zimi_kind"]
    assert record["kind"] is None
    assert record["sig"] == ["beta.zim", 20]


def test_registering_a_zim_does_not_drop_what_a_walk_just_learned(library):
    """The register path rewrites the whole file too."""
    _srv.kind_store(
        {"alpha": {"file": "alpha.zim", "sig": ["alpha.zim", 10], "kind": {"m": 1}}}
    )

    def add_gamma(disk):
        disk["gamma.zim"] = {"name": "gamma", "mtime": 3, "size": 30}
        return True

    _srv._update_disk_cache(add_gamma)
    disk = _on_disk()
    assert "gamma.zim" in disk
    assert "zimi_kind" in disk["alpha.zim"], "registering a ZIM erased provenance"


def test_the_file_is_never_left_half_written(library):
    """Readers run while writers do. A torn file reads as no cache at all,
    which throws the whole library back to a full rescan."""
    stop = threading.Event()
    torn = []

    def write():
        for i in range(ROUNDS):
            _srv._shape_store({"alpha": {"entries": i}})
        stop.set()

    def read():
        while not stop.is_set():
            try:
                json.loads(open(_srv._cache_file_path(), encoding="utf-8").read())
            except FileNotFoundError:
                pass
            except json.JSONDecodeError as e:
                torn.append(str(e))
                return

    w, r = threading.Thread(target=write), threading.Thread(target=read)
    r.start(), w.start()
    w.join(), r.join(timeout=10)
    assert not torn, f"a reader saw a half-written cache: {torn[:1]}"
