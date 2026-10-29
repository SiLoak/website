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

  // The filter form must not react to the bulk-form checkboxes.
  document.addEventListener("htmx:afterSwap", () => refresh(document.querySelector("[data-bulk-form]")));
  document.addEventListener("DOMContentLoaded", () => refresh(document.querySelector("[data-bulk-form]")));
})();
