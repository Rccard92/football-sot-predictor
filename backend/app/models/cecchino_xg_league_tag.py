"""Tag permanente per campionato: API-Football fornisce gli xG delle partite oppure no.

Decisione dell'utente (13/10/2026): un campionato che ha gia' risposto senza xG non li avra' la
settimana dopo, quindi non si richiedono piu' le sue statistiche per il profilo xG di Cecchino Today.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin

XG_TAG_PENDING = "pending"  # risposte ancora troppo poche per decidere
XG_TAG_HAS_XG = "has_xg"  # almeno una partita con xG: si continuano a scaricare le partite nuove
XG_TAG_NO_XG = "no_xg"  # abbastanza partite e nessun xG: niente piu' richieste


class CecchinoXgLeagueTag(Base, TimestampMixin):
    __tablename__ = "cecchino_xg_league_tags"

    provider_league_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=XG_TAG_PENDING)
    league_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # partite di cui API-Football ha gia' risposto (con o senza statistiche) e quante avevano gli xG
    fixtures_answered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fixtures_with_xg: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
