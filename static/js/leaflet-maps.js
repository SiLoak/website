(function () {
  "use strict";

  const DEFAULT_CENTER = [-6.4025, 106.7942];
  const TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";

  function parsePoints(element) {
    const source = document.getElementById(element.dataset.points);
    if (!source) return [];
    try {
      const points = JSON.parse(source.textContent);
      return points.map((point) => ({
        ...point,
        latitude: point.latitude === "" || point.latitude == null ? NaN : Number(point.latitude),
        longitude: point.longitude === "" || point.longitude == null ? NaN : Number(point.longitude),
      })).filter(hasCoordinates);
    } catch (error) {
      console.error("Invalid map point data", error);
      return [];
    }
  }

  function hasCoordinates(point) {
    return Number.isFinite(point.latitude) && Number.isFinite(point.longitude)
      && point.latitude >= -90 && point.latitude <= 90
      && point.longitude >= -180 && point.longitude <= 180;
  }

  function pointIcon(selected) {
    return L.divIcon({
      className: selected ? "siloak-marker-icon is-selected" : "siloak-marker-icon",
      html: "<span></span>",
      iconSize: [30, 38],
      iconAnchor: [15, 36],
      popupAnchor: [0, -34],
    });
  }

  function createMap(element, points, options = {}) {
    if (!window.L || !element) return null;
    const map = L.map(element, { scrollWheelZoom: false }).setView(options.center || DEFAULT_CENTER, options.zoom || 12);
    L.tileLayer(TILE_URL, {
      maxZoom: 19,
      referrerPolicy: "strict-origin-when-cross-origin",
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
    }).addTo(map);

    const markers = new Map();
    const bounds = [];
    let selectedId = null;
    points.map((point) => ({
      ...point,
      latitude: point.latitude === "" || point.latitude == null ? NaN : Number(point.latitude),
      longitude: point.longitude === "" || point.longitude == null ? NaN : Number(point.longitude),
    })).filter(hasCoordinates).forEach((point) => {
      const marker = L.marker([point.latitude, point.longitude], { icon: pointIcon(false) }).addTo(map);
      const popup = document.createElement("div");
      const name = document.createElement("strong");
      name.textContent = point.name || "Titik pengumpulan";
      popup.append(name);
      if (point.address) {
        const address = document.createElement("div");
        address.textContent = point.address;
        popup.append(address);
      }
      if (point.operating_hours) {
        const hours = document.createElement("div");
        hours.textContent = point.operating_hours;
        popup.append(hours);
      }
      marker.bindPopup(popup);
      if (point.id !== undefined) markers.set(String(point.id), marker);
      bounds.push([point.latitude, point.longitude]);
    });
    if (bounds.length > 1) map.fitBounds(bounds, { padding: [24, 24], maxZoom: 15 });
    else if (bounds.length === 1) map.setView(bounds[0], options.pointZoom || 15);
    function selectPoint(id, { center = false, openPopup = true } = {}) {
      const key = String(id);
      const marker = markers.get(key);
      if (!marker) return false;
      if (selectedId !== null && markers.has(selectedId)) {
        markers.get(selectedId).setIcon(pointIcon(false)).setZIndexOffset(0);
      }
      selectedId = key;
      marker.setIcon(pointIcon(true)).setZIndexOffset(1000);
      if (center) map.setView(marker.getLatLng(), Math.max(map.getZoom(), 15));
      if (openPopup) marker.openPopup();
      return true;
    }

    return { map, markers, selectPoint };
  }

  function distanceKm(fromLat, fromLng, toLat, toLng) {
    const radians = (degrees) => degrees * Math.PI / 180;
    const latDelta = radians(toLat - fromLat);
    const lngDelta = radians(toLng - fromLng);
    const value = Math.sin(latDelta / 2) ** 2
      + Math.cos(radians(fromLat)) * Math.cos(radians(toLat)) * Math.sin(lngDelta / 2) ** 2;
    return 6371 * 2 * Math.atan2(Math.sqrt(value), Math.sqrt(1 - value));
  }

  function bindNearestLocationButtons() {
    document.querySelectorAll("[data-find-nearest]").forEach((button) => {
      button.addEventListener("click", () => {
        const mapElement = document.getElementById(button.dataset.findNearest);
        const state = mapElement && mapElement._siloakMapState;
        const status = document.getElementById(button.dataset.findNearestStatus);
        if (!state || !status) return;
        if (!state.points.length) {
          status.textContent = "Belum ada titik pengumpulan dengan koordinat yang tersedia.";
          return;
        }
        if (!navigator.geolocation) {
          status.textContent = "GPS tidak tersedia di browser ini. Izinkan akses lokasi dan coba lagi.";
          return;
        }

        button.disabled = true;
        status.textContent = "Sedang mencari titik terdekat…";
        navigator.geolocation.getCurrentPosition((position) => {
          const latitude = position.coords.latitude;
          const longitude = position.coords.longitude;
          const nearest = state.points.map((point) => ({
            point,
            distance: distanceKm(latitude, longitude, point.latitude, point.longitude),
          })).sort((a, b) => a.distance - b.distance)[0];
          state.selectPoint(nearest.point.id, { center: true });
          status.textContent = "Titik terdekat: " + nearest.point.name + " ("
            + nearest.distance.toLocaleString("id-ID", { maximumFractionDigits: 1 }) + " km).";
          button.disabled = false;
        }, () => {
          status.textContent = "Lokasi tidak dapat diakses. Izinkan akses GPS lalu coba lagi.";
          button.disabled = false;
        }, { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 });
      });
    });
  }

  window.SiloakMaps = { createMap, parsePoints };

  function initializeDeclarativeMaps() {
    document.querySelectorAll("[data-leaflet-map][data-points]").forEach((element) => {
      const points = parsePoints(element);
      const result = createMap(element, points);
      if (!result) return;
      result.points = points;
      element._siloakMapState = result;
      element.dispatchEvent(new CustomEvent("siloak-map-ready", { detail: { ...result, points } }));
    });
    bindNearestLocationButtons();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initializeDeclarativeMaps);
  else initializeDeclarativeMaps();
})();
