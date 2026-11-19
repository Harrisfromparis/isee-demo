"""End-to-end tests for the places-directory pipeline, using only synthetic OSM data."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import build_directory as bd
from categories import CATEGORIES, classify
from counties import COUNTIES, normalise_name, region_for_name
from synthetic import POI_CASES, SKIPPED_CASES, Osm, base_boundaries

EPOCH = "1767225600"  # 2026-01-01T00:00:00Z
CONTACT_TAGS = {
    "phone": "+353 59 000 0000", "contact:phone": "059 111 1111", "email": "secret@example.org",
    "contact:email": "who@example.org", "website": "https://example.org/private-site",
    "contact:website": "https://example.net", "opening_hours": "Mo-Fr 09:00-17:00",
    "operator": "Mary Personal-Name", "contact:facebook": "https://facebook.com/xyz",
    "fax": "059 222 2222", "description": "A private description",
}


def poi_tags(name: str, tags: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in tags.items() if k != "__noname__"} | (
        {} if "__noname__" in tags else {"name": name})


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    """Build the synthetic file once; return (osm_path, expected-name -> (cat, label))."""
    tmp = tmp_path_factory.mktemp("world")
    osm = Osm()
    base_boundaries(osm)
    expected: dict[str, tuple[str, str]] = {}
    for i, (tags, cat, label) in enumerate(POI_CASES):
        name = f"Case {i:02d} {label}"
        lon, lat = -6.95 + (i % 10) * 0.09, 52.1 + (i // 10) * 0.08
        full = {**tags, "name": name, **CONTACT_TAGS}
        if i % 2 == 0:  # alternate nodes and closed ways to exercise both paths
            osm.node(lon, lat, full)
        else:
            osm.poi_square(lon, lat, 0.01, full)
        expected[name] = (cat, label)
    # skipped features, in Carlow
    for j, (name, tags) in enumerate(SKIPPED_CASES):
        osm.node(-6.5 + j * 0.01, 52.95, poi_tags(name, tags))
    # Fingal features
    osm.node(-5.5, 53.5, {"name": "Fingal Pharmacy", "amenity": "pharmacy",
                          "addr:housename": "Rose House", "addr:housenumber": "12",
                          "addr:street": "Main Street", "addr:place": "Swords",
                          "addr:city": "Swords", "addr:postcode": "K67 AC12"})
    osm.node(-5.4, 53.6, {"name": "Zed Cafe", "amenity": "cafe", "addr:town": "Malahide"})
    osm.node(-5.6, 53.7, {"name": "alpha cafe", "amenity": "cafe"})
    osm.node(-5.7, 53.8, {"name": "Beta Cafe", "amenity": "cafe", "addr:street": "B Road"})
    osm.node(-5.71, 53.8, {"name": "Beta Cafe", "amenity": "cafe", "addr:street": "A Road"})
    # Eircode cases (Carlow)
    for k, code in enumerate(["A65 F4E2", "a65f4e2", "D6W 1234", "d6w1234", "A65 F4E", "B12 ABCD",
                              "SW1A 1AA", "Dublin 4", "A65-F4E2", ""]):
        tags = {"name": f"Eir {k}", "amenity": "library"}
        if code:
            tags["addr:postcode"] = code
        osm.node(-6.95 + k * 0.001, 52.55, tags)
    # Northern Ireland and outside-everything points
    osm.node(-5.5, 54.5, {"name": "Antrim Cafe", "amenity": "cafe"})
    osm.node(10.0, 10.0, {"name": "Nowhere Cafe", "amenity": "cafe"})
    osm.node(10.1, 10.0, {"name": "Fallback Carlow Cafe", "amenity": "cafe", "addr:county": "Co. Carlow"})
    osm.node(10.2, 10.0, {"name": "Fallback Antrim Cafe", "amenity": "cafe", "addr:county": "Antrim"})
    osm.node(10.3, 10.0, {"name": "Bad County Cafe", "amenity": "cafe", "addr:county": "Mars"})
    # an exact duplicate (same everything) must be collapsed
    for _ in range(2):
        osm.node(-6.8, 52.7, {"name": "Twin Shop", "shop": "supermarket"})
    path = tmp / "synthetic.osm"
    osm.write(path)
    return path, expected


def run(path: Path, out: Path, epoch: str = EPOCH, monkeypatch=None, *extra: str) -> int:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", epoch)
    return bd.main(["--pbf", str(path), "--out", str(out), *extra])


@pytest.fixture(scope="module")
def built(world, tmp_path_factory):
    path, expected = world
    out = tmp_path_factory.mktemp("out")
    mp = pytest.MonkeyPatch()
    try:
        code = run(path, out, monkeypatch=mp)
    finally:
        mp.undo()
    assert code == 0
    return out, expected


def load(out: Path, county: str, cat: str) -> dict:
    return json.loads((out / county / f"{cat}.json").read_text(encoding="utf-8"))


def all_places(out: Path) -> list[tuple[str, str, dict]]:
    found = []
    for f in sorted(out.glob("*/*.json")):
        for p in json.loads(f.read_text(encoding="utf-8"))["places"]:
            found.append((f.parent.name, f.stem, p))
    return found


# ---------------------------------------------------------------- output contract

def test_index_contract(built):
    out, _ = built
    raw = (out / "index.json").read_text(encoding="utf-8")
    idx = json.loads(raw)
    assert raw == json.dumps(idx, ensure_ascii=False, separators=(",", ":"))  # compact
    assert list(idx) == ["generated", "source", "extract", "counties", "categories", "counts",
                         "eircodeCount", "total"]
    assert idx["generated"] == "2026-01-01T00:00:00Z"
    assert idx["source"] == "© OpenStreetMap contributors, Open Database Licence (ODbL)"
    assert idx["extract"] == "synthetic.osm"
    assert [c["slug"] for c in idx["counties"]] == sorted(c["slug"] for c in idx["counties"])
    assert [(c["slug"], c["name"]) for c in idx["counties"]] == list(COUNTIES)
    assert len(idx["counties"]) == 26
    assert [(c["slug"], c["name"]) for c in idx["categories"]] == list(CATEGORIES)
    assert [c["slug"] for c in idx["categories"]][:3] == ["health", "education", "worship"]
    places = all_places(out)
    assert idx["total"] == len(places)
    assert idx["eircodeCount"] == sum(1 for *_, p in places if p["e"])
    for c in idx["counties"]:
        assert c["total"] == sum(idx["counts"][c["slug"]].values())
    # counts match the files; files exist exactly where counts > 0
    for slug, cats in idx["counts"].items():
        for cat, n in cats.items():
            assert n == len(load(out, slug, cat)["places"]) > 0
    on_disk = {(f.parent.name, f.stem) for f in out.glob("*/*.json")}
    assert on_disk == {(s, c) for s, cats in idx["counts"].items() for c in cats}


def test_place_files_format(built):
    out, _ = built
    for f in out.glob("*/*.json"):
        raw = f.read_text(encoding="utf-8")
        doc = json.loads(raw)
        assert raw == json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
        assert list(doc) == ["county", "category", "places"]
        keys = [(p["n"].casefold(), p["n"], p["a"].casefold()) for p in doc["places"]]
        assert keys == sorted(keys)
        for p in doc["places"]:
            assert list(p) == ["n", "t", "a", "e", "lat", "lon"]
            assert p["lat"] == round(p["lat"], 5) and p["lon"] == round(p["lon"], 5)
            assert re.fullmatch(r"-?\d+(\.\d{1,5})?", repr(p["lat"]))


def test_every_category_rule(built):
    out, expected = built
    seen = {p["n"]: (cat, p["t"]) for county, cat, p in all_places(out) if county == "carlow"}
    for name, want in expected.items():
        assert seen.get(name) == want, name


def test_skipped_features_absent(built):
    out, _ = built
    names = {p["n"] for *_, p in all_places(out)}
    for name, tags in SKIPPED_CASES:
        assert name not in names
    carlow_skip_total = len([1 for _, c, p in all_places(out)
                             if p["n"] in {n for n, _ in SKIPPED_CASES}])
    assert carlow_skip_total == 0
    # nothing in Carlow other than the declared POIs, Eircode libraries and the shop twin
    carlow_names = {p["n"] for c, _, p in all_places(out) if c == "carlow"}
    from_cases = {f"Case {i:02d} {lbl}" for i, (_, _, lbl) in enumerate(POI_CASES)}
    extras = {n for n in carlow_names - from_cases if not n.startswith("Eir ")}
    assert extras == {"Twin Shop", "Fallback Carlow Cafe"}


def test_county_assignment_and_drops(built):
    out, _ = built
    by_name = {p["n"]: c for c, _, p in all_places(out)}
    assert by_name["Fingal Pharmacy"] == "dublin"  # Fingal -> Dublin, via name:en
    assert by_name["Fallback Carlow Cafe"] == "carlow"
    for dropped in ("Antrim Cafe", "Nowhere Cafe", "Fallback Antrim Cafe", "Bad County Cafe"):
        assert dropped not in by_name
    summary = (out / "summary.txt").read_text(encoding="utf-8")
    assert "dropped - Northern Ireland (out of scope): 2" in summary
    assert "dropped - could not be assigned to a county: 2" in summary
    assert "placed by addr:county fallback (no boundary polygon contained them): 2" in summary
    assert "dropped - exact duplicates: 1" in summary
    assert "-> carlow" in summary and "-> dublin" in summary and "-> ni" in summary
    assert "'Narnia Council'" in summary  # unmatched boundary listed


def test_missing_counties_flagged_in_summary(built):
    out, _ = built
    summary = (out / "summary.txt").read_text(encoding="utf-8")
    assert "WARNING: no boundary polygon found for 24 of 26 counties" in summary
    warning_line = summary.split("WARNING")[1].split("\n")[0]
    assert "Wicklow" in warning_line and "Carlow" not in warning_line and "Dublin" not in warning_line


def test_address_eircode_and_sorting(built):
    out, _ = built
    pharm = load(out, "dublin", "health")["places"][0]
    assert pharm == {"n": "Fingal Pharmacy", "t": "Pharmacy",
                     "a": "Rose House, 12 Main Street, Swords", "e": "K67 AC12",
                     "lat": 53.5, "lon": -5.5}
    cafes = load(out, "dublin", "cafes")["places"]
    assert [p["n"] for p in cafes] == ["alpha cafe", "Beta Cafe", "Beta Cafe", "Zed Cafe"]
    assert [p["a"] for p in cafes] == ["", "A Road", "B Road", "Malahide"]  # then by address
    assert all(p["e"] == "" for p in cafes)  # no postcode tag -> no Eircode, never derived
    eir = {p["n"]: p["e"] for p in load(out, "carlow", "libraries")["places"] if p["n"].startswith("Eir")}
    assert eir == {"Eir 0": "A65 F4E2", "Eir 1": "A65 F4E2", "Eir 2": "D6W 1234", "Eir 3": "D6W 1234",
                   "Eir 4": "", "Eir 5": "", "Eir 6": "", "Eir 7": "", "Eir 8": "", "Eir 9": ""}


def test_closed_way_point_inside_square(built):
    out, expected = built
    place = next(p for _, _, p in all_places(out) if p["n"].startswith("Case 01"))
    # closed way at lon -6.86, lat 52.1 with size 0.01 -> centroid at +0.005
    assert (place["lat"], place["lon"]) == (52.105, -6.855)


def test_no_contact_details_anywhere(built):
    out, _ = built
    blob = "".join(f.read_text(encoding="utf-8") for f in out.rglob("*") if f.is_file())
    for key, value in CONTACT_TAGS.items():
        assert value not in blob, key
    for fragment in ("@", "http", "+353", "Mon", "Mo-Fr"):
        assert fragment not in "".join(
            f.read_text(encoding="utf-8") for f in out.glob("*/*.json")), fragment


# ---------------------------------------------------------------- determinism and failure modes

def test_deterministic(world, tmp_path, monkeypatch):
    path, _ = world
    a, b, c = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    assert run(path, a, monkeypatch=monkeypatch) == 0
    assert run(path, b, monkeypatch=monkeypatch) == 0
    files = sorted(p.relative_to(a) for p in a.rglob("*") if p.is_file())
    assert files == sorted(p.relative_to(b) for p in b.rglob("*") if p.is_file())
    for f in files:
        assert (a / f).read_bytes() == (b / f).read_bytes(), f
    # a different clock changes only the `generated` stamp
    assert run(path, c, "1800000000", monkeypatch) == 0
    for f in files:
        ta, tc = (a / f).read_text(encoding="utf-8"), (c / f).read_text(encoding="utf-8")
        if f.name in ("index.json", "summary.txt"):
            assert ta.replace("2026-01-01T00:00:00Z", "X") == re.sub(r"2027-\d\d-\d\dT[\d:]+Z", "X", tc)
        else:
            assert ta == tc, f


def test_stale_files_removed(world, tmp_path, monkeypatch):
    path, _ = world
    (tmp_path / "wexford").mkdir()
    stale = tmp_path / "wexford" / "food.json"
    stale.write_text("{}")
    assert run(path, tmp_path, monkeypatch=monkeypatch) == 0
    assert not stale.exists()


def test_zero_counties_exits_1_and_writes_nothing(tmp_path, monkeypatch, capsys):
    osm = Osm()
    osm.boundary((0, 0, 1, 1), {"boundary": "administrative", "admin_level": "6", "name": "Narnia"})
    osm.node(0.5, 0.5, {"name": "Cafe", "amenity": "cafe"})
    src, out = tmp_path / "x.osm", tmp_path / "out"
    osm.write(src)
    assert run(src, out, monkeypatch=monkeypatch) == 1
    assert not out.exists()
    assert "::error::" in capsys.readouterr().out


def test_missing_counties_warns_but_exits_0(world, tmp_path, monkeypatch, capsys):
    path, _ = world
    assert run(path, tmp_path, monkeypatch=monkeypatch) == 0
    out = capsys.readouterr().out
    assert "::warning::No boundary polygon for 24 counties" in out


def test_historic_boundary_fallback(tmp_path, monkeypatch):
    osm = Osm()
    osm.boundary((-7, 52, -6, 53), {"boundary": "historic", "name": "County Carlow"})
    osm.boundary((-5, 52, -4, 53), {"boundary": "historic", "border_type": "barony", "name": "Wicklow"})
    osm.node(-6.5, 52.5, {"name": "Hist Cafe", "amenity": "cafe"})
    osm.node(-4.5, 52.5, {"name": "Barony Cafe", "amenity": "cafe"})
    src, out = tmp_path / "h.osm", tmp_path / "out"
    osm.write(src)
    assert run(src, out, monkeypatch=monkeypatch) == 0
    assert [p["n"] for _, _, p in all_places(out)] == ["Hist Cafe"]


# ---------------------------------------------------------------- unit tests

@pytest.mark.parametrize("raw,expected", [
    ("County Carlow", "carlow"), ("Carlow County Council", "carlow"),
    ("Fingal County Council", "dublin"), ("South Dublin County Council", "dublin"),
    ("Dún Laoghaire–Rathdown County Council", "dublin"), ("Dún Laoghaire-Rathdown", "dublin"),
    ("Dublin City Council", "dublin"), ("Cork City Council", "cork"), ("Cork City", "cork"),
    ("Galway City Council", "galway"), ("Limerick City and County Council", "limerick"),
    ("Waterford City and County Council", "waterford"), ("North Tipperary", "tipperary"),
    ("South Tipperary County Council", "tipperary"), ("Co. Mayo", "mayo"),
    ("County Antrim", "ni"), ("Northern Ireland", "ni"), ("Narnia", None), ("", None),
])
def test_region_for_name(raw, expected):
    assert region_for_name(raw) == expected


def test_normalise_name():
    assert normalise_name("  Dún  Laoghaire–Rathdown ") == "dun laoghaire rathdown"
    assert normalise_name("COUNTY KILKENNY") == "kilkenny"


def test_classify_requires_name_and_ignores_lifecycle():
    assert classify({"amenity": "cafe"}) is None
    assert classify({"amenity": "cafe", "name": "  "}) is None
    assert classify({"disused:amenity": "cafe", "name": "x"}) is None
    assert classify({"amenity": "cafe", "name": "x"}) == ("cafes", "Café")


def test_address_helper():
    assert bd.make_address({}) == ""
    assert bd.make_address({"addr:housenumber": "5"}) == ""  # a bare number is not an address
    assert bd.make_address({"addr:street": "Quay", "addr:housenumber": "5", "addr:city": "Cork",
                            "addr:county": "Cork"}) == "5 Quay, Cork"
    assert bd.make_address({"addr:place": "Ballybay", "addr:village": "Ballybay"}) == "Ballybay"
