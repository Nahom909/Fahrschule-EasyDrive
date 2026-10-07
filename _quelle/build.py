"""Baut die Website der Fahrschule EasyDrive.

    python _quelle/build.py

Liest alle Inhalte aus content/ (dort schreibt auch Decap CMS hinein),
kopiert static/ und schreibt die fertige Seite nach dist/.
Netlify führt genau diesen Befehl bei jeder Änderung aus.

Bilder werden beim Bauen automatisch verkleinert und als WebP in
mehreren Breiten abgelegt (dist/assets/img/_v/). Hochgeladene Fotos
dürfen also groß sein.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import quote_plus

try:
    from PIL import Image, ImageOps
except ImportError:  # Ohne Pillow werden die Originalbilder verwendet
    Image = None

import markdown as md_lib

BASE = Path(__file__).resolve().parent.parent
CONTENT = BASE / "content"
STATIC = BASE / "static"
DIST = BASE / "dist"
ICONS = Path(__file__).resolve().parent / "icons"
SITE = "https://www.fahrschule-easydrive.org"
VERSION = "14"  # bei Änderungen an CSS/JS hochzählen

esc = html.escape
WARNINGS: list[str] = []


# ---------------------------------------------------------------- Inhalte laden


def load(name: str) -> dict:
    return json.loads((CONTENT / name).read_text(encoding="utf-8"))


S = load("einstellungen.json")
HOME = load("startseite.json")
ST_PAGE = load("standorte-seite.json")
IMPRESSUM = load("impressum.json")
DATENSCHUTZ = load("datenschutz.json")

LOCATIONS = []
for f in sorted((CONTENT / "standorte").glob("*.json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    d["slug"] = f.stem
    LOCATIONS.append(d)
LOCATIONS.sort(key=lambda l: (l.get("reihenfolge") or 99, l["name"]))
LOC_BY_SLUG = {l["slug"]: l for l in LOCATIONS}

DAY_EN = {"1": "Monday", "2": "Tuesday", "3": "Wednesday", "4": "Thursday", "5": "Friday", "6": "Saturday", "0": "Sunday"}
KLASSEN_OPTIONEN = ["B", "BF17", "B197", "B78 (Automatik)", "BE", "A", "A2", "A1", "B196"]


# ---------------------------------------------------------------- Helfer


def tel(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("00"):
        return "+" + digits[2:]
    if digits.startswith("0"):
        return "+49" + digits[1:]
    return "+" + digits if digits else ""


def wa(phone: str) -> str:
    return tel(phone).lstrip("+")


def rel(root: str, path: str) -> str:
    """Wandelt /assets/... in einen relativen Pfad für die jeweilige Seitentiefe um."""
    if not path:
        return ""
    if re.match(r"^[a-z]+:", path):
        return path
    return root + path.lstrip("/")


def md(text: str) -> str:
    text = (text or "").replace("\\\n", "\n")
    return md_lib.markdown(text, extensions=["nl2br", "sane_lists"], output_format="html")


def md_inline(text: str) -> str:
    out = md(text).strip()
    return re.sub(r"^<p>(.*)</p>$", r"\1", out, flags=re.S)


_icon_cache: dict[str, str] = {}


def icon(name: str, cls: str = "") -> str:
    if name not in _icon_cache:
        path = ICONS / f"{name}.svg"
        if not path.exists():
            WARNINGS.append(f"Icon fehlt: {name}")
            return ""
        svg = path.read_text(encoding="utf-8").strip()
        svg = re.sub(r'<rect[^>]*fill="none"[^>]*/>', "", svg)
        _icon_cache[name] = svg
    klass = f"icon {cls}".strip()
    return _icon_cache[name].replace("<svg ", f'<svg class="{klass}" aria-hidden="true" focusable="false" ', 1)


# ---------------------------------------------------------------- Bilder


def pic(path: str, widths: tuple[int, ...]) -> dict:
    """Erzeugt verkleinerte WebP-Varianten und liefert src, srcset, Breite, Höhe."""
    info = {"src": path, "srcset": [], "w": None, "h": None}
    if not path or re.match(r"^[a-z]+:", path):
        return info
    src = STATIC / path.lstrip("/")
    if not src.exists():
        WARNINGS.append(f"Bild nicht gefunden: {path}")
        return info
    if Image is None or src.suffix.lower() == ".svg":
        return info
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        W, H = im.size
        info["w"], info["h"] = W, H
        tag = hashlib.md5(path.encode("utf-8")).hexdigest()[:6]
        out_dir = DIST / "assets" / "img" / "_v"
        out_dir.mkdir(parents=True, exist_ok=True)
        targets = sorted({min(w, W) for w in widths})
        for w in targets:
            name = f"{src.stem}-{tag}-{w}.webp"
            dest = out_dir / name
            if not dest.exists() or dest.stat().st_mtime < src.stat().st_mtime:
                frame = im if im.mode in ("RGB", "RGBA") else im.convert("RGBA" if "A" in im.getbands() else "RGB")
                h = round(H * w / W)
                resized = frame if w == W else frame.resize((w, h), Image.LANCZOS)
                resized.save(dest, "WEBP", quality=82, method=5)
            info["srcset"].append((w, f"/assets/img/_v/{name}"))
        info["src"] = info["srcset"][-1][1]
    return info


def img(root: str, path: str, widths: tuple[int, ...], sizes: str, alt: str = "", cls: str = "", attrs: str = "") -> str:
    p = pic(path, widths)
    parts = [f'<img src="{rel(root, p["src"])}"']
    if len(p["srcset"]) > 1:
        parts.append(f'srcset="{", ".join(f"{rel(root, u)} {w}w" for w, u in p["srcset"])}"')
        parts.append(f'sizes="{sizes}"')
    parts.append(f'alt="{esc(alt)}"')
    if p["w"]:
        parts.append(f'width="{p["w"]}" height="{p["h"]}"')
    if cls:
        parts.append(f'class="{cls}"')
    if attrs:
        parts.append(attrs)
    return " ".join(parts) + ">"


# ---------------------------------------------------------------- Strukturierte Daten


def ld_location(l: dict) -> dict:
    spec = []
    for row in l.get("buerozeiten", []):
        if row.get("von") and row.get("bis"):
            spec.append({
                "@type": "OpeningHoursSpecification",
                "dayOfWeek": [DAY_EN[d] for d in row.get("tage", []) if d in DAY_EN],
                "opens": row["von"],
                "closes": row["bis"],
            })
    data = {
        "@type": "DrivingSchool",
        "@id": f"{SITE}/standorte/{l['slug']}/#fahrschule",
        "name": f"{S['firmenname']} {l['kurzname']}",
        "url": f"{SITE}/standorte/{l['slug']}/",
        "telephone": tel(l["telefon"]),
        "email": l["email"],
        "address": {
            "@type": "PostalAddress",
            "streetAddress": l["strasse"],
            "postalCode": l["plz"],
            "addressLocality": l["ort"],
            "addressCountry": "DE",
        },
        "openingHoursSpecification": spec,
        "parentOrganization": {"@id": f"{SITE}/#organisation"},
    }
    if l.get("bild_karte"):
        data["image"] = SITE + l["bild_karte"]
    if l.get("breitengrad") and l.get("laengengrad"):
        data["geo"] = {"@type": "GeoCoordinates", "latitude": l["breitengrad"], "longitude": l["laengengrad"]}
    return data


def json_ld(data: dict) -> str:
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return f'<script type="application/ld+json">{raw}</script>'


def maps_url(l: dict) -> str:
    return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(f"{S['firmenname']} {l['strasse']} {l['plz']} {l['ort']}")


# ---------------------------------------------------------------- Seitengerüst

TOKEN_REDIRECT = (
    "<script>if(/(invite|recovery|confirmation|email_change)_token=/.test(location.hash))"
    "location.replace('/admin/'+location.hash)</script>"
)


def head(root: str, title: str, description: str, path: str, *, noindex: bool = False, preload: str = "", extra: str = "") -> str:
    robots = '\n  <meta name="robots" content="noindex, follow">' if noindex else ""
    canonical = f"{SITE}/{path}"
    share = SITE + S.get("teilen_bild", "")
    return f"""<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>{esc(title)}</title>
  <meta name="description" content="{esc(description)}">{robots}
  <link rel="canonical" href="{canonical}">
  <meta name="theme-color" content="#000000">
  <meta property="og:type" content="website">
  <meta property="og:locale" content="de_DE">
  <meta property="og:site_name" content="{esc(S['firmenname'])}">
  <meta property="og:title" content="{esc(title)}">
  <meta property="og:description" content="{esc(description)}">
  <meta property="og:url" content="{canonical}">
  <meta property="og:image" content="{share}">
  <link rel="icon" type="image/png" sizes="48x48" href="{root}assets/img/favicon.png">
  <link rel="apple-touch-icon" href="{root}assets/img/apple-touch-icon.png">
  <link rel="preload" href="{root}assets/fonts/archivo-latin.woff2" as="font" type="font/woff2" crossorigin>{preload}
  <link rel="stylesheet" href="{root}assets/css/style.css?v={VERSION}">
  <script src="{root}assets/js/main.js?v={VERSION}" defer></script>{extra}
