(() => {
  "use strict";

  const TODAY_WEEK_KEY = "2026-W39"; // matches data/score_summary.json scored_at (2026-09-21)

  const weeks = DataAccess.getWeeks();
  const weekSelect = document.getElementById("weekSelect");
  const weekPrev = document.getElementById("weekPrev");
  const weekNext = document.getElementById("weekNext");
  const weekEyebrow = document.getElementById("weekEyebrow");
  const eventMap = document.getElementById("eventMap");
  const selectedEventEl = document.getElementById("selectedEvent");
  const inventoryStack = document.getElementById("inventoryStack");
  const coverageLine = document.getElementById("coverageLine");
  const suppressedHeadline = document.getElementById("suppressedHeadline");
  const suppressedDetail = document.getElementById("suppressedDetail");
  const toggleSkips = document.getElementById("toggleSkips");
  const skipDrawer = document.getElementById("skipDrawer");
  const sourceButton = document.getElementById("sourceButton");

  let currentWeekIndex = Math.max(0, weeks.findIndex((w) => w.key === TODAY_WEEK_KEY));
  let selectedId = null;

  const PROFESSIONAL_VERDICTS = new Set(["go", "part", "go_if", "wildcard"]);
  const PROF_STATE_LABEL = { go: "GO", part: "PART", go_if: "GO IF", wildcard: "WILDCARD" };

  function fmtTime(iso) {
    if (!iso) return "Date unknown";
    const d = new Date(iso);
    return d.toLocaleString("en-US", {
      weekday: "short", month: "short", day: "numeric",
      hour: "numeric", minute: "2-digit", timeZone: "America/Los_Angeles",
    }) + " PT";
  }

  function place(e) {
    if (e.city) return e.city;
    if (e.map_bucket === "outside_bay_area") return "Outside the Bay Area";
    if (e.map_bucket === "unknown_location") return "Location unknown";
    return "Bay Area";
  }

  function pText(e) {
    return typeof e.predicted_p === "number" ? e.predicted_p.toFixed(2) : "—";
  }

  function rowKind(e) {
    if (e.track === "social_cohort") return "social_cohort";
    if (e.verdict === "suppressed" || e.verdict === "blocked") return "skip";
    return e.verdict; // go | part | go_if | wildcard | skip
  }

  function populateWeekSelect() {
    weekSelect.innerHTML = weeks
      .map((w, i) => `<option value="${i}">${w.label} · ${w.key}</option>`)
      .join("");
  }

  function setWeek(index) {
    currentWeekIndex = Math.min(Math.max(index, 0), weeks.length - 1);
    weekSelect.value = String(currentWeekIndex);
    weekPrev.disabled = currentWeekIndex === 0;
    weekNext.disabled = currentWeekIndex === weeks.length - 1;
    renderWeek();
  }

  function currentWeek() {
    return weeks[currentWeekIndex];
  }

  function renderWeek() {
    const week = currentWeek();
    const events = DataAccess.getEventsForWeek(week.key);
    weekEyebrow.textContent = `Week of ${week.label} · Bay Area`;
    document.getElementById("crumb").textContent = `DECISION BOARD · ${week.label.toUpperCase()}`;

    const professional = events.filter((e) => e.track === "professional" && PROFESSIONAL_VERDICTS.has(e.verdict));
    const social = events.filter((e) => e.track === "social_cohort");
    const skip = events.filter((e) => e.track === "professional" && (e.verdict === "skip" || e.verdict === "blocked"));
    const suppressed = events.filter((e) => e.track === "professional" && e.verdict === "suppressed");

    // Default selection: first professional GO, else first professional event, else anything.
    const defaultPick = professional.find((e) => e.verdict === "go") || professional[0] || social[0] || skip[0] || null;
    selectedId = defaultPick ? defaultPick.id : null;

    renderMap(events);
    renderSelected(selectedId ? DataAccess.getEvent(selectedId) : null);
    renderInventory(professional, social, skip);
    renderSuppressed(week, suppressed, skip);
    renderCoverageLine(week, suppressed);
  }

  function renderMap(weekEvents) {
    const plottable = weekEvents.filter((e) => e.map_bucket === "bay_area" && e.map_xy && e.verdict !== "suppressed" && e.verdict !== "blocked");
    if (!plottable.length) {
      eventMap.innerHTML = `<div class="map-empty">No plottable Bay Area events this week. Every listing is still in the inventory below.</div>`;
      return;
    }

    // Real venues repeat exact coordinates (same building hosts many campus events). Cluster
    // anything within ~4px of a shared point and ring the markers around the true location
    // instead of letting them render on top of each other.
    const clusters = [];
    plottable.forEach((e) => {
      const hit = clusters.find((c) => Math.hypot(c.x - e.map_xy[0], c.y - e.map_xy[1]) < 4);
      if (hit) hit.items.push(e);
      else clusters.push({ x: e.map_xy[0], y: e.map_xy[1], items: [e] });
    });

    const positioned = [];
    clusters.forEach((c) => {
      const n = c.items.length;
      const ringR = n > 1 ? Math.min(34, 10 + n * 3) : 0;
      c.items.forEach((e, i) => {
        const angle = (2 * Math.PI * i) / n - Math.PI / 2;
        const x = n > 1 ? c.x + ringR * Math.cos(angle) : c.x;
        const y = n > 1 ? c.y + ringR * Math.sin(angle) : c.y;
        positioned.push({ e, x: Math.max(14, Math.min(586, x)), y: Math.max(14, Math.min(466, y)) });
      });
    });

    const markers = positioned.map(({ e, x, y }) => {
      const kind = rowKind(e);
      let r = 6;
      if (kind === "social_cohort") r = 8;
      else if (kind === "skip") r = 5;
      else r = 6 + 20 * (e.predicted_p || 0);
      const isSelected = e.id === selectedId;
      const label = isSelected
        ? `<text x="${Math.min(x + r + 6, 430)}" y="${y + 4}">${escapeXml(e.name.length > 30 ? e.name.slice(0, 28) + "…" : e.name)}</text>`
        : "";
      return `<g class="map-point ${kind}${isSelected ? " selected" : ""}" data-id="${e.id}" tabindex="0" role="button" aria-label="${escapeXml(e.name)}, ${kind}">
        <title>${escapeXml(e.name)}</title>
        <circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r.toFixed(1)}"></circle>
        ${label}
      </g>`;
    }).join("");

    eventMap.innerHTML = `
      <svg viewBox="0 0 600 480" role="group" aria-label="Bay Area event map">
        <rect x="0" y="0" width="600" height="480" fill="#101414"></rect>
        ${markers}
      </svg>
      <div class="map-legend">
        <span><i></i>Go / Part</span>
        <span><i class="part"></i>Go if / conditional</span>
        <span><i class="social"></i>Social / cohort</span>
        <span><i class="skip"></i>Skip</span>
      </div>
      <div class="map-caption">
        <span><b>Radius scales with P.</b> Hover or select a dot for its name; a ring of dots shares one real address.</span>
      </div>`;

    eventMap.querySelectorAll(".map-point").forEach((node) => {
      node.addEventListener("click", () => selectEvent(node.dataset.id));
      node.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          selectEvent(node.dataset.id);
        }
      });
    });
  }

  function renderSelected(e) {
    if (!e) {
      selectedEventEl.className = "selected-event";
      selectedEventEl.innerHTML = `<p class="honest-line">Nothing to select this week.</p>`;
      return;
    }
    const kind = rowKind(e);
    selectedEventEl.className = `selected-event ${kind}`;
    const stateLabel = kind === "social_cohort" ? "SOCIAL / COHORT" : kind === "skip" ? "SETTLED SKIP" : PROF_STATE_LABEL[e.verdict] || e.verdict.toUpperCase();

    let scoreBlock;
    if (kind === "social_cohort") {
      scoreBlock = `<p class="p-score-help">A shared plan, not a professional bet. It never receives a P and it never becomes a read-back.</p>`;
    } else {
      scoreBlock = `
        <div class="selected-score">
          <b>${pText(e)}</b>
          <span>P(contact ∪ build) — pre-event chance of a traceable contact or build, not a fun/prestige score.</span>
        </div>`;
    }

    const dupNote = e.duplicate_of_name
      ? `<p class="selected-note">Also listed as "${escapeHtml(e.duplicate_of_name)}" — same host and time. Treat as one decision, not two.</p>`
      : "";

    selectedEventEl.innerHTML = `
      <div class="selected-state">${stateLabel} · SELECTED</div>
      <h2>${escapeHtml(e.name)}</h2>
      <div class="selected-address">${escapeHtml(e.address)} · ${escapeHtml(fmtTime(e.start))}</div>
      <p class="selected-line">${escapeHtml(e.decision_line)}</p>
      ${scoreBlock}
      ${dupNote}
      <div class="selected-actions">
        ${e.url ? `<a href="${escapeAttr(e.url)}" target="_blank" rel="noopener">EVENT LISTING ↗</a>` : `<span class="selected-note">No listing URL recorded.</span>`}
      </div>`;
  }

  function inventoryRow(e) {
    const kind = rowKind(e);
    const label = kind === "social_cohort" ? "SOCIAL" : kind === "skip" ? "SKIP" : (PROF_STATE_LABEL[e.verdict] || e.verdict.toUpperCase());
    const scoreCell = kind === "social_cohort" ? "PLAN" : kind === "skip" ? "SETTLED" : pText(e);
    return `<article class="inventory-row ${kind}${e.id === selectedId ? " selected" : ""}">
      <span class="item-state">${label}</span>
      <button class="event-name" type="button" data-id="${e.id}">${escapeHtml(e.name)}</button>
      <span class="inventory-score">${scoreCell}</span>
      <p class="inventory-meta">${escapeHtml(fmtTime(e.start))} · ${escapeHtml(place(e))}</p>
      <p class="inventory-reason"><b>WHY</b><span>${escapeHtml(e.decision_line)}</span></p>
    </article>`;
  }

  function renderInventory(professional, social, skip) {
    const groups = [
      ["PROFESSIONAL DECISIONS", professional],
      ["SOCIAL / COHORT", social],
      ["SET ASIDE / SKIP", skip],
    ];
    inventoryStack.innerHTML = groups.map(([title, items]) => `
      <section class="inventory-group">
        <div class="inventory-label">${title}<b>${items.length} listing${items.length === 1 ? "" : "s"}</b></div>
        <div class="inventory-list">
          ${items.length ? items.map(inventoryRow).join("") : `<p class="inventory-empty">None this week.</p>`}
        </div>
      </section>`).join("");

    inventoryStack.querySelectorAll("button.event-name").forEach((btn) => {
      btn.addEventListener("click", () => selectEvent(btn.dataset.id));
    });
  }

  function renderSuppressed(week, suppressed, skip) {
    suppressedHeadline.textContent = `${skip.length} skipped this week · ${suppressed.length} suppressed this week`;
    const reasonCounts = {};
    skip.concat(suppressed).forEach((e) => {
      const r = e.primary_reason || "unspecified";
      reasonCounts[r] = (reasonCounts[r] || 0) + 1;
    });
    const parts = Object.entries(reasonCounts).map(([r, n]) => `${n} ${r}`).join(", ");
    suppressedDetail.textContent = parts
      ? `Reasons: ${parts}. Suppressed means unreachable and outside this week's top 3 — not silently absent.`
      : "Nothing set aside this week.";

    const drawerItems = skip.concat(suppressed).map((e) => `
      <div class="skip-row">
        <b>${e.verdict === "suppressed" ? "SUPPRESSED" : "SKIP"}</b>
        <div>${escapeHtml(e.name)}<br><span>${escapeHtml(e.decision_line)}</span></div>
      </div>`).join("");
    skipDrawer.innerHTML = drawerItems || `<div class="skip-row"><span>Nothing set aside this week.</span></div>`;
  }

  function renderCoverageLine(week, weekSuppressed) {
    const summary = DataAccess.getScoreSummary();
    const total = summary.suppressed_summary ? summary.suppressed_summary.total : 0;
    coverageLine.innerHTML = `${total} events suppressed as unreachable across all scored weeks (${weekSuppressed.length} this week). <button id="suppressedJump" type="button">Inspect the boundary</button>`;
    const jump = document.getElementById("suppressedJump");
    if (jump) {
      jump.addEventListener("click", () => {
        document.getElementById("suppressedBlock").scrollIntoView({ behavior: "smooth", block: "center" });
      });
    }
  }

  function selectEvent(id) {
    selectedId = id;
    renderSelected(DataAccess.getEvent(id));
    document.querySelectorAll(".inventory-row").forEach((row) => {
      const btn = row.querySelector("button.event-name");
      row.classList.toggle("selected", btn && btn.dataset.id === id);
    });
    document.querySelectorAll(".map-point").forEach((node) => {
      node.classList.toggle("selected", node.dataset.id === id);
    });
  }

  function escapeHtml(str) {
    return String(str == null ? "" : str).replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }
  function escapeAttr(str) { return escapeHtml(str); }
  function escapeXml(str) { return escapeHtml(str); }

  weekPrev.addEventListener("click", () => setWeek(currentWeekIndex - 1));
  weekNext.addEventListener("click", () => setWeek(currentWeekIndex + 1));
  weekSelect.addEventListener("change", (ev) => setWeek(Number(ev.target.value)));
  toggleSkips.addEventListener("click", () => {
    const open = skipDrawer.classList.toggle("open");
    toggleSkips.setAttribute("aria-expanded", String(open));
    toggleSkips.textContent = open ? "Hide set-aside events" : "Show set-aside events";
  });
  sourceButton.addEventListener("click", () => {
    const generatedAt = DataAccess.getGeneratedAt();
    const scoredAt = DataAccess.getSourceScoredAt();
    window.alert(
      "Data source: data/events.json + data/score_summary.json (local pipeline, not Supabase).\n" +
      `Pipeline last scored: ${scoredAt}\n` +
      `Frontend snapshot built: ${generatedAt}\n` +
      "Regenerate with: python3 app/build_data.py"
    );
  });

  populateWeekSelect();
  setWeek(currentWeekIndex);
})();
