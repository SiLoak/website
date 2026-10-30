// Landing page "Temukan titik pengumpulan terdekat": an in-page finder backed by
// the location module API. Typing filters the list and the map, radius and
// "Cari yang terdekat" sort by distance from the visitor (or a searched area),
// and list cards and map markers select each other.
(function () {
  "use strict";

  const LIST_LIMIT = 6;
  const SEARCH_DELAY_MS = 350;

  const root = document.getElementById("landing-finder");
  if (!root) return;

  const els = {
    form: root.querySelector("[data-landing-form]"),
    q: root.querySelector("#landing-q"),
    list: root.querySelector(".landing-point-list"),
    more: root.querySelector("[data-landing-more]"),
    template: document.getElementById("landing-point-template"),
    status: document.getElementById("landing-nearest-status"),
    nearest: root.querySelector("[data-landing-nearest]"),
    radiusButtons: Array.from(root.querySelectorAll("[data-landing-radius]")),
    map: document.getElementById("landing-map"),
  };

  const state = { q: "", radius: "", origin: null, selectedId: null };
  let mapState = null;
  let originMarker = null;
  let radiusCircle = null;
  let request = null;
  let searchTimer = null;

  // ---------- Helpers ----------
  function setStatus(message, isError) {
    if (!els.status) return;
    els.status.textContent = message || "";
    els.status.classList.toggle("is-error", Boolean(isError));
  }

  async function getJson(url, signal) {
    const response = await fetch(url, { headers: { Accept: "application/json" }, signal });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "Data titik tidak dapat dimuat.");
    return data;
  }

  function apiParams(extra) {
    const params = new URLSearchParams(extra || {});
    if (state.q) params.set("q", state.q);
    if (state.origin) {
      params.set("lat", state.origin.latitude.toFixed(6));
      params.set("lng", state.origin.longitude.toFixed(6));
      if (state.radius) params.set("radius", state.radius);
    }
    return params;
  }

  function km(value) {
    return value.toLocaleString("id-ID", { maximumFractionDigits: 1 }) + " km";
  }

  // ---------- List ----------
  function fill(card, point) {
    card.dataset.pointId = point.id;
    card.querySelector('[data-field="name"]').textContent = point.name;
    card.querySelector('[data-field="address"]').textContent =
      point.address || "Alamat dimuat dari OpenStreetMap di halaman Titik Pengumpulan";
    card.querySelector('[data-field="category"]').textContent = point.category_label;

    const known = point.is_open !== null;
    const badge = card.querySelector('[data-field="badge"]');
    badge.hidden = !known;
    badge.textContent = point.is_open ? "Buka" : "Tutup";
    badge.classList.toggle("is-open", Boolean(point.is_open));
    card.querySelector('[data-field="opening"]').hidden = !known;
    card.querySelector('[data-field="opening-text"]').textContent = known ? point.opening_label : "";

    const distance = card.querySelector('[data-field="distance"]');
    distance.hidden = point.distance_km === null;
    distance.textContent = point.distance_km === null ? "" : km(point.distance_km) + " dari " + (state.origin.label || "kamu");

    card.querySelector('[data-field="directions"]').href = point.directions_url;
    const setor = card.querySelector('[data-field="setor"]');
    setor.href = setor.getAttribute("href").split("?")[0] + "?point=" + point.id;
    return card;
  }

  function renderList(results) {
    const cards = results.map((point) => fill(els.template.content.firstElementChild.cloneNode(true), point));
    if (!cards.length) {
      const empty = document.createElement("p");
      empty.className = "landing-point-empty";
      empty.textContent = "Tidak ada titik yang cocok. Coba kata lain atau perbesar jarak.";
      cards.push(empty);
    }
    els.list.replaceChildren(...cards, els.more);
    highlight();
  }

  function updateMoreLink(count) {
    const params = apiParams();
    if (state.origin && state.origin.label) params.set("near", state.origin.label);
    els.more.href = root.dataset.locationUrl + (params.toString() ? "?" + params : "");
    els.more.textContent = count > LIST_LIMIT
      ? "Lihat semua " + count + " titik di peta →"
      : "Buka halaman Titik Pengumpulan →";
  }

  // ---------- Map ----------
  function syncMap(results) {
    if (!mapState) return;
    const visible = new Set(results.map((point) => String(point.id)));
    const bounds = [];
    mapState.markers.forEach((marker, id) => {
      const show = !visible.size || visible.has(id);
      if (show && !mapState.map.hasLayer(marker)) marker.addTo(mapState.map);
      if (!show && mapState.map.hasLayer(marker)) marker.removeFrom(mapState.map);
      if (show && visible.has(id)) bounds.push(marker.getLatLng());
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
      }).addTo(mapState.map).bindTooltip(state.origin.label === "kamu" ? "Lokasimu" : state.origin.label);
      bounds.push(L.latLng(center));
      if (state.radius) {
        radiusCircle = L.circle(center, { radius: Number(state.radius) * 1000, color: "#3b507d", weight: 1, fillOpacity: 0.06 })
          .addTo(mapState.map);
      }
    }
    if (bounds.length > 1) mapState.map.fitBounds(L.latLngBounds(bounds), { padding: [28, 28], maxZoom: 15 });
    else if (bounds.length === 1) mapState.map.setView(bounds[0], 15);
  }

  function highlight() {
    const cards = Array.from(els.list.querySelectorAll("[data-landing-card]"));
    cards.forEach((card) => {
      const selected = state.selectedId !== null && Number(card.dataset.pointId) === state.selectedId;
      card.classList.remove("is-first");
      card.classList.toggle("is-selected", selected);
      card.setAttribute("aria-current", selected ? "true" : "false");
    });
    if (state.selectedId === null && cards.length) cards[0].classList.add("is-first");
  }

  function select(id, { fromMap = false } = {}) {
    state.selectedId = id;
    highlight();
    const card = els.list.querySelector('[data-landing-card][data-point-id="' + id + '"]');
    if (card && fromMap) card.scrollIntoView({ behavior: "smooth", block: "nearest" });
    if (mapState) mapState.selectPoint(id, { center: !fromMap, openPopup: true });
  }

  function bindMap(state_) {
    mapState = state_;
    mapState.markers.forEach((marker, id) => marker.on("click", () => select(Number(id), { fromMap: true })));
  }

  // ---------- Loading ----------
  async function load({ geocodeFallback = false } = {}) {
    if (request) request.abort();
    request = new AbortController();
    els.list.setAttribute("aria-busy", "true");
    renderControls();
    try {
      const data = await getJson(root.dataset.pointsUrl + "?" + apiParams({ limit: LIST_LIMIT }), request.signal);
      if (!data.count && geocodeFallback && state.q.length >= 3) {
        // No point has that name: treat the text as an area and search around it.
        const places = await getJson(root.dataset.geocodeUrl + "?" + new URLSearchParams({ q: state.q }), request.signal);
        if (places.results.length) {
          const place = places.results[0];
          state.origin = { latitude: place.latitude, longitude: place.longitude, label: place.label.split(",")[0] };
          state.q = "";
          return load();
        }
      }
      renderList(data.results);
      syncMap(data.results);
      updateMoreLink(data.count);
      setStatus(describe(data));
    } catch (error) {
      if (error.name !== "AbortError") setStatus(error.message, true);
    } finally {
      els.list.setAttribute("aria-busy", "false");
    }
  }

  function describe(data) {
    if (!data.count) return state.q ? "Tidak ada titik bernama \"" + state.q + "\". Tekan Enter untuk mencari di sekitar daerah itu." : "Tidak ada titik dalam jarak ini.";
    const first = data.results[0];
    if (state.origin && first && first.distance_km !== null) {
      return "Terdekat dari " + (state.origin.label === "kamu" ? "lokasimu" : state.origin.label) + ": " + first.name + " (" + km(first.distance_km) + ").";
    }
    return data.count + " titik ditemukan.";
  }

  function renderControls() {
    els.radiusButtons.forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.landingRadius === state.radius)));
  }

  // ---------- Controls ----------
  function locate(then) {
    if (!navigator.geolocation) {
      setStatus("Browser ini tidak menyediakan lokasi. Ketik nama daerahmu lalu tekan Enter.", true);
      return;
    }
    els.nearest.disabled = true;
    setStatus("Mencari lokasimu…");
    navigator.geolocation.getCurrentPosition((position) => {
      els.nearest.disabled = false;
      state.origin = { latitude: position.coords.latitude, longitude: position.coords.longitude, label: "kamu" };
      then();
    }, () => {
      els.nearest.disabled = false;
      setStatus("Lokasi tidak dapat diakses. Ketik nama daerahmu lalu tekan Enter.", true);
    }, { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 });
  }

  els.q.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => {
      state.q = els.q.value.trim();
      load();
    }, SEARCH_DELAY_MS);
  });

  els.form.addEventListener("submit", (event) => {
    event.preventDefault();
    window.clearTimeout(searchTimer);
    state.q = els.q.value.trim();
    load({ geocodeFallback: true });
  });

  els.radiusButtons.forEach((button) => button.addEventListener("click", (event) => {
    event.preventDefault();
    const radius = button.dataset.landingRadius;
    state.radius = state.radius === radius ? "" : radius;
    if (state.radius && !state.origin) locate(load);
    else load();
  }));

  els.nearest.addEventListener("click", () => locate(() => {
    state.q = "";
    els.q.value = "";
    load();
  }));

  els.list.addEventListener("click", (event) => {
    if (event.target.closest("a")) return;
    const card = event.target.closest("[data-landing-card]");
    if (card) select(Number(card.dataset.pointId));
  });
  els.list.addEventListener("keydown", (event) => {
    const card = event.target.closest("[data-landing-card]");
    if (card && event.target === card && (event.key === "Enter" || event.key === " ")) {
      event.preventDefault();
      select(Number(card.dataset.pointId));
    }
  });

  // The shared map helper builds the map on DOMContentLoaded; pick it up either way.
  if (els.map && els.map._siloakMapState) bindMap(els.map._siloakMapState);
  else if (els.map) els.map.addEventListener("siloak-map-ready", (event) => bindMap(event.detail), { once: true });
  renderControls();
})();
