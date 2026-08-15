#!/usr/bin/env python3
"""Instagram-Sync für der-fuchsbau.net.

Läuft täglich als GitHub Action: holt die neuesten Posts aus dem
Behold-JSON-Feed, verkleinert die Bilder, entfernt EXIF-Daten
(Datenschutz: Handyfotos enthalten oft GPS-Koordinaten) und legt sie
als lokale Dateien unter gallery/ ab. Die Website zeigt ausschließlich
diese lokalen Kopien — Besucher haben keinen Kontakt zu Meta/Behold.

Bricht die Verbindung irgendwann (API-Änderung, Konto getrennt),
schlägt dieses Skript fehl oder liefert nichts Neues — die Galerie
friert dann einfach beim letzten Stand ein. Kein Fehler auf der Seite.
"""

import io
import json
import os
import sys
from datetime import date

import requests
from PIL import Image

FEED_URL = os.environ.get("FEED_URL", "").strip()
MAX_POSTS = 6
MAX_WIDTH = 1200
JPEG_QUALITY = 82
OUT_DIR = "gallery"


def main() -> int:
    if not FEED_URL:
        print("FEED_URL ist leer — Sync übersprungen (noch nicht konfiguriert).")
        return 0

    resp = requests.get(FEED_URL, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    # Behold liefert je nach Version {"posts": [...]} oder direkt [...]
    posts = data.get("posts", data) if isinstance(data, dict) else data
    if not isinstance(posts, list):
        print("Unerwartetes Feed-Format — Sync abgebrochen, Galerie bleibt unverändert.")
        return 0

    os.makedirs(OUT_DIR, exist_ok=True)
    items = []
    n = 0
    for post in posts:
        if n >= MAX_POSTS:
            break
        if not isinstance(post, dict):
            continue
        media_type = post.get("mediaType", "IMAGE")
        # Bei Videos das Vorschaubild verwenden; ohne Bildquelle überspringen
        url = None
        if media_type == "VIDEO":
            url = post.get("thumbnailUrl")
        if not url:
            url = post.get("mediaUrl") or post.get("thumbnailUrl")
        # Behold-Sizes-Objekt (falls vorhanden): mittlere Größe reicht
        sizes = post.get("sizes")
        if isinstance(sizes, dict):
            for key in ("large", "medium", "full"):
                entry = sizes.get(key)
                if isinstance(entry, dict) and entry.get("mediaUrl"):
                    url = entry["mediaUrl"]
                    break
        if not url:
            continue

        try:
            img_resp = requests.get(url, timeout=60)
            img_resp.raise_for_status()
            im = Image.open(io.BytesIO(img_resp.content))
        except Exception as exc:  # noqa: BLE001 — einzelnes Bild überspringen
            print(f"Bild übersprungen ({exc})")
            continue

        im = im.convert("RGB")
        if im.width > MAX_WIDTH:
            im = im.resize(
                (MAX_WIDTH, round(im.height * MAX_WIDTH / im.width)),
                Image.LANCZOS,
            )

        n += 1
        filename = f"photo-{n}.jpg"
        # Neu kodieren ohne EXIF (kein exif=-Parameter ⇒ Metadaten entfernt)
        im.save(os.path.join(OUT_DIR, filename), "JPEG",
                quality=JPEG_QUALITY, optimize=True)

        caption = (post.get("caption") or "").strip().replace("\n", " ")
        alt = caption if len(caption) <= 120 else caption[:117] + "…"
        if len(caption) > 220:
            caption = caption[:217].rsplit(" ", 1)[0] + "…"
        items.append({
            "file": filename,
            "alt": alt or "Foto aus dem Fuchsbau (von Instagram)",
            "caption": caption,
            "link": post.get("permalink") or "",
        })

    if not items:
        print("Keine verwendbaren Bilder im Feed — Galerie bleibt unverändert.")
        return 0

    # Auf Instagram gelöschte Posts auch hier löschen: alle photo-*.jpg
    # entfernen, die nicht mehr zum aktuellen Bestand gehören
    current = {item["file"] for item in items}
    for existing in os.listdir(OUT_DIR):
        if existing.startswith("photo-") and existing.endswith(".jpg") and existing not in current:
            os.remove(os.path.join(OUT_DIR, existing))
            print(f"Entfernt (nicht mehr im Feed): {existing}")

    manifest = {"updated": date.today().isoformat(), "items": items}
    with open(os.path.join(OUT_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print(f"{len(items)} Bilder synchronisiert.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
