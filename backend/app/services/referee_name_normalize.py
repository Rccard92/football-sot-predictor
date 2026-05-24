"""Normalizzazione nomi arbitro per match cross-fixture."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

MatchConfidence = Literal["exact", "likely", "none"]

MATCH_WARNING_LIKELY = "Possibile match arbitro, verificare manualmente."


@dataclass(frozen=True)
class RefereeNameMatch:
    matches: bool
    confidence: MatchConfidence

    @property
    def match_warning(self) -> str | None:
        if self.confidence == "likely":
            return MATCH_WARNING_LIKELY
        return None


def normalize_referee_name(name: str | None) -> str:
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name.strip().lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def _tokens(name: str) -> list[str]:
    return normalize_referee_name(name).split()


def _initial_token(tok: str) -> str:
    t = tok.strip()
    if not t:
        return ""
    if len(t) == 1:
        return t
    if len(t) <= 3 and t.endswith("."):
        return t[0]
    return t[0]


def _likely_same_person(a_tokens: list[str], b_tokens: list[str]) -> bool:
    if not a_tokens or not b_tokens:
        return False
    if a_tokens == b_tokens:
        return True

    def variants(tokens: list[str]) -> list[list[str]]:
        if len(tokens) == 2:
            return [tokens, [tokens[1], tokens[0]]]
        return [tokens]

    for av in variants(a_tokens):
        for bv in variants(b_tokens):
            if av == bv:
                return True
            if len(av) >= 2 and len(bv) >= 2:
                a_last, b_last = av[-1], bv[-1]
                if a_last != b_last:
                    continue
                a_first, b_first = av[0], bv[0]
                if _initial_token(a_first) == _initial_token(b_first):
                    return True
                if len(av) > 2 and len(bv) > 2:
                    a_mid = " ".join(av[1:-1])
                    b_mid = " ".join(bv[1:-1])
                    if a_mid == b_mid and _initial_token(a_first) == _initial_token(b_first):
                        return True
    return False


def compare_referee_names(a: str | None, b: str | None) -> RefereeNameMatch:
    na = normalize_referee_name(a)
    nb = normalize_referee_name(b)
    if not na or not nb:
        return RefereeNameMatch(matches=False, confidence="none")
    if na == nb:
        return RefereeNameMatch(matches=True, confidence="exact")
    if _likely_same_person(_tokens(na), _tokens(nb)):
        return RefereeNameMatch(matches=True, confidence="likely")
    return RefereeNameMatch(matches=False, confidence="none")


def referee_names_match(a: str | None, b: str | None) -> bool:
    return compare_referee_names(a, b).matches
