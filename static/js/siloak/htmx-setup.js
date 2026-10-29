// Shared HTMX behaviour for every page: toasts and readable error messages.
(function () {
  "use strict";

  const TOAST_DURATION_MS = 4500;
  const STATUS_MESSAGES = {
    401: "Sesi kamu berakhir. Silakan masuk lagi.",
    403: "Kamu tidak memiliki akses untuk aksi ini.",
    404: "Data tidak ditemukan. Mungkin sudah dihapus.",
    409: "Data sudah berubah. Muat ulang halaman lalu coba lagi.",
    429: "Terlalu banyak permintaan. Tunggu sebentar lalu coba lagi.",
  };

  function showToast(message, level) {
    const region = document.getElementById("toast-region");
    if (!region || !message) return;
    const toast = document.createElement("div");
    toast.className = "siloak-toast is-" + (level || "success");
    toast.setAttribute("role", level === "error" ? "alert" : "status");
    toast.textContent = message;
    region.append(toast);
    window.setTimeout(() => toast.classList.add("is-leaving"), TOAST_DURATION_MS);
    window.setTimeout(() => toast.remove(), TOAST_DURATION_MS + 400);
  }

  function messageFromResponse(xhr) {
    const text = (xhr.responseText || "").trim();
    try {
      const data = JSON.parse(text);
      if (data && data.error) return data.error;
    } catch (error) {
      // Plain-text responses (such as the rate limiter's) are shown as they are.
      if (text && text.length < 200 && !text.startsWith("<")) return text;
    }
    return STATUS_MESSAGES[xhr.status] || "Terjadi kesalahan. Coba lagi.";
  }

  document.body.addEventListener("showToast", (event) => {
    showToast(event.detail.message, event.detail.level);
  });

  document.body.addEventListener("htmx:responseError", (event) => {
    showToast(messageFromResponse(event.detail.xhr), "error");
  });

  document.body.addEventListener("htmx:sendError", () => {
    showToast("Tidak dapat terhubung ke server. Periksa koneksimu.", "error");
  });

  window.SiloakToast = { show: showToast };
})();
