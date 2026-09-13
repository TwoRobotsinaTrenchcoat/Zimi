// Every clickable place on the world map lights something in the world clock.
//
// The clock renders a curated tour of 28 cities. Picking a place on the map
// resolves it to an IANA zone (_almTzForLocation) and then asks which card that
// zone lights (_almTzCardMatch). For most of the world a card matches outright
// or shares the offset, so the answer is some index. For a fractional zone it
// is -1: Eucla is UTC+8:45 and no card on the tour is, so every card stayed
// dark and the click read as a no-op. -1 is now a real answer that the caller
// handles by giving the zone a card of its own.
//
// Two things are guarded here, and they pull in opposite directions:
//
//   1. -1 must be REACHABLE, or the off-tour branch is dead code. The map has
//      dots for the fractional zones on purpose (Eucla, Chatham, Marquesas,
//      Lord Howe...), so those dots must produce it.
//   2. -1 must be RARE. If a whole-hour zone starts answering -1, an anchor or
//      a card was edited badly and ordinary places are about to sprout a
//      one-off card instead of lighting their column.
//
// Pure-helper approach, like tests/test_almanac_tz_resolution.cjs: the tables
// and functions are pulled out of almanac.js by source markers and run in a
// sandbox, so this drives the shipped code and not a copy.
//
// Run: node tests/test_tz_card_match.cjs   (exit 0 = pass)

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ALMANAC_JS = path.join(__dirname, '..', 'zimi', 'static', 'almanac.js');
const src = fs.readFileSync(ALMANAC_JS, 'utf8');

function extract(re, label) {
  const m = src.match(re);
  if (!m) throw new Error('could not extract ' + label + ' from almanac.js');
  return m[0];
}

const pieces = [
  extract(/var DEG_TO_RAD = [^;]+;/, 'DEG_TO_RAD'),
  extract(/var _TZ_ANCHORS = \[[\s\S]*?\n\];/, '_TZ_ANCHORS'),
  extract(/var _TZ_CITIES = \[[\s\S]*?\n\];/, '_TZ_CITIES'),
  extract(/var _MAP_CITIES = \[[\s\S]*?\n\];/, '_MAP_CITIES'),
  extract(/function _almTzForLocation\(lat, lon\)\s*\{[\s\S]*?\n\}/, '_almTzForLocation'),
  extract(/var _tzFmtCache = [^;]+;/, '_tzFmtCache'),
  extract(/function _tzFmt\(tz, opts, lang\)\s*\{[\s\S]*?\n\}/, '_tzFmt'),
  extract(/function _tzUtcOffsetMin\([\s\S]*?\n\}/, '_tzUtcOffsetMin'),
  extract(/function _almTzCardMatch\(targetTz, now\)\s*\{[\s\S]*?\n\}/, '_almTzCardMatch'),
  extract(/function _almTzCardLabel\(tz\)\s*\{[\s\S]*?\n\}/, '_almTzCardLabel'),
  extract(/function _almTzInsertAt\(tz, now\)\s*\{[\s\S]*?\n\}/, '_almTzInsertAt'),
];

const sandbox = { Intl, Date, Math, String, JSON, Object };
// _almTzCardLabel reads the stored location name; the sandbox stands in for
// sessionStorage with a settable stub so both of its branches can be driven.
sandbox._getLocation = () => sandbox.__loc;
sandbox.__loc = { name: '', lat: 0, lon: 0, stored: false };
vm.createContext(sandbox);
vm.runInContext(pieces.join('\n'), sandbox);

const { _almTzForLocation, _almTzCardMatch, _almTzCardLabel, _almTzInsertAt,
        _TZ_CITIES, _MAP_CITIES } = sandbox;

let failed = 0;
function check(name, cond, detail) {
  if (cond) { console.log('  ok: ' + name); return; }
  failed++;
  console.log('  FAIL: ' + name + (detail ? '\n        ' + detail : ''));
}

const JAN = new Date(Date.UTC(2026, 0, 15, 12));
const JUL = new Date(Date.UTC(2026, 6, 15, 12));

// --- 1. every card on the tour matches itself ------------------------------
let selfMatched = 0;
for (const c of _TZ_CITIES) {
  const m = _almTzCardMatch(c.tz, JAN);
  if (m >= 0 && _TZ_CITIES[m].tz === c.tz) selfMatched++;
}
check('each curated city lights its own card',
  selfMatched === _TZ_CITIES.length,
  selfMatched + '/' + _TZ_CITIES.length + ' matched');

// --- 2. a zone that only shares an offset still lights a column -------------
for (const [zone, expect] of [['Europe/Berlin', 'Europe/Paris'], ['America/Toronto', 'America/New_York']]) {
  const m = _almTzCardMatch(zone, JAN);
  check(zone + ' lights the column it shares an offset with',
    m >= 0 && _almTzCardMatch(_TZ_CITIES[m].tz, JAN) === m,
    'got ' + (m >= 0 ? _TZ_CITIES[m].tz : '-1') + ', wanted something at ' + expect + "'s offset");
}

// --- 3. the fractional zones are the ones that answer -1 -------------------
// Each is a dot on the map, so each is reachable by a click.
const OFF_TOUR = ['Australia/Eucla', 'Pacific/Chatham', 'Pacific/Marquesas'];
for (const zone of OFF_TOUR) {
  check(zone + ' is off the tour in both January and July',
    _almTzCardMatch(zone, JAN) === -1 && _almTzCardMatch(zone, JUL) === -1,
    'jan=' + _almTzCardMatch(zone, JAN) + ' jul=' + _almTzCardMatch(zone, JUL));
}

