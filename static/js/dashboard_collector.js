const configElement = document.getElementById("pickup-config");
const BASE_ENDPOINT = configElement.dataset.baseEndpoint;
const NEW_BASE_ENDPOINT = configElement.dataset.newBaseEndpoint;
const CSRF_TOKEN = configElement.dataset.csrfToken;
const DETAIL_URL_TEMPLATE = configElement.dataset.detailUrlTemplate;
const ACCEPT_URL_TEMPLATE = configElement.dataset.acceptUrlTemplate;

let pickupAbortController;
let newPickupAbortController;

// Elemen DOM
const loadingState = document.getElementById("loading");
const errorState = document.getElementById("error");
const emptyState = document.getElementById("empty");
const pickupGridContainer = document.getElementById("pickup-grid");

const newLoadingState = document.getElementById("new-loading");
const newErrorState = document.getElementById("new-error");
const newEmptyState = document.getElementById("new-empty");
const newPickupGridContainer = document.getElementById("new-pickup-grid");

const helloSubmsg = document.getElementById("hello-submsg");
const todaysPickupsCard = document.getElementById("todays-pickups-card");
const totalWeightCard = document.getElementById("total-weight-card");
const activePickupsCard = document.getElementById("active-pickups-card");
const completedPickupsCard = document.getElementById("completed-pickups-card");
const todaysPickupsStatCard = document.getElementById("todays-pickups-stat-card");
const todaysWeightCard = document.getElementById("todays-weight-card");
const pickupsCount = document.getElementById("pickups-count");
const newPickupsCount = document.getElementById("new-pickups-count");

// Menyembunyikan/Menampilkan section halaman
function displayPickupSection({ showLoading = false, showError = false, showEmpty = false, showGrid = false }) {
  loadingState.classList.toggle('hidden', !showLoading);
  errorState.classList.toggle('hidden', !showError);
  emptyState.classList.toggle('hidden', !showEmpty);
  pickupGridContainer.classList.toggle('hidden', !showGrid);
}

function displayNewPickupSection({ showLoading = false, showError = false, showEmpty = false, showGrid = false }) {
  newLoadingState.classList.toggle('hidden', !showLoading);
  newErrorState.classList.toggle('hidden', !showError);
  newEmptyState.classList.toggle('hidden', !showEmpty);
  newPickupGridContainer.classList.toggle('hidden', !showGrid);
}

// Formatting tanggal
function formatDate(date) {
  return new Intl.DateTimeFormat("id-ID", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "Asia/Jakarta",
  }).format(new Date(date));
}

const todayDate = new Intl.DateTimeFormat("en-CA", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  timeZone: "Asia/Jakarta",
}).format(new Date());
const today = formatDate(todayDate);
const now = new Date();

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

function getTodaysPickups(pickupData) {
  return pickupData.filter((pickup) => {
    const scheduledDate = formatDate(pickup.fields.scheduled_date);

    return scheduledDate === today;
  });
}

function getActivePickups(pickupData) {
  return pickupData.filter((pickup) => {
    return ["ASSIGNED", "ON_THE_WAY", "ARRIVED", "WEIGHING"].includes(pickup.fields.status);
  })
}

function getCompletedPickups(pickupData) {
  return pickupData.filter((pickup) => {
    const completedAt = pickup.fields.completed_at ? new Date(pickup.fields.completed_at) : null;
    return (
      completedAt !== null &&
      !Number.isNaN(completedAt.getTime()) &&
      completedAt.getMonth() === now.getMonth() &&
      completedAt.getFullYear() === now.getFullYear() &&
      pickup.fields.status === "COMPLETED"
    )
  })
}

function getUncompletedPickups(pickupData) {
  return pickupData.filter((pickup) => {
    return (
      pickup.fields.status !== "COMPLETED" &&
      pickup.fields.status !== "CANCELLED" &&
      pickup.fields.status !== "FAILED"
    )
  })
}