</head>"""


def header(root: str, active: str = "", solid: bool = False) -> str:
    home = root or "./"
    sub = "\n".join(
        f'              <li><a href="{root}standorte/{l["slug"]}/"><span>{esc(l["name"])}</span><small>{esc(l["strasse"])}</small></a></li>'
        for l in LOCATIONS
    )
    mm = "\n".join(
        f'    <li><a href="{root}standorte/{l["slug"]}/">{esc(l["name"])}<small>{esc(l["strasse"])}</small></a></li>'
        for l in LOCATIONS
    )
    cur = ' aria-current="page"' if active == "standorte" else ""
    home_cur = ' aria-current="page"' if active == "home" else ""
    solid_cls = " is-solid" if solid else ""
    return f"""<body>
<a class="skip-link" href="#inhalt">Zum Inhalt springen</a>
<header class="site-header{solid_cls}" data-header>
  <div class="wrap header-inner">
    <a class="brand" href="{home}" aria-label="{esc(S['firmenname'])}, zur Startseite">
      <img src="{rel(root, S['logo'])}" alt="{esc(S['firmenname'])}" width="779" height="438">
    </a>
    <nav class="nav" aria-label="Hauptnavigation">
      <ul class="nav-list">
        <li><a class="nav-home" href="{home}"{home_cur}>{icon("house")}Home</a></li>
        <li><a href="{root}#leistungen">Leistungen</a></li>
        <li><a href="{root}#preise">Preise</a></li>
        <li><a href="{root}#ueber-uns">Über uns</a></li>
        <li><a href="{root}#kontakt">Kontakt</a></li>
        <li class="has-sub">
          <a class="nav-standorte" href="{root}standorte/"{cur}>Standorte {icon("caret-down")}</a>
          <div class="sub">
            <ul>
{sub}
            </ul>
            <a class="sub-all" href="{root}standorte/">Alle Standorte {icon("arrow-right")}</a>
          </div>
        </li>
      </ul>
    </nav>
    <a class="home-mobil" href="{home}" aria-label="Zur Startseite">{icon("house")}</a>
    <button class="menu-toggle" type="button" aria-expanded="false" aria-controls="mobile-menu" data-menu-toggle>
      {icon("list", "icon-open")}{icon("x", "icon-close")}<span data-menu-label>Menü</span>
    </button>
  </div>
