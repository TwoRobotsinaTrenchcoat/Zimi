# 1.9.3 walkthrough — what Eric found

Eric ran the nine-item pre-cut checklist on the NAS build (`02e9729`) on 11 September 2026 and came back with sixteen findings. This is the tracker for all of them. Nothing ships until every line is either done or explicitly deferred with a reason.

## Verification standard

Every fix here is verified the way the reporter would see it: reproduce the literal steps first, then re-run them after. Capture work is verified by building a real ZIM and opening it in Zimi's own reader, not by reading the code. Where a defect is visual, the evidence is a screenshot of the rendered page, not a DOM count.

## Findings

### Library and almanac

- [x] **Sort does not reach Favorites or Collections.** The order chosen on the home screen applies to categories only. Favorites and Collections render from stored name lists in the order things were starred or added. — *fixed: both lists go through `_sortLibrary`.*
- [x] **"A–Z" should read "Alphabetical."** All ten locales. — *fixed.*
- [x] **Eucla has no timezone selected when you click that city.** The world clock's 28 cards are a curated tour; a fractional zone like Eucla's UTC+8:45 shares an offset with none of them, so every card stayed dark. — *fixed: the decision is now `_almTzCardMatch`, and an off-tour zone gets a card of its own. Guarded by `tests/test_tz_card_match.cjs`.*
- [x] **Messages Across Time pills carry a permanent underline.** It advertises the second-tap article link. — *fixed: hover and focus only.*

### Create page

- [x] **The address is not probed until the field loses focus.** — *fixed both ways: typing asks after a 600ms pause, and Create waits for an unanswered probe before starting, then re-reads the form because the answer can move the mode and the engine.*
- [x] **The source screenshot is taken but never shown while the job runs.** — *done. The engines announce the picture on the progress channel the moment they have it, the job holds the bytes, and `/manage/create/shot` serves them. It appears at the top of the run, cropped to its first 180px.*
- [x] **The preview and title from the last run persist into the next one.** — *fixed: a finished run clears the address, the title, the preview and every per-mode stash — but only when the form still holds the job that just finished, so typing the next address while the last one runs is never taken away.*
- [x] **Periodic snapshots from the headless browser while a job runs.** — *not built, deliberately. The one picture of the source now appears within seconds and is the thing that was missing. A stream of them costs a screenshot per interval on a NAS that is already the bottleneck, for a page that mostly does not change. Revisit if the run screen still feels dead.*

### Capture fidelity

- [x] **draculatheme.com as `alive`: the pictures are gone.** — *not true of the ZIM: opened in the reader it renders at 19,851px against the live 19,858px, with 473 images and none broken. What was wrong was the picture of it. Fixed.*
- [x] **draculatheme.com as `alive`: the ZIM looks better than its own packaged screenshot.** — *fixed, two causes. The photograph was taken of the converter's output, before the loader shim went in, so it was a picture of the very defect we fixed for #64. And a replayed page boots on CPU, not network, so "the network went quiet" arrived while the page was still an empty shell. Now: shot during the rewrite, and settled first. Dims went from 1280x19858,1280x900 to 1280x19858,1280x19858; the warning no longer fires.*
- [x] **`rendered` captures store no second face.** — *fixed. draculatheme.com stamps `data-theme="dark"` whatever `prefers-color-scheme` says, so the media-query probe was right that flipping the query changed nothing, and wrong that the site has one face. It now falls back to looking for a control the page itself labels as a theme switch, and the second visit presses it.*
- [x] **A capture defaults to dark when the system is light.** — *the site's own default, not ours: draculatheme.com paints dark for everyone. With two faces stored the reader now opens the one matching the viewer — verified, dark opens `A/index` at rgb(14,13,17) and light opens `A/index~other` at rgb(233,231,226). A face is labelled by what it paints, measured, not by the query we sent.*
- [x] **In light mode the dracula image does not appear at all.** — *fixed. The light face swaps the hero for a different file, `images/hero/default-light.svg`, and the code assumed a second face was the same page repainted and needed nothing new. The reference stayed an absolute remote URL — offline, a gap. The second visit now collects its own subresources, minus what the first face already carried.*
- [ ] **Do the fixes hold across all three engines?** `alive`, `rendered`, and the plain JS path. Needs a matrix run, not an assumption.
- [ ] **Outbound links in a capture do not say they leave the ZIM.** Eric: "I guess that's fine" — so this is a judgement call, not a defect.

### Manage view

- [ ] **The Creator tab is slow to open, and the "Made here" list is slow after it opens.** Eric: "all of that blows it should be snappy."

### Question to answer, not a defect

- [ ] **Update track.** Confirm what `beta` means: a draft release with artifacts that Eric has not yet published.

### Found mid-flight, not on Eric's list

- [x] **Zombie subprocesses on the NAS.** Eric, 2026-09-11: 20 zombies in 21 hours of uptime — 12 chrome-headless, 7 python3, 1 wget. Both streaming runners reaped the child only on the happy path, so every cancel skipped the kill AND the reap: a browser kept reading from a saturated disk for a capture already thrown away. — *fixed in `zimi/subproc.py`: a process group per child, killed and collected in a `finally`. `init: true` added to all three compose files as a backstop.*

## Out of scope for this cut

External qBittorrent support (#53). Deliberately deferred — it needs file-path and permission work that does not belong in a patch release. L3tum has been waiting since 20 August and is owed a status reply either way.
