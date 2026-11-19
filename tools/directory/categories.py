"""Category rules: which OpenStreetMap tags put a named feature in which directory category.

A feature goes in the FIRST category (in CATEGORIES order) whose rule matches.  Labels are
plain-language type names shown to the public.  Nothing is guessed: unknown tag values fall
back to a generic label or are shown as the tag value itself, made readable.
"""

from __future__ import annotations

from typing import Callable, Mapping

Tags = Mapping[str, str]

CATEGORIES: tuple[tuple[str, str], ...] = (
    ("health", "Health and therapy"),
    ("education", "Schools and education"),
    ("worship", "Places of worship"),
    ("libraries", "Libraries"),
    ("arts", "Theatres, cinemas and arts"),
    ("cafes", "Cafés"),
    ("food", "Restaurants, pubs and takeaways"),
    ("public", "Public services"),
    ("stay", "Hotels and places to stay"),
    ("leisure", "Sport and leisure"),
    ("shops", "Shops"),
    ("offices", "Offices and business services"),
    ("trades", "Trades and industry"),
)
CATEGORY_NAMES: dict[str, str] = dict(CATEGORIES)

# Every OSM key that any rule looks at (used to pre-filter the PBF cheaply).
RELEVANT_KEYS: tuple[str, ...] = (
    "amenity", "healthcare", "tourism", "leisure", "shop", "office", "craft", "man_made",
    "industrial",
)


def humanise(value: str) -> str:
    """'speech_therapist' -> 'Speech therapist'."""
    text = value.replace("_", " ").replace(";", ", ").strip()
    return text[:1].upper() + text[1:]


# ---------------------------------------------------------------- label tables

_HEALTH_AMENITY = {
    "doctors": "GP practice", "clinic": "Clinic", "dentist": "Dentist",
    "pharmacy": "Pharmacy", "hospital": "Hospital",
}
_HEALTH_HEALTHCARE = {
    "doctor": "GP practice", "clinic": "Clinic", "dentist": "Dentist",
    "pharmacy": "Pharmacy", "hospital": "Hospital",
    "physiotherapist": "Physiotherapist", "psychotherapist": "Psychotherapist",
    "psychologist": "Psychologist", "counselling": "Counselling",
    "counseling": "Counselling", "speech_therapist": "Speech and language therapist",
    "occupational_therapist": "Occupational therapist", "optometrist": "Optician",
    "podiatrist": "Podiatrist", "audiologist": "Audiologist",
    "alternative": "Alternative therapy", "midwife": "Midwife",
    "nurse": "Nurse", "dialysis": "Dialysis centre", "rehabilitation": "Rehabilitation",
    "blood_donation": "Blood donation centre", "laboratory": "Laboratory",
    "centre": "Health centre", "center": "Health centre", "yes": "Health service",
}
_EDUCATION = {
    "school": "School", "college": "College", "university": "University",
    "kindergarten": "Kindergarten", "childcare": "Childcare",
    "language_school": "Language school", "music_school": "Music school",
    "driving_school": "Driving school", "training": "Training centre",
}
_ARTS_AMENITY = {"theatre": "Theatre", "cinema": "Cinema", "arts_centre": "Arts centre"}
_ARTS_TOURISM = {"museum": "Museum", "gallery": "Gallery"}
_CAFES = {"cafe": "Café", "ice_cream": "Ice cream shop"}
_FOOD = {
    "restaurant": "Restaurant", "fast_food": "Takeaway or fast food", "pub": "Pub",
    "bar": "Bar", "food_court": "Food court",
}
_PUBLIC = {
    "townhall": "Town hall", "courthouse": "Courthouse", "police": "Garda station",
    "fire_station": "Fire station", "post_office": "Post office",
    "community_centre": "Community centre", "social_facility": "Social facility",
    "bank": "Bank", "public_building": "Public building",
}
_STAY = {
    "hotel": "Hotel", "guest_house": "Guest house", "hostel": "Hostel", "motel": "Motel",
}
_LEISURE = {
    "sports_centre": "Sports centre", "fitness_centre": "Gym or fitness centre",
    "swimming_pool": "Swimming pool", "bowling_alley": "Bowling alley",
    "dance": "Dance studio",
}
_LEISURE_TOURISM = {
    "attraction": "Visitor attraction", "theme_park": "Theme park", "zoo": "Zoo",
}
_SHOP_LABELS = {
    "convenience": "Convenience store", "supermarket": "Supermarket",
    "hairdresser": "Hairdresser", "clothes": "Clothes shop", "chemist": "Chemist",
    "doityourself": "DIY store", "mobile_phone": "Mobile phone shop",
    "beauty": "Beauty salon", "charity": "Charity shop", "second_hand": "Second-hand shop",
    "variety_store": "Variety store", "department_store": "Department store",
    "newsagent": "Newsagent", "bookmaker": "Bookmaker", "alcohol": "Off-licence",
    "car_repair": "Car repair", "car": "Car dealer", "bicycle": "Bicycle shop",
    "butcher": "Butcher", "bakery": "Bakery", "florist": "Florist",
    "greengrocer": "Greengrocer", "hardware": "Hardware shop", "optician": "Optician",
    "jewelry": "Jeweller", "furniture": "Furniture shop", "shoes": "Shoe shop",
    "books": "Bookshop", "gift": "Gift shop", "pet": "Pet shop", "tattoo": "Tattoo studio",
    "laundry": "Laundry", "dry_cleaning": "Dry cleaner", "kiosk": "Kiosk",
    "yes": "Shop",
}
_OFFICE_LABELS = {
    "lawyer": "Solicitor", "solicitor": "Solicitor", "estate_agent": "Estate agent",
    "accountant": "Accountant", "insurance": "Insurance", "company": "Company office",
    "it": "IT company", "ngo": "NGO", "charity": "Charity", "employment_agency":
    "Employment agency", "financial": "Financial services", "travel_agent": "Travel agent",
    "architect": "Architect", "educational_institution": "Educational institution",
    "association": "Association", "political_party": "Political party office",
    "yes": "Office",
}
_INDUSTRIAL_LABELS = {
    "warehouse": "Warehouse", "factory": "Factory", "depot": "Depot",
    "distribution": "Distribution centre", "workshop": "Workshop",
}
_DENOMINATIONS = {
    "roman_catholic": "Catholic", "catholic": "Catholic", "anglican": "Anglican",
    "church_of_ireland": "Church of Ireland", "presbyterian": "Presbyterian",
    "methodist": "Methodist", "baptist": "Baptist", "quaker": "Quaker",
    "orthodox": "Orthodox", "pentecostal": "Pentecostal", "evangelical": "Evangelical",
    "lutheran": "Lutheran", "jehovahs_witness": "Jehovah's Witness",
    "sunni": "Sunni", "shia": "Shia",
}
_RELIGIONS = {
    "christian": "Christian", "muslim": "Muslim", "jewish": "Jewish", "hindu": "Hindu",
    "buddhist": "Buddhist", "sikh": "Sikh", "bahai": "Baha'i", "multifaith": "Multi-faith",
}