// Being on the tour is a property of the INSTANT, not of the zone: Lord Howe
// keeps a half-hour DST step, so it sits on Sydney's +11 in January and drifts
// to a fractional +10:30 in July. The match is recomputed on every render, so
// the card appears and disappears with the season rather than being baked in.
check('Lord Howe is on the tour in January and off it in July',
  _almTzCardMatch('Australia/Lord_Howe', JAN) >= 0 &&
  _almTzCardMatch('Australia/Lord_Howe', JUL) === -1,
  'jan=' + _almTzCardMatch('Australia/Lord_Howe', JAN) +
  ' jul=' + _almTzCardMatch('Australia/Lord_Howe', JUL));

// --- 4. clicking Eucla on the map is what reaches that branch --------------
// The end-to-end path a person takes: map dot -> lat/lon -> zone -> card.
const eucla = _MAP_CITIES.find(c => /^Eucla/.test(c.name));
check('the map has a dot for Eucla', !!eucla);
if (eucla) {
  const zone = _almTzForLocation(eucla.lat, eucla.lon);
  check('clicking that dot resolves to Australia/Eucla', zone === 'Australia/Eucla', 'got ' + zone);
  check('and that zone lights no curated card', _almTzCardMatch(zone, JAN) === -1);
}

// --- 5. -1 stays rare: the map is mostly on the tour -----------------------
// A dot answering -1 is not a bug by itself, but a jump in how many do means a
// card or an anchor changed and ordinary places lost their column.
const offTour = [];
for (const c of _MAP_CITIES) {
  const zone = _almTzForLocation(c.lat, c.lon);
  if (_almTzCardMatch(zone, JAN) === -1 && _almTzCardMatch(zone, JUL) === -1) offTour.push(c.name + ' (' + zone + ')');
}
const pct = offTour.length / _MAP_CITIES.length;
check('most map dots still light a curated card',
  pct < 0.2,
  offTour.length + ' of ' + _MAP_CITIES.length + ' dots are off the tour:\n        ' + offTour.join('\n        '));
check('and some dots do reach the off-tour branch', offTour.length > 0);

// --- 6. the off-tour card gets a readable name ----------------------------
sandbox.__loc = { name: 'Eucla, Western Australia, Australia', lat: -31.68, lon: 128.89, stored: true };
check('a named pick is trimmed to its first part',
  _almTzCardLabel('Australia/Eucla') === 'Eucla',
  'got ' + JSON.stringify(_almTzCardLabel('Australia/Eucla')));
sandbox.__loc = { name: '', lat: -43.95, lon: -176.56, stored: true };
check('an unnamed pick falls back to the zone\'s own city',
  _almTzCardLabel('Pacific/Chatham') === 'Chatham',
  'got ' + JSON.stringify(_almTzCardLabel('Pacific/Chatham')));
check('and underscores in a zone name become spaces',
  _almTzCardLabel('Australia/Lord_Howe') === 'Lord Howe',
  'got ' + JSON.stringify(_almTzCardLabel('Australia/Lord_Howe')));

// --- 7. an off-tour card lands where its clock belongs ---------------------
// The row reads west to east. A card shoved to the front puts a +8:45 clock to
// the left of Honolulu's -10, which makes the whole line unreadable.
function offsetOf(tz, date) {
  const opts = {year:'numeric',month:'numeric',day:'numeric',hour:'numeric',minute:'numeric',second:'numeric',hour12:false};
  const fmt = (z) => new Intl.DateTimeFormat('en-US', Object.assign({timeZone:z}, opts)).format(date);
  return Math.round((new Date(fmt(tz)) - new Date(fmt('UTC'))) / 60000);
}
for (const zone of ['Australia/Eucla', 'Pacific/Chatham', 'Pacific/Marquesas']) {
  const at = _almTzInsertAt(zone, JAN);
  const mine = offsetOf(zone, JAN);
  const before = at > 0 ? offsetOf(_TZ_CITIES[at - 1].tz, JAN) : -Infinity;
  const after = at < _TZ_CITIES.length ? offsetOf(_TZ_CITIES[at].tz, JAN) : Infinity;
  check(zone + ' sits between the clocks either side of it',
    before <= mine && mine < after,
    'inserted at ' + at + ': ' + before + ' <= ' + mine + ' < ' + after);
}
check('Eucla lands in the middle of the row, not at either end',
  _almTzInsertAt('Australia/Eucla', JAN) > 0 &&
  _almTzInsertAt('Australia/Eucla', JAN) < _TZ_CITIES.length,
  'got ' + _almTzInsertAt('Australia/Eucla', JAN));
check('a zone nobody can read goes last rather than somewhere wrong',
  _almTzInsertAt('Not/AZone', JAN) === _TZ_CITIES.length);

console.log('');
if (failed) {
  console.log(failed + ' tz card-match check(s) failed');
  process.exit(1);
}
console.log('all tz card-match checks passed (' + _TZ_CITIES.length + ' cards, ' +
  _MAP_CITIES.length + ' map dots, ' + offTour.length + ' off-tour)');
