# Captures are first-class ZIMs

Eric, 2026-09-07: *"Yes make these not just equal to all the others, that's a requirement to be at par. Instead integrate properly fully and creatively beyond the limits in ways only vertical integration can deliver. Staying protocol compliant and compatible with all other viewers."*

## The situation

Two of Zimi's engines — `alive` and the `zimit` site crawl — hand a WARC to openZIM's `warc2zim`, which writes the ZIM. That is the right call: warc2zim owns replay, and rebuilding it would be years of work for a worse result. But warc2zim accepts nine flags and nothing else, so everything Zimi knows about the capture is discarded at the door.

An audit of a real alive ZIM against a Zimi-written one found what that costs. Ranked by damage:

| | what happens | who it hurts |
|---|---|---|
| 1 | The title index takes all 876 entries of a 2-page capture. The library's vocabulary becomes `com`, `avatars`, `githubusercontent` — GitHub avatar URLs. Searching "coma" suggests "com". | **every ZIM in the library** |
| 2 | Suggest returns `avatars.githubusercontent.com/u/100347457?v=4&s=60` as an article title | the capture |
| 3 | The ZIM registers under eight invented domains (`dracula.com`, `.org`, `.io`…) so cross-ZIM links miss it until a restart | cross-ZIM linking |
| 4 | Random article fails: 2 articles among 876 entries, sampled 8 at a time. Breaks the Discover card and the MCP tool | the capture, the agent API |
| 5 | The card says "2 entries" for an 876-entry site, and one of the two is a third-party feedback widget | the shelf |
| 6 | About says "This ZIM carries no Zimi history", under a badge saying Zimi made it. No source URL, because warc2zim parses `--source` and never writes it | trust |
| 7 | The two pictures cannot be stored at all | the capture |

Every one of these is downstream of a single missing fact: **Zimi does not know which entries are pages.**

## The idea

The capture already knows. The crawler visited each page, holds its final URL and its title, and knows exactly which of the hundreds of stored files were pages and which were assets. That knowledge is thrown away when the WARC crosses to warc2zim.

So: after warc2zim writes the ZIM, Zimi rewrites it once, adding what only Zimi can know.

Measured on the real 15.7 MB / 876-entry dracula capture: **1.1 seconds, same file size**, fulltext index rebuilt, main entry and redirects preserved. A rewrite is affordable because it happens once, at creation, on a file we just made.

## What the rewrite adds

**1. Front-article flags that tell the truth.** The ZIM format already has the field every viewer reads for "is this a page": the front-article flag, which feeds `article_count`, the title index, and random. warc2zim guesses from mimetype and gets a third-party widget iframe. Zimi *knows*, so it marks exactly the pages it visited and nothing else.

This is the whole trick, and it is why the result is not a Zimi extension: **Kiwix gets a better ZIM too.** Its random button starts working, its suggestions stop offering asset URLs, and its article count becomes the page count. We are not adding a private channel; we are filling in a standard field correctly because we are the only one who can.

**2. A capture record, as metadata.** One JSON document under `X-Zimi-Capture`, plus the two pictures under the keys they already use. It records the seed URL, the engine, every page (ZIM path, source URL, title), the asset count, the blocked hosts, and the timestamps. `X-` metadata is explicitly allowed by the openZIM spec, and every other viewer ignores what it does not recognise. Nothing about the ZIM's readability depends on it.

**3. The metadata warc2zim drops on the floor.** `Source` (it parses `--source` and never writes it) and `Publisher`. Both are standard keys other viewers show.

## What that unlocks, in order

Each of these becomes small once the record exists.

- **The title index indexes pages** (fixes 1 and 2, and stops one capture degrading the whole library's did-you-mean).
- **The domain map reads the record** instead of guessing TLDs off the filename (fixes 3). The interlanguage code already has the correct fallback; the server's copy is missing it despite a docstring promising they are in sync.
- **Random draws from pages** (fixes 4).
- **The card counts pages, and says so**: "12 pages · 900 files" (fixes 5).
- **About shows the source URL, the engine, and the capture history** (fixes 6).
- **The pictures are ZIM metadata, in the file, travelling with it** (fixes 7), replacing the store beside the library that 1.9.3 currently uses. Eric: *"it must be in the zim. We're making this thing, Zimi, not warc2zim."*

## Beyond parity

The three above are parity. These are what the vertical integration is actually for, and none of them are possible for a viewer that only ever sees the finished file:

- **Outbound links resolve into the library.** Zimi already answers "which ZIM holds this URL" (`/resolve`). With every capture's page URLs recorded, any external link *in any ZIM* — a Wikipedia citation, a Stack Overflow answer's source — can be checked against the library and rewritten to the local capture when we hold it. The reader stops being a set of islands. Kiwix cannot do this because the mapping is a library-level fact, not a file-level one.
- **Reader View that works on a capture.** At capture time a real browser had the page laid out. Storing the extracted reading text as part of the record makes Reader View correct and instant on a replayed page, where today the site's own dark CSS survives into the reader column and renders it unreadable.
- **The agent surface gets the truth.** `/chunks` and the MCP tools can name the source URL and the capture date per chunk, so an answer grounded in a captured page can cite where and when it was captured.

## Compatibility, stated as a rule

Every change here writes only: standard ZIM fields used as the spec intends, and `X-` metadata. No entry paths change, no content is rewritten, the main entry and every redirect are preserved, and the replay machinery is untouched. A rewritten ZIM must open in Kiwix and behave at least as well as before. That last sentence is a test, not a hope.

## Order of work

1. **Foundation** — `zimi/zimpatch.py`: the rewrite, the record, the front-article flags. Wire into the alive page path, the alive site path, and zimit. Move the two pictures into the ZIM and delete the store beside the library.
2. **The library reads it** — title index, domain map, random, counts, About.
3. **Beyond** — outbound link resolution, Reader View text, agent citations.

Wave 1 is the only one that has to happen at capture time; the rest are read-side and can land after.