</header>
<div class="mobile-menu" id="mobile-menu">
  <ul>
    <li><a href="{home}">Home</a></li>
    <li><a href="{root}#leistungen">Leistungen</a></li>
    <li><a href="{root}#preise">Preise</a></li>
    <li><a href="{root}#ueber-uns">Über uns</a></li>
    <li><a href="{root}#kontakt">Kontakt</a></li>
  </ul>
  <p class="mm-label"><a href="{root}standorte/">Standorte</a></p>
  <ul class="mm-standorte">
{mm}
  </ul>
  <a class="btn" href="{root}#kontakt">{esc(S['anmelden_text'])} {icon("arrow-right", "icon-arrow")}</a>
</div>"""


def footer(root: str) -> str:
    locs = "\n".join(f'          <li><a href="{root}standorte/{l["slug"]}/">{esc(l["name"])}</a></li>' for l in LOCATIONS)
    return f"""<footer class="site-footer">
  <div class="wrap">
    <div class="footer-grid">
      <div class="footer-brand">
        <img src="{rel(root, S['logo'])}" alt="{esc(S['firmenname'])}" width="779" height="438" loading="lazy">
        <p>{esc(S['footer_text'])}</p>
      </div>
      <div class="footer-col">
        <h2>Fahrschule</h2>
        <ul>
          <li><a href="{root}#leistungen">Leistungen</a></li>
          <li><a href="{root}#preise">Preise</a></li>
          <li><a href="{root}#ueber-uns">Über uns</a></li>
          <li><a href="{root}#kontakt">Kontakt</a></li>
        </ul>
      </div>
      <div class="footer-col">
        <h2>Standorte</h2>
        <ul>
{locs}
        </ul>
      </div>
      <div class="footer-col">
        <h2>Rechtliches</h2>
        <ul>
          <li><a href="{root}impressum/">Impressum</a></li>
          <li><a href="{root}datenschutz/">Datenschutz</a></li>
        </ul>
      </div>
    </div>
    <div class="footer-bottom">
      <span>© <span data-year>2026</span> {esc(S['firmenname'])}</span>
      <span>{esc(S['strasse'])}, {esc(S['plz'])} {esc(S['ort'])}</span>
    </div>
  </div>
