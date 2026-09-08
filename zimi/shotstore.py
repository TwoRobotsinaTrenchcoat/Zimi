"""The two pictures, for the ZIMs Zimi does not write.

Every engine that goes through Zimi's own Creator stores its live and packaged
pictures as ZIM metadata, beside the illustration, where they travel with the
file. Two engines do not go through it: ``alive`` and ``zimit`` hand a WARC to
warc2zim, which writes the ZIM itself. warc2zim takes a title, a description, a
language, an illustration — and no arbitrary metadata (its ``--help`` is the
whole list). A finished ZIM is sealed, so the only way to put a picture inside
one afterwards is to rewrite every byte of a file that can be gigabytes.

So for those two engines the pictures live beside the library instead, under
``<data_dir>/shots/``, and the same two routes serve them. What the reader sees
is identical; what differs is that copying such a ZIM to another machine leaves
its pictures behind. That is the honest trade, and it is the right way round:
the pictures answer "did this capture work?", which is a question asked on the
machine that just made it, minutes after it was made.

Names are the ZIM's own, sanitised to one path segment, so the store needs no
index and a stale entry is one file.
"""

import errno
import logging
import os
import re

log = logging.getLogger("zimi.shotstore")

DIRNAME = "shots"
KINDS = ("live", "zim")
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")
# A picture is a picture; anything larger is a bug upstream of here, and the
# writer's own budget (SHOT_MAX_BYTES) is well under this.
MAX_BYTES = 4 * 1024 * 1024


def _safe(name):
    return _SAFE.sub("_", (name or "").strip())[:180]


def store_dir(data_dir):
    return os.path.join(data_dir, DIRNAME)


def path_for(data_dir, zim_name, kind):
    """Where this ZIM's picture of ``kind`` lives, or None if either is junk."""
    safe = _safe(zim_name)
    if not safe or kind not in KINDS:
        return None
    return os.path.join(store_dir(data_dir), f"{safe}.{kind}.jpg")


def save(data_dir, zim_name, kind, jpeg):
    """Write one picture. Returns True when it landed.

    Never raises: a missing picture is a missing picture, never a failed
    capture. Written to a temporary name and moved into place, so a reader
    never opens a half-written file."""
    path = path_for(data_dir, zim_name, kind)
    if not path or not jpeg or len(jpeg) > MAX_BYTES:
        return False
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "wb") as f:
            f.write(jpeg)
        os.replace(tmp, path)
        return True
    except OSError as e:
        log.debug("could not store the %s picture for %s: %s", kind, zim_name, e)
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return False


def read(data_dir, zim_name, kind):
    """The stored picture, or None. Never raises."""
    path = path_for(data_dir, zim_name, kind)
    if not path:
        return None
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError as e:
        if e.errno not in (errno.ENOENT, errno.ENOTDIR):
            log.debug("could not read the %s picture for %s: %s", kind, zim_name, e)
        return None


def has(data_dir, zim_name, kind):
    path = path_for(data_dir, zim_name, kind)
    return bool(path) and os.path.isfile(path)


def forget(data_dir, zim_name):
    """Drop both pictures. Called when the ZIM they describe goes away, so the
    store cannot outlive the library by more than the file it names."""
    dropped = 0
    for kind in KINDS:
        path = path_for(data_dir, zim_name, kind)
        if not path:
            continue
        try:
            os.unlink(path)
            dropped += 1
        except OSError:
            pass
    return dropped