function getTotalWeight(pickupData) {
  let totalWeight = 0;
  pickupData.forEach((pickup) => {
    if (pickup.fields.status === "COMPLETED") {
      const weight = Number(pickup.fields.actual_weight);
      if (Number.isFinite(weight)) {
        totalWeight += weight;
      }
    }
  })
  return totalWeight;
}

function getTodaysStat(pickupData) {
  let todaysCompletedPickups = 0;
  let todaysActivePickups = 0;
  let todaysWaitingPickups = 0;

  pickupData.forEach((pickup) => {
    if (pickup.fields.status === "COMPLETED") {
      todaysCompletedPickups++;
    } else if (["WEIGHING", "ARRIVED", "ON_THE_WAY"].includes(pickup.fields.status)) {
      todaysActivePickups++;
    } else if (pickup.fields.status === "ASSIGNED") {
      todaysWaitingPickups++;
    }
  })

  return [todaysCompletedPickups, todaysActivePickups, todaysWaitingPickups];
}

function changeStatusBadge(pickupStatus) {
  let message = "";
  let color = "";
  switch (pickupStatus) {
    case "ASSIGNED":
      message = "Kurir Ditugaskan";
      color = "bg-status-warning-bg text-status-warning-text";
      break;
    case "ON_THE_WAY":
      message = "Kurir Dalam Perjalanan";
      color = "bg-status-warning-bg text-status-warning-text";
      break;
    case "ARRIVED":
      message = "Kurir Tiba";
      color = "bg-status-warning-bg text-status-warning-text";
      break;
    case "WEIGHING":
      message = "Penimbangan dan Verifikasi";
      color = "bg-status-warning-bg text-status-warning-text";
      break;
    case "COMPLETED":
      message = "Selesai";
      color = "bg-green-100 text-green-700"
      break;
    default:
      message = "Menunggu Penugasan";
      color = "bg-gray-100 text-gray-700";
      break;
  }
  return [message, color];
}

// Membuat elemen row untuk pickup list
function buildPickupRowElement(item) {
  const pickup = item.fields;
  const pickupId = item.pk;

  const articleElement = document.createElement("article");
  articleElement.className = "h-16 flex items-center justify-between py-2 transition-colors hover:bg-surface-soft/40 px-2 rounded-lg -mx-2"

  const detailUrl = DETAIL_URL_TEMPLATE.replace('00000000-0000-0000-0000-000000000000', pickupId);
  const itemSummary = (pickup.items || []).join(", ") || "Barang belum dicatat";
  const weight = pickup.status === "COMPLETED" ? pickup.actual_weight : pickup.estimated_weight;

  // Komponen row
  const completeRowHtml = `
    <div class="flex items-center gap-3 min-w-0">
      <div class="w-9 h-9 rounded-full bg-status-warning-bg text-status-warning-text flex items-center justify-center shrink-0">
        <span class="font-symbols font-normal not-italic leading-none tracking-normal normal-case whitespace-nowrap antialiased [font-feature-settings:'liga'] [-webkit-font-feature-settings:'liga'] text-[19px]">local_shipping</span>
      </div>
      <div class="min-w-0">
        <p class="font-label-md text-label-md font-medium text-text-primary truncate">${pickupId}</p>
        <p class="font-label-md text-label-md text-text-body/90 truncate">${escapeHtml(pickup.address_detail)}</p>
        <p class="font-label-sm text-label-sm text-text-body/70">${formatDate(pickup.scheduled_date)} • ${escapeHtml(pickup.time_slot)} WIB • ${escapeHtml(weight || "0")} kg · ${escapeHtml(itemSummary)}</p>
      </div>
    </div>
    <div class="shrink-0 pl-3 flex items-center gap-3">
      <span class="${changeStatusBadge(pickup.status)[1]} font-label-sm text-label-sm px-2.5 py-1 rounded-full font-medium">${changeStatusBadge(pickup.status)[0]}</span>
      <a class="font-label-md text-label-md font-semibold text-primary-container hover:underline inline-flex items-center gap-1 group" href="${detailUrl}">
        Detail
        <span class="font-symbols font-normal not-italic leading-none tracking-normal normal-case whitespace-nowrap antialiased [font-feature-settings:'liga'] [-webkit-font-feature-settings:'liga'] text-[16px] group-hover:translate-x-0.5 transition-transform">arrow_forward</span>
      </a>
    </div>
  `;

  articleElement.innerHTML = completeRowHtml;
  return articleElement;
}