</footer>
</body>
</html>
"""


def contact_form(root: str, form_id: str, to: str, subject: str, title: str, intro: str, *, with_standort: bool, klassen: list[str]) -> str:
    klasse_opts = "\n".join(f'          <option value="{esc(k)}">{esc(k)}</option>' for k in klassen)
    standort = ""
    if with_standort:
        so = "\n".join(f'          <option value="{esc(l["name"])}">{esc(l["name"])}</option>' for l in LOCATIONS)
        standort = f"""
      <div class="field">
        <label for="{form_id}-standort">Wunschstandort <span class="opt">(optional)</span></label>
        <select id="{form_id}-standort" name="standort">
          <option value="">Noch offen</option>
{so}
        </select>
      </div>"""
    klasse_cls = "field" if with_standort else "field field-full"
    return f"""<div class="form-card" data-reveal>
    <h3>{esc(title)}</h3>
    <p>{esc(intro)}</p>
    <form data-mailto="{esc(to)}" data-subject="{esc(subject)}" novalidate>
      <div class="form-grid">
      <div class="field">
        <label for="{form_id}-name">Name</label>
        <input id="{form_id}-name" name="name" type="text" autocomplete="name" required maxlength="120" aria-describedby="{form_id}-name-err">
        <span class="error" id="{form_id}-name-err">Bitte gib deinen Namen an.</span>
      </div>
      <div class="field">
        <label for="{form_id}-email">E-Mail</label>
        <input id="{form_id}-email" name="email" type="email" autocomplete="email" required maxlength="160" aria-describedby="{form_id}-email-err">
        <span class="error" id="{form_id}-email-err">Bitte gib eine gültige E-Mail-Adresse an.</span>
      </div>
      <div class="field">
        <label for="{form_id}-telefon">Telefon <span class="opt">(optional)</span></label>
        <input id="{form_id}-telefon" name="telefon" type="tel" autocomplete="tel" maxlength="40">
      </div>{standort}
      <div class="{klasse_cls}">
        <label for="{form_id}-klasse">Führerscheinklasse <span class="opt">(optional)</span></label>
        <select id="{form_id}-klasse" name="klasse">
          <option value="">Weiß ich noch nicht</option>
{klasse_opts}
        </select>
      </div>
      <div class="field field-full">
        <label for="{form_id}-nachricht">Nachricht</label>
        <textarea id="{form_id}-nachricht" name="nachricht" required maxlength="1500" rows="5" aria-describedby="{form_id}-nachricht-err"></textarea>
        <span class="error" id="{form_id}-nachricht-err">Bitte schreib uns kurz, worum es geht.</span>
      </div>
      </div>
      <div class="form-actions">
        <button class="btn" type="submit">Nachricht senden {icon("paper-plane-tilt")}</button>
        <p class="form-hinweis">Beim Absenden öffnet sich dein E-Mail-Programm mit der fertigen Nachricht an {esc(to)}. Mehr dazu in der <a href="{root}datenschutz/">Datenschutzerklärung</a>.</p>
        <div class="form-status" role="status" aria-live="polite" data-form-status></div>
      </div>
    </form>
  </div>"""


def opt_p(text: str, cls: str = "lead") -> str:
    """Absatz nur ausgeben, wenn in Decap etwas eingetragen ist."""
    return f'<p class="{cls}">{esc(text)}</p>' if (text or "").strip() else ""


def stars(n: int = 5) -> str:
    n = max(1, min(5, int(n or 5)))
    return f'<span class="sterne" role="img" aria-label="{n} von 5 Sternen">' + "".join(icon("star-fill") for _ in range(n)) + "</span>"


# ---------------------------------------------------------------- Startseite


def page_index() -> str:
    root = ""
    hero, lei, preise, ueber, bew, kon = (HOME[k] for k in ("hero", "leistungen", "preise", "ueber_uns", "bewertungen", "kontakt"))

    gruppen = []
    for gi, g in enumerate(lei.get("gruppen", [])):
        cards = []
        for i, k in enumerate(g.get("klassen", [])):
            ort = f'<p class="klasse-ort">{icon("map-pin")}{esc(k["ort"])}</p>' if k.get("ort") else ""
            cards.append(f"""            <article class="klasse" style="--i:{i}">
              <span class="klasse-code">{esc(k["code"])}</span>
              <h4>{esc(k["titel"])}</h4>
              <p>{esc(k["text"])}</p>
              {ort}
            </article>""")
        hint = lei.get("hinweis") or {}
        if gi == len(lei["gruppen"]) - 1 and hint.get("anzeigen"):
            target = LOC_BY_SLUG.get(hint.get("standort"))
            link = f'<a class="text-link" href="standorte/{target["slug"]}/">{esc(hint["link_text"])} {icon("arrow-right")}</a>' if target else ""
            cards.append(f"""            <article class="klasse klasse-hinweis" style="--i:{len(cards)}">
              <strong>{esc(hint["titel"])}</strong>
              {opt_p(hint.get("text", ""), "")}
              {link}
            </article>""")
        gruppen.append(f"""        <div class="klassen-gruppe">
          <h3 class="gruppe-titel">{icon(g.get("icon") or "car")}{esc(g["titel"])}</h3>
          <div class="klassen">
{chr(10).join(cards)}
          </div>
        </div>""")

    karten = []
    for i, k in enumerate(preise.get("karten", [])):
        row_list = []
        for p in k.get("posten", []):
            note = f"<small>{esc(p['hinweis'])}</small>" if p.get("hinweis") else ""
            row_list.append(f'            <li><span class="posten">{esc(p["name"])}{note}</span><span class="betrag">{esc(p["preis"])}</span></li>')
        rows = "\n".join(row_list)
        karten.append(f"""        <article class="preis-karte" data-reveal style="--i:{i}">
          <header>
            <span class="klassen-label">{esc(k["klassen"])}</span>
            <h3>{esc(k["titel"])}</h3>
          </header>
          <ul class="preis-liste">
{rows}
          </ul>
        </article>""")
    paket = preise.get("paket") or {}
    if paket.get("anzeigen"):
        karten.append(f"""        <article class="preis-paket" data-reveal>
          <div>
            <span class="klassen-label">{esc(paket["klassen"])}</span>
            <h3>{esc(paket["titel"])}</h3>
            <p>{esc(paket["text"])}</p>
          </div>
          <p class="paket-preis">{esc(paket["preis"])}<small>{esc(paket.get("preis_hinweis", ""))}</small></p>
        </article>""")
    hinweise = "\n".join(f'        <span>{icon("check")}{esc(h)}</span>' for h in preise.get("hinweise", []))

    bewertungen = ""
    if bew.get("anzeigen"):
        cards = "\n".join(
            f"""            <figure class="rev-card">
              {stars(r.get("sterne", 5))}
              <blockquote><p>{esc(r["text"])}</p></blockquote>
              <figcaption><span class="avatar" aria-hidden="true">{esc((r["name"] or "?")[:1].upper())}</span><span>{esc(r["name"])}<small>{esc(r.get("quelle", ""))}</small></span></figcaption>
            </figure>"""
            for r in bew.get("rezensionen", [])
        )
        bewertungen = f"""
  <section class="section" id="bewertungen" aria-labelledby="bewertungen-titel">
    <div class="wrap">
      <div class="bewertung-kopf" data-reveal>
        <h2 id="bewertungen-titel">{esc(bew["titel"])}</h2>
        <div class="rating">
          <span class="rating-zahl">{esc(bew["note"])}</span>
          <div class="rating-text">
            {stars(5)}
            <span><strong>{esc(bew["zeile_1"])}</strong> {esc(bew.get("zeile_1_rest", ""))}</span>
            <span>{esc(bew.get("zeile_2", ""))}</span>
          </div>
        </div>
      </div>
    </div>
    <div class="rev-rows">
      <div class="rev-row">
        <div class="rev-track">
{cards}
        </div>
      </div>
      <div class="rev-row" aria-hidden="true">
        <div class="rev-track">
{cards}
        </div>
      </div>
    </div>
  </section>"""

    standort_links = "\n".join(
        f'            <a href="standorte/{l["slug"]}/"><strong>{esc(l["name"])}</strong><small>{esc(l["strasse"])}, {esc(l["plz"])} {esc(l["ort"])}</small>{icon("arrow-right")}</a>'
        for l in LOCATIONS
    )
    chips = "\n".join(f'          <li class="chip">{esc(s)}</li>' for s in ueber.get("sprachen", []))
    galerie = [g for g in ueber.get("galerie", []) if g.get("bild")]
    galerie_items = []
    for i, g in enumerate(galerie):
        widths, sizes = ((700, 1400, 2000), "(max-width: 700px) 100vw, 66vw") if i == 0 else ((600, 1200), "(max-width: 700px) 50vw, 33vw")
        pos = esc(g.get("ausschnitt") or "50% 50%")
        picture = img(root, g["bild"], widths, sizes, g.get("alt", ""), attrs='loading="lazy" decoding="async"')
        galerie_items.append(f'        <figure class="g-item" data-reveal style="--i:{i};--pos:{pos}">{picture}</figure>')
    galerie_html = "\n".join(galerie_items)

    ld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Organization",
                "@id": f"{SITE}/#organisation",
                "name": S["firmenname"],
                "url": f"{SITE}/",
                "logo": f"{SITE}/assets/img/logo-weiss.png",
                "email": S["email"],
                "telephone": tel(S["telefon"]),
            },
            *[ld_location(l) for l in LOCATIONS],
        ],
    }

    # Bildfolge der Kamerafahrt (erzeugt mit _quelle/frames.py)
    def seq_satz(ordner: str) -> dict | None:
        mf = STATIC / "assets" / ordner / "manifest.json"
        if not mf.exists():
            return None
        m = json.loads(mf.read_text(encoding="utf-8"))
        basis = "/assets/" + ordner + "/"
        return {
            "w": m["breite"],
            "h": m["hoehe"],
            "frames": [rel(root, basis + f["src"]) for f in m["frames"]],
            # leichte Fassung fürs Handy (kleinere Bilder, gleiche Anzahl)
            "leicht": [rel(root, basis + m["leicht"] + f["src"]) for f in m["frames"]] if m.get("leicht") else None,
            "typ": m.get("typ", "folge"),
            "bbox": [f.get("bbox", [0, 0, 1, 1]) for f in m["frames"]],
            "schnitt": [f.get("schnitt", "") for f in m["frames"]],
            "zeiten": m.get("zeiten") or [i / max(1, len(m["frames"]) - 1) for i in range(len(m["frames"]))],
            # Lage des Autos im Leistungsbild (Anteile), damit das letzte Bild dort ankommt
            "endeBbox": m.get("ende_bbox", [0.1, 0.02, 0.9, 0.99]),
        }

    quer = seq_satz("seq")
    hoch = seq_satz("seq-hoch")  # optional: eigenes Hochformat-Video fürs Handy
    seq_cfg = {"quer": quer, "hoch": hoch}
    seq = {"breite": quer["w"], "hoehe": quer["h"]}
    erstes = quer["frames"][0]
    handy = "(max-width: 900px)"
    hochkant = "(max-width: 900px) and (orientation: portrait)"
    quellen = ""
    if hoch:
        quellen += f'<source media="{hochkant}" srcset="{(hoch["leicht"] or hoch["frames"])[0]}" width="{hoch["w"]}" height="{hoch["h"]}">'
    if quer["leicht"]:
        quellen += f'<source media="{handy}" srcset="{quer["leicht"][0]}">'
    preload = f'\n  <link rel="preload" as="image" href="{erstes}" fetchpriority="high" media="(min-width: 901px)">'
    if quer["leicht"] and not hoch:
        preload += f'\n  <link rel="preload" as="image" href="{quer["leicht"][0]}" fetchpriority="high" media="{handy}">'
    car_a = f'<picture>{quellen}<img class="car-a" src="{erstes}" alt="" width="{quer["w"]}" height="{quer["h"]}" fetchpriority="high" decoding="async"></picture>'
    car_b = img(root, lei["bild"], (1280, 1920, 2560), "100vw", cls="car-b", attrs='decoding="async"')
    if hoch and (STATIC / "assets" / "img" / "leistungen-film-hoch.webp").exists():
        hb = pic("/assets/img/leistungen-film-hoch.webp", (720, 1080))
        car_b = f'<picture><source media="{hochkant}" srcset="{", ".join(f"{rel(root, u)} {w}w" for w, u in hb["srcset"])}" sizes="100vw">{car_b}</picture>'
    pos = f'--b-pos:{esc(lei.get("bild_position") or "50% 50%")}'
    akzent = f' <span class="accent">{esc(hero["titel_akzent"])}</span>' if hero.get("titel_akzent") else ""
    seq_attr = esc(json.dumps(seq_cfg, separators=(",", ":")))

    return f"""{head(root, HOME["seo_titel"], HOME["seo_beschreibung"], "", preload=preload, extra=chr(10) + "  " + TOKEN_REDIRECT + chr(10) + "  " + json_ld(ld))}
{header(root, "home")}
<main id="inhalt">
  <div class="journey" data-journey data-seq="{seq_attr}" style="{pos}">
    <div class="stage-wrap">
      <div class="stage">
        {car_b}
        <div class="stage-scrim" aria-hidden="true"></div>
        <div class="stage-shade" aria-hidden="true"></div>
        <canvas class="seq" aria-hidden="true"></canvas>
        {car_a}
        <section class="hero-frame" aria-labelledby="hero-titel">
          <h1 id="hero-titel" class="hero-fade">{esc(hero["titel"])}{akzent}</h1>
          <div class="hero-bottom hero-fade">
            {opt_p(hero.get("text", ""))}
            <div class="hero-actions">
              <a class="btn" href="#kontakt">{esc(S["anmelden_text"])} {icon("arrow-right", "icon-arrow")}</a>
              <a class="btn btn-ghost" href="standorte/">{esc(hero["knopf_standorte"])}</a>
            </div>
          </div>
        </section>
      </div>
    </div>
    <div class="hero-space" aria-hidden="true"></div>

    <section class="leistungen" id="leistungen" aria-labelledby="leistungen-titel">
      <div class="wrap">
        <div class="section-head">
          <h2 id="leistungen-titel">{esc(lei["titel"])}</h2>
          {opt_p(lei.get("text", ""))}
        </div>
{chr(10).join(gruppen)}
      </div>
    </section>
  </div>

  <section class="section" id="preise" aria-labelledby="preise-titel">
    <div class="wrap">
      <div class="section-head" data-reveal>
        <h2 id="preise-titel">{esc(preise["titel"])}</h2>
        {opt_p(preise.get("text", ""))}
      </div>
      <div class="preise-grid">
{chr(10).join(karten)}
      </div>
      <div class="preise-fuss">
{hinweise}
      </div>
    </div>
  </section>

  <section class="section" id="ueber-uns" aria-labelledby="ueber-titel">
    <div class="wrap">
      <h2 id="ueber-titel" class="visually-hidden">Über uns</h2>
      <div class="galerie" data-count="{len(galerie)}">
{galerie_html}
      </div>
      <div class="sprachen" data-reveal>
        <h3>{icon("translate")}{esc(ueber["sprachen_titel"])}</h3>
        <ul class="chips">
{chips}
        </ul>
        {opt_p(ueber.get("sprachen_hinweis", ""), "sprachen-note")}
      </div>
    </div>
  </section>
{bewertungen}
  <section class="section" id="kontakt" aria-labelledby="kontakt-titel">
    <div class="wrap kontakt-grid">
      <div class="kontakt-info" data-reveal>
        <div class="section-head">
          <h2 id="kontakt-titel">{esc(kon["titel"])}</h2>
          <p class="lead">{esc(kon["text"])}</p>
        </div>
        <div class="kontakt-wege">
          <a href="tel:{tel(S["telefon"])}">{icon("phone")}<span>{esc(S["telefon"])}<small>{esc(S.get("telefon_hinweis", "Telefon"))}</small></span></a>
          <a href="https://wa.me/{wa(S["whatsapp"])}" target="_blank" rel="noopener">{icon("whatsapp-logo")}<span>{esc(S["whatsapp"])}<small>WhatsApp</small></span></a>
          <a href="mailto:{esc(S["email"])}">{icon("envelope-simple")}<span>{esc(S["email"])}<small>E-Mail</small></span></a>
        </div>
        <div>
          <p class="liste-titel">{esc(kon.get("standorte_titel", "Unsere Standorte"))}</p>
          <div class="standort-liste">
{standort_links}
          </div>
        </div>
      </div>
      {contact_form(root, "kf", S["email"], "Anfrage über die Website", kon["formular_titel"], kon["formular_text"], with_standort=True, klassen=KLASSEN_OPTIONEN)}
    </div>
  </section>
