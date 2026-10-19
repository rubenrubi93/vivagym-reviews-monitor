#!/usr/bin/env python3
"""Update VivaGym public Google Places ratings and review counts."""
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "reviews.json"
API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
TZ = ZoneInfo("Europe/Madrid")

def search_place(query):
    url = "https://places.googleapis.com/v1/places:searchText"
    body = json.dumps({"textQuery": query, "languageCode": "es", "regionCode": "ES"}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": API_KEY,
            "X-Goog-FieldMask": "places.id,places.displayName,places.rating,places.userRatingCount",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Google Places API devolvió HTTP {exc.code}: {detail[:500]}") from exc
    places = payload.get("places", [])
    if not places:
        raise RuntimeError(f"No se encontró ninguna ficha para: {query}")
    return places[0]

def main():
    if not API_KEY:
        print("Falta el secreto GOOGLE_MAPS_API_KEY. No se ha modificado reviews.json.", file=sys.stderr)
        return 2

    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    now = datetime.now(TZ)
    today = now.date().isoformat()
    updated = 0

    # Exact, location-specific searches reduce the risk of selecting another club.
    queries = {
        "VivaGym Alcalá Plaza": "VivaGym Alcalá Plaza, Alcalá de Guadaíra, Sevilla, España",
        "VivaGym Camas": "VivaGym Camas, Sevilla, España",
        "VivaGym Dos Hermanas": "VivaGym Dos Hermanas, Sevilla, España",
        "VivaGym Los Remedios": "VivaGym Los Remedios, Sevilla, España",
        "VivaGym Nervión": "VivaGym Nervión, Sevilla, España",
        "VivaGym Sevilla Este": "VivaGym Sevilla Este, Sevilla, España",
    }

    # Validate every response before writing, so a partial/failed run never corrupts data.
    fetched = []
    for club in data.get("clubs", []):
        query = queries.get(club.get("name"))
        if not query:
            raise RuntimeError(f"No hay consulta configurada para el club: {club.get('name')}")
        place = search_place(query)
        display_name = place.get("displayName", {}).get("text", "")
        expected_terms = {
            "VivaGym Alcalá Plaza": ("alcal", "plaza"),
            "VivaGym Camas": ("camas",),
            "VivaGym Dos Hermanas": ("dos hermanas",),
            "VivaGym Los Remedios": ("remedios",),
            "VivaGym Nervión": ("nervion", "nervión"),
            "VivaGym Sevilla Este": ("sevilla este",),
        }[club["name"]]
        normalized_name = display_name.casefold()
        if not display_name or "vivagym" not in normalized_name or not any(term in normalized_name for term in expected_terms):
            raise RuntimeError(f"Resultado inesperado para {club['name']}: {display_name!r}. No se guardaron cambios.")
        if "rating" not in place or "userRatingCount" not in place:
            raise RuntimeError(f"La API no devolvió puntuación y/o número de reseñas para {club['name']}. No se guardaron cambios.")
        fetched.append((club, place))

    for club, place in fetched:
        rating = place["rating"]
        count = place["userRatingCount"]
        previous = club.get("history", [])
        last = previous[-1] if previous else None
        if not last or last.get("date") != today or last.get("rating") != rating or last.get("reviewCount") != count:
            previous.append({
                "date": today,
                "rating": rating,
                "reviewCount": count,
                "sourceUrl": club.get("mapsUrl") or club.get("sourceUrl", ""),
            })
        club["rating"] = rating
        club["reviewCount"] = count
        club["checkedAt"] = today
        club["history"] = previous
        updated += 1

    data["updatedAt"] = today
    data["summary"] = f"Actualización automática mediante Google Places API el {today} (hora peninsular)."
    data["source"] = "Google Places API (Place Search Text); puntuación y total de valoraciones de fichas públicas."
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Actualización completada: {updated} clubes; fecha {today}.")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
