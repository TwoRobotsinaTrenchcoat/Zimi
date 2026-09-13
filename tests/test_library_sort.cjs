// How the home screen orders the ZIMs inside a category (#67).
//
// tripplehelix: "Alphabetise the categories in the home screen to help find
// ZIM's. Should display in the same order as in Settings -> Library."
// Article count was the old default; it rewards big files rather than the one
// you are looking for, and it disagreed with the Library list.
//
// Run: node tests/test_library_sort.cjs   (exit 0 = pass)

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const src = fs.readFileSync(path.join(__dirname, '..', 'zimi', 'static', 'app.js'), 'utf8');
function grab(name, kind) {
  const needle = kind === 'var' ? `var ${name} = ` : `function ${name}(`;
  const i = src.indexOf(needle);
  if (i < 0) throw new Error(name + ' not found');
  let j = src.indexOf(kind === 'var' ? '{' : '{', i), d = 0;
  for (; j < src.length; j++) {
    if (src[j] === '{') d++;
    else if (src[j] === '}' && --d === 0) {
      return src.slice(i, kind === 'var' ? j + 2 : j + 1);
    }
  }
  throw new Error('unbalanced ' + name);
}

const store = {};
const sandboxCalls = { rebuilt: 0, reordered: 0, canReorder: true };
const sandbox = {
  console,
  localStorage: {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
  },
  SK: { LIBRARY_SORT: 'zimi_library_sort' },
  // Changing the order moves the cards in place; when it cannot, the caller
  // rebuilds. Both are recorded so the fallback is a fact rather than a hope.
  renderHome: () => { sandboxCalls.rebuilt++; },
  _reorderLibraryInPlace: () => { sandboxCalls.reordered++; return sandboxCalls.canReorder; },
  _byFirstSeenDesc: (a, b) => (b.first_seen || 0) - (a.first_seen || 0),
  _byUpdatedDesc: (a, b) => (b.updated_at || 0) - (a.updated_at || 0),
};
vm.createContext(sandbox);
vm.runInContext(grab('LIBRARY_SORTS', 'var'), sandbox);
for (const fn of ['_librarySort', '_setLibrarySort', '_sortLibrary']) {
  vm.runInContext(grab(fn), sandbox);
}
vm.runInContext(grab('_LIBRARY_SORTERS', 'var'), sandbox);

let failures = 0;
const check = (ok, label) => { if (!ok) { console.error('FAIL: ' + label); failures++; } else console.log('ok: ' + label); };

const lib = [
  { name: 'zeta', title: 'Zebra Facts', entries: 900, first_seen: 30, updated_at: 5 },
  { name: 'alpha', title: 'apple orchard', entries: 10, first_seen: 10, updated_at: 40 },
  { name: 'mid', title: 'Middle Ground', entries: 500, first_seen: 20, updated_at: 20 },
];
const order = (list) => list.map(z => z.name);

check(vm.runInContext('_librarySort()', sandbox) === 'alpha', 'alphabetical is the default');
check(JSON.stringify(order(vm.runInContext('_sortLibrary(lib)', Object.assign(sandbox, { lib })))) ===
      JSON.stringify(['alpha', 'mid', 'zeta']), 'default order is by title, case-insensitively');

vm.runInContext("_setLibrarySort('entries')", sandbox);
check(JSON.stringify(order(vm.runInContext('_sortLibrary(lib)', sandbox))) ===
      JSON.stringify(['zeta', 'mid', 'alpha']), 'article count is still available');

vm.runInContext("_setLibrarySort('added')", sandbox);
check(order(vm.runInContext('_sortLibrary(lib)', sandbox))[0] === 'zeta', 'recently added puts the newest first');

vm.runInContext("_setLibrarySort('updated')", sandbox);
check(order(vm.runInContext('_sortLibrary(lib)', sandbox))[0] === 'alpha', 'recently updated puts the freshest first');

vm.runInContext("_setLibrarySort('nonsense')", sandbox);
check(vm.runInContext('_librarySort()', sandbox) === 'updated', 'an unknown order is refused, not stored');

