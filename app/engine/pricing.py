"""R$/kg normalization — pure functions lifted verbatim from the homelab
tracker (the definitive rule, validated against live Swift/Sam's/Superadega
pricing). Do not change the logic: correctness here is load-bearing."""
from __future__ import annotations

import re


def _weight_kg_from_name(name: str) -> float | None:
    """Largest plausible package weight in kg found in a product name."""
    if not name:
        return None
    best = None
    for m in re.finditer(r"(\d+(?:[.,]\d+)?)\s*(kg|g)\b", name, re.IGNORECASE):
        val = float(m.group(1).replace(",", "."))
        kg = val / 1000 if m.group(2).lower() == "g" else val
        if kg > 0 and (best is None or kg > best):
            best = kg
    return best


def _weights_kg_from_name(name: str) -> list[float]:
    """All weights found in a name, in kg (e.g. '0,8Kg a 1,2Kg' -> [0.8, 1.2])."""
    out = []
    for m in re.finditer(r"(\d+(?:[.,]\d+)?)\s*(kg|g)\b", name or "", re.IGNORECASE):
        v = float(m.group(1).replace(",", "."))
        out.append(v / 1000 if m.group(2).lower() == "g" else v)
    return out


def price_per_kg(price: float, sold_by_weight: bool, name: str) -> float | None:
    """Normalise an offer to R$/kg.

    ``sold_by_weight`` = the store sells this item by weight (VTEX
    measurementUnit kg/g, or ibecom unit_type "KG").
    - Sold by weight AND variable/loose (weight RANGE, "aprox"/"~", or NO weight
      in the name): ``price`` is ALREADY per kg -> return it.
    - Single EXACT weight in the name (fixed package): ``price``/weight.
    - Sold by unit with a weight in the name: package price -> price/weight.
    - Sold by unit, no weight: R$/kg unknown -> None (dropped when require_kg).
    """
    weights = _weights_kg_from_name(name)
    n = (name or "").lower()
    variable = "aprox" in n or "~" in n or "peso var" in n or len(weights) >= 2
    if sold_by_weight:
        if weights and not variable:
            return round(price / weights[0], 2)
        return round(price, 2)
    if weights:
        return round(price / max(weights), 2)
    return None
