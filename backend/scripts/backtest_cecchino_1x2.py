"""Back test della correzione del Cecchino 1-X-2 (documento "Modifiche" di Giovanni, punto 4, 09/11/2026).

Solo lettura, nessuna modifica al tool. Dati: tutte le partite di Cecchino Today dal 19/06/2026 con risultato
finale, quota Bet365 1-X-2 e i quattro picchetti salvati (esportate dal database in righe "a|b|c").

Versioni confrontate (solo sulla SECONDA meta' delle partite, in ordine di data):
  V0  Cecchino di oggi: quota finale = media pesata delle QUOTE dei picchetti (le probabilita' sommano ~95%)
  V0n la stessa riportata al 100% (solo per capire quanto pesa la sola somma)
  P1  punto 1: quota = 1 / (0,3/q_tot + 0,3/q_casafuori + 0,2/q_ult6 + 0,2/q_ult5) = media pesata delle probabilita'
  P2  punti 1 e 2: P1 con il fattore campo (p1 x k1, pX x kX, p2 invariata, poi somma al 100%);
      k1 e kX stimati SOLO sulla prima meta' (minimo LogLoss), e per confronto i valori proposti 1,08 / 0,98
  B365 Bet365 senza margine (1/quota riportata al 100%)

Misure: favorito azzeccato, Brier (somma sui 3 esiti), LogLoss, probabilita' media contro frequenza, resa delle
giocate con quota Bet365 >= quota Cecchino x 1,15. In piu' il primo tempo 1-X-2, che somma all'88%.

Uso: python -I scripts/backtest_cecchino_1x2.py <cartella con i file esportati> [--json out.json]
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
from dataclasses import dataclass

WEIGHTS = (0.3, 0.3, 0.2, 0.2)  # totali, casa/fuori, ultime 6 totali, ultime 5 casa/fuori (uguali su tutte le gare)
EPS = 1e-3  # probabilita' minima nel LogLoss (un picchetto a zero non deve dare infinito)
VALUE_MULT = 1.15


@dataclass
class Row:
    fid: int
    ko: str
    res: int  # 0 = 1, 1 = X, 2 = 2
    res_ht: int | None
    q0: tuple[float, float, float]
    pic: tuple[tuple[float, float, float], ...]
    book: tuple[float, float, float] | None
    book_ht: tuple[float, float, float] | None
    cec_ht: tuple[float, float, float] | None


def _outcome(h: int, a: int) -> int:
    return 0 if h > a else 1 if h == a else 2


def parse_line(line: str) -> Row | None:
    f = line.split("|")
    if len(f) < 22:
        return None
    try:
        fid, ko = int(f[0]), f[1]
        gh, ga = int(f[2]), int(f[3])
        ht = (int(f[4]), int(f[5])) if f[4] not in ("", None) and f[5] not in ("", None) else None
        q0 = tuple(float(x) for x in f[6:9])
        probs = [float(x) for x in f[9:21]]
    except ValueError:
        return None
    pic = tuple(tuple(probs[i * 3 : i * 3 + 3]) for i in range(4))
    kpi: dict[str, tuple[float | None, float | None]] = {}
    for part in (f[21] if len(f) > 21 else "").split(","):
        if not part:
            continue
        code, rest = part[0], part[1:]
        b, _, c = rest.partition("/")
        kpi[code] = (float(b) if b else None, float(c) if c else None)

    def trio(codes: str, idx: int) -> tuple[float, float, float] | None:
        vals = [kpi.get(c, (None, None))[idx] for c in codes]
        return tuple(vals) if all(v and v > 1.0 for v in vals) else None  # type: ignore[return-value]

    return Row(
        fid=fid,
        ko=ko,
        res=_outcome(gh, ga),
        res_ht=_outcome(*ht) if ht else None,
        q0=q0,  # type: ignore[arg-type]
        pic=pic,  # type: ignore[arg-type]
        book=trio("HDA", 0),
        book_ht=trio("hda", 0),
        cec_ht=trio("hda", 1),
    )


def load(folder: str) -> list[Row]:
    rows: dict[int, Row] = {}
    for path in sorted(glob.glob(os.path.join(folder, "*.txt"))):
        raw = json.load(open(path, encoding="utf8"))["result"]
        if "risposta tagliata" in raw:
            raise SystemExit(f"{path}: esportazione tagliata, rifare con meno righe")
        body = json.loads(raw)
        csv = body["rows"][0][0] or ""
        for line in csv.split("\n"):
            r = parse_line(line.strip())
            if r and all(x > 1.0 for x in r.q0):
                rows[r.fid] = r  # una riga per partita (riscansioni: l'ultima letta)
    return sorted(rows.values(), key=lambda r: (r.ko, r.fid))


def norm(p: tuple[float, ...]) -> tuple[float, ...]:
    s = sum(p)
    return tuple(x / s for x in p)


def v0(r: Row) -> tuple[float, float, float]:
    return tuple(1.0 / q for q in r.q0)  # type: ignore[return-value]


def p1(r: Row) -> tuple[float, float, float]:
    return tuple(sum(w * pk[i] for w, pk in zip(WEIGHTS, r.pic)) for i in range(3))  # type: ignore[return-value]


def p2(r: Row, k1: float, kx: float) -> tuple[float, float, float]:
    a, x, b = p1(r)
    return norm((a * k1, x * kx, b))  # type: ignore[return-value]


def b365(r: Row) -> tuple[float, float, float] | None:
    return norm(tuple(1.0 / q for q in r.book)) if r.book else None  # type: ignore[return-value]


def logloss(p: tuple[float, ...], res: int) -> float:
    return -math.log(max(p[res], EPS))


def brier(p: tuple[float, ...], res: int) -> float:
    return sum((p[i] - (1.0 if i == res else 0.0)) ** 2 for i in range(3))


def measure(rows: list[Row], probs, quotes=None, book=lambda r: r.book, res=lambda r: r.res) -> dict:
    n = fav = 0
    bs = ll = 0.0
    mean_p = [0.0, 0.0, 0.0]
    freq = [0, 0, 0]
    bets = won = 0
    profit = 0.0
    sums = 0.0
    by_sign = {i: [0, 0.0] for i in range(3)}
    for r in rows:
        p = probs(r)
        y = res(r)
        if p is None or y is None:
            continue
        n += 1
        sums += sum(p)
        fav += 1 if max(range(3), key=lambda i: p[i]) == y else 0
        bs += brier(p, y)
        ll += logloss(p, y)
        for i in range(3):
            mean_p[i] += p[i]
        freq[y] += 1
        b = book(r)
        if b is None:
            continue
        q_c = quotes(r) if quotes else tuple(1.0 / max(x, EPS) for x in p)
        for i in range(3):
            if b[i] >= q_c[i] * VALUE_MULT:
                bets += 1
                gain = (b[i] - 1.0) if y == i else -1.0
                profit += gain
                won += 1 if y == i else 0
                by_sign[i][0] += 1
                by_sign[i][1] += gain
    if not n:
        return {"n": 0}
    return {
        "n": n,
        "somma_prob_pct": round(100 * sums / n, 1),
        "favorito_pct": round(100 * fav / n, 1),
        "brier": round(bs / n, 4),
        "logloss": round(ll / n, 4),
        "prob_media_pct": [round(100 * m / n, 1) for m in mean_p],
        "frequenza_pct": [round(100 * f / n, 1) for f in freq],
        "giocate_valore": bets,
        "vinte_valore_pct": round(100 * won / bets, 1) if bets else None,
        "resa_valore_pct": round(100 * profit / bets, 1) if bets else None,
        "resa_per_segno": {k: {"giocate": v[0], "resa_pct": round(100 * v[1] / v[0], 1) if v[0] else None} for k, v in zip("1X2", by_sign.values())},
    }


def fit_home_factor(rows: list[Row]) -> tuple[float, float, float]:
    """k1 e kX che minimizzano il LogLoss sulla prima meta' (griglia di passo 0,01)."""
    best = (1.0, 1.0, float("inf"))
    for i in range(80, 131):
        k1 = i / 100
        for j in range(85, 116):
            kx = j / 100
            ll = sum(logloss(p2(r, k1, kx), r.res) for r in rows) / len(rows)
            if ll < best[2]:
                best = (k1, kx, ll)
    return best