const before = JSON.stringify(lib);
vm.runInContext('_sortLibrary(lib)', sandbox);
check(JSON.stringify(lib) === before, 'sorting never mutates the caller\'s list');

// ── the date you are sorting by is on the card ──────────────────────────────
//
// Eric, 2026-09-11: "when i sort by recently something maybe we should add the
// date since that's now relevant? Or always have in full view?"
//
// Only when it IS the sort key. The card already carries what it is, how much
// of it there is and how big it is; a fourth standing fact answers a question
// nobody asked. But an order whose key you cannot see is an order you have to
// take on trust, so the date appears the moment it becomes the question — and
// leaves when it stops being one.
Object.assign(sandbox, {
  Date, Intl,
  _currentLang: 'en',
  esc: (v) => String(v),
  escAttr: (v) => String(v),
});
sandbox.t = (k) => k;
vm.runInContext(grab('_AGE_STEPS', 'var'), sandbox);
vm.runInContext(grab('_shortAge'), sandbox);
vm.runInContext(grab('_sortedByDateHtml'), sandbox);

const NOW = Math.floor(Date.now() / 1000);
sandbox.dated = { name: 'atlas', first_seen: NOW - 3600, updated_at: NOW - 86400 * 3 };
const shown = (mode) => {
  vm.runInContext("_setLibrarySort('" + mode + "')", sandbox);
  return vm.runInContext('_sortedByDateHtml(dated)', sandbox);
};

check(shown('alpha') === '', 'alphabetical shows no date — it is not a date order');
check(shown('entries') === '', 'article count shows no date either');

const added = shown('added');
check(added.includes('card-when') && />1h</.test(added),
      'recently added shows how long ago it was added: ' + added.slice(-24));
const updated = shown('updated');
check(/>3d</.test(updated),
      'recently updated shows how long ago it was updated: ' + updated.slice(-24));

// Short enough to sit on a line that already holds a count and a size. The
// long form pushed that line onto two rows on a phone.
const ages = [[90, '1m'], [3600, '1h'], [172800, '2d'], [3456000, '1mo'], [34560000, '1y']];
for (const [secs, want] of ages) {
  const got = vm.runInContext('_shortAge(' + (NOW - secs) + ')', sandbox);
  check(got === want, secs + 's ago reads as ' + want + ' (got ' + got + ')');
  check(String(got).length <= 4, got + ' is short enough for the detail line');
}
// Under a minute has no useful unit, so it says so in words. The only row
// here that is allowed to be a phrase.
check(vm.runInContext('_shortAge(' + (NOW - 5) + ')', sandbox) === 'just_now',
      'a ZIM added seconds ago reads as words, not "0m"');

// Every library has some ZIM with no stamp. It must render nothing rather than
// "Invalid Date" or a dangling separator.
vm.runInContext("_setLibrarySort('added')", sandbox);
sandbox.undatedZim = { name: 'old' };
check(vm.runInContext('_sortedByDateHtml(undatedZim)', sandbox) === '',
      'an undated ZIM shows nothing rather than a broken date');

// ── moving beats rebuilding, and rebuilding is still there when it must be ──
sandboxCalls.rebuilt = 0; sandboxCalls.reordered = 0; sandboxCalls.canReorder = true;
vm.runInContext("_setLibrarySort('entries')", sandbox);
check(sandboxCalls.reordered === 1 && sandboxCalls.rebuilt === 0,
      'changing the order moves the cards instead of rebuilding them');

sandboxCalls.canReorder = false;
vm.runInContext("_setLibrarySort('alpha')", sandbox);
check(sandboxCalls.rebuilt === 1,
      'and rebuilds when the page is not the shape the move expects');

sandboxCalls.rebuilt = 0; sandboxCalls.reordered = 0;
vm.runInContext("_setLibrarySort('nonsense')", sandbox);
check(sandboxCalls.reordered === 0 && sandboxCalls.rebuilt === 0,
      'an order nobody offers does neither');

if (failures) { console.error(failures + ' failure(s)'); process.exit(1); }
console.log('all library sort checks passed');
