"""Build a small synthetic .osm XML file for the pipeline tests.

Geography (all invented squares):
  Carlow  boundary: lon -7..-6, lat 52..53   (relation of two ways, name only in official_name)
  Fingal  boundary: lon -6..-5, lat 53..54   (name "Fine Gall", name:en "Fingal County Council")
  County Antrim (NI): lon -6..-5, lat 54..55
  "Narnia Council" admin_level 6: lon 0..1, lat 0..1 (unrecognised name)
"""

from __future__ import annotations

from xml.sax.saxutils import quoteattr


class Osm:
    def __init__(self) -> None:
        self.nodes: list[str] = []
        self.ways: list[str] = []
        self.rels: list[str] = []
        self._nid = 100000
        self._wid = 100000
        self._rid = 100000

    @staticmethod
    def _tags(tags: dict[str, str]) -> str:
        return "".join(f"<tag k={quoteattr(k)} v={quoteattr(v)}/>" for k, v in tags.items())

    def node(self, lon: float, lat: float, tags: dict[str, str] | None = None) -> int:
        self._nid += 1
        self.nodes.append(f'<node id="{self._nid}" version="1" lat="{lat}" lon="{lon}">'
                          f'{self._tags(tags or {})}</node>')
        return self._nid

    def way(self, refs: list[int], tags: dict[str, str] | None = None) -> int:
        self._wid += 1
        nds = "".join(f'<nd ref="{r}"/>' for r in refs)
        self.ways.append(f'<way id="{self._wid}" version="1">{nds}{self._tags(tags or {})}</way>')
        return self._wid

    def square(self, lon0: float, lat0: float, lon1: float, lat1: float) -> list[int]:
        a, b = self.node(lon0, lat0), self.node(lon1, lat0)
        c, d = self.node(lon1, lat1), self.node(lon0, lat1)
        return [a, b, c, d]

    def relation(self, way_ids: list[int], tags: dict[str, str]) -> int:
        self._rid += 1
        members = "".join(f'<member type="way" ref="{w}" role="outer"/>' for w in way_ids)
        self.rels.append(f'<relation id="{self._rid}" version="1">{members}{self._tags(tags)}</relation>')
        return self._rid

    def boundary(self, box: tuple[float, float, float, float], tags: dict[str, str]) -> int:
        """Boundary relation made of two open ways that together close the square."""
        a, b, c, d = self.square(*box)
        w1 = self.way([a, b, c])
        w2 = self.way([c, d, a])
        return self.relation([w1, w2], {"type": "boundary", **tags})

    def poi_square(self, lon: float, lat: float, size: float, tags: dict[str, str]) -> int:
        a, b, c, d = self.square(lon, lat, lon + size, lat + size)
        return self.way([a, b, c, d, a], tags)

    def write(self, path) -> None:
        body = "\n".join(self.nodes + self.ways + self.rels)
        path.write_text(f"<?xml version='1.0' encoding='UTF-8'?>\n"
                        f'<osm version="0.6" generator="synthetic">\n{body}\n</osm>\n',
                        encoding="utf-8")


def base_boundaries(osm: Osm, *, carlow: bool = True, fingal: bool = True, ni: bool = True) -> None:
    if carlow:
        osm.boundary((-7, 52, -6, 53), {"boundary": "administrative", "admin_level": "6",
                                        "name": "Ceatharlach", "official_name": "Carlow County Council"})
    if fingal:
        osm.boundary((-6, 53, -5, 54), {"boundary": "administrative", "admin_level": "7",
                                        "name": "Fine Gall", "name:en": "Fingal County Council"})
    if ni:
        osm.boundary((-6, 54, -5, 55), {"boundary": "administrative", "admin_level": "6",
                                        "name": "County Antrim"})
    osm.boundary((0, 0, 1, 1), {"boundary": "administrative", "admin_level": "6",
                                "name": "Narnia Council"})


