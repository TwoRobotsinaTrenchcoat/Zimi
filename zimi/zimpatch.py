"""Give a ZIM that warc2zim wrote what only Zimi could know about it.

The alive and zimit engines hand a WARC to openZIM's warc2zim, which writes
the ZIM. That is the right division of labour — warc2zim owns replay, and
Zimi is not going to rebuild it — but the sidecar takes nine flags and
nothing else, so everything the capture learned is dropped at the door: which
of the stored files were pages, what URL each page came from, what the live
page looked like, which hosts were refused.

The cost of losing that is not confined to the capture. The title index takes
every entry, so one two-page capture puts eight hundred asset URLs into the
library's vocabulary and the whole library starts suggesting `com` for
"coma". Random article fails on a ZIM whose article count is 2 of 876. The
card says "2 entries" for a site.

So the ZIM is rewritten once, here, at creation, on a file we just made.
Measured on a real 15.7 MB capture: about a second, same size.

Two rules govern what this may do, and they are tested:

  * **Only standard fields, used as the spec intends, plus ``X-`` metadata.**
    The front-article flag is the field every viewer already reads for "is
    this a page"; warc2zim has to guess it from mimetype and picks up
    third-party widgets, while the capture *knows*. Setting it correctly is
    not a Zimi extension — Kiwix's random button and suggestions get better
    from the same change.
  * **Nothing else moves.** Entry paths, content, the main entry, redirects
    and the replay machinery are preserved exactly. A rewritten ZIM opens in
    any other viewer and behaves at least as well as it did before.
"""

import json
import logging
import os
import tempfile
import time

log = logging.getLogger("zimi.zimpatch")

# The capture record. `X-` is the openZIM spec's own space for a scraper's
# metadata, and every other viewer ignores what it does not recognise.
CAPTURE_METADATA_KEY = "X-Zimi-Capture"
RECORD_VERSION = 1

# libzim recomputes this at finalisation from what was actually written;
# handing it a copy makes a duplicate dirent and refuses the whole file.
_GENERATED_METADATA = {"Counter"}


def _pages_by_path(pages):
    """``{zim path: page}`` for the pages this capture visited.

    warc2zim stores a page at the URL without its scheme, which is what makes
    this mapping possible at all: `https://x.com/a?b=1` is stored at
    `x.com/a?b=1`."""
    out = {}
    for page in pages or []:
        url = (page or {}).get("url") or ""
        path = zim_path_for_url(url)
        if path:
            out[path] = page
    return out


def zim_path_for_url(url):
    """The entry path warc2zim gives a URL, or "" when it is not one."""
    url = (url or "").strip()
    for scheme in ("https://", "http://"):
        if url.lower().startswith(scheme):
            return url[len(scheme) :]
    return ""


def build_record(*, seed_url, engine, pages, assets, blocked=None, extra=None):
    """The capture record, as a plain dict ready to be stored."""
    record = {
        "version": RECORD_VERSION,
        "engine": engine,
        "source": seed_url,
        "captured": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "assets": int(assets or 0),
        "pages": [
            {
                "path": zim_path_for_url(p.get("url") or ""),
                "url": p.get("url") or "",
                "title": p.get("title") or "",
            }
            for p in (pages or [])
            if zim_path_for_url(p.get("url") or "")
        ],
    }
    if blocked:
        record["blocked"] = blocked
    if extra:
        record.update(extra)
    return record


