// Connects the setor form maps to the location module:
// - pickup address search and address lookup use /location/api/geocode/ and /reverse/
// - collection point cards load missing addresses from /location/api/points/<id>/address/
// - /waste/new/?point=<id> (from "Setor ke sini" / "Pilih Titik Ini") preselects that point
// The page's own script owns the maps; this file talks to it through events.
(function () {
  "use strict";

  const SUGGEST_DELAY_MS = 450;
  const PLACEHOLDER = "Alamat belum tersedia";

  async function getJson(url, signal) {
    const response = await fetch(url, { headers: { Accept: "application/json" }, signal });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "Permintaan gagal.");
    return data;
  }

  // ---------- Pickup address search ----------
  function initPickupSearch(root) {
    const input = root.querySelector("#pickup-address-search");
    const list = root.querySelector("#pickup-address-suggestions");
    const note = root.querySelector("[data-pickup-location-note]");
    const detail = document.getElementById("id_address_detail");
    if (!input || !list) return;

    let timer = null;
    let request = null;
    let results = [];
    let active = -1;

    function showNote(message) {
      if (!note) return;
      note.textContent = message;
      note.hidden = !message;
    }

    function hide() {
      list.hidden = true;
      list.replaceChildren();
      results = [];
      active = -1;
    }

    function choose(index) {
      const place = results[index];
      if (!place) return;
      input.value = place.label;
      hide();
      document.dispatchEvent(new CustomEvent("siloak:set-pickup-location", {
        detail: { latitude: place.latitude, longitude: place.longitude },
      }));
    }

    function render(places) {
      results = places;
      active = -1;
      const items = places.map((place, index) => {
        const item = document.createElement("li");
        item.setAttribute("role", "option");
        item.textContent = place.label.split(",")[0];
        const small = document.createElement("small");
        small.textContent = place.label;
        item.append(small);
        item.addEventListener("mousedown", (event) => {
          event.preventDefault();
          choose(index);
        });
        return item;
      });
      if (!items.length) {
        const empty = document.createElement("li");
        empty.className = "is-muted";
        empty.textContent = "Alamat tidak ditemukan. Coba kata lain atau klik peta.";
        items.push(empty);
      }
      list.replaceChildren(...items);
      list.hidden = false;
    }

    async function search(query) {
      if (request) request.abort();
      request = new AbortController();
      try {
        const data = await getJson(root.dataset.geocodeUrl + "?" + new URLSearchParams({ q: query }), request.signal);
        if (input.value.trim() === query && document.activeElement === input) render(data.results);
      } catch (error) {
        if (error.name !== "AbortError") showNote(error.message);
      }
    }

    input.addEventListener("input", () => {
      window.clearTimeout(timer);
      const query = input.value.trim();
      if (query.length < 3) { hide(); return; }
      timer = window.setTimeout(() => search(query), SUGGEST_DELAY_MS);
    });
    input.addEventListener("keydown", (event) => {
      if (event.key === "Escape") hide();
      if (!results.length) return;
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        active = (active + (event.key === "ArrowDown" ? 1 : -1) + results.length) % results.length;
        Array.from(list.children).forEach((item, index) => item.setAttribute("aria-selected", String(index === active)));
      } else if (event.key === "Enter") {
        event.preventDefault();
        choose(active >= 0 ? active : 0);
      }
    });
    input.addEventListener("blur", () => window.setTimeout(hide, 150));

    // Whenever the pin moves (map click, GPS, or search), show its address.
    let reverseRequest = null;
    document.addEventListener("siloak:pickup-location-changed", async (event) => {
      if (reverseRequest) reverseRequest.abort();
      reverseRequest = new AbortController();
      const params = new URLSearchParams({ lat: event.detail.latitude.toFixed(6), lng: event.detail.longitude.toFixed(6) });
      try {
        const data = await getJson(root.dataset.reverseUrl + "?" + params, reverseRequest.signal);
        if (!data.address) return;
        input.value = data.address;
        if (detail && !detail.value.trim()) {
          detail.value = data.address;
          detail.dispatchEvent(new Event("input", { bubbles: true }));
        }
        showNote("");
      } catch (error) {
        if (error.name !== "AbortError") showNote("Alamat untuk titik ini belum ditemukan. Tulis alamatnya di kolom detail.");
      }
    });
  }

  // ---------- Collection point cards ----------
  function initPointCards() {
    const list = document.getElementById("point-list");
    if (!list || !list.dataset.addressUrlTemplate) return;

    async function loadAddress(card) {
      const text = card.querySelector("[data-point-address-text]");
      if (!text || text.textContent.trim() !== PLACEHOLDER || card.dataset.addressLoading) return;
      card.dataset.addressLoading = "true";
      try {
        const url = list.dataset.addressUrlTemplate.replace(/0\/address\/$/, card.dataset.pointId + "/address/");
        const data = await getJson(url);
        if (data.address) {
          text.textContent = data.address;
          card.dataset.pointAddress = data.address;
          // Refresh the summary if this card is the chosen one.
          if (card.classList.contains("is-selected")) card.click();
        }
      } catch (error) {
        delete card.dataset.addressLoading;
      }
    }

    list.addEventListener("click", (event) => {
      const card = event.target.closest("[data-point-card]");
      if (card) loadAddress(card);
    });

    const pointId = new URLSearchParams(window.location.search).get("point");
    const preselected = pointId && list.querySelector('[data-point-card][data-point-id="' + CSS.escape(pointId) + '"]');
    if (preselected) {
      preselected.click();
      preselected.scrollIntoView({ block: "nearest" });
    } else {
      const selected = list.querySelector("[data-point-card].is-selected");
      if (selected) loadAddress(selected);
    }
  }

  function init() {
    document.querySelectorAll("[data-location-connect]").forEach(initPickupSearch);
    initPointCards();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
