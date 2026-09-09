"""A replayed page's own loader can still find its chunks (#64).

warc2zim stores references relative, so `src="/_next/app.js"` becomes
`src="_next/app.js"`. Right for the browser, wrong for the page's own
JavaScript when it reads the attribute back: Turbopack identifies a chunk by
`script.getAttribute("src")` and strips a leading `/_next/`. With the slash
gone every chunk registers under a name nothing waits for, the entry module
never runs, and the page renders and does nothing — no error, no failed
request. draculatheme.com/contribute was the reported case: 191 module
factories run on the live site, none in the ZIM.

Run: pytest tests/test_loader_shim.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from zimi.zimpatch import SHIM_MARKER, _with_loader_shim  # noqa: E402

ANCHOR = '<script src="../_zim_static/wombatSetup.js"></script>'
PAGE = f'<html><head>{ANCHOR}<script src="_next/static/app.js"></script></head><body>hi</body></html>'


def test_the_shim_lands_before_the_page_s_own_scripts():
    out = _with_loader_shim(PAGE)
    assert SHIM_MARKER in out
    assert out.index(SHIM_MARKER) < out.index("_next/static/app.js")


def test_it_goes_in_after_wombat_not_before():
    # It reads the .src property, which is wombat's to patch; installing ahead
    # of wombat would read the replay URL and answer with the wrong path.
    out = _with_loader_shim(PAGE)
    assert out.index("wombatSetup.js") < out.index(SHIM_MARKER)


def test_a_page_without_the_replay_shell_is_untouched():
    plain = "<html><head><title>x</title></head><body>hi</body></html>"
    assert _with_loader_shim(plain) == plain


def test_installing_twice_installs_once():
    once = _with_loader_shim(PAGE)
    assert _with_loader_shim(once) == once


def test_the_shim_only_answers_for_relative_script_sources():
    from zimi.zimpatch import LOADER_SHIM

    # It must leave absolute, protocol-relative and already-rooted values
    # alone: those are what the page shipped with, and rewriting them would
    # invent a path the loader never asked for.
    assert 'this.tagName==="SCRIPT"' in LOADER_SHIM
    assert 'v.charAt(0)!=="/"' in LOADER_SHIM
    assert "u.pathname+u.search" in LOADER_SHIM
