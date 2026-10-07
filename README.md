# Fahrschule EasyDrive – Website

Neue Website für die Fahrschule EasyDrive (Hannover-Ricklingen, Hemmingen, Laatzen, Hannover-List).
Statische Seiten, gebaut mit einem kleinen Python-Skript, bearbeitbar über **Decap CMS** auf **Netlify**.

## Aufbau

```
content/              Alle Texte und Bildpfade (JSON). Hier schreibt Decap CMS hinein.
  startseite.json       Hero, Leistungen, Preise, Über uns, Bewertungen, Kontakt
  standorte-seite.json  Übersichtsseite /standorte/
  standorte/*.json      Ein Datei pro Standort, jede wird automatisch zu einer Unterseite
  einstellungen.json    Logo, Hauptkontakt, Fußzeile
  impressum.json, datenschutz.json
static/               Wird 1:1 veröffentlicht: CSS, JS, Schrift, Bilder, Decap (/admin/), _redirects
_quelle/build.py      Baut aus content/ + static/ die fertige Seite nach dist/
dist/                 Fertige Website (wird von Netlify veröffentlicht, nicht ins Git)
netlify.toml          Build-Befehl und Cache-Header
requirements.txt      Python-Pakete für den Build (Markdown, Pillow)
```

Seiten: `/`, `/standorte/`, `/standorte/easydrive-<ort>/` (je Standort), `/impressum/`, `/datenschutz/`, `/admin/`.
Alte Jimdo-Adressen (`/preise/`, `/das-sind-wir/` …) leitet `static/_redirects` weiter.

## Lokal bauen und ansehen

```bash
pip install -r requirements.txt
python _quelle/build.py
python -m http.server 8783 --directory dist
```

Dann http://localhost:8783 öffnen. Nach jeder Änderung an `content/`, `static/` oder `build.py` neu bauen.

Decap lokal testen (ohne Netlify): im Projektordner `npx decap-server` starten, dann http://localhost:8783/admin/ öffnen und auf „Login“ klicken. Änderungen landen direkt in `content/`.

## Auf Netlify einrichten (einmalig)

1. Projektordner als eigenes GitHub-Repository hochladen (`dist/` ist per `.gitignore` ausgeschlossen).
2. Netlify: **Add new site → Import an existing project** → Repository wählen. Build-Einstellungen kommen aus `netlify.toml` (Befehl `python _quelle/build.py`, Ordner `dist`).
3. Netlify: **Site configuration → Identity → Enable Identity**.
   - Registration auf **Invite only** stellen.
   - Unter **Services → Git Gateway → Enable Git Gateway**.
4. Unter **Identity → Invite users** die E-Mail-Adresse der Fahrschule einladen. Der Einladungslink führt automatisch nach `/admin/`, dort wird das Passwort gesetzt.
5. Eigene Domain verbinden (`www.fahrschule-easydrive.org`) und HTTPS aktivieren.
6. Im Netlify-Konto den **Vertrag zur Auftragsverarbeitung (DPA)** annehmen (siehe Datenschutzerklärung).

Bearbeiten: `https://www.fahrschule-easydrive.org/admin/` → anmelden → ändern → **Veröffentlichen**. Netlify baut die Seite danach in etwa einer Minute neu.

Bilder können in Originalgröße hochgeladen werden: Der Build verkleinert sie automatisch und erzeugt WebP-Dateien in mehreren Breiten.

## Offene Punkte vor dem Livegang

- [x] Hero- und Leistungsbild (BMW, KI-generiert) eingesetzt. Das Leistungsbild steht auch oben auf allen Standortseiten (Decap: Standorte-Übersichtsseite → „Titelbild aller Standortseiten“). Im Impressum ist vermerkt, dass die Fahrzeugbilder KI-generiert sind.
- [ ] **Impressum** prüfen (gelber Kasten auf der Seite): Berufsbezeichnung Fahrlehrer, USt-IdNr. Die alte Seite führte unter „USt-IdNr.“ eine Steuernummer, die wurde entfernt.
- [ ] **Datenschutz**: Netlify-DPA annehmen; Instagram-Abschnitt nur behalten, wenn es ein Profil gibt.
- [ ] **WhatsApp Hannover-List**: Auf der alten Seite zeigte der Knopf auf 0176 45 34 88 83, der Text nannte 0162 97 91 401 (die Nummer aus Ricklingen). Übernommen wurde die Knopf-Nummer, bitte bestätigen lassen.
- [ ] **E-Mail Ricklingen**: Auf der alten Seite hatte der Link einen Tippfehler (`fahrsschule…`). Hier steht die richtige Adresse `fahrschuleeasydrive@hotmail.com`.
- [ ] **Rezensionen**: Die Karten sind Platzhalter. Echte Zitate in Decap unter Startseite → Bewertungen eintragen.
- [ ] Gelbe Hinweis-Kästen in Impressum und Datenschutz danach löschen.

## Kamerafahrt im Hero (Film)

Beim Scrollen läuft ein KI-generierter Film (`_quelle/kamerafahrt.mp4`, Kling, 5 s, 121 Bilder) Bild für Bild ab: Das Auto dreht sich von der Schrägansicht zur Front, der Ausschnitt wächst vom Startbild unten rechts bis zur vollen Fläche. Das letzte Bild (`static/assets/img/leistungen-film.webp`) ist der Hintergrund des ganzen Leistungs-Abschnitts. Das Kling-Wasserzeichen wird beim Zerlegen automatisch entfernt.

Neues Video einsetzen:

```bash
pip install imageio-ffmpeg
python _quelle/frames.py film <video.mp4>
python _quelle/build.py
```

Das Video sollte das Auto auf schwarzem Hintergrund zeigen und mit der Frontansicht enden.

## Kontaktformulare

Die Formulare öffnen das E-Mail-Programm der Besucher mit einer fertig ausgefüllten Nachricht an die jeweilige Standort-Adresse. Es wird nichts auf einem Server gespeichert, deshalb ist kein Cookie-Banner nötig. Sollen Nachrichten später direkt verschickt werden, lässt sich das mit Netlify Forms nachrüsten (Datenschutzerklärung dann anpassen).

## Quellen

Inhalte, Preise, Bürozeiten und Fotos stammen von der bisherigen Website fahrschule-easydrive.org. Google-Bewertungen (Stand Oktober 2026): Ricklingen 4,7 (243), Hemmingen 4,7 (20), Laatzen 4,8 (20), List noch ohne Bewertungen.
Schrift: Archivo (SIL Open Font License), lokal eingebunden. Icons: Phosphor Icons (MIT).