</main>
{footer(root)}"""


# ---------------------------------------------------------------- Standorte


def page_standorte() -> str:
    root = "../"
    p = ST_PAGE
    cards = []
    for i, l in enumerate(LOCATIONS):
        badge = f'<span class="badge-neu">{esc(l["neu_text"])}</span>' if l.get("neu") and l.get("neu_text") else ""
        cards.append(f"""        <a class="standort-karte" href="{l["slug"]}/" data-reveal style="--i:{i}">
          <div class="standort-bild">
            {img(root, l["bild_karte"], (480, 960), "(max-width: 600px) 100vw, (max-width: 1100px) 50vw, 25vw", attrs=f'loading="{"eager" if i < 2 else "lazy"}" decoding="async"')}
            <div class="stadt">
              <span class="stadt-ort">{esc(l["region"])}</span>
              <span class="stadt-name">{esc(l["kurzname"])}</span>
            </div>
            {badge}
          </div>
          <div class="standort-body">
            <address>{esc(l["strasse"])}<br>{esc(l["plz"])} {esc(l["ort"])}</address>
            <p>{esc(l["kartentext"])}</p>
            <span class="text-link">{esc(p["link_text"])} {icon("arrow-right")}</span>
          </div>
        </a>""")
    return f"""{head(root, p["seo_titel"], p["seo_beschreibung"], "standorte/")}
{header(root, "standorte")}
<main id="inhalt">
  <section class="page-hero" aria-labelledby="standorte-titel">
    {img(root, p["bild"], (1200, 2400), "100vw", p.get("bild_alt", ""), attrs='fetchpriority="high"')}
    <div class="wrap">
      <h1 id="standorte-titel">{esc(p["titel"])}</h1>
      <p class="lead">{esc(p["text"])}</p>
    </div>
  </section>

  <section class="section">
    <div class="wrap">
      <div class="standorte-grid">
{chr(10).join(cards)}
      </div>
    </div>
  </section>