def sanity(rows: list[Row]) -> dict:
    """Controllo: la quota salvata di oggi e' davvero la media pesata delle quote 1/p dei picchetti?"""
    ok = tot = 0
    for r in rows:
        if any(pk[i] <= 0 for pk in r.pic for i in range(3)):
            continue
        tot += 1
        rebuilt = [sum(w / pk[i] for w, pk in zip(WEIGHTS, r.pic)) for i in range(3)]
        ok += 1 if all(abs(a - b) / b < 0.02 for a, b in zip(rebuilt, r.q0)) else 0
    zeros = sum(1 for r in rows if any(pk[i] <= 0 for pk in r.pic for i in range(3)))
    return {"partite_controllate": tot, "quota_di_oggi_ricostruita_pct": round(100 * ok / tot, 1) if tot else None, "partite_con_un_picchetto_a_zero": zeros}


def paired(rows: list[Row], f, g) -> dict:
    """Differenza partita per partita (g - f) di Brier e LogLoss, con intervallo al 95%: negativa = g migliore."""
    out = {}
    for name, fn in (("brier", brier), ("logloss", logloss)):
        d = [fn(g(r), r.res) - fn(f(r), r.res) for r in rows]
        n = len(d)
        m = sum(d) / n
        sd = math.sqrt(sum((x - m) ** 2 for x in d) / (n - 1))
        half = 1.96 * sd / math.sqrt(n)
        out[name] = {"diff": round(m, 4), "ic95": [round(m - half, 4), round(m + half, 4)]}
    return out


