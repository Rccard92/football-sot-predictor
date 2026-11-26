"""Foto nelle note della giocata (capitolato del 24/11/2026, modifica 18).

Fino a 5 foto per giocata, JPG, PNG o WEBP, al massimo 5 MB l'una. Il sito le riduce a 1600 pixel sul lato lungo e
le salva in JPEG senza dati EXIF (posizione GPS, modello del telefono): si ricodifica solo l'immagine.
"""

from __future__ import annotations

import io

MAX_PHOTOS = 5
MAX_BYTES = 5 * 1024 * 1024
MAX_SIDE = 1600
MIN_CAPTION = 5
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
TOO_BIG = "Foto troppo grande: massimo 5 MB"


class PhotoError(ValueError):
    pass


def process_photo(raw: bytes) -> tuple[bytes, int, int]:
    """(jpeg, larghezza, altezza): ridotta a 1600 px sul lato lungo, girata come la scattata, senza EXIF."""
    if len(raw) > MAX_BYTES:
        raise PhotoError(TOO_BIG)
    try:
        from PIL import Image, ImageOps

        img = Image.open(io.BytesIO(raw))
        if (img.format or "").upper() not in ("JPEG", "PNG", "WEBP", "MPO"):
            raise PhotoError("Formato non ammesso: solo JPG, PNG o WEBP")
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "L"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            rgba = img.convert("RGBA")
            background.paste(rgba, mask=rgba.split()[-1])
            img = background
        elif img.mode == "L":
            img = img.convert("RGB")
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=85, optimize=True)  # niente exif=: i metadati non passano
        return out.getvalue(), img.width, img.height
    except PhotoError:
        raise
    except Exception as exc:  # noqa: BLE001 - file non leggibile come immagine
        raise PhotoError("File non leggibile come immagine") from exc