// Membuat elemen row untuk new pickup list
function buildNewPickupRowElement(item) {
  const newPickup = item.fields;
  const newPickupId = item.pk;

  const articleElement = document.createElement("article");
  articleElement.className = "h-16 flex items-center justify-between py-2 transition-colors hover:bg-surface-soft/40 px-2 rounded-lg -mx-2"

  const detailUrl = DETAIL_URL_TEMPLATE.replace('00000000-0000-0000-0000-000000000000', newPickupId);
  const acceptUrl = ACCEPT_URL_TEMPLATE.replace('00000000-0000-0000-0000-000000000000', newPickupId);
  const itemSummary = (newPickup.items || []).join(", ") || "Barang belum dicatat";

  // Komponen row
  const completeRowHtml = `
    <div class="flex items-center gap-3 min-w-0">
      <div class="w-9 h-9 rounded-full bg-surface-soft text-text-body flex items-center justify-center shrink-0">
        <span class="font-symbols font-normal not-italic leading-none tracking-normal normal-case whitespace-nowrap antialiased [font-feature-settings:'liga'] [-webkit-font-feature-settings:'liga'] text-[19px]">hourglass_top</span>
      </div>
      <div class="min-w-0">
        <p class="font-label-md text-label-md font-medium text-text-primary truncate">${newPickupId}</p>
        <p class="font-label-md text-label-md text-text-body/90 truncate">${escapeHtml(newPickup.address_detail)}</p>
        <p class="font-label-sm text-label-sm text-text-body/70">${formatDate(newPickup.scheduled_date)} • ${escapeHtml(newPickup.time_slot)} WIB • ${escapeHtml(newPickup.estimated_weight)} kg · ${escapeHtml(itemSummary)}</p>
      </div>
    </div>
    <div class="shrink-0 pl-3 flex items-center gap-3">
      <span class="bg-surface-soft text-text-body font-label-sm text-label-sm px-2.5 py-1 rounded-full font-medium">${changeStatusBadge(newPickup.status)[0]}</span>
      <a class="font-label-md text-label-md font-semibold text-primary-container hover:underline inline-flex items-center gap-1 group" href="${detailUrl}"> Detail <span class="font-symbols font-normal not-italic leading-none tracking-normal normal-case whitespace-nowrap antialiased [font-feature-settings:'liga'] [-webkit-font-feature-settings:'liga'] text-[16px] group-hover:translate-x-0.5 transition-transform">arrow_forward</span>
      </a>
      <form id="accept-form" method="post" action="${acceptUrl}">
        <input type="hidden" name="csrfmiddlewaretoken" value="${CSRF_TOKEN}">
        <button class="h-9 px-4 rounded-lg bg-primary text-on-primary font-label-md text-label-md font-semibold inline-flex items-center gap-1.5 hover:bg-tertiary transition-colors shadow-sm" type="submit">
          <span class="font-symbols font-normal not-italic leading-none tracking-normal normal-case whitespace-nowrap antialiased [font-feature-settings:'liga'] [-webkit-font-feature-settings:'liga'] text-[18px]">check</span>
          Terima
        </button>
      </form>
    </div>
  `;

  articleElement.innerHTML = completeRowHtml;
  return articleElement;
}

