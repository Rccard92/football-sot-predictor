"""V5: le giocate si chiudono solo a partita finita (31/10/2026), mai con il punteggio del momento."""

from types import SimpleNamespace

from app.services.cecchino_v5.pipeline import _finished


def _fx(status, h, a):
    return SimpleNamespace(status=status, ft_home=h, ft_away=a)


def test_live_score_is_not_final():
    assert not _finished(_fx("1H", 0, 0))
    assert not _finished(_fx("HT", 1, 0))
    assert not _finished(_fx("2H", 2, 1))


def test_finished_statuses():
    assert _finished(_fx("FT", 3, 2)) and _finished(_fx("AET", 1, 1)) and _finished(_fx("PEN", 0, 0))
    assert not _finished(_fx("FT", None, None))
    assert not _finished(_fx("ABD", 1, 0))
