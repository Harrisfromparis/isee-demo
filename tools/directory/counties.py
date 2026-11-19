"""County table and name normaliser for the places-directory pipeline.

The 26 counties of the Republic of Ireland are the only output regions.  OpenStreetMap
administrative areas are named in many ways ("County Carlow", "Fingal County Council",
"Dún Laoghaire–Rathdown", "Limerick City and County Council" ...), so every boundary name is
normalised and looked up in ALIASES, which maps council areas to the county they sit in.

The six Northern Ireland counties are recognised only so that points inside them can be
counted and dropped (NI does not use Eircodes); they are never written to the output.
"""

from __future__ import annotations

import re
import unicodedata

# (slug, display name) - alphabetical, exactly the 26 counties of the Republic.
COUNTIES: tuple[tuple[str, str], ...] = (
    ("carlow", "Carlow"), ("cavan", "Cavan"), ("clare", "Clare"), ("cork", "Cork"),
    ("donegal", "Donegal"), ("dublin", "Dublin"), ("galway", "Galway"), ("kerry", "Kerry"),
    ("kildare", "Kildare"), ("kilkenny", "Kilkenny"), ("laois", "Laois"),
    ("leitrim", "Leitrim"), ("limerick", "Limerick"), ("longford", "Longford"),
    ("louth", "Louth"), ("mayo", "Mayo"), ("meath", "Meath"), ("monaghan", "Monaghan"),
    ("offaly", "Offaly"), ("roscommon", "Roscommon"), ("sligo", "Sligo"),
    ("tipperary", "Tipperary"), ("waterford", "Waterford"), ("westmeath", "Westmeath"),
    ("wexford", "Wexford"), ("wicklow", "Wicklow"),
)
COUNTY_SLUGS: tuple[str, ...] = tuple(s for s, _ in COUNTIES)
COUNTY_NAMES: dict[str, str] = dict(COUNTIES)

# Pseudo-region used for Northern Ireland (counted and dropped, never published).
NI = "ni"

# Council areas (and a few spelling variants) that belong to a county.  Keys are already
# normalised (see normalise_name).  The bare county names are added below.
_COUNCIL_AREAS: dict[str, str] = {
    "fingal": "dublin",
    "south dublin": "dublin",
    "dun laoghaire rathdown": "dublin",
    "dun laoghaire and rathdown": "dublin",
    "dublin city": "dublin",
    "cork city": "cork",
    "galway city": "galway",
    "limerick city and county": "limerick",
    "limerick city": "limerick",
    "waterford city and county": "waterford",
    "waterford city": "waterford",
    "north tipperary": "tipperary",
    "south tipperary": "tipperary",
    "tipperary north": "tipperary",
    "tipperary south": "tipperary",
    "laoighis": "laois",
}

_NI_NAMES: tuple[str, ...] = (
    "antrim", "armagh", "down", "fermanagh", "londonderry", "derry", "tyrone",
    "northern ireland",
)

ALIASES: dict[str, str] = {slug: slug for slug in COUNTY_SLUGS}
ALIASES.update(_COUNCIL_AREAS)
ALIASES.update({n: NI for n in _NI_NAMES})

# Longest first so that "city and county council" wins over "county council".
_SUFFIXES: tuple[str, ...] = (
    " city and county council", " county council", " city council", " county",
)
_PREFIXES: tuple[str, ...] = ("county ", "co ")


def normalise_name(raw: str) -> str:
    """Lower-case, fold accents, drop punctuation and strip "county"/"council" wording."""
    text = unicodedata.normalize("NFKD", raw)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[-‐-―/]", " ", text)   # hyphens and dashes become spaces
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9 ]", "", text)             # drop apostrophes, full stops ...
    text = re.sub(r"\s+", " ", text).strip()
    changed = True
    while changed:
        changed = False
        for prefix in _PREFIXES:
            if text.startswith(prefix):
                text, changed = text[len(prefix):], True
        for suffix in _SUFFIXES:
            if text.endswith(suffix):
                text, changed = text[: -len(suffix)], True
    return text.strip()


def region_for_name(raw: str | None) -> str | None:
    """Return a county slug, NI, or None for an OSM name / addr:county value."""
    if not raw:
        return None
    return ALIASES.get(normalise_name(raw))