def patch(
    path,
    record,
    *,
    live_shot=None,
    packaged_shot=None,
    publisher="Zimi",
    note=None,
):
    """Rewrite the ZIM at ``path`` in place, adding what Zimi knows.

    Returns True when the file was replaced. Never raises and never leaves a
    half-written file under the real name: the new ZIM is built beside it and
    moved into place only once it is complete and readable, so any failure
    leaves the warc2zim original exactly as it was. A capture that succeeded
    must not be lost to an enrichment step.
    """
    say = note or (lambda _m: None)
    try:
        from libzim.reader import Archive
    except Exception as e:  # pragma: no cover - libzim is a hard dependency
        log.debug("no libzim, leaving %s alone: %s", path, e)
        return False

    tmp = None
    try:
        source = Archive(path)
        pages = _pages_by_path(record.get("pages"))
        fd, tmp = tempfile.mkstemp(
            prefix=".zimi-patch-", suffix=".zim", dir=os.path.dirname(path) or "."
        )
        os.close(fd)
        os.unlink(tmp)  # the Creator wants to make it itself
        _rewrite(
            source,
            tmp,
            pages=pages,
            record=record,
            live_shot=live_shot,
            packaged_shot=packaged_shot,
            publisher=publisher,
        )
        # Opened before it is trusted: a ZIM that cannot be read is not one we
        # are going to put in the library under the good file's name.
        check = Archive(tmp)
        if check.all_entry_count < 1 or not check.has_main_entry:
            raise ValueError("the rewritten ZIM has no main entry")
        del check, source
        os.replace(tmp, path)
        tmp = None
        say(f"recorded {len(pages)} page(s) and the capture's own metadata in the ZIM")
        return True
    except Exception as e:
        log.info("could not enrich %s, keeping it as written: %s", path, e)
        say("kept the ZIM exactly as the converter wrote it")
        return False
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _rewrite(source, out, *, pages, record, live_shot, packaged_shot, publisher):
    from libzim.writer import Creator, Hint, Item, StringProvider

    class _Copied(Item):
        """One entry, carried across unchanged except for what it is called."""

        def __init__(self, path, title, mimetype, data, front):
            super().__init__()
            self._path = path
            self._title = title
            self._mimetype = mimetype
            self._data = data
            self._front = front

        def get_path(self):
            return self._path

        def get_title(self):
            return self._title

        def get_mimetype(self):
            return self._mimetype

        def get_contentprovider(self):
            return StringProvider(self._data)

        def get_hints(self):
            return {Hint.FRONT_ARTICLE: self._front}

    metadata_keys = set(source.metadata_keys)
    language = _metadata_str(source, "Language") or "eng"
    main_path = source.main_entry.get_item().path

    with Creator(out).config_indexing(True, language) as creator:
        for index in range(source.all_entry_count):
            entry = source._get_entry_by_id(index)
            path = entry.path
            if path in metadata_keys:
                continue  # re-added below, from the source of truth
            if entry.is_redirect:
                try:
                    creator.add_redirection(
                        path,
                        entry.title,
                        entry.get_redirect_entry().path,
                        {Hint.FRONT_ARTICLE: False},
                    )
                except Exception as e:
                    log.debug("redirect %s not carried: %s", path, e)
                continue
            item = entry.get_item()
            page = pages.get(path)
            try:
                creator.add_item(
                    _Copied(
                        path,
                        # The page's own title, when the capture read one: it
                        # is the title a person saw, and warc2zim only has
                        # what the served HTML happened to carry.
                        (page or {}).get("title") or item.title,
                        item.mimetype,
                        bytes(item.content),
                        bool(page),
                    )
                )
            except Exception as e:
                log.debug("entry %s not carried: %s", path, e)

        # Collected first, written once: a key may be both copied from the
        # source and set by us, and adding the same one twice refuses the
        # whole file.
        values = {}
        for key in sorted(metadata_keys):
            if key in _GENERATED_METADATA:
                continue
            try:
                values[key] = bytes(source.get_metadata(key))
            except Exception:
                continue
        # What warc2zim parses and never writes, and what it stamps as its own.
        if record.get("source"):
            values["Source"] = record["source"].encode("utf-8")
        if publisher:
            values["Publisher"] = publisher.encode("utf-8")

        for key, value in values.items():
            if key.startswith("Illustration"):
                _add_illustration(creator, key, value)
            else:
                creator.add_metadata(key, value)

        creator.add_metadata(
            CAPTURE_METADATA_KEY,
            json.dumps(record, ensure_ascii=False, separators=(",", ":")),
            "application/json",
        )
        if live_shot:
            creator.add_metadata("X-Zimi-Screenshot", live_shot, "image/jpeg")
        if packaged_shot:
            creator.add_metadata("X-Zimi-Screenshot-Zim", packaged_shot, "image/jpeg")
        creator.set_mainpath(main_path)


def _add_illustration(creator, key, value):
    size = 48
    digits = "".join(ch for ch in key.split("@")[0] if ch.isdigit() or ch == "x")
    if "x" in digits:
        try:
            size = int(digits.split("x")[0])
        except ValueError:
            size = 48
    try:
        creator.add_illustration(size, value)
    except Exception as e:
        log.debug("illustration %s not carried: %s", key, e)


def _metadata_str(archive, key):
    try:
        return (
            bytes(archive.get_metadata(key)).decode("utf-8", errors="replace").strip()
        )
    except Exception:
        return ""


def read_record(archive):
    """The capture record inside a ZIM, or None. Never raises."""
    try:
        raw = bytes(archive.get_metadata(CAPTURE_METADATA_KEY))
    except Exception:
        return None
    try:
        record = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:
        return None
    return record if isinstance(record, dict) else None
