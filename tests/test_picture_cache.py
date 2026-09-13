"""A library re-render must not cost one locked archive read per source.

The icon at /w/<zim>/-/icon, and the two capture pictures beside it, were sent
with `Cache-Control: max-age=0, must-revalidate` and an ETag over the CONTENT.
Correct, and ruinous: the browser asked about every picture on every render,
and answering the ask meant opening the archive and hashing the illustration —
under the global libzim lock, the same one every search and every article read
needs. Seventy-four sources on the home screen is seventy-four locked reads on
every sort, every view toggle, every return to the page.

Eric, 2026-09-11: "icons disappear and redownload when i toggle compact or
full", and "the whole site is held up".

Two properties fix that, and both are guarded here:

  1. The tag comes from the FILE's identity, not a digest of its bytes, so a
     revalidation can be answered before the archive is opened at all.
  2. There is a freshness window, so a re-render within it does not ask.

And one property must NOT regress: replacing a ZIM, or re-capturing over the
same filename, has to change the picture. That is why this is not `immutable`
— a previous version of this code was, and Eric watched a ZIM he had just made
show a missing icon for a week in the one browser that asked too early.

Run: pytest tests/test_picture_cache.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import zimi.http as zhttp  # noqa: E402
import zimi.server as _srv  # noqa: E402


class _Handler(zhttp.ZimHandler):
    """The handler with the socket taken out: records the response instead."""

    def __init__(self, headers=None):
        self.headers = headers or {}
        self.status = None
        self.sent = {}
        self.body = b""

    def send_response(self, code, *a):
        self.status = code

    def send_header(self, key, value):
        self.sent[key] = value

    def end_headers(self):
        pass

    @property
    def wfile(self):
        handler = self

        class _W:
            def write(self, data):
                handler.body += data

        return _W()


@pytest.fixture
def library(monkeypatch):
    """One installed ZIM, known mtime and size, no archive behind it."""
    entries = [
        {"name": "atlas", "file": "atlas.zim", "size_bytes": 4096, "mtime": 1700000000}
    ]
    monkeypatch.setattr(_srv, "_zim_list_cache", entries)
    return entries


def test_the_tag_names_the_file_not_its_bytes(library):
    h = _Handler()
    etag = h._picture_etag("atlas", "-/icon")
    assert etag == '"icon-1700000000-4096"'
    # Each picture is its own resource; they must not share a tag or a browser
    # holding one would be handed the other.
    assert h._picture_etag("atlas", "-/shot-live") == '"shot-live-1700000000-4096"'
    assert h._picture_etag("atlas", "-/shot-zim") == '"shot-zim-1700000000-4096"'


def test_a_replaced_zim_gets_a_new_tag(library):
    h = _Handler()
    before = h._picture_etag("atlas", "-/icon")
    library[0]["mtime"] = 1700009999  # re-captured over the same filename
    assert h._picture_etag("atlas", "-/icon") != before
    library[0]["mtime"] = 1700000000
    library[0]["size_bytes"] = 5000  # rebuilt, same instant, different content
    assert h._picture_etag("atlas", "-/icon") != before


def test_a_zim_we_know_nothing_about_gets_no_tag(library):
    """Falling back to the content digest is what keeps this honest when the
    list cache has not been built — a tag over a file we cannot identify would
    be a promise we cannot keep."""
    h = _Handler()
    assert h._picture_etag("not-installed", "-/icon") == ""


def test_revalidation_never_opens_the_archive(library, monkeypatch):
    """The whole point. If this ever takes the lock again, a home screen full
    of sources is a home screen full of locked reads."""
    opened = []

    def must_not_be_called(name):
        opened.append(name)
        raise AssertionError("the archive was opened to answer a revalidation")

    monkeypatch.setattr(_srv, "get_archive", must_not_be_called)

    h = _Handler({"If-None-Match": '"icon-1700000000-4096"'})
    h._serve_zim_content("atlas", "-/icon")
    assert h.status == 304
    assert h.body == b""
    assert opened == []
    assert "max-age=" in h.sent["Cache-Control"]


def test_a_stale_tag_is_not_answered_from_the_cache(library, monkeypatch):
    """A browser holding last week's icon has to be given this week's."""
    reached = []

    def get_archive(name):
        reached.append(name)
        return None  # far enough: we only care that it went looking

    monkeypatch.setattr(_srv, "get_archive", get_archive)
    h = _Handler({"If-None-Match": '"icon-1699999999-4096"'})
    h._serve_zim_content("atlas", "-/icon")
    assert reached == ["atlas"], "a stale tag was answered without looking"
    assert h.status != 304


def test_the_window_is_short_and_revalidated(library):
    """Not `immutable`, and not a week. A ZIM's bytes can change at the same
    URL, so the browser has to come back and ask — just not on every render."""
    h = _Handler()
    control = h._picture_cache_control()
    assert "immutable" not in control
    assert "must-revalidate" in control
    assert 0 < zhttp.ZimHandler.PICTURE_MAX_AGE <= 300, (
        "long enough that a re-render does not ask, short enough that a "
        "re-captured ZIM's icon appears while the admin is still looking"
    )


def test_the_bookkeeping_the_etag_needs_stays_off_the_wire(library):
    """The file identity lives on the same dict as the facts, because that dict
    IS the library cache. /list must not carry it.

    That payload is what the home screen waits on. On a 74-ZIM library these
    two fields were 19% of it — 9 KB of 47 KB — for a copy of the provenance
    record that /zim-info?kinds=1 already serves deliberately, and an mtime
    that first_seen and updated_at already answer for.
    """
    entry = dict(
        library[0],
        zimi_kind={"file": "atlas.zim", "sig": ["atlas.zim", 4096], "kind": {}},
        title="Atlas",
    )
    public = zhttp._public_zim_entry(entry)

    for private in zhttp._PRIVATE_ZIM_FIELDS:
        assert private not in public, f"{private} reached the client"
    # Everything a client actually reads survives.
    for kept in ("name", "file", "size_bytes", "title"):
        assert public[kept] == entry[kept]

    # And the server still has what the tag is built from — the projection is a
    # copy, so stripping the response must not strip the cache.
    assert "mtime" in entry and "zimi_kind" in entry
    assert _Handler()._picture_etag("atlas", "-/icon") == '"icon-1700000000-4096"'


def test_an_entry_with_nothing_private_is_passed_straight_through(library):
    """No copy per ZIM per request when there is nothing to remove."""
    plain = {"name": "atlas", "file": "atlas.zim"}
    assert zhttp._public_zim_entry(plain) is plain
