#!/usr/bin/env python3
"""Google-Bewertungen-Sync für der-fuchsbau.net.

Läuft täglich als GitHub Action: holt Gesamtwertung + Rezensionen über
die offizielle Google-Places-API (New) und schreibt sie als reviews.json
ins Repo. Die Website zeigt ausschließlich diese lokale Kopie — Besucher
haben keinen Kontakt zu Google.

Der API-Schlüssel kommt aus dem GitHub-Secrets-Tresor (GOOGLE_PLACES_KEY),
die Place-ID ist öffentlich und steht im Workflow. Ist eines von beiden
leer, wird der Sync still übersprungen — die Anzeige friert dann beim
letzten Stand ein, nichts geht kaputt.
"""

import json
import os
import sys
from datetime import date

import requests

API_KEY = os.environ.get("GOOGLE_PLACES_KEY", "").strip()
PLACE_ID = os.environ.get("GOOGLE_PLACE_ID", "").strip()
MAX_REVIEWS = 3
MAX_CHARS = 220


def main() -> int:
    if not API_KEY or not PLACE_ID:
        print("GOOGLE_PLACES_KEY/GOOGLE_PLACE_ID leer — Bewertungs-Sync übersprungen.")
        return 0

    resp = requests.get(
        f"https://places.googleapis.com/v1/places/{PLACE_ID}",
        params={"languageCode": "de"},
        headers={
            "X-Goog-Api-Key": API_KEY,
            "X-Goog-FieldMask": "rating,userRatingCount,reviews",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    rating = data.get("rating")
    count = data.get("userRatingCount")
    if not rating or not count:
        print("Keine Bewertungsdaten im Ergebnis — reviews.json bleibt unverändert.")
        return 0

    items = []
    for review in data.get("reviews", []):
        if len(items) >= MAX_REVIEWS:
            break
        text = ((review.get("text") or {}).get("text") or "").strip().replace("\n", " ")
        if not text:
            continue
        if len(text) > MAX_CHARS:
            text = text[: MAX_CHARS - 1].rsplit(" ", 1)[0] + "…"
        # Datenschutz: nur der Vorname des öffentlichen Google-Profils
        full_name = ((review.get("authorAttribution") or {}).get("displayName") or "").strip()
        first_name = full_name.split(" ")[0] if full_name else ""
        items.append({
            "stars": review.get("rating", 5),
            "text": text,
            "name": first_name,
        })

    out = {
        "updated": date.today().isoformat(),
        "rating": round(float(rating), 1),
        "count": int(count),
        "items": items,
    }
    with open("reviews.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"Bewertungen synchronisiert: {rating} ★ aus {count} Rezensionen, {len(items)} Zitate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
