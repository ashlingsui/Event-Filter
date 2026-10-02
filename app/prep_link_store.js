/*
 * Events added directly on #/prep by pasting a link — for preparing for something the local
 * pipeline never scraped at all (not even as an UNSCORED candidate; that's #/intake, step 4's
 * separate link-intake workflow per SPEC.md §5 / DESIGN_V12_HANDOFF.md). There is no server to
 * fetch and parse an arbitrary URL, so this stores only what she actually typed — saved to this
 * browser only, always labeled "Added by you," never a claim the pipeline scored or even saw
 * this event.
 */
const PrepLinkStore = (() => {
  const KEY = "skipgo:prep_link:v1";

  function getAll() {
    try {
      const raw = localStorage.getItem(KEY);
      return raw ? JSON.parse(raw) : [];
    } catch (err) {
      return [];
    }
  }

  function save(all) {
    try {
      localStorage.setItem(KEY, JSON.stringify(all));
      return true;
    } catch (err) {
      return false;
    }
  }

  function add({ name, url }) {
    const all = getAll();
    const row = {
      event_id: `prep:${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`,
      name: name || url,
      url: url || null,
      local: true,
      created_at: new Date().toISOString(),
    };
    all.push(row);
    save(all);
    return row;
  }

  return { getAll, add };
})();
