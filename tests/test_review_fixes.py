"""What the pre-release review caught, held down.

Three defects, all found by reading the diff rather than by a failing test,
which is why each one gets a test now.

Run: pytest tests/test_review_fixes.py -v
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import zimi.alive as alive  # noqa: E402
import zimi.http as http  # noqa: E402
import zimi.server as server  # noqa: E402


class _Page:
    def __init__(self, shot):
        self.shot = shot
        self.html = "<html></html>"
        self.bytes = 12
        self.content_language = "eng"
        self.final_url = "https://example.com/"

    def discard(self):
        return None


class _Session:
    """A session that hands back a different picture on every fetch, the way a
    crawl of several pages does."""

    def __init__(self, shots):
        self._shots = list(shots)
        self.recorded = 0
        self.blocked = 0
        self.blocked_hosts = set()
        self.blocklist = None

    def start(self):
        return self

    def capture(self, _url):
        return _Page(self._shots.pop(0))


def test_the_live_picture_is_the_page_the_crawl_started_from():
    """A crawl fetches every page in the frontier through the same capture.
    Keeping the last one left the About panel showing a random interior page
    as "the live page" beside a packaged picture of the front page — two
    unrelated pages presented as before and after."""
    capture = alive.AliveCapture.__new__(alive.AliveCapture)
    capture._session = _Session([b"seed-shot", b"second-page", b"third-page"])
    capture._started = True
    capture.last_shot = None
    capture.count = 0
    # Built bare, so the progress sink a real capture always has is supplied
    # here. It records the announcements, which is the second half of the rule:
    # one picture, announced once.
    announced = []
    capture._note = announced.append

    for url in (
        "https://example.com/",
        "https://example.com/two",
        "https://example.com/three",
    ):
        capture.fetch(url)

    assert capture.last_shot == b"seed-shot"
    assert [e for e in announced if e.get("event") == "shot"] != [], (
        "the page being captured is announced so the run screen can show it"
    )
    assert len([e for e in announced if e.get("event") == "shot"]) == 1, (
        "announced once, for the seed — not once per page in the frontier"
    )


class _Archive:
    def __init__(self, value):
        self._value = value

    def get_metadata(self, _key):
        return (
            self._value.encode("utf-8") if isinstance(self._value, str) else self._value
        )


def test_a_faces_record_that_is_not_a_record_is_refused_not_raised():
    """Both readers promise they never raise. A hand-made or corrupted ZIM
    whose metadata parses to a list or a string used to reach `.get()` on it
    and throw, which aborted metadata extraction for the whole ZIM."""
    for junk in ('["not", "a", "record"]', '"a string"', "42", "true"):
        assert server._read_faces(_Archive(junk)) is None, junk
        assert (
            http._faces_summary({http.__dict__.get("_FACES_KEY", "X-Zimi-Faces"): junk})
            is None
        ), junk


def test_a_faces_record_missing_its_other_half_is_refused():
    from zimi.creator import FACES_METADATA_KEY

    for value in (
        '{"main": "light"}',
        '{"main": "light", "other": "dark"}',
        '{"other": {}}',
    ):
        assert server._read_faces(_Archive(value)) is None, value
        assert http._faces_summary({FACES_METADATA_KEY: value}) is None, value


def test_a_real_faces_record_still_reads():
    from zimi.creator import FACES_METADATA_KEY

    good = json.dumps(
        {"main": "light", "other": {"scheme": "dark", "path": "A/index~other"}}
    )
    assert server._read_faces(_Archive(good))["other"]["path"] == "A/index~other"
    assert http._faces_summary({FACES_METADATA_KEY: good})["other"]["scheme"] == "dark"


def test_a_recording_pass_never_pays_for_a_second_face():
    """The alive engine's archive is what becomes the ZIM, and a second visit
    is not recorded into it — so asking for the other face would double the
    time and bandwidth of every alive capture for something nothing reads."""
    from zimi.renderer import RenderedSession

    session = RenderedSession(recorder=object(), note=lambda _m: None)
    assert session._has_second_face(object()) is False

    # And without a recorder the question is still asked (the browser call
    # fails here, which is the "no opinion" answer, not a skip).
    plain = RenderedSession(note=lambda _m: None)
    assert plain._recorder is None
