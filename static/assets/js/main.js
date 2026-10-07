/* Fahrschule EasyDrive – Seitenlogik (ohne Bibliotheken) */
(function () {
  "use strict";

  var doc = document.documentElement;
  doc.classList.add("js");

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  var clamp = function (v, min, max) { return Math.min(max, Math.max(min, v)); };

  /* ---------- Kopfzeile + Kamerafahrt im Hero (Bildfolge auf Leinwand) ----------
     Prinzip aus dem scroll-world-Skill: Der Scroll gibt nur das Ziel vor, die Kamera läuft per
     requestAnimationFrame weich hinterher. Die freigestellte Bildfolge (data-seq) wird Bild für
     Bild gezeichnet; dabei wandert der Bildausschnitt vom Startbild unten rechts bis dorthin,
     wo das Auto im Leistungsbild steht. Ganz am Ende übernimmt das scharfe Leistungsbild. */

  var header = document.querySelector("[data-header]");
  var journey = document.querySelector("[data-journey]");
  var FAHRT = 1.6;        // Länge der Kamerafahrt in Bildschirmhöhen
  var NACHLAUF = 0.12;    // 0 bis 1: kleiner = weicher, träger
  var ENDE = 0.9;         // ab hier übernimmt das Leistungsbild
  var target = 0;
  var current = 0;
  var running = false;

  // Mehrere Fassungen: quer (Laptop, Tablet quer), hoch (Handy hochkant, falls vorhanden),
  // jeweils mit leichter Bildgröße fürs Handy. Gewählt wird nach Bildschirm.
  var saetze = null;
  if (journey && journey.getAttribute("data-seq")) {
    try { saetze = JSON.parse(journey.getAttribute("data-seq")); } catch (err) { saetze = null; }
  }
  var seq = null;
  var satzSchluessel = "";
  function waehleSatz() {
    if (!saetze || !saetze.quer) return false;
    var klein = window.innerWidth <= 900;
    var hochkant = window.innerHeight > window.innerWidth;
    var name = klein && hochkant && saetze.hoch ? "hoch" : "quer";
    var satz = saetze[name];
    // Hochformat wird auf dem Handy gezoomt, deshalb dort die scharfen großen Bilder
    var leicht = klein && satz.leicht && name !== "hoch";
    var schluessel = name + (leicht ? "-leicht" : "");
    if (schluessel === satzSchluessel) return false;
    satzSchluessel = schluessel;
    seq = {};
    for (var k in satz) seq[k] = satz[k];
    if (leicht) seq.frames = satz.leicht;
    return true;
  }
  waehleSatz();
  var stage = journey && journey.querySelector(".stage");
  var canvas = journey && journey.querySelector("canvas.seq");
  var carA = journey && journey.querySelector(".car-a");
  var carB = journey && journey.querySelector(".car-b");
  var ctx = canvas && canvas.getContext ? canvas.getContext("2d") : null;
  var bilder = [];
  var R0 = null;
  var R1 = null;
  var dpr = 1;

  function easeInOut(t) { return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; }
  function lerp(a, b, t) { return a + (b - a) * t; }

  // Bilder laden: zuerst jedes vierte (grobe Vorschau), dann den Rest
  function ladeBilder() {
    if (!seq || !ctx) return;
    bilder = [];
    var satz = satzSchluessel;
    var n = seq.frames.length;
    var reihenfolge = [];
    for (var i = 0; i < n; i += 4) reihenfolge.push(i);
    for (var j = 0; j < n; j++) if (reihenfolge.indexOf(j) === -1) reihenfolge.push(j);
    reihenfolge.forEach(function (idx) {
      var im = new Image();
      im.decoding = "async";
      im.onload = function () {
        if (satz !== satzSchluessel) return; // inzwischen anderer Satz (z. B. gedreht)
        bilder[idx] = im;
        if (current > 0) zeichne(current);
      };
      im.src = seq.frames[idx];
    });
  }

  // Handy hochkant mit 9:16-Film: Das Auto ist im Film nur ein Streifen in der Mitte.
  // Deshalb wird gezoomt: Am Anfang füllt das Auto den freien Platz unter den Knöpfen,
  // am Ende füllt die Front gut die halbe Bildschirmhöhe (wie am PC die Motorhaube).
  var HOCH_ENDE_HOEHE = 0.52;  // Anteil der Bildschirmhöhe, den die Front am Ende einnimmt
  var HOCH_ENDE_MITTE = 0.46;  // senkrechte Lage der Front am Ende
  function vermesseHoch(sw, sh) {
    var W = seq.w, H = seq.h;
    var b0 = seq.bandStart, b1 = seq.bandEnde;
    var unten = journey.querySelector(".hero-bottom");
    var frei0 = unten ? unten.offsetTop + unten.offsetHeight + 20 : sh * 0.45;
    var frei1 = sh - 8;
    var bandAsp = ((b0[2] - b0[0]) * W) / ((b0[3] - b0[1]) * H);
    // Auto so groß wie möglich im freien Bereich, höchstens 1,35-fache Bildschirmbreite (Heck darf raus)
    var bh = Math.min((frei1 - frei0) * 0.95, (sw * 1.35) / bandAsp);
    var s0 = bh / ((b0[3] - b0[1]) * H);
    var bandOben = frei0 + (frei1 - frei0 - bh) / 2;
    R0 = { w: W * s0, h: H * s0, x: sw * 0.02 - b0[0] * W * s0, y: bandOben - b0[1] * H * s0 };
    var s1 = (HOCH_ENDE_HOEHE * sh) / ((b1[3] - b1[1]) * H);
    var cx = ((b1[0] + b1[2]) / 2) * W * s1;
    var cy = ((b1[1] + b1[3]) / 2) * H * s1;
    R1 = { w: W * s1, h: H * s1, x: sw / 2 - cx, y: sh * HOCH_ENDE_MITTE - cy };
    setzeRect(carA, R0);
    setzeRect(carB, R1);
    T0 = T1 = true;
  }
  function setzeRect(el, R) {
    if (!el) return;
    el.style.left = R.x + "px";
    el.style.top = R.y + "px";
    el.style.width = R.w + "px";
    el.style.height = R.h + "px";
    el.style.right = "auto";
    el.style.bottom = "auto";
    el.style.maxWidth = "none";
    el.style.objectFit = "fill";
    el.style.transform = "none";
  }
  function stileZuruecksetzen() {
    [carA, carB].forEach(function (el) {
      if (!el) return;
      ["left", "top", "width", "height", "right", "bottom", "maxWidth", "objectFit", "transform"].forEach(function (k) { el.style[k] = ""; });
    });
  }

  // Wo steht das Auto am Anfang (Startbild) und am Ende (im Leistungsbild)?
  function vermesse() {
    if (!seq || !ctx || !stage) return;
    var sw = stage.clientWidth;
    var sh = stage.clientHeight;
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(sw * dpr);
    canvas.height = Math.round(sh * dpr);
    buehne = { w: sw, h: sh };
    if (satzSchluessel.indexOf("hoch") === 0 && seq.bandStart && seq.bandEnde) {
      vermesseHoch(sw, sh);
      return;
    }
    stileZuruecksetzen();
    var st = stage.getBoundingClientRect();
    var a = carA.getBoundingClientRect();
    R0 = { x: a.left - st.left, y: a.top - st.top, w: a.width, h: a.height };

    // Leistungsbild: auf dem Desktop füllend (cover), auf dem Handy ganz sichtbar (contain)
    var iw = carB.naturalWidth || 1672;
    var ih = carB.naturalHeight || 940;
    var fit = getComputedStyle(carB).objectFit;
    var s = fit === "contain" ? Math.min(sw / iw, sh / ih) : Math.max(sw / iw, sh / ih);
    var pos = getComputedStyle(carB).objectPosition.split(" ");
    var px = parseFloat(pos[0]) / 100;
    var py = parseFloat(pos[1]) / 100;
    var bx = (sw - iw * s) * (isNaN(px) ? 0.5 : px);
    var by = (sh - ih * s) * (isNaN(py) ? 0.5 : py);
    buehne = { w: sw, h: sh };
    if (seq.typ === "film") {
      // Film: das letzte Bild ist das Leistungsbild selbst, die Fahrt endet genau auf seiner Fläche
      R1 = { x: bx, y: by, w: iw * s, h: ih * s };
      T0 = T1 = true;
      return;
    }
    var e = seq.endeBbox;
    var ziel = { x0: bx + e[0] * iw * s, y0: by + e[1] * ih * s, x1: bx + e[2] * iw * s, y1: by + e[3] * ih * s };
    // letztes Bild der Folge so legen, dass sein Auto über dem Auto im Leistungsbild liegt
    var f = seq.bbox[seq.bbox.length - 1];
    var k = (ziel.x1 - ziel.x0) / ((f[2] - f[0]) * seq.w);
    R1 = { w: seq.w * k, h: seq.h * k, x: ziel.x0 - f[0] * seq.w * k, y: ziel.y1 - f[3] * seq.h * k };
    // Kamerapfad über das Auto selbst: Mitte und Höhe des Autos am Anfang und am Ende
    T0 = autoBox(R0, seq.bbox[0]);
    T1 = autoBox(R1, f);
    oberkanteAmRand = fit !== "contain";
    buehne = { w: sw, h: sh };
  }

  var T0 = null;
  var T1 = null;
  var buehne = null;
  var oberkanteAmRand = true;

  function autoBox(R, b) {
    var x0 = R.x + b[0] * R.w;
    var y0 = R.y + b[1] * R.h;
    var x1 = R.x + b[2] * R.w;
    var y1 = R.y + b[3] * R.h;
    return { cx: (x0 + x1) / 2, cy: (y0 + y1) / 2, h: y1 - y0 };
  }

  // welches Einzelbild gehört zu dieser Stelle der Fahrt (Zeiten aus dem Manifest)
  function bildIndex(ps) {
    var z = seq.zeiten;
    var i = 0;
    for (var k = 0; k < z.length; k++) if (ps >= z[k] - 1e-6) i = k;
    return i;
  }

  // Film (z. B. KI-Video mit schwarzem Hintergrund): Bild für Bild, der Bildausschnitt wächst
  // vom Startbild unten rechts bis zur vollen Fläche. Angeschnittene Kanten blenden ins Schwarz.
  function zeichneFilm(ps) {
    var n = seq.frames.length;
    var a = Math.min(n - 1, Math.round(ps * (n - 1)));
    while (a > 0 && !bilder[a]) a--;
    if (!bilder[a]) return;
    var e = easeInOut(ps);
    var x = lerp(R0.x, R1.x, e);
    var y = lerp(R0.y, R1.y, e);
    var w = lerp(R0.w, R1.w, e);
    var h = lerp(R0.h, R1.h, e);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(bilder[a], x, y, w, h);
    // weiche Kanten, solange der Ausschnitt noch nicht am Bildschirmrand liegt (wie die Maske am Startbild)
    var oben = clamp(y / (buehne.h * 0.05), 0, 1);
    if (oben > 0) {
      var g = ctx.createLinearGradient(0, y, 0, y + h * 0.22);
      g.addColorStop(0, "rgba(0,0,0," + oben + ")");
      g.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = g;
      ctx.fillRect(x, y, w, h * 0.22);
    }
    var links = clamp(x / (buehne.w * 0.05), 0, 1);
    if (links > 0) {
      var g2 = ctx.createLinearGradient(x, 0, x + w * 0.08, 0);
      g2.addColorStop(0, "rgba(0,0,0," + links + ")");
      g2.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = g2;
      ctx.fillRect(x, y, w * 0.08, h);
    }
  }

  function zeichne(p) {
    if (!seq || !ctx || !T0 || !T1) return;
    var ps = Math.min(1, p / ENDE);
    if (seq.typ === "film") { zeichneFilm(ps); return; }
    var e = easeInOut(ps);
    // immer genau ein Einzelbild zeichnen (keine Überblendung zwischen Bildern, also kein Morphen)
    var a = bildIndex(ps);
    while (a > 0 && !bilder[a]) a--;
    if (!bilder[a]) return;
    // Kamera gleitet gleichmäßig: jedes Bild wird so gelegt, dass sein Auto genau im Kamerapfad sitzt.
    // So verschwinden die Größensprünge des Storyboards, nur die Pose des Autos wechselt.
    var b = seq.bbox[a];
    var cx = lerp(T0.cx, T1.cx, e);
    var cy = lerp(T0.cy, T1.cy, e);
    var th = lerp(T0.h, T1.h, e);
    var k = th / ((b[3] - b[1]) * seq.h);
    var w = seq.w * k;
    var h = seq.h * k;
    var x = cx - ((b[0] + b[2]) / 2) * w;
    var y = cy - ((b[1] + b[3]) / 2) * h;
    // abgeschnittene Kanten nie mitten im Bild zeigen: an den Bildschirmrand schieben
    var schnitt = seq.schnitt[a] || "";
    if (schnitt.indexOf("r") !== -1 && x + b[2] * w < buehne.w) x = buehne.w - b[2] * w;
    if (schnitt.indexOf("o") !== -1 && oberkanteAmRand && y + b[1] * h > 0) y = -b[1] * h;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(bilder[a], x, y, w, h);
  }

  function render(p) {
    var st = journey.style;
    var reduce = reduceMotion.matches || !ctx || !seq;
    if (reduce) {
      // Ohne Bewegung: Startbild, ab der Hälfte das Leistungsbild
      st.setProperty("--ao", p < 0.5 ? "1" : "0");
      st.setProperty("--co", "0");
      st.setProperty("--bo", p < 0.5 ? "0" : "1");
    } else {
      zeichne(p);
      st.setProperty("--ao", p > 0.002 ? "0" : "1");
      st.setProperty("--co", p > 0.002 ? (1 - clamp((p - ENDE) / (1 - ENDE), 0, 1)).toFixed(4) : "0");
      st.setProperty("--bo", clamp((p - ENDE) / (1 - ENDE), 0, 1).toFixed(4));
    }
    st.setProperty("--hf", (1 - clamp(p / 0.12, 0, 1)).toFixed(4));
    journey.classList.toggle("hero-gone", p > 0.14);
    // Leistungen erst zeigen, wenn die Fahrt angekommen ist
    journey.classList.toggle("leistungen-da", p > 0.985);
    st.setProperty("--sc", clamp((p - 0.85) / 0.15, 0, 1).toFixed(4));
  }

  var letzterSchritt = 0;
  function step(jetzt) {
    var diff = target - current;
    // zeitbasiert: gleich schnell auf 60-Hz-, 120-Hz- und langsamen Handys
    var dt = letzterSchritt ? Math.min(250, (jetzt || 16.7) - letzterSchritt) : 16.7;
    letzterSchritt = jetzt || 0;
    if (reduceMotion.matches || Math.abs(diff) < 0.0005) current = target;
    else current += diff * (1 - Math.pow(1 - NACHLAUF, dt / 16.7));
    render(current);
    if (current !== target) window.requestAnimationFrame(step);
    else { running = false; letzterSchritt = 0; }
  }

  function onScroll() {
    var y = window.pageYOffset || doc.scrollTop;
    if (header && !header.classList.contains("is-solid")) {
      header.classList.toggle("is-scrolled", y > 24);
    }
    if (!journey) return;
    var vh = window.innerHeight;
    var into = -journey.getBoundingClientRect().top;
    target = clamp(into / (vh * FAHRT), 0, 1);
    // Abdunklung, sobald die Leistungs-Kästen über das Bild laufen (direkt am Scroll)
    var staerke = satzSchluessel.indexOf("hoch") === 0 ? 0.42 : 0.66;
    var s = clamp((into - vh * (FAHRT + 0.35)) / (vh * 0.5), 0, 1) * staerke;
    journey.style.setProperty("--s", s.toFixed(3));
    if (!running) {
      running = true;
      window.requestAnimationFrame(step);
    }
  }

  var letzteBreite = window.innerWidth;
  function onResize() {
    // Auf dem Handy nur bei echter Breitenänderung neu vermessen (Adressleiste ein/aus ignorieren)
    var touch = window.matchMedia("(pointer: coarse)").matches;
    if (!journey || (touch && window.innerWidth === letzteBreite)) { onScroll(); return; }
    letzteBreite = window.innerWidth;
    if (waehleSatz()) ladeBilder();
    vermesse();
    render(current);
    onScroll();
  }

  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onResize);
  if (journey) {
    var start = function () {
      vermesse();
      ladeBilder();
      onScroll();
      current = target;
      render(current);
    };
    if (carA && !carA.complete) carA.addEventListener("load", start, { once: true });
    else start();
    if (carB && !carB.complete) carB.addEventListener("load", function () { vermesse(); render(current); }, { once: true });
  } else {
    onScroll();
  }

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
