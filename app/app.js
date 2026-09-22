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

  const detailOverlay = document.getElementById("detailOverlay");
  const detailSheet = document.getElementById("detailSheet");
  const closeDetailBtn = document.getElementById("closeDetail");
  const wantButton = document.getElementById("wantButton");
  const passButton = document.getElementById("passButton");
  const contextSection = document.getElementById("context");
  const toastEl = document.getElementById("toast");

  const currentWeekKey = DataAccess.getCurrentWeekKey();
  let currentWeekIndex = Math.max(0, weeks.findIndex((w) => w.key === currentWeekKey));
  let selectedId = null;
  let detailEventId = null;
  let detailContext = { ride: null, companion: null, hook: null };
  let lastFocusBeforeDetail = null;
  let toastTimer = null;

  // 'schematic' (default, no external dependency) or 'google' (this account's own Maps API key,
  // see app/maps_key.example.js). Falls back to schematic if no key is configured or the Google
  // script fails to load — DESIGN_BRIEF.md's "no server, opens anywhere" baseline has to hold
  // even without a key or a network connection.
  let mapMode = "schematic";
  let mapModeNote = "";
  let googleMap = null;
  let googleOverlays = []; // {marker, event}
  let clusterBadgeOverlays = []; // one per real-world cluster with 2+ events
  let selectionHalo = null; // one reusable DOM overlay, shown around whichever marker is selected
  let standingHaloOverlays = []; // one per GO/GO_IF event — these pulse always, not just on selection
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

  // The "halo" around the selected marker, brought back as a DOM overlay instead of a static
  // google.maps.Circle so it can carry a real CSS pulse animation — two staggered expanding
  // rings plus a solid glowing core, so it reads clearly even at a zoom level where the map
  // itself isn't moving and the marker alone could get lost in a cluster. Respects
  // prefers-reduced-motion (DESIGN_BRIEF.md baseline requirement) by falling back to a static
  // ring rather than disabling the indicator entirely.
  function makeHalo() {
    class Halo extends google.maps.OverlayView {
      // setMap() schedules onAdd() asynchronously — it does NOT run synchronously before the
      // next line executes. The very first renderMapGoogle() call runs show() immediately after
      // ensureGoogleMap()'s setMap(), so this.div was reliably still null at that point: the
      // style-setting silently no-op'd, while this.position (set unconditionally) got picked up
      // later by Maps' automatic draw() calls during fitBounds — which is why the halo div was
      // positioned correctly but never actually visible. Desired state now lives on the instance
      // (_visible/_color) independent of whether the div exists yet, and onAdd re-applies it.
      onAdd() {
        this.div = document.createElement("div");
        this.div.className = "map-selection-halo";
        this.div.innerHTML = `<div class="ring"></div><div class="ring ring-2"></div><div class="core"></div>`;
        this.getPanes().floatPane.appendChild(this.div);
        this._applyState();
      }
      draw() {
        if (!this.position || !this.div) return;
        const point = this.getProjection().fromLatLngToDivPixel(this.position);
        if (point) {
          this.div.style.left = `${point.x}px`;
          this.div.style.top = `${point.y}px`;
        }
      }
      _applyState() {
        if (!this.div) return;
        this.div.style.display = this._visible ? "block" : "none";
        if (this._visible && this._color) {
          this.div.style.color = this._color;
          this.div.querySelectorAll(".ring").forEach((r) => { r.style.background = this._color; });
        }
      }
      show(position, colorHex) {
        this.position = position instanceof google.maps.LatLng ? position : new google.maps.LatLng(position.lat, position.lng);
        this._visible = true;
        this._color = colorHex;
        this._applyState();
        this.draw();
      }
      hide() {
        this._visible = false;
        this._applyState();
      }
      onRemove() {
        if (this.div && this.div.parentNode) this.div.parentNode.removeChild(this.div);
        this.div = null;
      }
    }
    return new Halo();
  }

  // A small persistent (not hover-only) badge at a real cluster's true center, tallying what's
  // there by kind — "so many events this week, here's what's under that one dot when you're
  // zoomed out." Unlike the hover tooltip and halo, one of these exists per cluster, rebuilt
  // every render since composition changes week to week.
  function makeClusterBadge(position, countsByKind) {
    class ClusterBadge extends google.maps.OverlayView {
      onAdd() {
        this.div = document.createElement("div");
        this.div.className = "map-cluster-badge";
        this.div.innerHTML = countsByKind.map(([kind, n]) => (
          `<span><i style="background:${KIND_HEX[kind] || "#7e8782"}"></i>${n}</span>`
        )).join("");
        this.div.style.display = "block";
        this.getPanes().floatPane.appendChild(this.div);
      }
      draw() {
        if (!this.div) return;
        const point = this.getProjection().fromLatLngToDivPixel(this.position);
        if (point) {
          this.div.style.left = `${point.x}px`;
          this.div.style.top = `${point.y}px`;
        }
      }
      onRemove() {
        if (this.div && this.div.parentNode) this.div.parentNode.removeChild(this.div);
        this.div = null;
      }
    }
    const overlay = new ClusterBadge();
    overlay.position = position instanceof google.maps.LatLng ? position : new google.maps.LatLng(position.lat, position.lng);
    overlay.setMap(googleMap);
    return overlay;
  }

  const PROFESSIONAL_VERDICTS = new Set(["go", "part", "go_if", "wildcard"]);
  const PROF_STATE_LABEL = { go: "GO", part: "PART", go_if: "GO IF", wildcard: "WILDCARD" };
  // Skip's map color is deliberately lighter than the grey used for its text/badges elsewhere
  // (--faint #7e8782) — on a real, visually dark map style, a dark-grey dot on dark-grey tiles
  // has almost no contrast to register as a point at all, "quiet" or not. A light neutral grey
  // reads clearly against the dark basemap while still staying desaturated/calm, never a color.
  const KIND_HEX = { go: "#00b94f", part: "#ffc400", go_if: "#ffc400", wildcard: "#00b94f", social_cohort: "#189fd8", skip: "#cfd2cb" };

  const DETAIL_GLOW = {
    go: "rgba(0,185,79,.25)", wildcard: "rgba(0,185,79,.25)",
    part: "rgba(255,196,0,.25)", go_if: "rgba(255,196,0,.25)",
    social_cohort: "rgba(24,159,216,.25)", skip: "rgba(130,140,135,.16)",
  };

  // The handoff's four decision-tier lines (Set B), reserved for this exact banner per the
  // 2026-09-21 conflict resolution — SPEC/DESIGN_BRIEF's four principle lines (Set A) stay on
  // the board headline and Learning/About material instead. "What decision does this event
  // deserve?" is the standing kicker above the banner (see index.html); these three answer it.
  function principleLineFor(kind, verdict) {
    if (kind === "social_cohort") return "A shared plan, not a professional bet.";
    if (verdict === "go" || verdict === "go_if" || verdict === "wildcard") return "Strong room + real access. Go with intent.";
    if (verdict === "part") return "Interesting, but the outcome is not clear enough.";
    return "Not everything good belongs on your calendar."; // skip, suppressed, blocked
  }

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
        <span><i></i>Go</span>
        <span><i class="part"></i>Part / go if</span>
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
    legend.innerHTML = `<span><i></i>Go</span><span><i class="part"></i>Part / go if</span><span><i class="social"></i>Social / cohort</span><span><i class="skip"></i>Skip</span>`;
    eventMap.appendChild(legend);
    const caption = document.createElement("div");
    caption.className = "map-caption";
    caption.innerHTML = `<span><b>Dot size scales with P.</b> Go, part, and go-if pulse on their own — every professional decision made this week. Hover for a name, click for the decision. A labeled tag means several events share one address.</span>`;
    eventMap.appendChild(caption);
    hoverTooltip = makeHoverTooltip();
    hoverTooltip.setMap(googleMap);
    selectionHalo = makeHalo();
    selectionHalo.setMap(googleMap);
    return googleMap;
  }

  // Real campus venues repeat the exact same lat/lng (one building hosts many club events) —
  // confirmed live: 10 plottable events this week share one Haas coordinate, including every
  // social/cohort event. Without spreading them apart, every marker stacks on one pixel and only
  // whichever one happens to draw last is visible — which is why the blue social markers were
  // invisible, not filtered out. Same technique as the schematic SVG's clustering, done in real
  // lat/lng degrees instead of pixels so it still plots at an honest, traceable location.
  function groupByProximity(events) {
    const clusters = [];
    events.forEach((e) => {
      const hit = clusters.find((c) => Math.abs(c.lat - e.lat) < 0.0002 && Math.abs(c.lng - e.lng) < 0.0002);
      if (hit) hit.items.push(e);
      else clusters.push({ lat: e.lat, lng: e.lng, items: [e] });
    });
    return clusters;
  }

  // Returns {positioned, clusters}: positioned is every event with its spread-apart lat/lng
  // (small ring around clusters of 2+, since markers are now compact fixed-pixel dots — a wide
  // spread just made a crowded building look scattered across three neighborhoods); clusters is
  // the raw grouping, used separately to render a count-by-kind badge at each real cluster's
  // true center once zoomed out far enough that even the spread ring collapses back to one dot.
  function spreadOverlappingPositions(events) {
    const clusters = groupByProximity(events);
    const positioned = [];
    clusters.forEach((c) => {
      const n = c.items.length;
      const ringM = n > 1 ? Math.min(85, 26 + n * 8) : 0;
      const latDegPerM = 1 / 111320;
      const lngDegPerM = 1 / (111320 * Math.cos((c.lat * Math.PI) / 180));
      c.items.forEach((e, i) => {
        const angle = (2 * Math.PI * i) / n - Math.PI / 2;
        const lat = n > 1 ? c.lat + ringM * Math.cos(angle) * latDegPerM : c.lat;
        const lng = n > 1 ? c.lng + ringM * Math.sin(angle) * lngDegPerM : c.lng;
        positioned.push({ event: e, lat, lng });
      });
    });
    return { positioned, clusters };
  }

  function renderMapGoogle(weekEvents) {
    ensureGoogleMap();
    googleOverlays.forEach(({ marker }) => marker.setMap(null));
    googleOverlays = [];
    clusterBadgeOverlays.forEach((b) => b.setMap(null));
    clusterBadgeOverlays = [];
    standingHaloOverlays.forEach((h) => h.setMap(null));
    standingHaloOverlays = [];
    selectionHalo.hide();
    let selectedShown = false;

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
    // now reads as a small tidy cluster of dots instead of stacked translucent haze.
    const { positioned, clusters } = spreadOverlappingPositions(plottable);
    const llBounds = new google.maps.LatLngBounds();
    positioned.forEach(({ event: e, lat, lng }) => {
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

      // GO, PART, and GO_IF all pulse always, not just when selected — they're every
      // professional decision the board actually made this week, and the point is that they
      // should stand out on their own when scanning a busy map, not only after you've already
      // clicked something (Ashling's framing: "so many events going on... the highlighted ones
      // are the ones that you picked out"). Only SKIP and SOCIAL/COHORT stay click-only.
      const isPick = e.verdict === "go" || e.verdict === "go_if" || e.verdict === "part";
      if (isPick) {
        const halo = makeHalo();
        halo.setMap(googleMap);
        halo.show(position, color);
        standingHaloOverlays.push(halo);
      }
      if (isSelected && !isPick) {
        selectionHalo.show(position, color);
        selectedShown = true;
      }
    });
    if (!selectedShown) selectionHalo.hide();

    // Cluster badges: "6 blue, 4 white, 1 yellow" at a glance, at the cluster's TRUE (unspread)
    // coordinate — zoomed out far enough, even the small spread ring collapses back into what
    // looks like one dot, and this is what tells you it isn't.
    clusters.filter((c) => c.items.length > 1).forEach((c) => {
      const counts = {};
      c.items.forEach((e) => { const k = rowKind(e); counts[k] = (counts[k] || 0) + 1; });
      const order = ["go", "part", "go_if", "wildcard", "social_cohort", "skip"];
      const countsByKind = order.filter((k) => counts[k]).map((k) => [k, counts[k]]);
      clusterBadgeOverlays.push(makeClusterBadge({ lat: c.lat, lng: c.lng }, countsByKind));
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
      <h2><button type="button" class="selected-title-link" data-open-detail="${e.id}">${escapeHtml(e.name)}</button></h2>
      <div class="selected-address">${escapeHtml(e.address)} · ${escapeHtml(fmtTime(e.start))}</div>
      <p class="selected-line">${escapeHtml(e.decision_line)}</p>
      ${scoreBlock}
      ${dupNote}
      <div class="selected-actions">
        ${e.url ? `<a href="${escapeAttr(e.url)}" target="_blank" rel="noopener">EVENT LISTING ↗</a>` : `<span class="selected-note">No listing URL recorded.</span>`}
      </div>`;
    // Same pattern as the board title/detail title elsewhere: the title itself is the primary
    // link, here into this event's detail page — not a separate "open details" button.
    const openBtn = selectedEventEl.querySelector("[data-open-detail]");
    if (openBtn) openBtn.addEventListener("click", () => openDetail(e.id));
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

    // Clicking an event's title on the board goes straight to its detail page (Ashling's call,
    // 2026-09-22) — select it first so the side panel/map stay in sync once the overlay closes.
    inventoryStack.querySelectorAll("button.event-name").forEach((btn) => {
      btn.addEventListener("click", () => {
        selectEvent(btn.dataset.id);
        openDetail(btn.dataset.id);
      });
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

  // ---------- Event detail overlay (step 2) ----------

  function showToast(msg) {
    toastEl.textContent = msg;
    toastEl.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toastEl.classList.remove("show"), 3400);
  }

  function renderWhyGrid(e, kind) {
    const grid = document.getElementById("whyGrid");
    if (kind === "social_cohort") {
      grid.innerHTML = "";
      return;
    }
    const participantTxt = e.participant === true ? "Participant" : e.participant === false ? "Spectator" : "Unknown";
    const roomTxt = {
      none: "No target-company density", wrong_ladder: "VC/founder room, not a target-employer room",
      some: "Some target-company density", high: "High target-company density",
    }[e.target_proximity] || "Unknown";
    const hookTxt = { none: "None", topic: "Topic hook (×1.20 value)" }[e.prior_hook] || "Unknown";
    const companionsTxt = e.companions && e.companions.length ? e.companions.join(", ") : "None recorded";
    const cohortTxt = { none: "Low", some: "Some (×0.85 value)", high: "High (×0.60 value)" }[e.cohort_saturation] || "Unknown";
    const travelBits = [`${e.cost_blocks != null ? e.cost_blocks : "—"} cost blocks`];
    if (e.bart_walk_min != null) travelBits.push(`${e.bart_walk_min} min BART walk`);
    if (e.reachable === false) travelBits.push("not BART-reachable");
    const rows = [
      ["Format", `${e.format || "Unknown"} · ${participantTxt}`],
      ["Room", roomTxt],
      ["Prior hook", hookTxt],
      ["Companions", companionsTxt],
      ["Cohort saturation", cohortTxt],
      ["Travel", travelBits.join(" · ")],
    ];
    grid.innerHTML = rows.map(([k, v]) => `<div><b>${escapeHtml(k)}</b><span>${escapeHtml(v)}</span></div>`).join("");
  }

  function renderDetailFacts(e) {
    const rows = [
      ["Address", e.address],
      ["Host", e.host_display || "Not listed"],
      ["RSVP state", e.rsvp_state || "none"],
      ["Data status", "Pre-event score and listing provenance retained"],
    ];
    if (e.duplicate_of_name) rows.push(["Also listed as", `${e.duplicate_of_name} — same host and time`]);
    if (e.recurring) rows.push(["Recurring", e.next_occurrence ? `Next: ${fmtTime(e.next_occurrence)}` : "Yes"]);
    if (e.speakers && e.speakers.length) {
      rows.push(["Speakers", e.speakers.map((s) => (typeof s === "string" ? s : s.name)).filter(Boolean).join(", ") || "Listed, names pending"]);
    }
    document.getElementById("detailFacts").innerHTML = rows.map(([k, v]) => `<div><b>${escapeHtml(k)}</b><span>${escapeHtml(v)}</span></div>`).join("");
  }

  function renderProvenance(e) {
    const scoredAt = DataAccess.getSourceScoredAt();
    const listingLink = e.url
      ? `<a href="${escapeAttr(e.url)}" target="_blank" rel="noopener">Open event listing ↗</a>`
      : "No listing URL recorded.";
    document.getElementById("provenance").innerHTML =
      `<b>PROVENANCE</b>Source: ${escapeHtml(e.source || "unknown")}. Score facts were recorded before the decision — pipeline last scored ${escapeHtml(scoredAt || "unknown")}. ${listingLink}`;
  }

  function updateToggleUI() {
    contextSection.querySelectorAll(".toggle").forEach((t) => {
      const field = t.dataset.field;
      t.querySelectorAll("button").forEach((b) => {
        const val = b.dataset.value === "yes";
        b.classList.toggle("selected", detailContext[field] === val);
      });
    });
  }

  function updateRecomputeDisplay(e, kind) {
    const rec = document.getElementById("recompute");
    const probEl = document.getElementById("detailProbability");
    const anyAnswered = detailContext.ride !== null || detailContext.companion !== null || detailContext.hook !== null;
    if (kind === "social_cohort") {
      rec.classList.remove("show");
      probEl.textContent = `${pText(e)} P — pipeline's number, not why this is on your plan`;
      return;
    }
    if (!anyAnswered) {
      rec.classList.remove("show");
      probEl.textContent = `${pText(e)} P(contact ∪ build)`;
      return;
    }
    const newP = Scoring.recomputeP(e, detailContext);
    const newCost = Scoring.recomputeCostBlocks(e, detailContext);
    const oldP = typeof e.predicted_p === "number" ? e.predicted_p : 0;
    const oldCost = typeof e.cost_blocks === "number" ? e.cost_blocks : 0;
    const changed = Math.abs(newP - oldP) > 0.004 || Math.abs(newCost - oldCost) > 0.004;
    rec.classList.add("show");
    rec.textContent = changed
      ? `Recomputed: P ${oldP.toFixed(2)} → ${newP.toFixed(2)}, cost ${oldCost} → ${newCost} blocks. The verdict itself is decided by the next real pipeline run, not live here.`
      : `Recomputed: no change from what was already scraped (P stays ${newP.toFixed(2)}).`;
    probEl.textContent = `${newP.toFixed(2)} P(contact ∪ build) — recomputed live`;
  }

  function updateIntentUI(intent) {
    wantButton.classList.toggle("selected", intent === "want");
    passButton.classList.toggle("selected", intent === "pass");
    contextSection.classList.toggle("open", intent === "want");
    const status = document.getElementById("intentStatus");
    const saved = IntentStore.get(detailEventId);
    status.textContent = saved
      ? `Saved on this device — ${saved.intent}, ${new Date(saved.saved_at).toLocaleString()}. Not yet part of the outcome record.`
      : "Not recorded yet — this stays on this device only, not in data/outcomes.json.";
  }

  function saveIntent(intent) {
    IntentStore.set(detailEventId, { intent, context: detailContext });
    updateIntentUI(intent);
  }

  function openDetail(id) {
    const e = DataAccess.getEvent(id);
    if (!e) return;
    detailEventId = id;
    lastFocusBeforeDetail = document.activeElement;
    const kind = rowKind(e);

    detailSheet.style.setProperty("--detail-glow", DETAIL_GLOW[kind] || DETAIL_GLOW.skip);
    document.getElementById("detailSource").textContent = e.source ? `${e.source} · listing` : "Source unknown";
    document.getElementById("detailTitle").textContent = e.name;
    const titleLink = document.getElementById("detailTitleLink");
    if (e.url) titleLink.setAttribute("href", e.url);
    else titleLink.removeAttribute("href"); // no href = CSS hides it (see .detail-title-link[href])
    document.getElementById("detailWhen").textContent = fmtTime(e.start);
    document.getElementById("detailPlace").textContent = e.address;

    const banner = document.getElementById("decisionBanner");
    banner.className = `decision-banner ${kind}`;
    const stateLabel = kind === "social_cohort" ? "SOCIAL / COHORT" : kind === "skip" ? "SETTLED SKIP" : (PROF_STATE_LABEL[e.verdict] || e.verdict.toUpperCase());
    document.getElementById("detailVerdict").textContent = stateLabel;
    document.getElementById("detailPrincipleLine").textContent = principleLineFor(kind, e.verdict);
    document.getElementById("detailReason").textContent = e.decision_line;

    renderWhyGrid(e, kind);
    renderDetailFacts(e);
    renderProvenance(e);

    const saved = IntentStore.get(id);
    detailContext = saved && saved.context ? { ...saved.context } : { ride: null, companion: null, hook: null };
    updateToggleUI();
    updateIntentUI(saved ? saved.intent : null);
    updateRecomputeDisplay(e, kind);

    // Intent/context only make sense for professional decisions — a social plan or a settled
    // skip has nothing to "want" in the SPEC.md §1b sense.
    const showIntent = kind !== "social_cohort" && kind !== "skip";
    document.getElementById("intentPills").style.display = showIntent ? "" : "none";
    document.getElementById("intentStatus").style.display = showIntent ? "" : "none";
    if (!showIntent) contextSection.classList.remove("open");

    detailOverlay.classList.add("open");
    detailOverlay.setAttribute("aria-hidden", "false");
    document.addEventListener("keydown", onDetailKeydown);
    closeDetailBtn.focus();
  }

  function closeDetail() {
    detailOverlay.classList.remove("open");
    detailOverlay.setAttribute("aria-hidden", "true");
    document.removeEventListener("keydown", onDetailKeydown);
    if (lastFocusBeforeDetail && typeof lastFocusBeforeDetail.focus === "function") lastFocusBeforeDetail.focus();
    detailEventId = null;
  }

  function onDetailKeydown(ev) {
    if (ev.key === "Escape") closeDetail();
  }

  closeDetailBtn.addEventListener("click", closeDetail);
  detailOverlay.addEventListener("click", (ev) => {
    if (ev.target === detailOverlay) closeDetail();
  });
  wantButton.addEventListener("click", () => {
    saveIntent("want");
    showToast("Recorded as want — saved on this device. Add ride/companion/hook if it changes the picture.");
  });
  passButton.addEventListener("click", () => {
    detailContext = { ride: null, companion: null, hook: null };
    saveIntent("pass");
    updateToggleUI();
    const e = DataAccess.getEvent(detailEventId);
    if (e) updateRecomputeDisplay(e, rowKind(e));
    showToast("Passed — saved on this device. Won't be raised again this session.");
  });
  contextSection.querySelectorAll(".toggle button").forEach((btn) => {
    btn.addEventListener("click", () => {
      const field = btn.closest(".toggle").dataset.field;
      detailContext[field] = btn.dataset.value === "yes";
      updateToggleUI();
      const e = DataAccess.getEvent(detailEventId);
      if (!e) return;
      const kind = rowKind(e);
      updateRecomputeDisplay(e, kind);
      const intent = wantButton.classList.contains("selected") ? "want" : (passButton.classList.contains("selected") ? "pass" : "want");
      IntentStore.set(detailEventId, { intent, context: detailContext });
      updateIntentUI(intent);
    });
  });

  function escapeHtml(str) {
    return String(str == null ? "" : str).replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }
  function escapeAttr(str) { return escapeHtml(str); }
  function escapeXml(str) { return escapeHtml(str); }

  // ---------- Read-back (step 3) ----------
  // No live free-text extraction anywhere on this page — turning a note into a Recorded fact or
  // a Suspected hypothesis needs a real model call, which needs a server holding an API key. A
  // static page has no server, and unlike the Google Maps key, an LLM key is a real secret that
  // must never be embedded in client-side code anyone can view-source (SPEC.md §5 already names
  // the real fix — a serverless function — for when this moves off local-only). So a saved note
  // stays exactly what she typed; capture_feedback.py remains the real, reviewable path from a
  // note to a recorded fact.

  let readbackEventId = null;

  function readbackOutcomeRows() {
    const outcomes = DataAccess.getOutcomes();
    return outcomes && outcomes.rows ? outcomes.rows : [];
  }

  // Real pipeline rows first, then anything added by link (LocalOutcomeStore) — sorted newest
  // first within each group so a just-added event is easy to find.
  function readbackAllRows() {
    const real = readbackOutcomeRows().slice().sort((a, b) => (a.date < b.date ? 1 : -1));
    const local = LocalOutcomeStore.getAll().slice().sort((a, b) => (a.date < b.date ? 1 : -1));
    return [...real, ...local];
  }

  const SHORT_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function fmtDateShort(dateStr) {
    if (!dateStr) return "Unknown date";
    // Plain "YYYY-MM-DD" (outcomes.json's date/t7_due fields) has no time component, but
    // `new Date("2026-09-18")` parses it as UTC midnight — formatting that back with
    // toLocaleDateString() uses the LOCAL timezone, which rolls it back to Sep 17 anywhere west
    // of UTC (confirmed live: Pacific showed "Sep 17"/"Sep 24" for dates that are really the
    // 18th/25th). Read the calendar digits directly instead of going through Date/timezone
    // conversion at all for this format.
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(dateStr);
    if (m) return `${SHORT_MONTHS[parseInt(m[2], 10) - 1]} ${parseInt(m[3], 10)}`;
    const d = new Date(dateStr);
    return Number.isNaN(d.getTime()) ? dateStr : d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  }

  function readbackStatusLabel(row) {
    if (row.label_status === "labeled") return "Labelled";
    if (row.t7_due) {
      const due = new Date(row.t7_due);
      const now = new Date();
      return due > now ? `T+7 due ${fmtDateShort(row.t7_due)}` : `T+7 due ${fmtDateShort(row.t7_due)} — overdue`;
    }
    return "Unknown";
  }

  function populateReadbackSelect() {
    const select = document.getElementById("readbackEvent");
    const rows = readbackAllRows();
    select.innerHTML = rows.length
      ? rows.map((r) => `<option value="${escapeAttr(r.event_id)}">${escapeHtml(fmtDateShort(r.date))} · ${escapeHtml(r.name)} · ${escapeHtml(r.local ? "Added by you" : readbackStatusLabel(r))}</option>`).join("")
      : `<option value="">No attended events recorded yet</option>`;
  }

  function renderRecordedFacts(row) {
    const container = document.getElementById("recordedFacts");
    const notesContainer = document.getElementById("pendingNotesList");
    const sourceEl = document.getElementById("recordedSource");
    if (!row) {
      container.innerHTML = `<p class="recorded-empty">No attended events yet.</p>`;
      notesContainer.innerHTML = "";
      sourceEl.textContent = "facts · from data/outcomes.json";
      return;
    }

    if (row.local) {
      // Added by link, not the pipeline — the only real "facts" are what she typed herself.
      sourceEl.textContent = "facts · added by you, this device only";
      const rows = [["date", fmtDateShort(row.date)]];
      if (row.url) rows.push(["link", row.url]);
      rows.push(["felt_score", row.felt_score != null ? String(row.felt_score) : "not set yet"]);
      if (row.felt_note) rows.push(["felt_note", row.felt_note]);
      container.innerHTML = rows.map(([k, v]) => `<div class="fact"><b>${escapeHtml(k)}</b><span>${escapeHtml(v)}</span></div>`).join("");
      notesContainer.innerHTML = "";
      return;
    }

    sourceEl.textContent = "facts · from data/outcomes.json";
    const rows = [];
    rows.push(["attended", row.partial ? "true (partial)" : String(!!row.attended)]);
    if (row.felt_score != null) rows.push(["felt_score", String(row.felt_score)]);
    if (row.companions && row.companions.length) rows.push(["companions", row.companions.join(", ")]);
    if (row.trip_chained != null) rows.push(["trip_chained", String(row.trip_chained)]);
    if (row.cost_blocks != null) rows.push(["cost_blocks", String(row.cost_blocks)]);
    ["s1_pov", "s2_contact", "s3_build", "s4_cohort"].forEach((k) => {
      if (row[k] !== undefined) rows.push([k, String(row[k])]);
    });
    if (row.hit !== undefined) rows.push(["hit", String(row.hit)]);
    if (row.felt_note) rows.push(["felt_note", row.felt_note]);
    container.innerHTML = rows.map(([k, v]) => `<div class="fact"><b>${escapeHtml(k)}</b><span>${escapeHtml(v)}</span></div>`).join("");

    const notes = ReadbackStore.getNotes(row.event_id);
    notesContainer.innerHTML = notes.length
      ? notes.map((n) => `<div class="pending-note"><b>YOUR NOTE · SAVED ON THIS DEVICE · ${escapeHtml(new Date(n.saved_at).toLocaleString())}</b>${escapeHtml(n.text)}</div>`).join("")
      : "";
  }

  function renderSuspectedHypotheses(row) {
    const container = document.getElementById("suspectedHypotheses");
    const awaiting = document.getElementById("awaitingNote");
    if (!row) {
      container.innerHTML = "";
      awaiting.textContent = "";
      return;
    }
    const hyps = DataAccess.getPendingHypotheses();
    const all = hyps && hyps.hypotheses ? Object.values(hyps.hypotheses) : [];
    const relevant = all.filter((h) => (h.supporting_events || []).includes(row.event_id));
    if (!relevant.length) {
      container.innerHTML = `<p class="suspected-empty">No pending hypothesis names this event as supporting evidence yet.</p>`;
      awaiting.textContent = "";
      return;
    }
    container.innerHTML = relevant.map((h) => {
      const n = (h.supporting_events || []).length;
      const pct = Math.min(100, Math.round((n / 3) * 100));
      return `<div class="hypothesis"><b>${escapeHtml(h.hypothesis)}</b><p>${n} of 3 supporting events.</p><div class="progress"><i style="width:${pct}%"></i></div></div>`;
    }).join("");
    awaiting.textContent = "AWAITING 3 INDEPENDENT EVENTS BEFORE ANY WEIGHT CHANGE";
  }

  function selectReadbackEvent(eventId) {
    readbackEventId = eventId || null;
    const row = readbackAllRows().find((r) => r.event_id === eventId) || null;
    const select = document.getElementById("readbackEvent");
    if (eventId && select.value !== eventId) select.value = eventId;

    const statusEl = document.getElementById("readbackStatus");
    const promptEl = document.getElementById("readbackPrompt");
    const feltInput = document.getElementById("feltScoreInput");
    const feltRange = document.getElementById("feltScoreRange");
    if (!row) {
      statusEl.textContent = "";
      promptEl.textContent = "Tell me what happened";
      feltInput.hidden = true;
    } else {
      statusEl.textContent = `${row.name.toUpperCase()} · ${fmtDateShort(row.date).toUpperCase()} · ${(row.local ? "ADDED BY YOU" : readbackStatusLabel(row).toUpperCase())}`;
      promptEl.textContent = `Tell me what happened at ${row.name}`;
      // Felt-score capture only makes sense for events added by link — a real outcomes.json row
      // already has its own felt_score set by the actual T+0 capture; this page doesn't write
      // back to that real record (no server to write it to).
      feltInput.hidden = !row.local;
      if (row.local) {
        const val = row.felt_score != null ? row.felt_score : 5;
        feltRange.value = val;
        document.getElementById("feltScoreValue").textContent = String(val);
      }
    }
    renderRecordedFacts(row);
    renderSuspectedHypotheses(row);
  }

  function renderReadback() {
    populateReadbackSelect();
    const rows = readbackAllRows();
    selectReadbackEvent(rows.length ? rows[0].event_id : null);
    if (!DataAccess.getOutcomes()) {
      showToast("No local pipeline outcomes (app/generated/private_data.js missing) — you can still add events by link below.");
    }
  }

  document.getElementById("readbackEvent").addEventListener("change", (ev) => selectReadbackEvent(ev.target.value));
  document.getElementById("readbackSubmit").addEventListener("click", () => {
    const textarea = document.getElementById("readbackFeedback");
    const text = textarea.value.trim();
    if (!text || !readbackEventId) return;
    const row = readbackAllRows().find((r) => r.event_id === readbackEventId);
    if (row && row.local) {
      LocalOutcomeStore.setFeeling(readbackEventId, { felt_note: text });
      showToast("Saved on this device — your own note, not a scored or verified record.");
    } else {
      ReadbackStore.addNote(readbackEventId, text);
      showToast("Saved on this device as a note — not yet a recorded fact. capture_feedback.py is still the real path into data/outcomes.json.");
    }
    textarea.value = "";
    renderRecordedFacts(readbackAllRows().find((r) => r.event_id === readbackEventId) || null);
  });

  const feltScoreRange = document.getElementById("feltScoreRange");
  feltScoreRange.addEventListener("input", () => {
    document.getElementById("feltScoreValue").textContent = feltScoreRange.value;
  });
  feltScoreRange.addEventListener("change", () => {
    if (!readbackEventId) return;
    LocalOutcomeStore.setFeeling(readbackEventId, { felt_score: Number(feltScoreRange.value) });
    renderRecordedFacts(readbackAllRows().find((r) => r.event_id === readbackEventId) || null);
  });

  const toggleAddEvent = document.getElementById("toggleAddEvent");
  const addEventForm = document.getElementById("addEventForm");
  toggleAddEvent.addEventListener("click", () => {
    const open = addEventForm.hidden;
    addEventForm.hidden = !open;
    toggleAddEvent.setAttribute("aria-expanded", String(open));
    toggleAddEvent.textContent = open
      ? "− Hide the add-event form"
      : "+ Add an event by link — one the pipeline never scored";
  });
  addEventForm.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const url = document.getElementById("addEventUrl").value.trim();
    const name = document.getElementById("addEventName").value.trim();
    const date = document.getElementById("addEventDate").value;
    if (!url || !name) return;
    const row = LocalOutcomeStore.add({ url, name, date });
    addEventForm.reset();
    addEventForm.hidden = true;
    toggleAddEvent.setAttribute("aria-expanded", "false");
    toggleAddEvent.textContent = "+ Add an event by link — one the pipeline never scored";
    populateReadbackSelect();
    selectReadbackEvent(row.event_id);
    showToast(`Added "${row.name}" — saved on this device. Set how it felt and add a note below.`);
  });

  // ---------- Routing ----------
  const navLinks = document.querySelectorAll(".nav-link[data-view]");
  function showView(viewId) {
    document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === viewId));
    navLinks.forEach((a) => a.classList.toggle("on", a.dataset.view === viewId));
    if (viewId === "readback") {
      document.getElementById("crumb").textContent = "READ-BACK";
      renderReadback();
    } else {
      document.getElementById("crumb").textContent = `DECISION BOARD · ${currentWeek().label.toUpperCase()}`;
    }
  }
  function routeFromHash() {
    const id = location.hash.replace("#/", "") || "choose";
    showView(id === "readback" ? "readback" : "choose");
  }
  window.addEventListener("hashchange", routeFromHash);

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
    routeFromHash();
  }

  boot();
})();
