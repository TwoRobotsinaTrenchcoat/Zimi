"""One unusable reference may cost itself and nothing more.

Found by the pre-release engine matrix, 2026-09-12: capturing
nerdfonts.com/cheat-sheet with the builtin engine died outright with
``http.client.InvalidURL: URL can't contain control characters``. The
reference was a real file on a real site —
``/assets/fonts/Symbols-2048-em Nerd Font Complete v233.woff2`` — whose name
contains spaces. Every browser fetches it by encoding them. Python's
http.client refuses it, and the exception escaped and took the whole capture
with it.

Two separate faults, and the second is the one that mattered:

  1. The URL was handed over as written instead of encoded, so a file that a
     browser fetches happily was unreachable.
  2. ``_http_asset_reader`` caught only OSError. InvalidURL is an
     HTTPException, so it went straight past — and a capture ended over one
     font. Its sibling sixty lines up in the same file already caught all
     three families, with a comment explaining why after a nonsense reference
     took down a fifteen-page sqlite.org crawl. This was the twin that had
     been missed.

Run: pytest tests/test_asset_url_safety.py -v
"""

import http.client
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from zimi import creator  # noqa: E402


@pytest.mark.parametrize(
    "url, expected",
    [
        pytest.param(
            "https://x.test/fonts/Symbols-2048-em Nerd Font Complete v233.woff2",
            "https://x.test/fonts/Symbols-2048-em%20Nerd%20Font%20Complete%20v233.woff2",
            id="the_real_one",
        ),
        pytest.param("https://x.test/a.js", "https://x.test/a.js", id="untouched"),
        pytest.param(
            # Already encoded. Encoding again would give %2520 and a 404, which
            # is why this substitutes the illegal characters rather than
            # running the whole URL through quote().
            "https://x.test/a%20b.woff2",
            "https://x.test/a%20b.woff2",
            id="never_double_encoded",
        ),
        pytest.param(
            "https://x.test/a\nb.css", "https://x.test/a%0Ab.css", id="newline"
        ),
        pytest.param("https://x.test/a\tb", "https://x.test/a%09b", id="tab"),
        pytest.param(
            # The query string is part of the request target too.
            "https://x.test/i.png?q=a b",
            "https://x.test/i.png?q=a%20b",
            id="in_query",
        ),
    ],
)
def test_a_url_is_made_fetchable_the_way_a_browser_would(url, expected):
    assert creator._request_safe(url) == expected


def test_what_the_encoding_produces_is_actually_acceptable():
    """The point is not the string, it is that http.client stops refusing it.

    Asserting against the library that did the refusing, rather than against
    my own idea of which characters are illegal.
    """
    raw = "/fonts/Symbols-2048-em Nerd Font Complete v233.woff2"
    with pytest.raises(http.client.InvalidURL):
        http.client.HTTPConnection("x.test")._validate_path(raw)
    # No exception is the assertion.
    http.client.HTTPConnection("x.test")._validate_path(creator._request_safe(raw))


def test_no_single_asset_can_end_a_capture(monkeypatch):
    """The reader returns None for a reference it cannot use, whatever went
    wrong. InvalidURL is the one that escaped; the others are here so the
    clause cannot be narrowed back to OSError without something noticing."""
    reader = creator._http_asset_reader("https://x.test", None, 5)

    for boom in (
        http.client.InvalidURL("control characters"),
        http.client.HTTPException("protocol trouble"),
        ValueError("unknown url type"),
        OSError("could not reach it"),
    ):

        def _raise(*_a, **_kw):
            raise boom

        monkeypatch.setattr(creator, "_urlopen_retry", _raise)
        assert (
            reader("label", "some/asset.woff2") is None
        ), f"{type(boom).__name__} escaped and would have ended the capture"


def test_a_reference_that_cannot_even_be_parsed_costs_only_itself():
    """Request() construction raises for a different set of malformed inputs
    than urlopen does, which is why it belongs inside the try."""
    reader = creator._http_asset_reader("gopher://x.test", None, 5)
    assert reader("label", "thing") is None