// fetch pickup list
async function fetchPickupList() {
  if (pickupAbortController) pickupAbortController.abort();
  pickupAbortController = new AbortController();

  try {
    displayPickupSection({ showLoading: true });

    const url = BASE_ENDPOINT;

    const response = await fetch(url, {
      headers: { 'Accept': 'application/json', 'X-CSRFToken': CSRF_TOKEN },
      signal: pickupAbortController.signal,
    });

    if (!response.ok) throw new Error("Gagal mengambil data.");

    const pickupData = await response.json();

    const uncompletedPickupData = getUncompletedPickups(pickupData);

    if (uncompletedPickupData.length === 0) {
      displayPickupSection({ showEmpty: true });
    } else {
      pickupGridContainer.innerHTML = "";
      uncompletedPickupData.forEach(item => {
        pickupGridContainer.appendChild(buildPickupRowElement(item));
      })

      displayPickupSection({ showGrid: true });
    }

    const todaysPickups = getTodaysPickups(pickupData);
    todaysPickupsCard.textContent = todaysPickups.length;

    const totalWeight = getTotalWeight(todaysPickups);
    totalWeightCard.textContent = totalWeight;

    const activePickups = getActivePickups(pickupData);
    activePickupsCard.textContent = activePickups.length;

    const completedPickups = getCompletedPickups(pickupData);
    completedPickupsCard.textContent = completedPickups.length;

    const [todaysCompletedPickups, todaysActivePickups, todaysWaitingPickups] = getTodaysStat(todaysPickups);
    todaysPickupsStatCard.textContent = `${todaysCompletedPickups} selesai • ${todaysActivePickups} aktif • ${todaysWaitingPickups} menunggu`;
    todaysWeightCard.textContent = `Dari ${todaysCompletedPickups} pick up selesai`;

    pickupsCount.textContent = `${pickupData.length} tugas`;
    helloSubmsg.textContent = `Ada ${todaysPickups.length - todaysCompletedPickups} tugas jemput yang belum selesai hari ini.`
  } catch (error) {
    if (error.name === 'AbortError') return;
    console.error('Error loading pickup:', error);
    displayPickupSection({ showError: true });
  }
}

newPickupGridContainer.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-accept-url]");
  if (!button) return;
  button.disabled = true;
  try {
    const response = await fetch(button.dataset.acceptUrl, {
      method: "POST",
      headers: { "X-CSRFToken": CSRF_TOKEN, "Accept": "application/json" },
      mode: "same-origin",
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Pickup tidak dapat diterima.");
    await Promise.all([fetchPickupList(), fetchNewPickupList()]);
  } catch (error) {
    newErrorState.textContent = error.message || "Pickup tidak dapat diterima.";
    displayNewPickupSection({ showError: true });
    button.disabled = false;
  }
});

// fetch new pickup list
async function fetchNewPickupList() {
  if (newPickupAbortController) newPickupAbortController.abort();
  newPickupAbortController = new AbortController();

  try {
    displayNewPickupSection({ showLoading: true });

    const url = NEW_BASE_ENDPOINT;

    const response = await fetch(url, {
      headers: { 'Accept': 'application/json' },
      signal: newPickupAbortController.signal,
    });

    if (!response.ok) throw new Error("Gagal mengambil data.");

    const newPickupData = await response.json();

    if (newPickupData.length === 0) {
      displayNewPickupSection({ showEmpty: true });
    } else {
      newPickupGridContainer.innerHTML = "";
      newPickupData.forEach(item => {
        newPickupGridContainer.appendChild(buildNewPickupRowElement(item));
      })
      displayNewPickupSection({ showGrid: true });
    }

    newPickupsCount.textContent = `${newPickupData.length} permintaan`;
  } catch (error) {
    if (error.name === 'AbortError') return;
    console.error('Error loading new pickup:', error);
    displayNewPickupSection({ showError: true });
  }
}

document.addEventListener("submit", async (event) => {
  const form = event.target.closest(".accept-form");

  if (!form) return;

  event.preventDefault();

  try {
    const response = await fetch(form.action, {
      method: "POST",
      headers: {
        "X-CSRFToken": CSRF_TOKEN,
        "X-Requested-With": "XMLHttpRequest",
      },
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.message || "Gagal menerima pickup.");
    }

    // Hapus card setelah berhasil
    form.closest(".pickup-card")?.remove();

  } catch (error) {
    console.error(error);
  }
});

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    fetchPickupList();
    fetchNewPickupList();
  });
} else {
  fetchPickupList();
  fetchNewPickupList();
}
