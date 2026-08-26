(() => {
  "use strict";

  document.addEventListener("click", async (event) => {
    const copyButton = event.target.closest("[data-copy-value]");
    if (copyButton) {
      const label = copyButton.querySelector("span");
      try {
        await navigator.clipboard.writeText(copyButton.dataset.copyValue);
        copyButton.classList.add("is-copied");
        if (label) label.textContent = "已复制";
        window.setTimeout(() => {
          copyButton.classList.remove("is-copied");
          if (label) label.textContent = "复制";
        }, 1600);
      } catch (_error) {
        if (label) label.textContent = "复制失败";
      }
      return;
    }

    const toggle = event.target.closest("[data-id-toggle]");
    if (toggle) {
      const container = toggle.closest("[data-identifier]");
      const value = container?.querySelector("[data-id-value]");
      if (!value) return;
      const expanded = value.classList.toggle("is-expanded");
      value.textContent = expanded ? value.dataset.full : value.dataset.short;
      toggle.textContent = expanded ? "收起" : "展开";
      return;
    }

    const logToggle = event.target.closest("[data-log-level]");
    if (logToggle) {
      const pressed = logToggle.getAttribute("aria-pressed") === "true";
      logToggle.setAttribute("aria-pressed", String(!pressed));
      const viewer = logToggle.closest(".lv");
      const enabled = new Set(
        [...viewer.querySelectorAll("[data-log-level][aria-pressed='true']")].map(
          (button) => button.dataset.logLevel,
        ),
      );
      viewer.querySelectorAll("[data-log-row]").forEach((row) => {
        const normalized = row.dataset.logRow === "CRITICAL" ? "ERROR" : row.dataset.logRow;
        row.hidden = !enabled.has(normalized);
      });
    }
  });

  document.addEventListener("change", (event) => {
    const input = event.target.closest("[data-auto-submit]");
    if (input?.files?.length) input.form.requestSubmit();
  });
})();
