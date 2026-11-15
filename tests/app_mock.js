// stand-in for the database: window.claude.use("db") with the app's small interface, filled from data.json
window.claude = { use: async () => {
  const D = window.__DATA;
  const docs = (c) => Object.entries(D[c] || {}).map(([id, d]) => ({ id, data: () => d }));
  const coll = (name, filters = [], order = null, lim = null) => ({
    where: (f, op, v) => coll(name, [...filters, [f, v]], order, lim),
    orderBy: (f, dir) => coll(name, filters, [f, dir], lim),
    limit: (n) => coll(name, filters, order, n),
    onSnapshot: (cb) => { let r = docs(name).filter((x) => filters.every(([f, v]) => x.data()[f] === v));
      if (order) r.sort((a, b) => String(a.data()[order[0]] ?? a.id).localeCompare(String(b.data()[order[0]] ?? b.id)) * (order[1] === "desc" ? -1 : 1));
      if (lim) r = r.slice(0, lim); setTimeout(() => cb({ docs: r }), 0); return () => {}; },
    add: async () => {},
  });
  const doc = (p) => { const [c, id] = p.split("/"); return { onSnapshot: (cb) => { const d = (D[c] || {})[id]; setTimeout(() => cb({ exists: !!d, data: () => d }), 0); return () => {}; }, update: async () => {}, set: async () => {}, delete: async () => {} }; };
  return { collection: (n) => coll(n), doc };
} };
