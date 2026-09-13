"""A capture keeps both of a site's faces, however the site switches them.

Two mechanisms exist in the wild and Zimi has to answer both.

The easy one is a media query: the site reads prefers-color-scheme and paints
accordingly, so flipping the query is enough to see the other face.

The hard one is a site that ignores the query entirely and keeps its themes in
its own hands. draculatheme.com stamps data-theme="dark" whatever the query
says and flips only when its moon is pressed, so the media-query probe answered
"one face" and the capture stored a page whose visible theme button did
nothing. Eric, 2026-09-11: "no dark/light stored (there's even an in-page
toggle moon button that doesn't work)".

Those sites also break the comfortable assumption that a second face is the
same page repainted. Dracula's hero is a different FILE in light
(images/hero/default-light.svg), and a face whose picture was never carried
renders offline as a gap where the hero was — "in light mode the dracula image
doesn't appear".

The fixture below is that site in miniature: no media query, a labelled theme
button, and an image that swaps file when it is pressed.

Run: pytest tests/test_second_face.py -v
"""

import functools
import http.server
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import zimi.renderer as renderer  # noqa: E402
from zimi.renderer import RenderedSession  # noqa: E402


def _need_browser():
    """Skip, checked inside the test: browser_available() launches a real
    chromium, so a module-level skipif costs minutes on a machine that has
    none."""
    if not renderer.browser_available():
        pytest.skip("playwright + chromium are not usable here")


def browser(fn):
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        _need_browser()
        return fn(*a, **kw)

    return wrapper


# A one-pixel SVG, twice, so the two faces reference genuinely different files
# and "was the light one carried" is a real question.
DARK_PIC = b'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><rect width="8" height="8" fill="#101014"/></svg>'
LIGHT_PIC = b'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><rect width="8" height="8" fill="#eeeeee"/></svg>'

# Deliberately no @media (prefers-color-scheme). The page starts dark, and the
# ONLY way to the light face is the button — which is what makes this the case
# the media-query probe cannot see.
PAGE = """<!doctype html>
<html data-theme="dark"><head><meta charset="utf-8"><title>Two faces</title>
<style>
  html[data-theme="dark"] body { background: #101014; color: #c2c0ce; }
  html[data-theme="light"] body { background: #f4f2ee; color: #201f1c; }
  body { margin: 0; padding: 40px; min-height: 1200px; }
</style></head>
<body>
  <button id="tt" aria-label="Toggle theme">moon</button>
  <h1>Two faces</h1>
  <img id="hero" src="/hero-dark.svg" width="8" height="8" alt="">
  <script>
    document.getElementById('tt').addEventListener('click', function () {
      var root = document.documentElement;
      var dark = root.getAttribute('data-theme') === 'dark';
      root.setAttribute('data-theme', dark ? 'light' : 'dark');
      document.getElementById('hero').src = dark ? '/hero-light.svg' : '/hero-dark.svg';
    });
  </script>
</body></html>
"""

# The same page with no button at all: one face, and the capture must not pay
# for a second visit looking for one.
ONE_FACE = PAGE.replace('<button id="tt" aria-label="Toggle theme">moon</button>', "")


@pytest.fixture
def site():
    """Serves the fixture on localhost; yields its base URL."""
    bodies = {
        "/": (b"text/html", PAGE.encode("utf-8")),
        "/one-face": (b"text/html", ONE_FACE.encode("utf-8")),
        "/hero-dark.svg": (b"image/svg+xml", DARK_PIC),
        "/hero-light.svg": (b"image/svg+xml", LIGHT_PIC),
    }

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            found = bodies.get(self.path)
            if found is None:
                self.send_error(404)
                return
            mime, body = found
            self.send_response(200)
            self.send_header("Content-Type", mime.decode())
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_a):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


@browser
def test_a_site_that_only_switches_by_button_still_has_two_faces(site):
    """The whole path, end to end: the probe finds no media-query difference,
    falls back to looking for a control, the second visit presses it, and the
    face that comes back is labelled by what it PAINTS rather than by the query
    we sent — which that site never read."""
    with RenderedSession(note=lambda _m: None) as session:
        page = session.capture(site + "/")
        assert page.other_face is not None, "the button was not found or not pressed"
        scheme, html, resources = page.other_face

        assert scheme == "light", "the kept face is measured, not assumed"
        assert 'data-theme="light"' in html

        # And its own picture came with it. The dark face's hero was carried by
        # the primary capture; this is the file only the light face asks for.
        assert any(
            url.endswith("/hero-light.svg") for url in resources
        ), f"the light face's own image was not carried: {sorted(resources)}"
        # Not a second copy of what the first face already had.
        assert not any(url.endswith("/hero-dark.svg") for url in resources)


@browser
def test_a_site_with_one_face_pays_for_no_second_visit(site):
    """False for most of the web, which is the point. A second visit is only
    worth its seconds when there is something to fetch."""
    with RenderedSession(note=lambda _m: None) as session:
        page = session.capture(site + "/one-face")
        assert page.other_face is None


@browser
def test_a_recording_pass_never_looks_for_a_second_face(site):
    """The alive engine's archive IS the ZIM, and a second visit is not
    recorded into it. Asking would double the time and bandwidth of every alive
    capture of a site with a dark mode for something nothing would read."""

    class _Recorder:
        def record(self, *_a, **_kw):
            pass

    with RenderedSession(note=lambda _m: None, recorder=_Recorder()) as session:
        page = session._context.new_page()
        try:
            page.goto(site + "/", wait_until="domcontentloaded")
            assert session._has_second_face(page) is False
        finally:
            page.close()


@browser
def test_which_face_is_which_is_measured_from_the_page(site):
    """The label on a stored face has to come from the pixels. A site that
    ignores the query we sent would otherwise be filed under the query."""
    with RenderedSession(note=lambda _m: None) as session:
        page = session._context.new_page()
        try:
            page.goto(site + "/", wait_until="domcontentloaded")
            assert session._face_scheme(page) == "dark"
            page.click("#tt")
            page.wait_for_timeout(300)
            assert session._face_scheme(page) == "light"
        finally:
            page.close()


def test_only_controls_that_say_what_they_do_are_clicked():
    """This ends in a real click on somebody else's site, so the bar is that
    the page said what the button does — never a guess from a moon glyph or a
    class that merely contains "toggle"."""
    selectors = " ".join(renderer._THEME_CONTROL_SELECTORS).lower()
    for claim in ("theme", "appearance", "dark mode", "light mode"):
        assert claim in selectors
    for guess in ("submit", "delete", "buy", "checkout", "signin", "login"):
        assert guess not in selectors
    # Every selector names an element that is a control, or an attribute only a
    # theme switch carries.
    for selector in renderer._THEME_CONTROL_SELECTORS:
        assert selector.startswith(("button", "a[", "[data-theme", "#theme", "[role="))
