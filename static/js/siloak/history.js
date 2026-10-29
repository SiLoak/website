// History page: checkbox selection for bulk cancel.
// Uses event delegation, so it keeps working after HTMX swaps the results.
(function () {
  "use strict";

  function selectionState(form) {
    const boxes = Array.from(form.querySelectorAll("[data-select-entry]"));
    const checked = boxes.filter((box) => box.checked);
    return { boxes, checked };
  }

  function refresh(form) {
    if (!form) return;
    const { boxes, checked } = selectionState(form);
    const button = form.querySelector("[data-bulk-submit]");
    const count = form.querySelector("[data-selected-count]");
    const selectAll = form.querySelector("[data-select-all]");
    if (count) count.textContent = String(checked.length);
    if (button) button.disabled = checked.length === 0;
    if (selectAll) {
      selectAll.disabled = boxes.length === 0;
      selectAll.checked = boxes.length > 0 && checked.length === boxes.length;
      selectAll.indeterminate = checked.length > 0 && checked.length < boxes.length;
    }
  }

  document.addEventListener("change", (event) => {
    const form = event.target.closest("[data-bulk-form]");
    if (!form) return;
    if (event.target.matches("[data-select-all]")) {
      selectionState(form).boxes.forEach((box) => { box.checked = event.target.checked; });
    }
    refresh(form);
  });

  // Optimistic cancel: show the row as cancelled at once, and roll back if
  // the server refuses. A successful response replaces the row anyway.
  const OPTIMISTIC_STATE = new WeakMap();

  function optimisticRow(event) {
    const trigger = event.detail.elt;
    if (!trigger || !trigger.matches("[data-optimistic-cancel]")) return null;
    return trigger.closest("[data-entry-row]");
  }

  document.addEventListener("htmx:beforeRequest", (event) => {
    const row = optimisticRow(event);
    if (!row) return;
    const badge = row.querySelector("[data-status-badge]");
    const checkbox = row.querySelector("[data-select-entry]");
    OPTIMISTIC_STATE.set(row, { badgeText: badge.textContent, badgeClass: badge.className, rowClass: row.className });
    badge.textContent = "Dibatalkan";
    badge.className = "history-badge is-canceled";
    row.className = "history-row is-canceled is-pending-change";
    if (checkbox) {
      checkbox.checked = false;
      checkbox.hidden = true;
    }
    event.detail.elt.hidden = true;
    refresh(row.closest("[data-bulk-form]"));
  });

  function rollback(event) {
    const row = optimisticRow(event);
    const saved = row && OPTIMISTIC_STATE.get(row);
    if (!saved) return;
    const badge = row.querySelector("[data-status-badge]");
    badge.textContent = saved.badgeText;
    badge.className = saved.badgeClass;
    row.className = saved.rowClass;
    const checkbox = row.querySelector("[data-select-entry]");
    if (checkbox) checkbox.hidden = false;
    event.detail.elt.hidden = false;
    OPTIMISTIC_STATE.delete(row);
  }

  document.addEventListener("htmx:responseError", rollback);
  document.addEventListener("htmx:sendError", rollback);

  // Keep the selection counter right after HTMX swaps the results.
  document.addEventListener("htmx:afterSwap", () => refresh(document.querySelector("[data-bulk-form]")));
  document.addEventListener("DOMContentLoaded", () => refresh(document.querySelector("[data-bulk-form]")));
})();