# (tags, expected category slug, expected type label); placed inside Carlow, one per rule.
POI_CASES: list[tuple[dict[str, str], str, str]] = [
    ({"amenity": "doctors"}, "health", "GP practice"),
    ({"amenity": "clinic"}, "health", "Clinic"),
    ({"amenity": "dentist"}, "health", "Dentist"),
    ({"amenity": "pharmacy"}, "health", "Pharmacy"),
    ({"amenity": "hospital"}, "health", "Hospital"),
    ({"healthcare": "physiotherapist"}, "health", "Physiotherapist"),
    ({"healthcare": "speech_therapist"}, "health", "Speech and language therapist"),
    ({"healthcare": "occupational_therapist"}, "health", "Occupational therapist"),
    ({"healthcare": "optometrist"}, "health", "Optician"),
    ({"healthcare": "something_new"}, "health", "Health service"),
    ({"amenity": "school"}, "education", "School"),
    ({"amenity": "college"}, "education", "College"),
    ({"amenity": "university"}, "education", "University"),
    ({"amenity": "kindergarten"}, "education", "Kindergarten"),
    ({"amenity": "childcare"}, "education", "Childcare"),
    ({"amenity": "language_school"}, "education", "Language school"),
    ({"amenity": "music_school"}, "education", "Music school"),
    ({"amenity": "driving_school"}, "education", "Driving school"),
    ({"amenity": "training"}, "education", "Training centre"),
    ({"amenity": "place_of_worship", "religion": "christian", "denomination": "roman_catholic"},
     "worship", "Place of worship (Catholic)"),
    ({"amenity": "place_of_worship", "religion": "muslim"}, "worship", "Place of worship (Muslim)"),
    ({"amenity": "place_of_worship"}, "worship", "Place of worship"),
    ({"amenity": "library"}, "libraries", "Library"),
    ({"amenity": "theatre"}, "arts", "Theatre"),
    ({"amenity": "cinema"}, "arts", "Cinema"),
    ({"amenity": "arts_centre"}, "arts", "Arts centre"),
    ({"tourism": "museum"}, "arts", "Museum"),
    ({"tourism": "gallery"}, "arts", "Gallery"),
    ({"amenity": "cafe"}, "cafes", "Café"),
    ({"amenity": "ice_cream"}, "cafes", "Ice cream shop"),
    ({"amenity": "restaurant"}, "food", "Restaurant"),
    ({"amenity": "fast_food"}, "food", "Takeaway or fast food"),
    ({"amenity": "pub"}, "food", "Pub"),
    ({"amenity": "bar"}, "food", "Bar"),
    ({"amenity": "food_court"}, "food", "Food court"),
    ({"amenity": "townhall"}, "public", "Town hall"),
    ({"amenity": "courthouse"}, "public", "Courthouse"),
    ({"amenity": "police"}, "public", "Garda station"),
    ({"amenity": "fire_station"}, "public", "Fire station"),
    ({"amenity": "post_office"}, "public", "Post office"),
    ({"amenity": "community_centre"}, "public", "Community centre"),
    ({"amenity": "social_facility"}, "public", "Social facility"),
    ({"amenity": "bank"}, "public", "Bank"),
    ({"amenity": "public_building"}, "public", "Public building"),
    ({"office": "government"}, "public", "Government office"),
    ({"tourism": "hotel"}, "stay", "Hotel"),
    ({"tourism": "guest_house"}, "stay", "Guest house"),
    ({"tourism": "hostel"}, "stay", "Hostel"),
    ({"tourism": "motel"}, "stay", "Motel"),
    ({"leisure": "sports_centre"}, "leisure", "Sports centre"),
    ({"leisure": "fitness_centre"}, "leisure", "Gym or fitness centre"),
    ({"leisure": "swimming_pool"}, "leisure", "Swimming pool"),
    ({"leisure": "bowling_alley"}, "leisure", "Bowling alley"),
    ({"leisure": "dance"}, "leisure", "Dance studio"),
    ({"tourism": "attraction"}, "leisure", "Visitor attraction"),
    ({"tourism": "theme_park"}, "leisure", "Theme park"),
    ({"tourism": "zoo"}, "leisure", "Zoo"),
    ({"shop": "supermarket"}, "shops", "Supermarket"),
    ({"shop": "hairdresser"}, "shops", "Hairdresser"),
    ({"shop": "yes"}, "shops", "Shop"),
    ({"shop": "bicycle_repair_odd"}, "shops", "Bicycle repair odd"),
    ({"office": "lawyer"}, "offices", "Solicitor"),
    ({"office": "estate_agent"}, "offices", "Estate agent"),
    ({"office": "accountant"}, "offices", "Accountant"),
    ({"office": "insurance"}, "offices", "Insurance"),
    ({"office": "yes"}, "offices", "Office"),
    ({"craft": "carpenter"}, "trades", "Carpenter"),
    ({"craft": "yes"}, "trades", "Craft business"),
    ({"man_made": "works"}, "trades", "Factory or works"),
    ({"industrial": "warehouse"}, "trades", "Warehouse"),
    # first-match-wins checks
    ({"amenity": "cafe", "shop": "bakery"}, "cafes", "Café"),
    ({"tourism": "museum", "leisure": "sports_centre"}, "arts", "Museum"),
    ({"amenity": "pharmacy", "shop": "chemist"}, "health", "Pharmacy"),
    ({"shop": "bakery", "office": "yes"}, "shops", "Bakery"),
]

# Features that must NOT appear anywhere in the output.
SKIPPED_CASES: list[tuple[str, dict[str, str]]] = [
    ("Unnamed Cafe", {"amenity": "cafe", "__noname__": "1"}),
    ("Disused Prefixed Cafe", {"amenity": "cafe", "disused:shop": "yes"}),
    ("Abandoned Pub", {"amenity": "pub", "abandoned:amenity": "pub"}),
    ("Disused Yes Shop", {"shop": "bakery", "disused": "yes"}),
    ("Lifecycle Only Cafe", {"disused:amenity": "cafe"}),
    ("Private Pool", {"leisure": "swimming_pool", "access": "private"}),
    ("Vacant Shop", {"shop": "vacant"}),
    ("Vet Practice", {"amenity": "veterinary"}),
    ("A Plain Bench", {"amenity": "bench"}),
]
