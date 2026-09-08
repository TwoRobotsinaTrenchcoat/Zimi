"""The picture store, for the ZIMs Zimi does not write.

warc2zim writes the ZIM for the alive and zimit engines, takes no arbitrary
metadata, and seals the file — so those captures cannot carry their two
pictures inside them. 1.9.2 shipped the feature without them, which meant the
engine most likely to produce a broken-looking capture was the one engine that
could not show you. These live beside the library instead, and the same two
routes serve them.

Run: pytest tests/test_shotstore.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import zimi.shotstore as shotstore  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0" + b"picture bytes"


def test_a_picture_goes_in_and_comes_back(tmp_path):
    data_dir = str(tmp_path)
    assert shotstore.save(data_dir, "wikipedia_en_all", "live", JPEG) is True
    assert shotstore.read(data_dir, "wikipedia_en_all", "live") == JPEG
    assert shotstore.has(data_dir, "wikipedia_en_all", "live") is True


def test_the_two_kinds_do_not_collide(tmp_path):
    data_dir = str(tmp_path)
    shotstore.save(data_dir, "z", "live", b"\xff\xd8live")
    shotstore.save(data_dir, "z", "zim", b"\xff\xd8packaged")
    assert shotstore.read(data_dir, "z", "live") == b"\xff\xd8live"
    assert shotstore.read(data_dir, "z", "zim") == b"\xff\xd8packaged"


def test_a_missing_picture_is_none_not_an_error(tmp_path):
    assert shotstore.read(str(tmp_path), "never-captured", "live") is None
    assert shotstore.has(str(tmp_path), "never-captured", "live") is False


def test_a_name_cannot_escape_the_store(tmp_path):
    # A ZIM name reaches here from a filename, so it is not trusted input.
    data_dir = str(tmp_path)
    for hostile in ("../../etc/passwd", "..", "a/b/c", "/absolute"):
        path = shotstore.path_for(data_dir, hostile, "live")
        if path is None:
            continue
        parent = os.path.dirname(os.path.abspath(path))
        assert parent == os.path.abspath(shotstore.store_dir(data_dir)), hostile


def test_an_empty_or_oversize_picture_is_refused(tmp_path):
    data_dir = str(tmp_path)
    assert shotstore.save(data_dir, "z", "live", b"") is False
    assert (
        shotstore.save(data_dir, "z", "live", b"x" * (shotstore.MAX_BYTES + 1)) is False
    )
    assert shotstore.has(data_dir, "z", "live") is False


def test_an_unknown_kind_is_refused(tmp_path):
    assert shotstore.path_for(str(tmp_path), "z", "thumbnail") is None
    assert shotstore.save(str(tmp_path), "z", "thumbnail", JPEG) is False


def test_forgetting_a_zim_drops_both_pictures(tmp_path):
    # A deleted ZIM must not leave pictures behind for the next ZIM that takes
    # its name to serve as its own.
    data_dir = str(tmp_path)
    shotstore.save(data_dir, "gone", "live", JPEG)
    shotstore.save(data_dir, "gone", "zim", JPEG)
    assert shotstore.forget(data_dir, "gone") == 2
    assert shotstore.read(data_dir, "gone", "live") is None
    assert shotstore.read(data_dir, "gone", "zim") is None


def test_a_half_written_picture_is_never_visible(tmp_path):
    # save() writes to a temporary name and moves it into place, so a reader
    # either sees the whole picture or no picture.
    data_dir = str(tmp_path)
    shotstore.save(data_dir, "z", "live", JPEG)
    leftovers = [
        p for p in os.listdir(shotstore.store_dir(data_dir)) if p.endswith(".tmp")
    ]
    assert leftovers == []


def test_the_alive_engine_stores_what_it_took(tmp_path, monkeypatch):
    import zimi.alive as alive
    import zimi.server as srv

    monkeypatch.setattr(srv, "ZIMI_DATA_DIR", str(tmp_path))
    # No browser in this test, so the packaged picture cannot be taken; the
    # live one still must land, and the result must say exactly that.
    monkeypatch.setattr(alive, "shot_verdict", lambda a, b: ("", False), raising=False)
    said = []
    stored = alive.store_pictures(
        os.path.join(str(tmp_path), "mysite.zim"), JPEG, said.append
    )
    assert stored["live"] is True
    assert shotstore.read(str(tmp_path), "mysite", "live") == JPEG
    assert any("live page" in line for line in said)


def test_the_http_layer_falls_back_to_the_store():
    # The route and the info payload both have to know about the store, or an
    # alive capture's pictures exist and are never shown.
    import inspect

    import zimi.http as http

    assert "shotstore" in inspect.getsource(http.ZimHandler._serve_zim_metadata_image)
    assert "shotstore" in inspect.getsource(http._shot_beside)
    assert "_shot_beside" in inspect.getsource(http._zim_info)