</main>
{footer(root)}"""


def page_standort(l: dict) -> str:
    root = "../../"
    chips = "\n".join(f'            <li class="chip">{esc(c)}</li>' for c in l.get("klassen", []))
    rows = []
    for r in l.get("buerozeiten", []):
        slot = f'{r["von"]}-{r["bis"]}' if r.get("von") and r.get("bis") else ""
        shown = f'{esc(r["von"])} - {esc(r["bis"])}' if slot else "geschlossen"
        rows.append(f'              <tr data-days="{",".join(r.get("tage", []))}" data-slots="{slot}"><th scope="row">{esc(r["bezeichnung"])}</th><td>{shown}</td></tr>')
    others = "\n".join(
        f'        <a href="../{o["slug"]}/"><strong>{esc(o["name"])} {icon("arrow-right")}</strong><small>{esc(o["strasse"])}</small></a>'
        for o in LOCATIONS if o is not l
    )
    form_klassen = ["B78 (Automatik)" if k == "B-Automatik" else k for k in l.get("klassen", [])] or KLASSEN_OPTIONEN
    ld = {"@context": "https://schema.org", **ld_location(l)}
    title = f"{S['firmenname']} {l['kurzname']} | {l['strasse']}, {l['ort']}"
    desc = f"{S['firmenname']} in {l['name']}, {l['strasse']}. Bürozeiten, Theorie, Führerscheinklassen und direkter Kontakt per Telefon, WhatsApp und E-Mail."
    theorie = ""
    if l.get("theorie_tage"):
        theorie = f"""
          <div class="zeiten-karte">
            <h3>Theorieunterricht</h3>
            <table class="zeiten-tabelle">
              <caption class="visually-hidden">Theorieunterricht {esc(l["name"])}</caption>
              <tr><th scope="row">{esc(l["theorie_tage"])}</th><td>{esc(l.get("theorie_zeit", ""))}</td></tr>
            </table>
          </div>"""
    return f"""{head(root, title, desc, f"standorte/{l['slug']}/", extra=chr(10) + "  " + json_ld(ld))}
{header(root, "standorte")}
<main id="inhalt">
  <section class="page-hero" aria-labelledby="ort-titel">
    {img(root, l.get("bild_titel") or ST_PAGE["standort_bild"], (1200, 1800), "100vw", attrs='fetchpriority="high"')}
    <div class="wrap">
      <nav class="crumbs" aria-label="Brotkrumen"><a href="../">Standorte</a>{icon("arrow-right")}<span aria-current="page">{esc(l["kurzname"])}</span></nav>
      <h1 id="ort-titel">{esc(l["name"])}</h1>
      <p class="lead">{esc(l["strasse"])}, {esc(l["plz"])} {esc(l["ort"])}</p>
    </div>
  </section>

  <section class="section">
    <div class="wrap standort-layout">
      <div class="standort-main">
        <p class="intro" data-reveal>{esc(l["einleitung"])}</p>

        <div data-reveal>
          <h2 class="block-titel">Kontakt</h2>
          <div class="aktionen">
            <a class="aktion" href="tel:{tel(l["telefon"])}">{icon("phone")}<span><strong>Anrufen</strong><small>{esc(l["telefon"])}</small></span></a>
            <a class="aktion" href="https://wa.me/{wa(l["whatsapp"])}" target="_blank" rel="noopener">{icon("whatsapp-logo")}<span><strong>WhatsApp</strong><small>{esc(l["whatsapp"])}</small></span></a>
            <a class="aktion" href="mailto:{esc(l["email"])}">{icon("envelope-simple")}<span><strong>E-Mail</strong><small>{esc(l["email"])}</small></span></a>
            <a class="aktion" href="{maps_url(l)}" target="_blank" rel="noopener">{icon("map-pin")}<span><strong>Route planen</strong><small>Google Maps</small></span></a>
          </div>
        </div>

        <div class="zeiten" data-reveal>
          <div class="zeiten-karte">
            <h3>Bürozeiten <span class="status" data-status></span></h3>
            <table class="zeiten-tabelle" data-hours>
              <caption class="visually-hidden">Bürozeiten {esc(l["name"])}</caption>
{chr(10).join(rows)}
            </table>
          </div>{theorie}
        </div>

        <div data-reveal>
          <h2 class="block-titel">Führerscheinklassen</h2>
          {opt_p(l.get("klassen_text", ""), "lead klassen-lead")}
          <ul class="chips">
{chips}
          </ul>
        </div>
      </div>

      <aside class="standort-side" aria-label="Kontaktformular">
        {contact_form(root, "kf-" + l["slug"], l["email"], f"Anfrage über die Website ({l['kurzname']})", f"Nachricht an EasyDrive {l['kurzname']}", HOME["kontakt"]["formular_text"], with_standort=False, klassen=form_klassen)}
      </aside>
    </div>
  </section>

  <section class="section">
    <div class="wrap">
      <h2 class="block-titel">{esc(ST_PAGE.get("weitere_titel", "Weitere Standorte"))}</h2>
      <div class="weitere">
{others}
      </div>
    </div>
  </section>
