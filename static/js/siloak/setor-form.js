// Setor Loak form: items, delivery method, collection points, pickup address
// and schedule, and the live summary. HTMX swaps the form back in after a
// failed submit, so init() runs on every load of #waste-submission-form.
(function () {
  "use strict";

  function init(form) {


    const itemContainer = document.getElementById("item-forms");
    const addItemButton = document.getElementById("add-item");
    const totalForms = document.getElementById("id_items-TOTAL_FORMS");
    const maxFormsInput = document.getElementById("id_items-MAX_NUM_FORMS");
    const emptyTemplate = document.getElementById("empty-item-form");
    const maxForms = Number(maxFormsInput && maxFormsInput.value) || 6;
    const collectionSelect = document.getElementById("id_collection_point");
    const pointCards = Array.from(document.querySelectorAll("[data-point-card]"));
    const pointMarkers = new Map();
    const radiusButtons = Array.from(document.querySelectorAll("[data-radius]"));
    const pointSearch = document.getElementById("point-search");
    const radiusNote = document.getElementById("radius-note");
    const gpsState = document.querySelector("[data-gps-state]");
    const deliveryInputs = Array.from(document.querySelectorAll("[data-delivery-mode]"));
    const methodCards = Array.from(document.querySelectorAll("[data-method-card]"));
    const submitButton = document.getElementById("submit-waste");
    const submitLabel = submitButton.querySelector("[data-submit-label]");
    const submitArrow = submitButton.querySelector("[data-submit-arrow]");
    const selectedPointId = form.dataset.selectedPoint;
    const mapElement = document.getElementById("waste-point-map");
    const mapPoints = pointCards.map((card) => ({
      id: card.dataset.pointId,
      name: card.dataset.pointName,
      address: card.dataset.pointAddress,
      operating_hours: card.dataset.pointHours,
      latitude: card.dataset.lat,
      longitude: card.dataset.lng,
    }));
    const mapState = window.SiloakMaps && SiloakMaps.createMap(mapElement, mapPoints);
    const collectionMap = mapState && mapState.map;
    if (mapState) {
      mapState.markers.forEach((marker, id) => {
        pointMarkers.set(id, marker);
        marker.on("click", () => selectPoint(id));
      });
    }
    const pickupPreview = document.getElementById("pickup-preview-map");
    const pickupLatInput = document.getElementById("id_latitude");
    const pickupLngInput = document.getElementById("id_longitude");
    const pickupAddressInput = document.getElementById("id_pickup_address");
    const addressSuggestions = document.querySelector("[data-address-suggestions]");
    const addressTitle = document.querySelector("[data-pickup-address-title]");
    const addressSub = document.querySelector("[data-pickup-address-sub]");
    const pickupGpsState = document.querySelector("[data-pickup-gps-state]");
    const NOMINATIM_URL = "https://nominatim.openstreetmap.org";
    let pickupMap = null;
    let pickupMarker = null;
    let reverseRequest = 0;

    const pickupDateInput = document.getElementById("pickup-date-option");
    const pickupTimeInput = document.getElementById("pickup-time-slot");
    const dateButtons = Array.from(document.querySelectorAll("[data-date-option]"));
    const timeButtons = Array.from(document.querySelectorAll("[data-time-slot]"));
    const customDateWrap = document.querySelector("[data-custom-date-wrap]");
    const addressInput = document.getElementById("id_address_detail");
    const customDateInput = document.getElementById("id_custom_date");

    // Nominatim returns "Jl. Mawar 12, Pasar Minggu, Jakarta Selatan, ..., Indonesia".
    // The first two parts become the title, the rest the second line.
    function splitAddress(address) {
      const parts = (address || "").split(",").map((part) => part.trim()).filter(Boolean);
      if (parts.length && parts[parts.length - 1] === "Indonesia") parts.pop();
      return { title: parts.slice(0, 2).join(", "), sub: parts.slice(2).join(", ") };
    }

    function cleanAddress(address) {
      return (address || "").replace(/,\s*Indonesia$/, "").trim();
    }

    function updateAddressCard() {
      const value = pickupAddressInput ? pickupAddressInput.value.trim() : "";
      const parts = splitAddress(value);
      if (addressTitle) addressTitle.textContent = parts.title || "Alamat belum dipilih";
      if (addressSub) addressSub.textContent = value ? (parts.sub || "Alamat penjemputan") : "Cari alamat, pakai lokasimu, atau klik peta.";
      if (pickupMarker) {
        pickupMarker.setTooltipContent(parts.title ? parts.title.split(",")[0] : "Lokasi penjemputan");
      }
      updatePickupSummary();
    }

    function pickupPinIcon() {
      return L.divIcon({
        className: "siloak-pickup-pin",
        html: "<span></span>",
        iconSize: [22, 22],
        iconAnchor: [11, 11],
        tooltipAnchor: [0, -14],
      });
    }

    async function reverseGeocode(latitude, longitude) {
      const requestId = ++reverseRequest;
      showLocationNote("Mencari alamat dari titik peta…");
      try {
        const params = new URLSearchParams({ format: "jsonv2", lat: latitude, lon: longitude, zoom: "18", "accept-language": "id" });
        const response = await fetch(NOMINATIM_URL + "/reverse?" + params.toString(), { headers: { Accept: "application/json" } });
        if (!response.ok) throw new Error("reverse geocode failed");
        const data = await response.json();
        if (requestId !== reverseRequest) return;
        if (data && data.display_name && pickupAddressInput) {
          pickupAddressInput.value = cleanAddress(data.display_name);
          updateAddressCard();
        }
        showLocationNote("");
      } catch (error) {
        if (requestId !== reverseRequest) return;
        showLocationNote("Alamat untuk titik ini tidak ditemukan. Tulis alamatnya secara manual di kolom pencarian.");
      }
    }

    function setPickupLocation(latitude, longitude, { center = false, reverse = true } = {}) {
      if (!pickupMap || !pickupLatInput || !pickupLngInput) return;
      pickupLatInput.value = latitude.toFixed(6);
      pickupLngInput.value = longitude.toFixed(6);
      if (pickupMarker) {
        pickupMarker.setLatLng([latitude, longitude]);
      } else {
        pickupMarker = L.marker([latitude, longitude], { icon: pickupPinIcon(), draggable: true, autoPan: true })
          .addTo(pickupMap)
          .bindTooltip("Lokasi penjemputan", { permanent: true, direction: "top", className: "siloak-pickup-label" });
        pickupMarker.on("dragend", () => {
          const position = pickupMarker.getLatLng();
          setPickupLocation(position.lat, position.lng);
        });
      }
      if (center) pickupMap.setView([latitude, longitude], 17);
      if (reverse) reverseGeocode(latitude, longitude);
      else updateAddressCard();
    }

    if (pickupPreview && window.L) {
      const latitude = Number(pickupPreview.dataset.latitude);
      const longitude = Number(pickupPreview.dataset.longitude);
      const hasCoordinates = Number.isFinite(latitude) && Number.isFinite(longitude) && pickupPreview.dataset.latitude && pickupPreview.dataset.longitude;
      const pickupMapState = SiloakMaps.createMap(pickupPreview, [], {
        center: hasCoordinates ? [latitude, longitude] : [-6.2297, 106.8295],
        zoom: hasCoordinates ? 17 : 11,
      });
      pickupMap = pickupMapState ? pickupMapState.map : null;
      if (pickupMap) {
        if (hasCoordinates) setPickupLocation(latitude, longitude, { reverse: false });
        pickupMap.on("click", (event) => setPickupLocation(event.latlng.lat, event.latlng.lng));
      }
    }

    let suggestionTimer = null;
    let suggestionRequest = 0;
    let suggestionResults = [];

    function hideSuggestions() {
      if (!addressSuggestions) return;
      addressSuggestions.hidden = true;
      addressSuggestions.replaceChildren();
      suggestionResults = [];
    }

    function chooseSuggestion(result) {
      if (!result || !pickupAddressInput) return;
      pickupAddressInput.value = cleanAddress(result.display_name);
      hideSuggestions();
      setPickupLocation(Number(result.lat), Number(result.lon), { center: true, reverse: false });
    }

    function renderSuggestions(results) {
      if (!addressSuggestions) return;
      addressSuggestions.replaceChildren();
      suggestionResults = results;
      if (!results.length) {
        const empty = document.createElement("li");
        empty.className = "is-empty";
        empty.textContent = "Alamat tidak ditemukan. Coba kata kunci lain atau klik peta.";
        addressSuggestions.append(empty);
      }
      results.forEach((result) => {
        const parts = splitAddress(cleanAddress(result.display_name));
        const item = document.createElement("li");
        item.setAttribute("role", "option");
        item.tabIndex = -1;
        const title = document.createElement("strong");
        title.textContent = parts.title;
        const sub = document.createElement("span");
        sub.textContent = parts.sub;
        item.append(title, sub);
        item.addEventListener("mousedown", (event) => {
          event.preventDefault();
          chooseSuggestion(result);
        });
        addressSuggestions.append(item);
      });
      addressSuggestions.hidden = false;
    }

    async function searchAddress(query) {
      const requestId = ++suggestionRequest;
      try {
        const params = new URLSearchParams({ format: "jsonv2", q: query, countrycodes: "id", limit: "5", "accept-language": "id" });
        const response = await fetch(NOMINATIM_URL + "/search?" + params.toString(), { headers: { Accept: "application/json" } });
        if (!response.ok) throw new Error("search failed");
        const results = await response.json();
        if (requestId === suggestionRequest && document.activeElement === pickupAddressInput) renderSuggestions(results);
        return results;
      } catch (error) {
        if (requestId === suggestionRequest) showLocationNote("Pencarian alamat sedang tidak tersedia. Klik peta untuk menandai lokasimu.");
        return [];
      }
    }

    if (pickupAddressInput) {
      pickupAddressInput.addEventListener("input", () => {
        updateAddressCard();
        window.clearTimeout(suggestionTimer);
        const query = pickupAddressInput.value.trim();
        if (query.length < 4) {
          hideSuggestions();
          return;
        }
        suggestionTimer = window.setTimeout(() => searchAddress(query), 600);
      });
      pickupAddressInput.addEventListener("keydown", async (event) => {
        if (event.key === "Escape") hideSuggestions();
        if (event.key !== "Enter") return;
        event.preventDefault();
        window.clearTimeout(suggestionTimer);
        const query = pickupAddressInput.value.trim();
        if (suggestionResults.length) {
          chooseSuggestion(suggestionResults[0]);
        } else if (query.length >= 4) {
          const results = await searchAddress(query);
          if (results.length) chooseSuggestion(results[0]);
        }
      });
      pickupAddressInput.addEventListener("blur", () => window.setTimeout(hideSuggestions, 150));
    }

    const changeAddressButton = document.querySelector("[data-pickup-change]");
    if (changeAddressButton && pickupAddressInput) {
      changeAddressButton.addEventListener("click", () => {
        pickupAddressInput.focus();
        pickupAddressInput.select();
      });
    }
    let currentRadius = 5;
    let userPosition = null;

    function currency(value) {
      return "Rp " + new Intl.NumberFormat("id-ID", { maximumFractionDigits: 0 }).format(value);
    }

    function selectedMethod() {
      const choice = deliveryInputs.find((input) => input.checked);
      return choice ? choice.value : "antar_sendiri";
    }

    function updateMode() {
      const pickup = selectedMethod() === "minta_dijemput";
      document.querySelectorAll("[data-self-only]").forEach((section) => { section.hidden = pickup; });
      document.querySelectorAll("[data-pickup-only]").forEach((section) => { section.hidden = !pickup; });
      methodCards.forEach((card) => {
        const input = card.querySelector("[data-delivery-mode]");
        card.classList.toggle("is-selected", Boolean(input && input.checked));
        card.classList.toggle("is-inactive", Boolean(input && !input.checked));
      });
      document.querySelector("[data-incentive-step]").textContent = pickup ? "5" : "4";
      document.querySelector("[data-summary-method]").textContent = pickup ? "Cara menyetor: Minta dijemput" : "Cara menyetor: Antar sendiri";
      document.querySelector("[data-summary-method-note]").textContent = pickup ? "Penjemputan langsung ke rumah" : "Tidak ada biaya penjemputan";
      document.querySelector("[data-summary-point-row]").hidden = pickup;
      document.querySelectorAll("[data-summary-pickup-row]").forEach((row) => { row.hidden = !pickup; });
      submitLabel.textContent = form.dataset.editing === "true"
        ? "Simpan perubahan"
        : (pickup ? "Minta pick-up" : "Buat pengajuan");
      if (pickup) updatePickupSummary();
      window.setTimeout(() => {
        if (pickup && pickupMap) pickupMap.invalidateSize();
        if (!pickup && collectionMap) collectionMap.invalidateSize();
      }, 0);
    }

    deliveryInputs.forEach((input) => input.addEventListener("change", updateMode));

    function rateFromOption(option) {
      if (!option || !option.value) return null;
      const label = option.textContent.trim();
      const marker = " — Rp ";
      const markerIndex = label.lastIndexOf(marker);
      if (markerIndex < 0 || !label.endsWith("/kg")) return null;
      const numeric = label.slice(markerIndex + marker.length, -3).split(".").join("").split(",").join("");
      const parsed = Number(numeric);
      return Number.isFinite(parsed) ? parsed : null;
    }

    function labelFromOption(option) {
      if (!option || !option.value) return "";
      const label = option.textContent.trim();
      const markerIndex = label.lastIndexOf(" — ");
      return markerIndex > -1 ? label.slice(0, markerIndex) : label;
    }

    function itemRows() {
      return Array.from(itemContainer.querySelectorAll("[data-item-form]"));
    }

    function activeItemRows() {
      return itemRows().filter((row) => row.dataset.deleted !== "true");
    }

    function updateItemRow(row) {
      const select = row.querySelector('select[name$="-waste_type"]');
      const weightInput = row.querySelector('input[name$="-estimated_weight"]');
      const option = select && select.options[select.selectedIndex];
      const weight = Number(weightInput && weightInput.value) || 0;
      const label = labelFromOption(option);
      const currentType = select ? select.value : "";
      const snapshotRate = row.dataset.initialWasteType === currentType ? Number(row.dataset.snapshotRate) : NaN;
      const rate = Number.isFinite(snapshotRate) && row.dataset.snapshotRate !== "" ? snapshotRate : rateFromOption(option);
      const subtotal = row.querySelector("[data-item-subtotal]");
      const rateNote = row.querySelector("[data-item-rate-note] strong");
      if (subtotal) subtotal.textContent = rate === null ? "—" : currency(weight * rate);
      if (rateNote) rateNote.textContent = rate === null ? (label ? "Menunggu konfirmasi" : "Menunggu pilihan") : currency(rate) + " / kg";
      return { label, weight, rate, subtotal: rate === null ? null : weight * rate };
    }

    function updateSummaryItems() {
      const summary = document.getElementById("summary-items");
      const empty = summary.querySelector("[data-summary-empty]");
      summary.querySelectorAll("[data-generated-summary-item]").forEach((item) => item.remove());
      let totalWeight = 0;
      let totalReward = 0;
      let completeReward = true;
      let visibleCount = 0;
      activeItemRows().forEach((row) => {
        const item = updateItemRow(row);
        if (!item.label && !item.weight) return;
        if (!item.label) return;
        visibleCount += 1;
        totalWeight += item.weight;
        if (item.rate === null) completeReward = false;
        else totalReward += item.subtotal;
        const wrapper = document.createElement("div");
        wrapper.className = "waste-summary-item";
        wrapper.dataset.generatedSummaryItem = "true";
        const left = document.createElement("div");
        const name = document.createElement("strong");
        name.textContent = item.label;
        const info = document.createElement("span");
        info.textContent = item.weight.toLocaleString("id-ID", { maximumFractionDigits: 2 }) + " kg × " + (item.rate === null ? "tarif menunggu konfirmasi" : currency(item.rate));
        left.append(name, info);
        const amount = document.createElement("b");
        amount.textContent = item.subtotal === null ? "—" : currency(item.subtotal);
        wrapper.append(left, amount);
        summary.append(wrapper);
      });
      if (empty) empty.hidden = visibleCount > 0;
      document.querySelector("[data-total-weight]").textContent = totalWeight.toLocaleString("id-ID", { maximumFractionDigits: 2 }) + " kg";
      document.querySelector("[data-total-reward]").textContent = completeReward && visibleCount ? currency(totalReward) : "Menunggu tarif";
    }

    function syncItemControls() {
      const visible = activeItemRows();
      addItemButton.disabled = visible.length >= maxForms;
      addItemButton.setAttribute("aria-disabled", String(addItemButton.disabled));
      addItemButton.classList.toggle("opacity-50", addItemButton.disabled);
      itemRows().forEach((row) => {
        const button = row.querySelector("[data-remove-item]");
        if (button) button.hidden = visible.length <= 1 && row.dataset.deleted !== "true";
      });
      updateSummaryItems();
    }

    itemContainer.addEventListener("input", (event) => {
      if (event.target.matches('input[name$="-estimated_weight"]')) updateSummaryItems();
    });
    itemContainer.addEventListener("change", (event) => {
      if (event.target.matches('select[name$="-waste_type"]')) updateSummaryItems();
    });
    itemContainer.addEventListener("click", (event) => {
      const button = event.target.closest("[data-remove-item]");
      if (!button) return;
      const row = button.closest("[data-item-form]");
      const deleteField = row.querySelector('input[name$="-DELETE"]');
      if (deleteField) deleteField.checked = true;
      row.dataset.deleted = "true";
      row.hidden = true;
      syncItemControls();
    });
    addItemButton.addEventListener("click", () => {
      if (activeItemRows().length >= maxForms) return;
      const index = Number(totalForms.value);
      const wrapper = document.createElement("div");
      wrapper.innerHTML = emptyTemplate.innerHTML.replaceAll("__prefix__", String(index));
      const row = wrapper.firstElementChild;
      itemContainer.append(row);
      totalForms.value = String(index + 1);
      syncItemControls();
    });
    itemRows().forEach((row) => {
      const deleteField = row.querySelector('input[name$="-DELETE"]');
      if (deleteField && deleteField.checked) {
        row.dataset.deleted = "true";
        row.hidden = true;
      }
    });
    syncItemControls();

    function haversine(lat1, lng1, lat2, lng2) {
      const radians = (value) => value * Math.PI / 180;
      const dLat = radians(lat2 - lat1);
      const dLng = radians(lng2 - lng1);
      const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
        Math.cos(radians(lat1)) * Math.cos(radians(lat2)) *
        Math.sin(dLng / 2) * Math.sin(dLng / 2);
      return 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    function distanceFor(card) {
      if (!userPosition) return null;
      const lat = Number(card.dataset.lat);
      const lng = Number(card.dataset.lng);
      if (!Number.isFinite(lat) || !Number.isFinite(lng) || !card.dataset.lat || !card.dataset.lng) return null;
      return haversine(userPosition.latitude, userPosition.longitude, lat, lng);
    }

    function applyPointFilters() {
      const query = pointSearch.value.trim().toLocaleLowerCase("id");
      let visible = 0;
      let unknownDistances = 0;
      const missingPointCoordinates = pointCards.filter((card) => !card.dataset.lat || !card.dataset.lng).length;
      pointCards.forEach((card) => {
        const text = (card.dataset.pointName + " " + card.dataset.pointAddress).toLocaleLowerCase("id");
        const distance = distanceFor(card);
        const matchesText = !query || text.includes(query);
        const matchesRadius = distance === null || distance <= currentRadius;
        card.hidden = !(matchesText && matchesRadius);
        if (!card.hidden) visible += 1;
        if (distance === null && matchesText) unknownDistances += 1;
        card.dataset.distanceKm = distance === null ? "" : String(distance);
        const distanceLabel = card.querySelector("[data-distance-label]");
        if (distanceLabel) distanceLabel.textContent = distance === null ? "Jarak belum tersedia" : distance.toLocaleString("id-ID", { maximumFractionDigits: 1 }) + " km dari kamu";
      });
      pointMarkers.forEach((marker, id) => {
        const card = pointCards.find((item) => item.dataset.pointId === id);
        if (!card || card.hidden) marker.removeFrom(collectionMap);
        else if (collectionMap && !collectionMap.hasLayer(marker)) marker.addTo(collectionMap);
      });
      document.getElementById("point-no-results").hidden = visible > 0;
      if (unknownDistances && userPosition) {
        radiusNote.textContent = missingPointCoordinates > 0 && missingPointCoordinates === pointCards.length
          ? "Koordinat titik pengumpulan belum diatur; pencarian terdekat dan filter jarak belum tersedia."
          : "Jarak beberapa titik belum tersedia karena koordinatnya belum diatur.";
        radiusNote.hidden = false;
      } else if (!userPosition) {
        radiusNote.textContent = missingPointCoordinates > 0 && missingPointCoordinates === pointCards.length
          ? "Aktifkan lokasi; pencarian jarak juga memerlukan koordinat titik pengumpulan."
          : "Aktifkan lokasi untuk menyaring titik berdasarkan jarak.";
        radiusNote.hidden = false;
      } else {
        radiusNote.hidden = true;
      }
    }

    function selectPoint(id) {
      const card = pointCards.find((item) => item.dataset.pointId === id);
      if (!card || !collectionSelect) return;
      collectionSelect.value = id;
      collectionSelect.dispatchEvent(new Event("change", { bubbles: true }));
      pointCards.forEach((item) => {
        item.classList.toggle("is-selected", item === card);
        item.setAttribute("aria-pressed", String(item === card));
      });
      const marker = pointMarkers.get(id);
      if (marker && collectionMap) {
        if (mapState) mapState.selectPoint(id, { center: true });
      }
      document.querySelector("[data-summary-point]").textContent = card.dataset.pointName;
      const distance = distanceFor(card);
      const distanceText = distance === null ? "" : " · " + distance.toLocaleString("id-ID", { maximumFractionDigits: 1 }) + " km dari kamu";
      const hours = card.dataset.pointHours || "Jam layanan belum tersedia";
      document.querySelector("[data-summary-point-meta]").textContent = card.dataset.pointAddress + " (" + hours + ")" + distanceText;
      if (document.activeElement !== card) card.setAttribute("aria-pressed", "true");
    }

    pointCards.forEach((card) => {
      card.addEventListener("click", () => selectPoint(card.dataset.pointId));
    });
    if (collectionSelect && collectionSelect.value) selectPoint(collectionSelect.value || selectedPointId);
    pointSearch.addEventListener("input", applyPointFilters);
    radiusButtons.forEach((button) => button.addEventListener("click", () => {
      currentRadius = Number(button.dataset.radius);
      radiusButtons.forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
      applyPointFilters();
    }));

    document.getElementById("find-nearest").addEventListener("click", () => {
      if (!navigator.geolocation) {
        gpsState.textContent = "GPS tidak tersedia";
        radiusNote.textContent = "Browser ini tidak menyediakan lokasi. Cari titik berdasarkan nama atau alamat.";
        radiusNote.hidden = false;
        return;
      }
      gpsState.textContent = "Mencari lokasi…";
      navigator.geolocation.getCurrentPosition((position) => {
        userPosition = { latitude: position.coords.latitude, longitude: position.coords.longitude };
        gpsState.textContent = "GPS Aktif";
        const withCoordinates = pointCards.filter((card) => distanceFor(card) !== null);
        withCoordinates.sort((a, b) => distanceFor(a) - distanceFor(b));
        if (withCoordinates.length) selectPoint(withCoordinates[0].dataset.pointId);
        applyPointFilters();
      }, () => {
        gpsState.textContent = "GPS belum aktif";
        radiusNote.textContent = "Lokasi tidak dapat diakses. Kamu tetap bisa mencari dan memilih titik secara manual.";
        radiusNote.hidden = false;
      }, { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 });
    });

    document.querySelector("[data-map-recenter]").addEventListener("click", () => {
      if (collectionSelect && collectionSelect.value) selectPoint(collectionSelect.value);
      else if (collectionMap && pointMarkers.size) collectionMap.fitBounds(Array.from(pointMarkers.values()).map((marker) => marker.getLatLng()), { padding: [24, 24] });
    });

    const incentiveInputs = Array.from(document.querySelectorAll("[data-incentive-choice]"));
    const incentiveCards = Array.from(document.querySelectorAll("[data-incentive-card]"));
    function updateIncentive() {
      incentiveCards.forEach((card) => {
        const input = card.querySelector("[data-incentive-choice]");
        card.classList.toggle("is-selected", Boolean(input && input.checked));
      });
      const selected = incentiveInputs.find((input) => input.checked);
      document.querySelector("[data-summary-incentive]").textContent = selected && selected.value === "donation" ? "akan didonasikan melalui mitra SiLoak" : "akan masuk ke saldo Dompet";
    }
    incentiveInputs.forEach((input) => input.addEventListener("change", updateIncentive));
    updateIncentive();

    function selectedDateText() {
      if (!pickupDateInput) return { short: "", full: "" };
      if (pickupDateInput.value === "custom") {
        if (!customDateInput || !customDateInput.value) return { short: "", full: "" };
        const date = new Date(customDateInput.value + "T00:00:00");
        return {
          short: date.toLocaleDateString("id-ID", { weekday: "short", day: "numeric", month: "short" }),
          full: date.toLocaleDateString("id-ID", { weekday: "long", day: "numeric", month: "short", year: "numeric" }),
        };
      }
      const activeDate = dateButtons.find((button) => button.dataset.dateOption === pickupDateInput.value);
      if (!activeDate) return { short: "", full: "" };
      return { short: activeDate.dataset.dateLabel, full: activeDate.dataset.dateFull };
    }

    function updatePickupSummary() {
      const addressEl = document.querySelector("[data-summary-pickup-address]");
      const addressSubEl = document.querySelector("[data-summary-pickup-address-sub]");
      const scheduleEl = document.querySelector("[data-summary-pickup-schedule]");
      const dateEl = document.querySelector("[data-summary-pickup-date]");
      if (!pickupDateInput || !pickupTimeInput || !addressEl || !scheduleEl) return;
      const parts = splitAddress(pickupAddressInput ? pickupAddressInput.value.trim() : "");
      const detail = addressInput ? addressInput.value.trim() : "";
      addressEl.textContent = parts.title || "Alamat penjemputan belum diisi";
      addressSubEl.textContent = [parts.sub.split(",").slice(0, 2).join(",").trim(), detail ? "(" + detail + ")" : ""].filter(Boolean).join(" ") || "Tentukan lokasi di peta.";
      const dateText = selectedDateText();
      const activeTime = timeButtons.find((button) => button.dataset.timeSlot === pickupTimeInput.value);
      const timeText = activeTime ? activeTime.textContent.trim() : "";
      scheduleEl.textContent = [dateText.short, timeText].filter(Boolean).join(", ") || "Jadwal belum dipilih";
      dateEl.textContent = timeText && dateText.full ? dateText.full : "Pilih tanggal dan rentang waktu.";
    }

    // Slots that already started today cannot be picked (the server checks this too).
    function updateSlotAvailability() {
      const isToday = pickupDateInput && pickupDateInput.value === "today";
      const now = new Date();
      const minutesNow = now.getHours() * 60 + now.getMinutes();
      let available = 0;
      timeButtons.forEach((button) => {
        const [hours, minutes] = button.dataset.timeSlot.split("-")[0].split(":").map(Number);
        const passed = isToday && hours * 60 + minutes <= minutesNow;
        button.disabled = passed;
        if (!passed) available += 1;
        if (passed && pickupTimeInput.value === button.dataset.timeSlot) pickupTimeInput.value = "";
      });
      const passedNote = document.querySelector("[data-slots-passed]");
      if (passedNote) passedNote.hidden = available > 0;
      return available;
    }

    // Late in the day nothing is left for today, so start on tomorrow instead.
    if (pickupDateInput && pickupDateInput.value === "today" && !pickupTimeInput.value && updateSlotAvailability() === 0) {
      pickupDateInput.value = "tomorrow";
    }

    function updateSchedule() {
      if (!pickupDateInput || !pickupTimeInput) return;
      updateSlotAvailability();
      dateButtons.forEach((button) => {
        const active = button.dataset.dateOption === pickupDateInput.value;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", String(active));
      });
      timeButtons.forEach((button) => {
        const active = button.dataset.timeSlot === pickupTimeInput.value;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", String(active));
      });
      if (customDateWrap) customDateWrap.hidden = pickupDateInput.value !== "custom";
      updatePickupSummary();
    }

    dateButtons.forEach((button) => button.addEventListener("click", () => {
      pickupDateInput.value = button.dataset.dateOption;
      updateSchedule();
    }));
    timeButtons.forEach((button) => button.addEventListener("click", () => {
      pickupTimeInput.value = button.dataset.timeSlot;
      updateSchedule();
    }));
    if (addressInput) addressInput.addEventListener("input", updatePickupSummary);
    if (customDateInput) customDateInput.addEventListener("input", updatePickupSummary);

    const useLocationButton = document.querySelector("[data-pickup-use-location]");
    const locationNote = document.querySelector("[data-pickup-location-note]");
    function showLocationNote(message) {
      if (!locationNote) return;
      locationNote.textContent = message;
      locationNote.hidden = !message;
    }
    if (useLocationButton) {
      useLocationButton.addEventListener("click", () => {
        if (!navigator.geolocation) {
          showLocationNote("Browser ini tidak menyediakan lokasi. Klik peta untuk menandai lokasimu.");
          return;
        }
        showLocationNote("Mencari lokasi…");
        if (pickupGpsState) pickupGpsState.textContent = "Mencari lokasi…";
        navigator.geolocation.getCurrentPosition((position) => {
          if (pickupGpsState) pickupGpsState.textContent = "GPS Aktif";
          setPickupLocation(position.coords.latitude, position.coords.longitude, { center: true });
        }, () => {
          if (pickupGpsState) pickupGpsState.textContent = "GPS belum aktif";
          showLocationNote("Lokasi tidak dapat diakses. Cari alamat atau klik peta untuk menandai lokasimu.");
        }, { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 });
      });
    }
    updateAddressCard();

    updateSchedule();

    updateMode();
    applyPointFilters();

    const firstError = form.querySelector(".waste-field-error, .waste-selection-error, .waste-alert[role=alert]");
    if (firstError) firstError.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function initWithin(root) {
    const form = root.id === "waste-submission-form" ? root : root.querySelector && root.querySelector("#waste-submission-form");
    if (!form || form.dataset.ready === "true") return;
    form.dataset.ready = "true";
    init(form);
  }

  if (window.htmx) window.htmx.onLoad(initWithin);
  document.addEventListener("DOMContentLoaded", () => initWithin(document.body));
})();
