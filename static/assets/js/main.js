/* Fahrschule EasyDrive – Seitenlogik (ohne Bibliotheken) */
(function () {
  "use strict";

  var doc = document.documentElement;
  doc.classList.add("js");

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  var clamp = function (v, min, max) { return Math.min(max, Math.max(min, v)); };

  /* ---------- Kopfzeile: Linie erst nach dem Scrollen ---------- */

  var header = document.querySelector("[data-header]");
  function onScroll() {
    var y = window.pageYOffset || doc.scrollTop;
    if (header) header.classList.toggle("is-scrolled", y > 8);
  }
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  /* ---------- Mobiles Menü ---------- */

  var toggle = document.querySelector("[data-menu-toggle]");
  var menu = document.getElementById("mobile-menu");
  if (toggle && menu) {
    var setMenu = function (open) {
      document.body.classList.toggle("menu-open", open);
      toggle.setAttribute("aria-expanded", String(open));
      toggle.querySelector("[data-menu-label]").textContent = open ? "Schließen" : "Menü";
      if (open) menu.removeAttribute("inert"); else menu.setAttribute("inert", "");
    };
    menu.setAttribute("inert", "");
    toggle.addEventListener("click", function () {
      setMenu(toggle.getAttribute("aria-expanded") !== "true");
    });
    menu.addEventListener("click", function (ev) {
      if (ev.target.closest("a")) setMenu(false);
    });
    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && document.body.classList.contains("menu-open")) {
        setMenu(false);
        toggle.focus();
      }
    });
    window.matchMedia("(min-width: 1024px)").addEventListener("change", function (mq) {
      if (mq.matches) setMenu(false);
    });
  }

  /* ---------- Einblenden beim Scrollen ---------- */

  var revealEls = document.querySelectorAll("[data-reveal]");
  if ("IntersectionObserver" in window && revealEls.length) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-in");
          io.unobserve(entry.target);
        }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.12 });
    revealEls.forEach(function (el) { io.observe(el); });
  } else {
    revealEls.forEach(function (el) { el.classList.add("is-in"); });
  }

  /* ---------- Rezensions-Laufband: Karten einmal duplizieren ---------- */

  document.querySelectorAll(".rev-track").forEach(function (track) {
    Array.prototype.slice.call(track.children).forEach(function (card) {
      var copy = card.cloneNode(true);
      copy.setAttribute("aria-hidden", "true");
      track.appendChild(copy);
    });
  });

  /* ---------- Bürozeiten: heutigen Tag markieren, Status anzeigen ---------- */

  function toMinutes(hhmm) {
    var parts = hhmm.split(":");
    return parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10);
  }
  document.querySelectorAll("[data-hours]").forEach(function (table) {
    var now = new Date();
    var day = now.getDay();
    var minutes = now.getHours() * 60 + now.getMinutes();
    var open = false;
    table.querySelectorAll("tr[data-days]").forEach(function (row) {
      var days = row.getAttribute("data-days").split(",").map(Number);
      if (days.indexOf(day) === -1) return;
      row.classList.add("is-today");
      (row.getAttribute("data-slots") || "").split(",").forEach(function (slot) {
        var range = slot.split("-");
        if (range.length === 2 && minutes >= toMinutes(range[0]) && minutes < toMinutes(range[1])) open = true;
      });
    });
    var status = document.querySelector("[data-status]");
    if (status) {
      status.textContent = open ? "Jetzt geöffnet" : "Gerade geschlossen";
      status.classList.toggle("is-open", open);
    }
  });

  /* ---------- Kontaktformulare: Nachricht als E-Mail vorbereiten ---------- */

  document.querySelectorAll("form[data-mailto]").forEach(function (form) {
    var statusBox = form.querySelector("[data-form-status]");

    function fieldOf(el) { return el.closest(".field"); }

    function validate(el) {
      var field = fieldOf(el);
      if (!field) return true;
      var ok = el.checkValidity();
      if (ok) field.removeAttribute("data-invalid");
      else field.setAttribute("data-invalid", "");
      el.setAttribute("aria-invalid", String(!ok));
      return ok;
    }

    form.querySelectorAll("input, select, textarea").forEach(function (el) {
      el.addEventListener("blur", function () {
        if (el.value !== "") validate(el);
      });
      el.addEventListener("input", function () {
        if (fieldOf(el) && fieldOf(el).hasAttribute("data-invalid")) validate(el);
      });
    });

    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var firstInvalid = null;
      form.querySelectorAll("input, select, textarea").forEach(function (el) {
        if (!validate(el) && !firstInvalid) firstInvalid = el;
      });
      if (firstInvalid) {
        firstInvalid.focus();
        return;
      }

      var data = new FormData(form);
      var get = function (key) { return (data.get(key) || "").toString().trim(); };
      var lines = [
        "Name: " + get("name"),
        "E-Mail: " + get("email"),
        "Telefon: " + (get("telefon") || "-")
      ];
      if (form.querySelector("[name=standort]")) lines.push("Wunschstandort: " + (get("standort") || "-"));
      lines.push("Führerscheinklasse: " + (get("klasse") || "-"));
      lines.push("", "Nachricht:", get("nachricht"));

      var subject = form.getAttribute("data-subject") || "Anfrage über die Website";
      if (get("klasse")) subject += " (Klasse " + get("klasse") + ")";

      var to = form.getAttribute("data-mailto");
      var href = "mailto:" + to +
        "?subject=" + encodeURIComponent(subject) +
        "&body=" + encodeURIComponent(lines.join("\r\n"));

      if (statusBox) {
        statusBox.innerHTML = "";
        statusBox.appendChild(document.createTextNode("Dein E-Mail-Programm sollte sich jetzt mit der fertigen Nachricht öffnen. Falls nicht, schreib uns direkt an "));
        var link = document.createElement("a");
        link.href = "mailto:" + to;
        link.textContent = to;
        statusBox.appendChild(link);
        statusBox.appendChild(document.createTextNode("."));
        statusBox.classList.add("is-visible");
      }
      window.location.href = href;
    });
  });

  /* ---------- Jahr in der Fußzeile ---------- */

  document.querySelectorAll("[data-year]").forEach(function (el) {
    el.textContent = String(new Date().getFullYear());
  });
})();
