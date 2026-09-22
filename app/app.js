(() => {
  "use strict";

  const TODAY_WEEK_KEY = "2026-W39"; // matches data/score_summary.json scored_at (2026-09-21)

  const weeks = DataAccess.getWeeks();
  const bounds = DataAccess.getMapBounds();
  const referenceCities = DataAccess.getMapReferenceCities() || [];
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

  // 'schematic' (default, no external dependency) or 'google' (this account's own Maps API key,
  // see app/maps_key.example.js). Falls back to schematic if no key is configured or the Google
  // script fails to load — DESIGN_BRIEF.md's "no server, opens anywhere" baseline has to hold
  // even without a key or a network connection.
  let mapMode = "schematic";
  let mapModeNote = "";
  let googleMap = null;
  let googleOverlays = []; // {circle, marker}

  const PROFESSIONAL_VERDICTS = new Set(["go", "part", "go_if", "wildcard"]);
  const PROF_STATE_LABEL = { go: "GO", part: "PART", go_if: "GO IF", wildcard: "WILDCARD" };
  const KIND_HEX = { go: "#00b94f", part: "#ffc400", go_if: "#ffc400", wildcard: "#00b94f", social_cohort: "#189fd8", skip: "#7e8782" };

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

  function plottableEvents(weekEvents) {
    return weekEvents.filter((e) => e.map_bucket === "bay_area" && e.map_xy && e.verdict !== "suppressed" && e.verdict !== "blocked");
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

    if (mapMode === "google" && googleMap) renderMapGoogle(events);
    else renderMapSchematic(events);
    renderSelected(selectedId ? DataAccess.getEvent(selectedId) : null);
    renderInventory(professional, social, skip);
    renderSuppressed(week, suppressed);
    renderCoverageLine(week, suppressed);
  }

  // ---------- Schematic fallback map (no external dependency, no network required) ----------

  function renderMapSchematic(weekEvents) {
    const plottable = plottableEvents(weekEvents);
    const backdrop = schematicBackdrop();

    if (!plottable.length) {
      eventMap.innerHTML = `${mapModeNoteHtml()}<div class="map-empty">No plottable Bay Area events this week. Every listing is still in the inventory below.</div>`;
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
      ${mapModeNoteHtml()}
      <svg viewBox="0 0 600 480" role="group" aria-label="Schematic Bay Area event map — not to scale">
        ${backdrop}
        ${markers}
      </svg>
      <div class="map-legend">
        <span><i></i>Go / Part</span>
        <span><i class="part"></i>Go if / conditional</span>
        <span><i class="social"></i>Social / cohort</span>
        <span><i class="skip"></i>Skip</span>
      </div>
      <div class="map-caption">
        <span><b>Radius scales with P.</b> Hover or select a dot for its name; a ring of dots shares one real address. Schematic, not to scale.</span>
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

  function mapModeNoteHtml() {
    return mapModeNote ? `<div class="map-note-banner">${escapeHtml(mapModeNote)}</div>` : "";
  }

  // A schematic (not-to-scale) Bay-Area backdrop: water down the middle, land on both sides,
  // closing at the south where the peninsula and East Bay actually connect. Built once from
  // real reference-city coordinates (app/build_data.py projects them through the same lat/lng
  // formula as event markers) rather than hand-fit to any particular week's events, so it stays
  // correct as the selected week changes.
  function schematicBackdrop() {
    const cityLabels = referenceCities.filter((c) => c.xy).map((c) => (
      `<text class="map-city" x="${c.xy[0] + 8}" y="${c.xy[1] + 3}">${escapeXml(c.name.toUpperCase())}</text>
       <circle class="map-city-dot" cx="${c.xy[0]}" cy="${c.xy[1]}" r="2.5"></circle>`
    )).join("");

    return `
      <rect class="map-water" x="0" y="0" width="600" height="480"></rect>
      <path class="map-land" d="M0 0H150C130 60 150 120 118 190C95 250 100 330 70 410C55 445 30 465 0 480H0Z"></path>
      <path class="map-land" d="M260 0H600V480H320C300 400 270 340 240 280C205 210 215 150 245 95C265 58 262 25 260 0Z"></path>
      <path class="map-bart-line" d="M40 470C90 400 110 330 100 250C95 190 130 140 175 95C210 60 230 30 245 5"></path>
      <text class="map-note" x="16" y="22">BAY AREA · SCHEMATIC, NOT TO SCALE</text>
      ${cityLabels}`;
  }

  // ---------- Google Maps (this session's own API key, see app/maps_key.example.js) ----------

  function loadGoogleMaps(apiKey, onReady, onError) {
    if (window.google && window.google.maps) {
      onReady();
      return;
    }
    window.__onGoogleMapsReady = onReady;
    const script = document.createElement("script");
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey)}&callback=__onGoogleMapsReady&loading=async`;
    script.async = true;
    script.onerror = onError;
    document.head.appendChild(script);
  }

  const DARK_MAP_STYLE = [
    { elementType: "geometry", stylers: [{ color: "#121515" }] },
    { elementType: "labels.text.fill", stylers: [{ color: "#a9aaa6" }] },
    { elementType: "labels.text.stroke", stylers: [{ color: "#0b0d0d" }] },
    { featureType: "water", elementType: "geometry", stylers: [{ color: "#0a1011" }] },
    { featureType: "landscape", elementType: "geometry", stylers: [{ color: "#171b1a" }] },
    { featureType: "road", elementType: "geometry", stylers: [{ color: "#2a302e" }] },
    { featureType: "poi", stylers: [{ visibility: "off" }] },
    { featureType: "transit", elementType: "geometry", stylers: [{ color: "#189fd8" }, { visibility: "simplified" }] },
    { featureType: "administrative", elementType: "geometry", stylers: [{ color: "#2a302e" }] },
  ];

  function ensureGoogleMap() {
    if (googleMap) return googleMap;
    const canvas = document.createElement("div");
    canvas.id = "googleMapCanvas";
    canvas.style.cssText = "width:100%;height:500px;min-height:500px";
    eventMap.innerHTML = "";
    eventMap.appendChild(canvas);
    googleMap = new google.maps.Map(canvas, {
      center: { lat: (bounds.lat_min + bounds.lat_max) / 2, lng: (bounds.lng_min + bounds.lng_max) / 2 },
      zoom: 12,
      styles: DARK_MAP_STYLE,
      disableDefaultUI: true,
      zoomControl: true,
      streetViewControl: false,
      mapTypeControl: false,
    });
    const legend = document.createElement("div");
    legend.className = "map-legend";
    legend.innerHTML = `<span><i></i>Go / Part</span><span><i class="part"></i>Go if / conditional</span><span><i class="social"></i>Social / cohort</span><span><i class="skip"></i>Skip</span>`;
    eventMap.appendChild(legend);
    const caption = document.createElement("div");
    caption.className = "map-caption";
    caption.innerHTML = `<span><b>Radius scales with P.</b> Click a circle for its name and decision.</span>`;
    eventMap.appendChild(caption);
    return googleMap;
  }

  function renderMapGoogle(weekEvents) {
    ensureGoogleMap();
    googleOverlays.forEach(({ circle, marker }) => {
      circle.setMap(null);
      marker.setMap(null);
    });
    googleOverlays = [];

    const plottable = plottableEvents(weekEvents);
    if (!plottable.length) {
      googleMap.setCenter({ lat: (bounds.lat_min + bounds.lat_max) / 2, lng: (bounds.lng_min + bounds.lng_max) / 2 });
      googleMap.setZoom(11);
      return;
    }

    const llBounds = new google.maps.LatLngBounds();
    plottable.forEach((e) => {
      const kind = rowKind(e);
      let radiusM = 120;
      if (kind === "social_cohort") radiusM = 180;
      else if (kind === "skip") radiusM = 90;
      else radiusM = 120 + 700 * (e.predicted_p || 0);
      const color = KIND_HEX[kind] || "#7e8782";
      const position = { lat: e.lat, lng: e.lng };

      const circle = new google.maps.Circle({
        map: googleMap,
        center: position,
        radius: radiusM,
        strokeColor: color,
        strokeWeight: e.id === selectedId ? 3 : 2,
        fillColor: color,
        fillOpacity: 0.22,
        clickable: true,
      });
      const marker = new google.maps.Marker({
        map: googleMap,
        position,
        title: `${e.name} — ${kind}`,
        icon: {
          path: google.maps.SymbolPath.CIRCLE,
          scale: 4,
          fillColor: color,
          fillOpacity: 1,
          strokeColor: "#0b0d0d",
          strokeWeight: 1,
        },
      });
      const onSelect = () => selectEvent(e.id);
      circle.addListener("click", onSelect);
      marker.addListener("click", onSelect);
      googleOverlays.push({ circle, marker });
      llBounds.extend(position);
    });

    if (plottable.length === 1) {
      googleMap.setCenter(llBounds.getCenter());
      googleMap.setZoom(14);
    } else {
      googleMap.fitBounds(llBounds, 48);
    }
  }

  // ---------- Shared rendering (selected panel, inventory, suppressed summary) ----------

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

  // Suppressed events ONLY — skip events are already fully enumerated above in the
  // "SET ASIDE / SKIP" inventory group with their own reason line, so they don't belong here
  // too. Suppressed rows are deliberately kept OUT of the main inventory (SPEC.md: "~60
  // events/week are suppressed... shown as a single honest line, never as 60 rows"), so this
  // block — count + reason breakdown + an optional per-row drawer — is their only home.
  function renderSuppressed(week, suppressed) {
    suppressedHeadline.textContent = `${suppressed.length} suppressed this week`;
    const reasonCounts = {};
    suppressed.forEach((e) => {
      const r = e.primary_reason || "unspecified";
      reasonCounts[r] = (reasonCounts[r] || 0) + 1;
    });
    const parts = Object.entries(reasonCounts).map(([r, n]) => `${n} ${r}`).join(", ");
    suppressedDetail.textContent = parts
      ? `Reasons: ${parts}. Suppressed means unreachable and outside this week's top 3 — not silently absent.`
      : "Nothing suppressed this week.";

    const drawerItems = suppressed.map((e) => `
      <div class="skip-row">
        <b>SUPPRESSED</b>
        <div>${escapeHtml(e.name)}<br><span>${escapeHtml(e.decision_line)}</span></div>
      </div>`).join("");
    skipDrawer.innerHTML = drawerItems || `<div class="skip-row"><span>Nothing suppressed this week.</span></div>`;
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
    if (mapMode === "google" && googleMap) {
      renderMapGoogle(DataAccess.getEventsForWeek(currentWeek().key));
    } else {
      document.querySelectorAll(".map-point").forEach((node) => {
        node.classList.toggle("selected", node.dataset.id === id);
      });
      // Re-render so the newly-selected marker gets its label in the schematic view.
      renderMapSchematic(DataAccess.getEventsForWeek(currentWeek().key));
    }
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
    toggleSkips.textContent = open ? "Hide suppressed events" : "Show suppressed events";
  });
  sourceButton.addEventListener("click", () => {
    const generatedAt = DataAccess.getGeneratedAt();
    const scoredAt = DataAccess.getSourceScoredAt();
    window.alert(
      "Data source: data/events.json + data/score_summary.json (local pipeline, not Supabase).\n" +
      `Pipeline last scored: ${scoredAt}\n` +
      `Frontend snapshot built: ${generatedAt}\n` +
      `Map: ${mapMode === "google" ? "Google Maps (app/maps_key.local.js)" : "schematic fallback (no key configured, or Google failed to load)"}\n` +
      "Regenerate with: python3 app/build_data.py"
    );
  });

  function boot() {
    populateWeekSelect();
    const key = window.GOOGLE_MAPS_API_KEY;
    if (key) {
      loadGoogleMaps(
        key,
        () => { mapMode = "google"; setWeek(currentWeekIndex); },
        () => { mapMode = "schematic"; mapModeNote = "Google Maps failed to load — showing the schematic fallback."; setWeek(currentWeekIndex); }
      );
    } else {
      setWeek(currentWeekIndex);
    }
  }

  boot();
})();
