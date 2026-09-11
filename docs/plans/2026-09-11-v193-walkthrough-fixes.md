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

- [ ] **The address is not probed until the field loses focus.** Someone can paste and hit Create without the probe ever running, and silently get a worse result than the probe would have chosen.
- [ ] **The source screenshot is taken but never shown while the job runs.** It exists; put it at the top of the running job.
- [ ] **The preview and title from the last run persist into the next one.** A finished job should leave the form fresh.
- [ ] **Periodic snapshots from the headless browser while a job runs.** Eric's own words: "might be overkill." Decide, do not drift.

### Capture fidelity

- [ ] **draculatheme.com as `alive`: the pictures are gone.** Worse than the same site as `rendered`. The short-page warning fires.
- [ ] **draculatheme.com as `alive`: the ZIM looks better than its own packaged screenshot.** The screenshot is being taken before the page has settled, so the warning it drives is wrong too.
- [ ] **`rendered` captures store no second face.** The in-page theme toggle is present and does nothing, because only one face was recorded. Two-faces currently runs for some engines and not others.
- [ ] **A capture defaults to dark when the system is light.** Backwards. The stored faces must be chosen by the viewer's scheme, not by whichever was recorded first.
- [ ] **In light mode the dracula image does not appear at all.**
- [ ] **Do the fixes hold across all three engines?** `alive`, `rendered`, and the plain JS path. Needs a matrix run, not an assumption.
- [ ] **Outbound links in a capture do not say they leave the ZIM.** Eric: "I guess that's fine" — so this is a judgement call, not a defect.

### Manage view

- [ ] **The Creator tab is slow to open, and the "Made here" list is slow after it opens.** Eric: "all of that blows it should be snappy."

### Question to answer, not a defect

- [ ] **Update track.** Confirm what `beta` means: a draft release with artifacts that Eric has not yet published.

## Out of scope for this cut

External qBittorrent support (#53). Deliberately deferred — it needs file-path and permission work that does not belong in a patch release. L3tum has been waiting since 20 August and is owed a status reply either way.
