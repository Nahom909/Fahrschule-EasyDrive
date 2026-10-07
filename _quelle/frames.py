"""Erzeugt die Bildfolge für die Scroll-Kamerafahrt im Hero.

Quellen:
  python _quelle/frames.py raster <bild> --spalten 4 --zeilen 3 [--x 0,418,836,1253,1672 --y 0,362,666,941]
      Zerlegt ein Storyboard-Raster in Einzelbilder (Reihenfolge zeilenweise).
  python _quelle/frames.py video <datei.mp4> [--max 240]
      Zerlegt ein Video in so viele Einzelbilder wie möglich (braucht: pip install imageio-ffmpeg).
  python _quelle/frames.py film <datei.mp4> [--breite 1600] [--hoch]
      Video als fertige Kamerafahrt: alle Bilder, Hintergrund bleibt, Wasserzeichen wird entfernt.
  python _quelle/frames.py ordner <ordner>
      Nimmt alle Bilder eines Ordners in Dateinamen-Reihenfolge (z. B. 01.png, 02.png …).
  python _quelle/frames.py freistellen <bild> <ziel.webp>
      Stellt ein einzelnes Autobild frei (Hintergrund wird transparent).

Jedes Bild wird freigestellt (heller oder schwarzer Hintergrund wird transparent),
auf eine gemeinsame Größe gebracht und als WebP mit Transparenz gespeichert.
Ergebnis: static/assets/seq/frame-001.webp … und static/assets/seq/manifest.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "static" / "assets" / "seq"
OUT_MANIFEST_ALT: dict = {}


# ---------------------------------------------------------------- Freistellen


def _flood_from_border(mask: np.ndarray) -> np.ndarray:
    """Alle Hintergrund-Kandidaten, die mit dem Bildrand verbunden sind."""
    filled = np.zeros_like(mask)
    filled[0, :] = mask[0, :]
    filled[-1, :] = mask[-1, :]
    filled[:, 0] = mask[:, 0]
    filled[:, -1] = mask[:, -1]
    while True:
        grown = filled.copy()
        grown[1:, :] |= filled[:-1, :]
        grown[:-1, :] |= filled[1:, :]
        grown[:, 1:] |= filled[:, :-1]
        grown[:, :-1] |= filled[:, 1:]
        grown &= mask
        if np.array_equal(grown, filled):
            return filled
        filled = grown


def _dilate(mask: np.ndarray, steps: int) -> np.ndarray:
    out = mask.copy()
    for _ in range(steps):
        g = out.copy()
        g[1:, :] |= out[:-1, :]
        g[:-1, :] |= out[1:, :]
        g[:, 1:] |= out[:, :-1]
        g[:, :-1] |= out[:, 1:]
        out = g
    return out


def _box_mean(a: np.ndarray, r: int) -> np.ndarray:
    """Mittelwert in einem (2r+1)²-Fenster, über ein Integralbild."""
    p = np.pad(a, r + 1, mode="edge")
    c = p.cumsum(0).cumsum(1)
    k = 2 * r + 1
    s = c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]
    return s[: a.shape[0], : a.shape[1]] / (k * k)


def freistellen(img: Image.Image) -> Image.Image:
    """Macht den Hintergrund transparent. Erkennt automatisch hell (weiß/grau) oder schwarz.
    Ist das Bild schon freigestellt (eigene Transparenz), wird diese übernommen."""
    if "A" in img.getbands():
        a = np.asarray(img.getchannel("A"))
        if (a < 10).mean() > 0.02:
            return img.convert("RGBA")
    rgb = np.asarray(img.convert("RGB")).astype(np.float32)
    lum = rgb @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    sat = rgb.max(axis=2) - rgb.min(axis=2)
    border = np.concatenate([lum[0], lum[-1], lum[:, 0], lum[:, -1]])
    hell = np.median(border) > 128

    if hell:
        bg = _flood_from_border((lum > 120) & (sat < 70))
        # helle Sprenkel, die das Fluten nicht erreicht (Kompressionsrauschen), ebenfalls entfernen:
        # helle Pixel, deren Umgebung überwiegend Hintergrund ist
        anteil = _box_mean(bg.astype(np.float32), 9)
        bg |= (lum > 120) & (anteil > 0.45)
        rand = _dilate(bg, 2) & ~bg
        alpha = np.ones_like(lum)
        alpha[bg] = 0.0
        # weicher Übergang am Rand: je heller, desto durchsichtiger
        alpha[rand] = np.clip((235.0 - lum[rand]) / 175.0, 0.0, 1.0)
        # Weißsaum entfernen (Farbe gegen Weiß zurückrechnen)
        a = np.maximum(alpha, 1e-3)[..., None]
        rgb = np.where(rand[..., None], np.clip((rgb - (1 - a) * 255.0) / a, 0, 255), rgb)
    else:
        bg = _flood_from_border(rgb.max(axis=2) <= 10)
        rand = _dilate(bg, 2) & ~bg
        alpha = np.ones_like(lum)
        alpha[bg] = 0.0
        alpha[rand] = np.clip(rgb.max(axis=2)[rand] / 40.0, 0.0, 1.0)

    rgba = np.dstack([rgb, alpha * 255.0]).astype(np.uint8)
    out = Image.fromarray(rgba, "RGBA")
    # Alphakante minimal glätten
    a = out.getchannel("A").filter(ImageFilter.GaussianBlur(0.6))
    out.putalpha(a)
    return out


def veredeln(img: Image.Image) -> Image.Image:
    """Einheitlicher Look: tiefere Schwärzen, klarere Reflexe (nur Farbe, Transparenz bleibt)."""
    from PIL import ImageEnhance
    rgb = img.convert("RGB")
    rgb = ImageEnhance.Contrast(rgb).enhance(1.12)
    rgb = ImageEnhance.Color(rgb).enhance(1.06)
    out = rgb.convert("RGBA")
    out.putalpha(img.getchannel("A"))
    return out


def schaerfen(img: Image.Image, skalierung: float) -> Image.Image:
    """Nach dem Hochrechnen nachschärfen; stärker, je mehr hochgerechnet wurde."""
    staerke = 70 if skalierung <= 1 else 105
    rgb = img.convert("RGB").filter(ImageFilter.UnsharpMask(radius=1.6, percent=staerke, threshold=2))
    rgb = rgb.filter(ImageFilter.UnsharpMask(radius=0.6, percent=40, threshold=1))
    out = rgb.convert("RGBA")
    out.putalpha(img.getchannel("A"))
    return out


def schnittkanten(img: Image.Image) -> str:
    """Welche Bildkanten schneiden das Auto ab? (o = oben, r = rechts, u = unten, l = links)
    Gilt als Schnitt, wenn das Auto auf mindestens 40 % der Kantenlänge anliegt."""
    a = np.asarray(img.getchannel("A")) > 24
    kanten = ""
    if a[:6, :].any(axis=0).mean() > 0.4:
        kanten += "o"
    if a[:, -6:].any(axis=1).mean() > 0.4:
        kanten += "r"
    if a[-6:, :].any(axis=0).mean() > 0.4:
        kanten += "u"
    if a[:, :6].any(axis=1).mean() > 0.4:
        kanten += "l"
    return kanten


def bbox(img: Image.Image) -> tuple[int, int, int, int]:
    a = np.asarray(img.getchannel("A"))
    ys, xs = np.where(a > 24)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


# ---------------------------------------------------------------- Ausgabe


def schreibe_folge(bilder: list[Image.Image], skalierung: float, quelle: str) -> None:
    """Alle Bilder auf gleiche Leinwand (größtes Bild), freistellen, speichern."""
    W = max(b.width for b in bilder)
    H = max(b.height for b in bilder)
    global OUT_MANIFEST_ALT
    m = OUT / "manifest.json"
    OUT_MANIFEST_ALT = json.loads(m.read_text(encoding="utf-8")) if m.exists() else {}
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    frames = []
    for i, b in enumerate(bilder, 1):
        cut = veredeln(freistellen(b))
        schnitt = schnittkanten(cut)
        leinwand = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        leinwand.paste(cut, ((W - b.width) // 2, (H - b.height) // 2))
        if skalierung != 1:
            leinwand = leinwand.resize((round(W * skalierung), round(H * skalierung)), Image.LANCZOS)
        leinwand = schaerfen(leinwand, skalierung)
        name = f"frame-{i:03d}.webp"
        leinwand.save(OUT / name, "WEBP", quality=88, alpha_quality=92, method=6)
        x0, y0, x1, y1 = bbox(leinwand)
        frames.append({
            "src": name,
            "bbox": [x0 / leinwand.width, y0 / leinwand.height, x1 / leinwand.width, y1 / leinwand.height],
            "schnitt": schnitt,
        })
        print("  ", name, leinwand.size, "Schnitt:", schnitt or "-")
    alt = OUT_MANIFEST_ALT.copy()
    manuell = alt.get("schnitt_manuell", {})
    for nr, kanten in manuell.items():
        if 1 <= int(nr) <= len(frames):
            frames[int(nr) - 1]["schnitt"] = kanten
    zeiten = alt.get("zeiten") if alt.get("zeiten") and len(alt["zeiten"]) == len(frames) else None
    manifest = {
        "ende_bbox": alt.get("ende_bbox", [0.055, 0.0, 0.945, 0.99]),
        "schnitt_manuell": manuell,
        "zeiten": zeiten or [round(i / max(1, len(frames) - 1), 4) for i in range(len(frames))],
        "quelle": quelle,
        "breite": round(W * skalierung),
        "hoehe": round(H * skalierung),
        "anzahl": len(frames),
        "frames": frames,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(frames)} Bilder, {manifest['breite']} x {manifest['hoehe']} px, gespeichert in static/assets/seq/")


def raster(pfad: str, spalten: int, zeilen: int, xs: list[int] | None, ys: list[int] | None, rand: int) -> None:
    im = Image.open(pfad)
    im = im.convert("RGBA") if "A" in im.getbands() else im.convert("RGB")
    xs = xs or [round(im.width * c / spalten) for c in range(spalten + 1)]
    ys = ys or [round(im.height * r / zeilen) for r in range(zeilen + 1)]
    kacheln = []
    for r in range(zeilen):
        for c in range(spalten):
            kacheln.append(im.crop((xs[c] + rand, ys[r] + rand, xs[c + 1] - rand, ys[r + 1] - rand)))
    schreibe_folge(kacheln, 2.0, f"Storyboard {Path(pfad).name}")


def video(pfad: str, maximum: int) -> None:
    try:
        import imageio_ffmpeg
    except ImportError:
        sys.exit("Bitte zuerst installieren: pip install imageio-ffmpeg")
    reader = imageio_ffmpeg.read_frames(pfad)
    meta = next(reader)
    w, h = meta["size"]
    alle = [Image.frombytes("RGB", (w, h), f) for f in reader]
    if len(alle) > maximum:
        idx = np.linspace(0, len(alle) - 1, maximum).round().astype(int)
        alle = [alle[i] for i in idx]
    faktor = min(1.0, 1600 / w)
    schreibe_folge(alle, faktor, f"Video {Path(pfad).name}")


def _wasserzeichen_maske(st: np.ndarray) -> np.ndarray:
    """Findet ein festes, helles Overlay (z. B. „KlingAI“) im unteren rechten Viertel:
    Pixel, die in JEDEM Bild hell sind. Das Auto bewegt sich, das Wasserzeichen nicht."""
    hell_immer = st.min(axis=0).max(axis=2) > 35
    h, w = hell_immer.shape
    bereich = np.zeros_like(hell_immer)
    bereich[int(h * 0.82):, int(w * 0.75):] = True
    return _dilate(hell_immer & bereich, 3)


def _ausfuellen(bild: np.ndarray, maske: np.ndarray, runden: int = 60) -> np.ndarray:
    """Füllt die Maske von außen nach innen mit dem Mittel der Nachbarn (einfache Retusche).
    Gerechnet wird nur im Rechteck um die Maske, das hält es schnell."""
    ys, xs = np.where(maske)
    y0, y1 = max(0, ys.min() - 4), min(maske.shape[0], ys.max() + 5)
    x0, x1 = max(0, xs.min() - 4), min(maske.shape[1], xs.max() + 5)
    ergebnis = bild.copy()
    ergebnis[y0:y1, x0:x1] = _ausfuellen_ausschnitt(bild[y0:y1, x0:x1], maske[y0:y1, x0:x1], runden)
    return ergebnis


def _ausfuellen_ausschnitt(bild: np.ndarray, maske: np.ndarray, runden: int) -> np.ndarray:
    out = bild.astype(np.float32).copy()
    offen = maske.copy()
    for _ in range(runden):
        if not offen.any():
            break
        summe = np.zeros_like(out)
        anzahl = np.zeros(offen.shape, np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nachbar_ok = ~np.roll(offen, (dy, dx), axis=(0, 1))
            summe += np.roll(out, (dy, dx), axis=(0, 1)) * nachbar_ok[..., None]
            anzahl += nachbar_ok
        rand = offen & (anzahl > 0)
        out[rand] = summe[rand] / anzahl[rand][:, None]
        offen &= ~rand
    return out.clip(0, 255).astype(np.uint8)


def film(pfad: str, breite: int, ende_ziel: str | None, hoch: bool = False, kante_oben: int = 0) -> None:
    """Video unverändert in Einzelbilder zerlegen (Hintergrund bleibt, z. B. schwarz),
    Wasserzeichen wegretuschieren, als WebP speichern.
    Es entstehen zwei Sätze: volle Größe und eine leichte Fassung fürs Handy (Unterordner m/).
    hoch=True: Hochformat-Video fürs Handy, landet in static/assets/seq-hoch/."""
    try:
        import imageio_ffmpeg
    except ImportError:
        sys.exit("Bitte zuerst installieren: pip install imageio-ffmpeg")
    ziel = BASE / "static" / "assets" / ("seq-hoch" if hoch else "seq")
    reader = imageio_ffmpeg.read_frames(pfad)
    meta = next(reader)
    w, h = meta["size"]
    st = np.stack([np.frombuffer(f, np.uint8).reshape(h, w, 3) for f in reader])
    maske = _wasserzeichen_maske(st)
    if maske.any():
        ys, xs = np.where(maske)
        print(f"Wasserzeichen gefunden bei x {xs.min()}-{xs.max()}, y {ys.min()}-{ys.max()}, wird entfernt")
    if ziel.exists():
        shutil.rmtree(ziel)
    (ziel / "m").mkdir(parents=True)
    faktor = min(1.0, breite / w)
    W, H = round(w * faktor), round(h * faktor)
    leicht = min(1.0, (720 if hoch else 820) / w)
    Wm, Hm = round(w * leicht), round(h * leicht)
    # harte, waagerechte Schnittkante über dem Auto weich ins Schwarz auslaufen lassen
    verlauf = None
    if kante_oben:
        band = max(40, h // 20)
        t = np.clip((np.arange(h) - kante_oben) / band, 0, 1)
        verlauf = (t * t * (3 - 2 * t)).astype(np.float32)[:, None, None]
        print(f"Oberkante bei y={kante_oben} wird über {band} px ausgeblendet")
    frames = []
    letztes = None
    for i, f in enumerate(st, 1):
        if maske.any():
            f = _ausfuellen(f, maske)
        if verlauf is not None:
            f = (f.astype(np.float32) * verlauf).astype(np.uint8)
        im = Image.fromarray(f)
        letztes = im
        name = f"frame-{i:03d}.webp"
        gross = im.resize((W, H), Image.LANCZOS) if faktor != 1 else im
        gross.filter(ImageFilter.UnsharpMask(radius=1.0, percent=45, threshold=2)).save(ziel / name, "WEBP", quality=80, method=6)
        klein = im.resize((Wm, Hm), Image.LANCZOS).filter(ImageFilter.UnsharpMask(radius=0.8, percent=40, threshold=2))
        klein.save(ziel / "m" / name, "WEBP", quality=74, method=6)
        frames.append({"src": name})
    if ende_ziel and letztes is not None:
        letztes.save(BASE / ende_ziel, "WEBP", quality=90, method=6)
        print("Endbild (volle Auflösung):", ende_ziel)
    def band(bild: Image.Image) -> list[float]:
        g = np.asarray(bild.convert("L"))
        hh, ww = g.shape
        g = g[: int(hh * 0.93)]  # Wasserzeichen-Zone unten ignorieren
        r = np.where((g > 30).mean(1) > 0.03)[0]
        c = np.where((g > 30).mean(0) > 0.03)[0]
        return [round(c.min() / ww, 3), round(r.min() / hh, 3), round(c.max() / ww, 3), round(r.max() / hh, 3)]

    erstes_bild = Image.open(ziel / frames[0]["src"])
    letztes_bild = Image.open(ziel / frames[-1]["src"])
    manifest = {
        "typ": "film",
        "band_start": band(erstes_bild),   # wo das Auto im ersten Bild liegt (Anteile)
        "band_ende": band(letztes_bild),   # und im letzten
        "quelle": f"Video {Path(pfad).name}",
        "breite": W,
        "hoehe": H,
        "anzahl": len(frames),
        "leicht": "m/",
        "frames": frames,
    }
    (ziel / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(frames)} Bilder, {W} x {H} px (Handy: {Wm} x {Hm}), gespeichert in {ziel.relative_to(BASE)}")


def ordner(pfad: str) -> None:
    dateien = sorted(p for p in Path(pfad).iterdir() if p.suffix.lower() in (".png", ".webp", ".jpg", ".jpeg"))
    if not dateien:
        sys.exit("Keine Bilder im Ordner gefunden.")
    bilder = [Image.open(d) for d in dateien]
    faktor = min(1.0, 1600 / max(b.width for b in bilder))
    schreibe_folge(bilder, faktor, f"Ordner {Path(pfad).name}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="modus", required=True)
    r = sub.add_parser("raster")
    r.add_argument("bild")
    r.add_argument("--spalten", type=int, default=4)
    r.add_argument("--zeilen", type=int, default=3)
    r.add_argument("--x", help="Spaltengrenzen in Pixeln, kommagetrennt")
    r.add_argument("--y", help="Zeilengrenzen in Pixeln, kommagetrennt")
    r.add_argument("--rand", type=int, default=3, help="Pixel, die an jeder Kachelkante abgeschnitten werden")
    v = sub.add_parser("video")
    v.add_argument("datei")
    v.add_argument("--max", type=int, default=240)
    fi = sub.add_parser("film", help="Video als Kamerafahrt (Hintergrund bleibt, Wasserzeichen wird entfernt)")
    fi.add_argument("datei")
    fi.add_argument("--breite", type=int, default=1600)
    fi.add_argument("--ende", default=None, help="letztes Bild in voller Auflösung hierhin")
    fi.add_argument("--hoch", action="store_true", help="Hochformat-Video fürs Handy (9:16)")
    fi.add_argument("--kante-oben", type=int, default=0, help="y-Pixel einer harten Kante über dem Auto, wird weich ausgeblendet")
    o = sub.add_parser("ordner")
    o.add_argument("pfad")
    f = sub.add_parser("freistellen")
    f.add_argument("bild")
    f.add_argument("ziel")
    a = ap.parse_args()
    if a.modus == "raster":
        raster(a.bild, a.spalten, a.zeilen,
               [int(x) for x in a.x.split(",")] if a.x else None,
               [int(y) for y in a.y.split(",")] if a.y else None, a.rand)
    elif a.modus == "video":
        video(a.datei, a.max)
    elif a.modus == "film":
        ende = a.ende or ("static/assets/img/leistungen-film-hoch.webp" if a.hoch else "static/assets/img/leistungen-film.webp")
        film(a.datei, a.breite if not a.hoch or a.breite != 1600 else 1080, ende, a.hoch, a.kante_oben)
    elif a.modus == "ordner":
        ordner(a.pfad)
    else:
        out = freistellen(Image.open(a.bild))
        out.save(a.ziel, "WEBP", quality=88, alpha_quality=92, method=6)
        print("freigestellt:", a.ziel, out.size, "Auto:", bbox(out))


if __name__ == "__main__":
    main()
