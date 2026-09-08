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
const sandbox = {
  console,
  localStorage: {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
  },
  SK: { LIBRARY_SORT: 'zimi_library_sort' },
  renderHome: () => {},
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

if (failures) { console.error(failures + ' failure(s)'); process.exit(1); }
console.log('all library sort checks passed');
