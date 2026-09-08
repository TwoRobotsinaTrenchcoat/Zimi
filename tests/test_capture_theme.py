"""A capture takes the face of the site the person asked for (#65).

tripplehelix, 2026-09-08: the capture "doesn't respect the theme the site was
crawled in". It did not: nothing set a colour scheme, so every capture was
taken in the browser's default, which is light. A site with its own dark mode
serves a different page for each, so someone reading in dark got a capture that
looked nothing like the site they were looking at.

Run: pytest tests/test_capture_theme.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from zimi.renderer import RenderedSession  # noqa: E402


class _Browser:
    """Enough of a browser to record what the session asks for."""

    def __init__(self):
        self.options = None
        self.version = "test"

    def new_context(self, **options):
        self.options = options
        return _Context()


class _Context:
    def set_default_timeout(self, _ms):
        pass

    def route(self, *_args, **_kwargs):
        pass


def _options_for(color_scheme):
    session = RenderedSession(color_scheme=color_scheme, note=lambda _m: None)
    browser = _Browser()
    session._browser = browser
    session._pw = object()
    session._install_blocking = lambda: None
    # The part of start() after the browser is up.
    session._driver_pid = None
    session._context = browser.new_context(
        **{
            "viewport": {"width": session._viewport[0], "height": session._viewport[1]},
            "user_agent": session._user_agent(),
            "ignore_https_errors": False,
            **(
                {"color_scheme": color_scheme}
                if color_scheme in ("dark", "light")
                else {}
            ),
        }
    )
    return browser.options


def test_a_dark_capture_asks_the_browser_for_dark():
    assert _options_for("dark")["color_scheme"] == "dark"


def test_a_light_capture_asks_for_light():
    assert _options_for("light")["color_scheme"] == "light"


def test_no_preference_leaves_the_browser_alone():
    # None must not become the string "None" or force light explicitly; the
    # browser's own default is the honest answer when nobody asked.
    assert "color_scheme" not in _options_for(None)


def test_the_session_start_passes_it_through():
    # The test above builds the options the same way start() does; this holds
    # them together, so the option cannot be dropped from start() alone.
    import inspect

    source = inspect.getsource(RenderedSession.start)
    assert "self._color_scheme" in source
    assert "color_scheme" in source
