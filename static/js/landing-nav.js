(function () {
  "use strict";

  const nav = document.querySelector("[data-landing-nav]");
  if (!nav) return;

  if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    document.documentElement.style.scrollBehavior = "smooth";
  }

  const links = Array.from(nav.querySelectorAll("[data-landing-nav-link]"));
  const sectionIds = Array.from(new Set(links.map((link) => link.dataset.landingNavLink)));
  const sections = sectionIds.map((id) => document.getElementById(id)).filter(Boolean);
  if (!links.length || !sections.length) return;

  function setActive(id) {
    links.forEach((link) => {
      link.setAttribute("aria-current", String(link.dataset.landingNavLink === id));
    });
  }

  function updateFromScroll() {
    const header = nav.closest("header");
    const activeLine = (header ? header.getBoundingClientRect().height : nav.getBoundingClientRect().height) + 32;
    let currentId = sections[0].id;

    sections.forEach((section) => {
      if (section.getBoundingClientRect().top <= activeLine) currentId = section.id;
    });

    setActive(currentId);
  }

  let frame = null;
  let pendingTarget = null;
  let settleTimer = null;
  function scheduleUpdate() {
    if (pendingTarget !== null) return;
    if (frame !== null) return;
    frame = window.requestAnimationFrame(() => {
      frame = null;
      updateFromScroll();
    });
  }

  function onScroll() {
    if (pendingTarget === null) {
      scheduleUpdate();
      return;
    }

    window.clearTimeout(settleTimer);
    settleTimer = window.setTimeout(() => {
      pendingTarget = null;
      updateFromScroll();
    }, 180);
  }

  nav.addEventListener("click", (event) => {
    const link = event.target.closest("[data-landing-nav-link]");
    if (!link) return;

    pendingTarget = link.dataset.landingNavLink;
    setActive(pendingTarget);
    window.clearTimeout(settleTimer);
    settleTimer = window.setTimeout(() => {
      pendingTarget = null;
      updateFromScroll();
    }, 180);
  });

  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", scheduleUpdate);
  window.addEventListener("hashchange", scheduleUpdate);
  updateFromScroll();
})();