</main>
{footer(root)}"""


# ---------------------------------------------------------------- Rechtstexte


def page_legal(data: dict, path: str, description: str) -> str:
    root = "../"
    return f"""{head(root, data["seo_titel"], description, path, noindex=True)}
{header(root, solid=True)}
<main id="inhalt" class="legal">
  <div class="wrap">
    <h1>{esc(data["titel"])}</h1>
    {md(data["inhalt"])}
  </div>
</main>
{footer(root)}"""


def page_404() -> str:
    root = "/"
    return f"""{head(root, "Seite nicht gefunden | " + S["firmenname"], "Diese Seite gibt es nicht.", "404.html", noindex=True)}
{header(root, solid=True)}
<main id="inhalt" class="legal">
  <div class="wrap">
    <h1>Seite nicht gefunden</h1>
    <p>Diese Adresse gibt es nicht oder nicht mehr.</p>
    <p style="margin-top:28px"><a class="btn" href="/">Zur Startseite {icon("arrow-right", "icon-arrow")}</a></p>
  </div>
</main>
{footer(root)}"""


# ---------------------------------------------------------------- Ausgabe


def write(relpath: str, content: str) -> None:
    path = DIST / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    print("  ", relpath)


def sitemap() -> str:
    urls = ["", "standorte/"] + [f"standorte/{l['slug']}/" for l in LOCATIONS]
    items = "\n".join(f"  <url><loc>{SITE}/{u}</loc></url>" for u in urls)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{items}\n</urlset>\n'


def main() -> None:
    # dist leeren, aber den Bild-Zwischenspeicher behalten
    cache = DIST / "assets" / "img" / "_v"
    keep = None
    if cache.exists():
        keep = BASE / ".bildcache"
        if keep.exists():
            shutil.rmtree(keep)
        shutil.move(str(cache), str(keep))
    if DIST.exists():
        shutil.rmtree(DIST)
    shutil.copytree(STATIC, DIST)
    if keep:
        cache.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(keep), str(cache))

    print("Baue Seiten:")
    write("index.html", page_index())
    write("standorte/index.html", page_standorte())
    for l in LOCATIONS:
        write(f"standorte/{l['slug']}/index.html", page_standort(l))
    write("impressum/index.html", page_legal(IMPRESSUM, "impressum/", f"Impressum der {S['firmenname']}, {S['strasse']}, {S['plz']} {S['ort']}."))
    write("datenschutz/index.html", page_legal(DATENSCHUTZ, "datenschutz/", f"Datenschutzerklärung der {S['firmenname']}."))
    write("404.html", page_404())
    write("sitemap.xml", sitemap())
    write("robots.txt", f"User-agent: *\nDisallow: /admin/\n\nSitemap: {SITE}/sitemap.xml\n")

    if WARNINGS:
        print("\nHinweise:")
        for w in WARNINGS:
            print("  -", w)
    print("\nFertig. Ausgabe in dist/")


if __name__ == "__main__":
    sys.exit(main())
