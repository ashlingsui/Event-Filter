(() => {
  "use strict";

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

  const currentWeekKey = DataAccess.getCurrentWeekKey();
  let currentWeekIndex = Math.max(0, weeks.findIndex((w) => w.key === currentWeekKey));
  let selectedId = null;

  // 'schematic' (default, no external dependency) or 'google' (this account's own Maps API key,
  // see app/maps_key.example.js). Falls back to schematic if no key is configured or the Google
  // script fails to load — DESIGN_BRIEF.md's "no server, opens anywhere" baseline has to hold
  // even without a key or a network connection.
  let mapMode = "schematic";
  let mapModeNote = "";
  let googleMap = null;
  let googleOverlays = []; // {marker, event}
  let selectionHalo = null; // the one Circle overlay, drawn only around the selected marker
  let hoverTooltip = null;

  // A custom OverlayView instead of google.maps.InfoWindow — the default InfoWindow renders as
  // a white rounded card with its own chrome (close button, pointer tail) that Google doesn't
  // expose a clean styling API for, and it clashed badly with the dark theme. This is a plain
  // div positioned via the map's projection, styled entirely by our own CSS (.map-hover-tooltip).
  function makeHoverTooltip() {
    class HoverTooltip extends google.maps.OverlayView {
      onAdd() {
        this.div = document.createElement("div");
        this.div.className = "map-hover-tooltip";
        this.getPanes().floatPane.appendChild(this.div);
      }
      draw() {
        if (!this.position || !this.div) return;
        const point = this.getProjection().fromLatLngToDivPixel(this.position);
        if (point) {
          this.div.style.left = `${point.x}px`;
          this.div.style.top = `${point.y}px`;
        }
      }
      show(position, name, stateLabel) {
        this.position = position instanceof google.maps.LatLng ? position : new google.maps.LatLng(position.lat, position.lng);
        if (this.div) {
          this.div.innerHTML = `<b>${escapeHtml(name)}</b><small>${escapeHtml(stateLabel)}</small>`;
          this.div.style.display = "block";
        }
        this.draw();
      }
      hide() {
        if (this.div) this.div.style.display = "none";
      }
      onRemove() {
        if (this.div && this.div.parentNode) this.div.parentNode.removeChild(this.div);
        this.div = null;
      }
    }
    return new HoverTooltip();
  }

  const PROFESSIONAL_VERDICTS = new Set(["go", "part", "go_if", "wildcard"]);
  const PROF_STATE_LABEL = { go: "GO", part: "PART", go_if: "GO IF", wildcard: "WILDCARD" };
  // Skip's map color is deliberately lighter than the grey used for its text/badges elsewhere
  // (--faint #7e8782) — on a real, visually dark map style, a dark-grey dot on dark-grey tiles
  // has almost no contrast to register as a point at all, "quiet" or not. A light neutral grey
  // reads clearly against the dark basemap while still staying desaturated/calm, never a color.
  const KIND_HEX = { go: "#00b94f", part: "#ffc400", go_if: "#ffc400", wildcard: "#00b94f", social_cohort: "#189fd8", skip: "#cfd2cb" };

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

    // Bug fixed 2026-09-22: this used to also require `googleMap` truthy, but googleMap only
    // becomes truthy INSIDE renderMapGoogle (via ensureGoogleMap) — so the very first render
    // after Google's script loads always failed this check and silently fell back to the
    // schematic map, even though google.maps had loaded correctly. mapMode alone is the right
    // gate; renderMapGoogle creates the map lazily on its own first call.
    if (mapMode === "google") renderMapGoogle(events);
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
    caption.innerHTML = `<span><b>Radius scales with P.</b> Hover for the name, click for the decision.</span>`;
    eventMap.appendChild(caption);
    hoverTooltip = makeHoverTooltip();
    hoverTooltip.setMap(googleMap);
    return googleMap;
  }

  // Real campus venues repeat the exact same lat/lng (one building hosts many club events) —
  // confirmed live: 10 plottable events this week share one Haas coordinate, including every
  // social/cohort event. Without spreading them apart, every marker stacks on one pixel and only
  // whichever one happens to draw last is visible — which is why the blue social markers were
  // invisible, not filtered out. Same technique as the schematic SVG's clustering, done in real
  // lat/lng degrees instead of pixels so it still plots at an honest, traceable location.
  function spreadOverlappingPositions(events) {
    const clusters = [];
    events.forEach((e) => {
      const hit = clusters.find((c) => Math.abs(c.lat - e.lat) < 0.0002 && Math.abs(c.lng - e.lng) < 0.0002);
      if (hit) hit.items.push(e);
      else clusters.push({ lat: e.lat, lng: e.lng, items: [e] });
    });
    const out = [];
    clusters.forEach((c) => {
      const n = c.items.length;
      // Markers are now small fixed-pixel dots, not meter-radius circles (see renderMapGoogle),
      // so a tight ring is enough to separate them — a wide spread just made a crowded building
      // look like it was scattered across three neighborhoods, which was its own kind of wrong.
      const ringM = n > 1 ? Math.min(85, 26 + n * 8) : 0;
      const latDegPerM = 1 / 111320;
      const lngDegPerM = 1 / (111320 * Math.cos((c.lat * Math.PI) / 180));
      c.items.forEach((e, i) => {
        const angle = (2 * Math.PI * i) / n - Math.PI / 2;
        const lat = n > 1 ? c.lat + ringM * Math.cos(angle) * latDegPerM : c.lat;
        const lng = n > 1 ? c.lng + ringM * Math.sin(angle) * lngDegPerM : c.lng;
        out.push({ event: e, lat, lng });
      });
    });
    return out;
  }

  function renderMapGoogle(weekEvents) {
    ensureGoogleMap();
    googleOverlays.forEach(({ marker }) => marker.setMap(null));
    googleOverlays = [];
    if (selectionHalo) { selectionHalo.setMap(null); selectionHalo = null; }

    const plottable = plottableEvents(weekEvents);
    if (!plottable.length) {
      googleMap.setCenter({ lat: (bounds.lat_min + bounds.lat_max) / 2, lng: (bounds.lng_min + bounds.lng_max) / 2 });
      googleMap.setZoom(11);
      return;
    }

    // Real venues repeating the same building coordinate (confirmed live: up to 10 events on
    // one Haas geocode) made full meter-radius Circle overlays overlap into an unreadable blob
    // the moment more than 2-3 shared a spot — bigger P meant a bigger circle meant MORE overlap,
    // exactly backwards. Switched to compact icon markers whose SIZE IS IN FIXED SCREEN PIXELS,
    // not real-world meters: P still drives size for professional events, but a crowded building
    // now reads as a small tidy cluster of dots instead of stacked translucent haze. The one
    // exception is the selected event, which gets a single real Circle "halo" — there's only
    // ever one of those on screen at a time, so it can't crowd anything.
    const llBounds = new google.maps.LatLngBounds();
    spreadOverlappingPositions(plottable).forEach(({ event: e, lat, lng }) => {
      const kind = rowKind(e);
      let scale = 5;
      if (kind === "social_cohort") scale = 7;
      else if (kind === "skip") scale = 4;
      else scale = 5 + 9 * (e.predicted_p || 0); // ~5-13.5px, P drives it without touching real distance
      const color = KIND_HEX[kind] || "#7e8782";
      const position = { lat, lng };
      const isSelected = e.id === selectedId;

      const marker = new google.maps.Marker({
        map: googleMap,
        position,
        title: `${e.name} — ${kind}`,
        zIndex: isSelected ? 999 : undefined,
        icon: {
          path: google.maps.SymbolPath.CIRCLE,
          scale,
          fillColor: color,
          fillOpacity: 1,
          strokeColor: isSelected ? "#f4f2ea" : "#0b0d0d",
          strokeWeight: isSelected ? 2 : 1,
        },
      });
      const onSelect = () => selectEvent(e.id);
      const stateLabel = kind === "social_cohort" ? "Social / cohort" : kind === "skip" ? "Skip" : (PROF_STATE_LABEL[e.verdict] || e.verdict);
      marker.addListener("click", onSelect);
      marker.addListener("mouseover", () => hoverTooltip.show(position, e.name, stateLabel));
      marker.addListener("mouseout", () => hoverTooltip.hide());
      googleOverlays.push({ marker, event: e });
      llBounds.extend(position);

      if (isSelected) {
        selectionHalo = new google.maps.Circle({
          map: googleMap,
          center: position,
          radius: 90,
          strokeColor: color,
          strokeOpacity: 0.9,
          strokeWeight: 2,
          fillColor: color,
          fillOpacity: 0.15,
          clickable: false,
        });
      }
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
      // score/verdicts.py scores this row like any other event — it has no "social" concept.
      // The real P exists; show it, de-emphasized, rather than falsely claim there isn't one.
      scoreBlock = `
        <div class="selected-score muted-score">
          <b>${pText(e)}</b>
          <span>PIPELINE'S P</span>
        </div>
        <p class="p-score-help">Shown for transparency, not why this is on your plan — the pipeline scores every row the same way, and this one just isn't a professional bet. It never becomes a read-back.</p>`;
    } else {
      scoreBlock = `
        <div class="selected-score">
          <b>${pText(e)}</b>
          <span>P(contact ∪ build)</span>
        </div>
        <p class="p-score-help">Pre-event chance of a traceable contact or build, not a fun/prestige score.</p>`;
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
      </div>
      ${moreDetailBlock(e, kind)}`;
  }

  // A compact stand-in for the full event-detail page (step 2, not built yet). Board-scoped:
  // more of the facts already in the data, not the Want/Pass workflow or context-strip inputs,
  // which belong to that step. Native <details> keeps it keyboard/screen-reader accessible with
  // no extra JS.
  function moreDetailBlock(e, kind) {
    const rows = [
      ["Host", e.host_display || "Not listed"],
      ["Format", e.format || "Unknown"],
      ["Source", e.source || "Unknown"],
      ["RSVP state", e.rsvp_state || "none"],
    ];
    if (kind !== "social_cohort") {
      rows.push(["Cost blocks", e.cost_blocks != null ? String(e.cost_blocks) : "Unknown"]);
      rows.push(["BART walk", e.bart_walk_min != null ? `${e.bart_walk_min} min` : "Unknown"]);
      if (e.why_raw) rows.push(["Score factors (raw)", e.why_raw]);
    }
    return `
      <details class="more-detail">
        <summary>More detail</summary>
        <div class="detail-facts">
          ${rows.map(([k, v]) => `<div><b>${escapeHtml(k)}</b><span>${escapeHtml(v)}</span></div>`).join("")}
        </div>
      </details>`;
  }

  function inventoryRow(e) {
    const kind = rowKind(e);
    const label = kind === "social_cohort" ? "SOCIAL" : kind === "skip" ? "SKIP" : (PROF_STATE_LABEL[e.verdict] || e.verdict.toUpperCase());
    const scoreCell = kind === "social_cohort" ? `${pText(e)} · plan` : kind === "skip" ? "SETTLED" : pText(e);
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
    // California-only, recomputed in app/build_data.py — score_summary.json's raw total (59)
    // still includes the out-of-state/international rows this board excludes entirely, so it
    // no longer matches what's actually reachable from this page.
    const total = DataAccess.getCaliforniaSuppressedTotal();
    coverageLine.innerHTML = `${total} California events suppressed as unreachable across all scored weeks (${weekSuppressed.length} this week). <button id="suppressedJump" type="button">Inspect the boundary</button>`;
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
    if (mapMode === "google") {
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
