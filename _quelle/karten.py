"""Erzeugt für jeden Standort ein statisches Kartenbild (dunkel, mit Markierung).

    python _quelle/karten.py

Die Kacheln kommen von OpenStreetMap (einmalig beim Erzeugen, nicht beim Besuch der Seite).
Es wird also nichts eingebettet, Besucher laden nur ein lokales Bild: kein Cookie-Banner nötig.
Ergebnis: static/assets/img/karte-<standort>.webp
Pflicht laut OSM-Lizenz: Hinweis „© OpenStreetMap-Mitwirkende“ beim Bild (steht im HTML).
"""
from __future__ import annotations

import io
import json
import math
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageOps

BASE = Path(__file__).resolve().parent.parent
ZOOM = 16
BREITE, HOEHE = 1200, 700
UA = "FahrschuleEasyDrive-Kartenbild/1.0 (statisches Bild fuer die Website)"


def kachel(x: int, y: int) -> Image.Image:
    url = f"https://tile.openstreetmap.org/{ZOOM}/{x}/{y}.png"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return Image.open(io.BytesIO(urllib.request.urlopen(req, timeout=20).read())).convert("RGB")


def karte(lat: float, lon: float) -> Image.Image:
    n = 2 ** ZOOM
    px = (lon + 180) / 360 * n * 256
    py = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n * 256
    x0, y0 = px - BREITE / 2, py - HOEHE / 2
    tx0, ty0 = int(x0 // 256), int(y0 // 256)
    tx1, ty1 = int((x0 + BREITE) // 256), int((y0 + HOEHE) // 256)
    gross = Image.new("RGB", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256))
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            gross.paste(kachel(tx, ty), ((tx - tx0) * 256, (ty - ty0) * 256))
    ox, oy = int(x0 - tx0 * 256), int(y0 - ty0 * 256)
    bild = gross.crop((ox, oy, ox + BREITE, oy + HOEHE))
    # dunkler Kartenstil passend zur Seite: grau, invertiert, gedämpft
    bild = ImageOps.invert(ImageOps.grayscale(bild)).convert("RGB")
    bild = ImageEnhance.Brightness(bild).enhance(0.62)
    bild = ImageEnhance.Contrast(bild).enhance(1.15)
    # Markierung (Stecknadel) in der Mitte, auf transparenter Ebene für weiche Kanten
    ebene = Image.new("RGBA", (BREITE * 2, HOEHE * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(ebene)
    cx, cy = BREITE, HOEHE
    d.ellipse((cx - 70, cy - 22, cx + 70, cy + 22), fill=(255, 255, 255, 45))     # Schatten/Schein am Boden
    d.polygon([(cx - 30, cy - 78), (cx + 30, cy - 78), (cx, cy)], fill=(255, 255, 255, 255))
    d.ellipse((cx - 38, cy - 136, cx + 38, cy - 60), fill=(255, 255, 255, 255))
    d.ellipse((cx - 15, cy - 113, cx + 15, cy - 83), fill=(24, 24, 26, 255))
    ebene = ebene.resize((BREITE, HOEHE), Image.LANCZOS)
    bild = Image.alpha_composite(bild.convert("RGBA"), ebene).convert("RGB")
    return bild


def main() -> None:
    for f in sorted((BASE / "content" / "standorte").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if not d.get("breitengrad") or not d.get("laengengrad"):
            print("übersprungen (keine Koordinaten):", f.stem)
            continue
        ziel = BASE / "static" / "assets" / "img" / f"karte-{f.stem}.webp"
        karte(d["breitengrad"], d["laengengrad"]).save(ziel, "WEBP", quality=82, method=6)
        print("Karte:", ziel.relative_to(BASE))


if __name__ == "__main__":
    main()