def _lookup(tags: Tags, key: str, table: Mapping[str, str]) -> str | None:
    value = tags.get(key)
    return table.get(value) if value else None


# ---------------------------------------------------------------- category rules
# Each returns a label when the tags match the category, otherwise None.

def _health(t: Tags) -> str | None:
    if t.get("amenity") == "veterinary" or t.get("healthcare") == "veterinary":
        return None  # animal care is not a people service
    label = _lookup(t, "amenity", _HEALTH_AMENITY)
    if label:
        return label
    value = t.get("healthcare")
    if value and value != "no":
        return _HEALTH_HEALTHCARE.get(value, "Health service")
    return None


def _education(t: Tags) -> str | None:
    return _lookup(t, "amenity", _EDUCATION)


def _worship(t: Tags) -> str | None:
    if t.get("amenity") != "place_of_worship":
        return None
    denomination = t.get("denomination", "").strip()
    religion = t.get("religion", "").strip()
    detail = None
    if denomination:
        detail = _DENOMINATIONS.get(denomination) or humanise(denomination)
    elif religion:
        detail = _RELIGIONS.get(religion) or humanise(religion)
    return f"Place of worship ({detail})" if detail else "Place of worship"


def _libraries(t: Tags) -> str | None:
    return "Library" if t.get("amenity") == "library" else None


def _arts(t: Tags) -> str | None:
    return _lookup(t, "amenity", _ARTS_AMENITY) or _lookup(t, "tourism", _ARTS_TOURISM)


def _cafes(t: Tags) -> str | None:
    return _lookup(t, "amenity", _CAFES)


def _food(t: Tags) -> str | None:
    return _lookup(t, "amenity", _FOOD)


def _public(t: Tags) -> str | None:
    label = _lookup(t, "amenity", _PUBLIC)
    if label:
        return label
    return "Government office" if t.get("office") == "government" else None


def _stay(t: Tags) -> str | None:
    return _lookup(t, "tourism", _STAY)


def _leisure(t: Tags) -> str | None:
    return _lookup(t, "leisure", _LEISURE) or _lookup(t, "tourism", _LEISURE_TOURISM)


def _shops(t: Tags) -> str | None:
    value = t.get("shop")
    if not value or value in ("vacant", "no"):
        return None
    return _SHOP_LABELS.get(value) or humanise(value)


def _offices(t: Tags) -> str | None:
    value = t.get("office")
    if not value or value == "no":
        return None
    return _OFFICE_LABELS.get(value) or humanise(value)


def _trades(t: Tags) -> str | None:
    craft = t.get("craft")
    if craft and craft != "no":
        return "Craft business" if craft == "yes" else humanise(craft)
    if t.get("man_made") == "works":
        return "Factory or works"
    industrial = t.get("industrial")
    if industrial and industrial != "no":
        return _INDUSTRIAL_LABELS.get(industrial) or (
            "Industrial site" if industrial == "yes" else humanise(industrial))
    return None


_RULES: dict[str, Callable[[Tags], str | None]] = {
    "health": _health, "education": _education, "worship": _worship,
    "libraries": _libraries, "arts": _arts, "cafes": _cafes, "food": _food,
    "public": _public, "stay": _stay, "leisure": _leisure, "shops": _shops,
    "offices": _offices, "trades": _trades,
}


def is_excluded(tags: Tags) -> bool:
    """True for private places and anything tagged as disused / abandoned."""
    if tags.get("access") == "private":
        return True
    if tags.get("disused") == "yes" or tags.get("abandoned") == "yes":
        return True
    return any(k.startswith(("disused:", "abandoned:")) for k in tags)


def classify(tags: Tags) -> tuple[str, str] | None:
    """Return (category slug, type label) for a directory-worthy feature, else None.

    A feature needs a non-empty `name`.  Lifecycle-prefixed main tags (disused:amenity=...)
    never match because the rules only read the plain keys.
    """
    if not tags.get("name", "").strip() or is_excluded(tags):
        return None
    for slug, _ in CATEGORIES:
        label = _RULES[slug](tags)
        if label:
            return slug, label
    return None