def value_share(rows: list[Row], quotes) -> dict:
    """Quante quote 1-X-2 del book superano la quota Cecchino (valore positivo nel pannello) e quante x 1,15."""
    pos = big = tot = 0
    for r in rows:
        q = quotes(r)
        for i in range(3):
            tot += 1
            pos += 1 if r.book[i] > q[i] else 0
            big += 1 if r.book[i] >= q[i] * VALUE_MULT else 0
    return {"quote": tot, "book_sopra_cecchino_pct": round(100 * pos / tot, 1), "book_sopra_x1_15_pct": round(100 * big / tot, 1)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--json")
    args = ap.parse_args()
    rows = load(args.folder)
    rows = [r for r in rows if r.book]
    half = len(rows) // 2
    first, second = rows[:half], rows[half:]
    k1, kx, ll_fit = fit_home_factor(first)
    out = {
        "dati": {
            "partite": len(rows),
            "dal": rows[0].ko,
            "al": rows[-1].ko,
            "prima_meta": {"partite": len(first), "dal": first[0].ko, "al": first[-1].ko},
            "seconda_meta": {"partite": len(second), "dal": second[0].ko, "al": second[-1].ko},
        },
        "controllo": sanity(rows),
        "fattore_campo_stimato_prima_meta": {"k1": k1, "kX": kx, "logloss_prima_meta": round(ll_fit, 4)},
        "seconda_meta": {
            "V0 Cecchino di oggi": measure(second, v0, quotes=lambda r: r.q0),
            "V0 riportato al 100%": measure(second, lambda r: norm(v0(r))),
            "P1 somma al 100%": measure(second, p1),
            f"P2 fattore campo stimato ({k1:.2f}/{kx:.2f})": measure(second, lambda r: p2(r, k1, kx)),
            "P2 fattore campo proposto (1,08/0,98)": measure(second, lambda r: p2(r, 1.08, 0.98)),
            "Bet365 senza margine": measure(second, b365, quotes=lambda r: r.book),
        },
        "primo_tempo_seconda_meta": {
            "Cecchino PT di oggi": measure(
                second,
                lambda r: tuple(1.0 / q for q in r.cec_ht) if r.cec_ht else None,
                quotes=lambda r: r.cec_ht,
                book=lambda r: r.book_ht,
                res=lambda r: r.res_ht,
            ),
            "Cecchino PT riportato al 100%": measure(
                second,
                lambda r: norm(tuple(1.0 / q for q in r.cec_ht)) if r.cec_ht else None,
                book=lambda r: r.book_ht,
                res=lambda r: r.res_ht,
            ),
            "Bet365 PT senza margine": measure(
                second,
                lambda r: norm(tuple(1.0 / q for q in r.book_ht)) if r.book_ht else None,
                quotes=lambda r: r.book_ht,
                book=lambda r: r.book_ht,
                res=lambda r: r.res_ht,
            ),
        },
        "differenze_seconda_meta": {
            "P1 meno V0": paired(second, v0, p1),
            "P1 meno V0 al 100%": paired(second, lambda r: norm(v0(r)), p1),
            "P2 stimato meno P1": paired(second, p1, lambda r: p2(r, k1, kx)),
            "P2 1,08/0,98 meno P1": paired(second, p1, lambda r: p2(r, 1.08, 0.98)),
        },
        "fattore_campo_stimato_seconda_meta_solo_controllo": dict(zip(("k1", "kX", "logloss"), fit_home_factor(second))),
        "quote_con_valore_tutte_le_partite": {
            "V0": value_share(rows, lambda r: r.q0),
            "P1": value_share(rows, lambda r: tuple(1 / x for x in p1(r))),
            "P2 stimato": value_share(rows, lambda r: tuple(1 / x for x in p2(r, k1, kx))),
        },
        "tutte_le_partite": {
            "V0 Cecchino di oggi": measure(rows, v0, quotes=lambda r: r.q0),
            "P1 somma al 100%": measure(rows, p1),
            "Bet365 senza margine": measure(rows, b365, quotes=lambda r: r.book),
        },
    }
    text = json.dumps(out, ensure_ascii=False, indent=1)
    if args.json:
        open(args.json, "w", encoding="utf8").write(text)
    sys.stdout.write(text + "\n")


if __name__ == "__main__":
    main()
