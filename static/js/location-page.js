// Titik Pengumpulan page: search, filters, nearest, and a map kept in sync
// with the list. Data comes from /location/api/points/ and place search from
// /location/api/geocode/ (OpenStreetMap, proxied by the server).
(function () {
  "use strict";

  const app = document.getElementById("location-app");
  if (!app) return;

  const SEARCH_DELAY_MS = 300;
  const SUGGEST_DELAY_MS = 500;

  // ---------- Elements ----------
  const els = {
    q: document.getElementById("location-q"),
    suggestions: document.getElementById("location-suggestions"),
    category: document.getElementById("location-category"),
    sort: document.getElementById("location-sort"),
    list: document.getElementById("location-list"),
    empty: app.querySelector("[data-empty]"),
    status: document.getElementById("location-status"),
    summary: app.querySelector("[data-result-summary]"),
    countPill: app.querySelector("[data-count-pill]"),
    originLabel: app.querySelector("[data-origin-label]"),
    template: document.getElementById("location-card-template"),
    radiusButtons: Array.from(app.querySelectorAll("[data-radius]")),
    openNow: app.querySelector('[data-action="open-now"]'),
    locate: app.querySelector('[data-action="locate"]'),
    reset: app.querySelector('[data-action="reset"]'),
    map: document.getElementById("location-map"),
  };

  // ---------- State (mirrored in the URL so a filtered view can be shared) ----------
  const state = {
    q: "",
    category: "",
    sort: "nearest",
    radius: "",
    openNow: false,
    origin: null, // { latitude, longitude, label }
    selectedId: null,
  };

  function readUrl() {
    const params = new URLSearchParams(window.location.search);
    state.q = params.get("q") || "";
    state.category = params.get("category") || "";
    state.sort = params.get("sort") || "nearest";
    state.radius = params.get("radius") || "";
    state.openNow = params.get("open_now") === "1";
    const lat = Number(params.get("lat"));
    const lng = Number(params.get("lng"));
    if (params.get("lat") && params.get("lng") && Number.isFinite(lat) && Number.isFinite(lng)) {
      state.origin = { latitude: lat, longitude: lng, label: params.get("near") || "lokasi terpilih" };
    }
  }

  function queryParams() {
    const params = new URLSearchParams();
    if (state.q) params.set("q", state.q);
    if (state.category) params.set("category", state.category);
    if (state.sort !== "nearest") params.set("sort", state.sort);
    if (state.openNow) params.set("open_now", "1");
    if (state.origin) {
      params.set("lat", state.origin.latitude.toFixed(6));
      params.set("lng", state.origin.longitude.toFixed(6));
      if (state.radius) params.set("radius", state.radius);
    }
    return params;
  }

  function writeUrl() {
    const params = queryParams();
    if (state.origin) params.set("near", state.origin.label);
    const query = params.toString();
    window.history.replaceState(null, "", window.location.pathname + (query ? "?" + query : ""));
  }

  // ---------- API ----------
  let pointsRequest = null;
  const addressCache = new Map(); // point id -> address looked up on OpenStreetMap

  async function getJson(url, signal) {
    const response = await fetch(url, { headers: { Accept: "application/json" }, signal });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.error || "Permintaan gagal (" + response.status + ").");
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function addressUrl(id) {
    return app.dataset.addressUrlTemplate.replace(/0\/address\/$/, id + "/address/");
  }

  // ---------- Rendering ----------
  function formatKm(value) {
    return value.toLocaleString("id-ID", { maximumFractionDigits: 1 }) + " km dari " + (state.origin && state.origin.label !== "lokasimu" ? "titik cari" : "kamu");
  }

  function fillCard(card, point) {
    card.dataset.pointId = point.id;
    card.querySelector('[data-field="name"]').textContent = point.name;
    const address = card.querySelector('[data-field="address"]');
    const knownAddress = point.address || addressCache.get(point.id) || "";
    address.textContent = knownAddress || "Alamat belum tersedia";
    address.dataset.missing = knownAddress ? "false" : "true";
    const badge = card.querySelector('[data-field="open-badge"]');
    badge.className = "location-badge " + (point.is_open === true ? "is-open" : point.is_open === false ? "is-closed" : "is-unknown");
    badge.textContent = point.is_open === true ? "Buka" : point.is_open === false ? "Tutup" : "Jam ?";
    card.querySelector('[data-field="category"]').textContent = point.category_label;
    card.querySelector('[data-field="opening"]').textContent = point.opening_label;
    const distance = card.querySelector('[data-field="distance"]');
    distance.hidden = point.distance_km === null;
    distance.textContent = point.distance_km === null ? "" : formatKm(point.distance_km);
    card.querySelector('[data-field="directions"]').href = point.directions_url;
    return card;
  }

  function renderList(results) {
    const cards = results.map((point) => {
      const card = els.template.content.firstElementChild.cloneNode(true);
      return fillCard(card, point);
    });
    els.list.replaceChildren(...cards);
    els.empty.hidden = results.length > 0;
    highlightSelected();
  }

  function renderCategories(categories) {
    const current = state.category;
    const options = [new Option("Semua jenis layanan", "")];
    categories.forEach((category) => options.push(new Option(category.label + " (" + category.count + ")", category.value)));
    if (current && !categories.some((category) => category.value === current)) {
      options.push(new Option("Jenis terpilih (0)", current));
    }
    els.category.replaceChildren(...options);
    els.category.value = current;
  }

  function setStatus(message, isError) {
    els.status.textContent = message;
    els.status.classList.toggle("is-error", Boolean(isError));
  }

  function renderControls() {
    els.q.value = state.q;
    els.sort.value = state.sort;
    els.openNow.setAttribute("aria-pressed", String(state.openNow));
    els.radiusButtons.forEach((button) => {
      button.disabled = !state.origin && button.dataset.radius !== "";
      button.setAttribute("aria-pressed", String(button.dataset.radius === state.radius));
    });
    els.originLabel.hidden = !state.origin;
    els.originLabel.textContent = state.origin ? "Dari " + state.origin.label : "";
  }

  // ---------- Map ----------
  const initialPoints = JSON.parse(document.getElementById("location-map-points").textContent);
  const mapState = window.SiloakMaps ? window.SiloakMaps.createMap(els.map, initialPoints) : null;
  let originMarker = null;
  let radiusCircle = null;

  if (mapState) {
    mapState.markers.forEach((marker, id) => marker.on("click", () => select(Number(id), { fromMap: true })));
  }

  function syncMap(results) {
    if (!mapState) return;
    const visible = new Set(results.map((point) => String(point.id)));
    const bounds = [];
    mapState.markers.forEach((marker, id) => {
      if (visible.has(id)) {
        if (!mapState.map.hasLayer(marker)) marker.addTo(mapState.map);
        bounds.push(marker.getLatLng());
      } else if (mapState.map.hasLayer(marker)) {
        marker.removeFrom(mapState.map);
      }
    });

    if (originMarker) originMarker.remove();
    if (radiusCircle) radiusCircle.remove();
    originMarker = radiusCircle = null;
    if (state.origin) {
      const center = [state.origin.latitude, state.origin.longitude];
      originMarker = L.marker(center, {
        icon: L.divIcon({ className: "location-origin-marker", html: "<span></span>", iconSize: [18, 18], iconAnchor: [9, 9] }),
        keyboard: false,
        zIndexOffset: 2000,
      }).addTo(mapState.map).bindTooltip(state.origin.label === "lokasimu" ? "Lokasimu" : state.origin.label);
      bounds.push(L.latLng(center));
      if (state.radius) {
        radiusCircle = L.circle(center, { radius: Number(state.radius) * 1000, color: "#1b367e", weight: 1, fillOpacity: 0.06 }).addTo(mapState.map);
      }
    }
    if (bounds.length > 1) mapState.map.fitBounds(L.latLngBounds(bounds), { padding: [32, 32], maxZoom: 15 });
    else if (bounds.length === 1) mapState.map.setView(bounds[0], 15);
  }

  // ---------- Selection ----------
  function highlightSelected() {
    els.list.querySelectorAll("[data-point-card]").forEach((card) => {
      const selected = Number(card.dataset.pointId) === state.selectedId;
      card.classList.toggle("is-selected", selected);
      card.setAttribute("aria-pressed", String(selected));
    });
  }

  async function loadMissingAddress(card, id) {
    const address = card.querySelector('[data-field="address"]');
    if (address.dataset.missing !== "true" || address.dataset.loading === "true") return;
    address.dataset.loading = "true";
    address.classList.add("is-loading");
    address.textContent = "Memuat alamat dari OpenStreetMap…";
    try {
      const data = await getJson(addressUrl(id));
      address.textContent = data.address || "Alamat belum tersedia";
      address.dataset.missing = data.address ? "false" : "true";
      if (data.address) addressCache.set(id, data.address);
    } catch (error) {
      address.textContent = "Alamat belum tersedia";
    } finally {
      address.classList.remove("is-loading");
      address.dataset.loading = "false";
    }
  }

  function select(id, { fromMap = false } = {}) {
    state.selectedId = id;
    highlightSelected();
    const card = els.list.querySelector('[data-point-id="' + id + '"]');
    if (card) {
      if (fromMap) card.scrollIntoView({ behavior: "smooth", block: "nearest" });
      loadMissingAddress(card, id);
    }
    if (mapState) mapState.selectPoint(id, { center: !fromMap, openPopup: true });
  }

  els.list.addEventListener("click", (event) => {
    if (event.target.closest("a")) return;
    const card = event.target.closest("[data-point-card]");
    if (card) select(Number(card.dataset.pointId));
  });
  els.list.addEventListener("keydown", (event) => {
    const card = event.target.closest("[data-point-card]");
    if (!card || event.target !== card) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      select(Number(card.dataset.pointId));
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const sibling = event.key === "ArrowDown" ? card.nextElementSibling : card.previousElementSibling;
      if (sibling) sibling.focus();
    }
  });

  // ---------- Loading points ----------
  async function loadPoints() {
    if (pointsRequest) pointsRequest.abort();
    pointsRequest = new AbortController();
    els.list.setAttribute("aria-busy", "true");
    writeUrl();
    renderControls();
    try {
      const data = await getJson(app.dataset.pointsUrl + "?" + queryParams().toString(), pointsRequest.signal);
      renderCategories(data.categories);
      renderList(data.results);
      syncMap(data.results);
      els.summary.textContent = data.count + " titik ditemukan" + (state.origin && state.radius ? " dalam " + state.radius + " km" : "");
      els.countPill.textContent = data.count + " lokasi " + (state.openNow ? "buka sekarang" : "aktif");
      setStatus(describeResults(data));
    } catch (error) {
      if (error.name === "AbortError") return;
      setStatus(error.message || "Data titik tidak dapat dimuat. Periksa koneksimu.", true);
    } finally {
      els.list.setAttribute("aria-busy", "false");
    }
  }

  function describeResults(data) {
    if (!data.count && state.q) {
      return "Tidak ada titik bernama \"" + state.q + "\". Pilih tempat di saran untuk mencari titik di sekitarnya.";
    }
    if (!data.count && state.openNow) {
      return "Belum ada titik yang sedang buka. Sebagian besar titik belum mencatat jam operasional.";
    }
    if (!data.count) return "Tidak ada titik yang cocok dengan filter.";
    const nearest = data.results[0];
    if (state.origin && state.sort === "nearest" && nearest && nearest.distance_km !== null) {
      return "Terdekat: " + nearest.name + " (" + nearest.distance_km.toLocaleString("id-ID", { maximumFractionDigits: 1 }) + " km).";
    }
    return "Menampilkan " + data.count + " titik pengumpulan.";
  }

  // ---------- Search box: filter by name/address, suggest places nearby ----------
  let searchTimer = null;
  let suggestTimer = null;
  let suggestRequest = null;
  let suggestionItems = [];
  let activeSuggestion = -1;

  function hideSuggestions() {
    els.suggestions.hidden = true;
    els.suggestions.replaceChildren();
    els.q.setAttribute("aria-expanded", "false");
    suggestionItems = [];
    activeSuggestion = -1;
  }

  function useOrigin(origin) {
    state.origin = origin;
    state.sort = "nearest";
    state.q = "";
    hideSuggestions();
    loadPoints();
  }

  function renderSuggestions(results) {
    suggestionItems = results;
    activeSuggestion = -1;
    const items = results.map((place, index) => {
      const item = document.createElement("li");
      item.setAttribute("role", "option");
      item.id = "location-suggestion-" + index;
      item.textContent = "Cari di sekitar " + place.label.split(",")[0];
      const detail = document.createElement("small");
      detail.textContent = place.label;
      item.append(detail);
      item.addEventListener("mousedown", (event) => {
        event.preventDefault();
        chooseSuggestion(index);
      });
      return item;
    });
    if (!items.length) {
      const empty = document.createElement("li");
      empty.className = "is-muted";
      empty.textContent = "Tidak ada tempat dengan nama itu.";
      items.push(empty);
    }
    els.suggestions.replaceChildren(...items);
    els.suggestions.hidden = false;
    els.q.setAttribute("aria-expanded", "true");
  }

  function chooseSuggestion(index) {
    const place = suggestionItems[index];
    if (!place) return;
    useOrigin({ latitude: place.latitude, longitude: place.longitude, label: place.label.split(",")[0] });
  }

  function moveSuggestion(step) {
    if (!suggestionItems.length) return;
    activeSuggestion = (activeSuggestion + step + suggestionItems.length) % suggestionItems.length;
    Array.from(els.suggestions.children).forEach((item, index) => item.setAttribute("aria-selected", String(index === activeSuggestion)));
    els.q.setAttribute("aria-activedescendant", "location-suggestion-" + activeSuggestion);
  }

  async function suggestPlaces(query) {
    if (suggestRequest) suggestRequest.abort();
    suggestRequest = new AbortController();
    try {
      const data = await getJson(app.dataset.geocodeUrl + "?" + new URLSearchParams({ q: query }), suggestRequest.signal);
      if (els.q.value.trim() === query) renderSuggestions(data.results);
    } catch (error) {
      if (error.name === "AbortError") return;
      if (error.status === 429 || error.status === 502) setStatus(error.message, true);
    }
  }

  els.q.addEventListener("input", () => {
    const query = els.q.value.trim();
    window.clearTimeout(searchTimer);
    window.clearTimeout(suggestTimer);
    searchTimer = window.setTimeout(() => {
      state.q = query;
      loadPoints();
    }, SEARCH_DELAY_MS);
    if (query.length >= 3) suggestTimer = window.setTimeout(() => suggestPlaces(query), SUGGEST_DELAY_MS);
    else hideSuggestions();
  });
  els.q.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") { event.preventDefault(); moveSuggestion(1); }
    else if (event.key === "ArrowUp") { event.preventDefault(); moveSuggestion(-1); }
    else if (event.key === "Escape") hideSuggestions();
    else if (event.key === "Enter") {
      event.preventDefault();
      if (activeSuggestion >= 0) chooseSuggestion(activeSuggestion);
    }
  });
  els.q.addEventListener("blur", () => window.setTimeout(hideSuggestions, 150));

  // ---------- Filters ----------
  els.category.addEventListener("change", () => { state.category = els.category.value; loadPoints(); });
  els.sort.addEventListener("change", () => { state.sort = els.sort.value; loadPoints(); });
  els.openNow.addEventListener("click", () => { state.openNow = !state.openNow; loadPoints(); });
  els.radiusButtons.forEach((button) => button.addEventListener("click", () => {
    state.radius = button.dataset.radius;
    loadPoints();
  }));
  els.reset.addEventListener("click", () => {
    Object.assign(state, { q: "", category: "", sort: "nearest", radius: "", openNow: false, origin: null, selectedId: null });
    hideSuggestions();
    loadPoints();
  });

  els.locate.addEventListener("click", () => {
    if (!navigator.geolocation) {
      setStatus("Browser ini tidak menyediakan lokasi. Cari nama daerahmu di kolom pencarian.", true);
      return;
    }
    els.locate.disabled = true;
    setStatus("Mencari lokasimu…");
    navigator.geolocation.getCurrentPosition((position) => {
      els.locate.disabled = false;
      useOrigin({ latitude: position.coords.latitude, longitude: position.coords.longitude, label: "lokasimu" });
    }, () => {
      els.locate.disabled = false;
      setStatus("Lokasi tidak dapat diakses. Izinkan akses lokasi, atau cari nama daerahmu.", true);
    }, { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 });
  });

  // ---------- Start ----------
  readUrl();
  renderControls();
  if (window.location.search) loadPoints();
  else if (mapState) syncMap(initialPoints);
})();
