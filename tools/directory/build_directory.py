#!/usr/bin/env python3
"""Build the iSEE places directory (per county, per category) from an OpenStreetMap extract.

Usage:  build_directory.py --pbf ireland-and-northern-ireland-latest.osm.pbf --out seat-finder/data

Source data: (c) OpenStreetMap contributors, Open Database Licence (ODbL).

How it works
  1. One pyosmium FileProcessor run over the extract (osmium reads it twice internally to
     assemble areas).  Node locations are held in an in-memory "flex_mem" index.
  2. Named nodes and areas (closed ways / multipolygons) that match a category rule become
     candidate places; areas are reduced to one point inside the shape.
  3. Administrative / historic / ceremonial county boundaries become polygons per county.
  4. Every place is put in a county by point-in-polygon (shapely STRtree + prepared
     geometry), falling back on `addr:county`.  Northern Ireland and unplaceable features
     are counted and dropped.
  5. JSON files and a human-readable summary.txt are written deterministically.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import numpy as np
import osmium
import shapely
from osmium.filter import KeyFilter
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree

from categories import CATEGORIES, CATEGORY_NAMES, RELEVANT_KEYS, classify
from counties import COUNTIES, COUNTY_NAMES, COUNTY_SLUGS, NI, region_for_name

SOURCE_TEXT = "© OpenStreetMap contributors, Open Database Licence (ODbL)"
EIRCODE_RE = re.compile(r"^(?:[AC-FHKNPRTV-Y][0-9]{2}|D6W)\s?[0-9AC-FHKNPRTV-Y]{4}$", re.IGNORECASE)
COORD_DP = 5
MAX_LISTED_UNMATCHED = 200

# Keys that let a feature through the pre-filter: category keys plus "boundary".
_FILTER_KEYS = tuple(dict.fromkeys(RELEVANT_KEYS + ("boundary",)))
_ADMIN_LEVELS = {"5", "6", "7"}


# ------------------------------------------------------------------ field helpers

def clean(text: str | None) -> str:
    """Collapse whitespace and strip control characters."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]", " ", text)).strip()


def make_address(tags: dict[str, str]) -> str:
    """Join the address parts that exist; never invent any.  The county is not included."""
    street = clean(tags.get("addr:street"))
    number = clean(tags.get("addr:housenumber"))
    # A house number is only meaningful next to its street.
    street_part = f"{number} {street}" if (number and street) else street
    parts = [
        clean(tags.get("addr:housename")),
        street_part,
        clean(tags.get("addr:place")),
        clean(tags.get("addr:city") or tags.get("addr:town") or tags.get("addr:village")),
    ]
    out: list[str] = []
    for part in parts:
        if part and part.casefold() not in (p.casefold() for p in out):
            out.append(part)
    return ", ".join(out)


def make_eircode(raw: str | None) -> str:
    """Return a normalised Eircode ("A65 F4E2") only if `raw` has the Eircode shape."""
    value = clean(raw)
    if not value or not EIRCODE_RE.match(value):
        return ""
    compact = re.sub(r"\s", "", value).upper()
    return f"{compact[:3]} {compact[3:]}"


# ------------------------------------------------------------------ data holders

@dataclass(slots=True)
class Candidate:
    category: str
    name: str
    type_label: str
    address: str
    eircode: str
    lat: float
    lon: float
    addr_county: str | None


@dataclass(slots=True)
class BoundaryInfo:
    osm_ref: str          # e.g. "relation 123"
    name: str
    admin_level: str
    kind: str             # administrative / historic / ceremonial / county border
    region: str | None    # county slug, NI, or None when the name is not recognised


@dataclass
class Collected:
    candidates: list[Candidate] = field(default_factory=list)
    # tier (0 = administrative, 1 = historic/ceremonial) -> region -> polygons
    polygons: dict[int, dict[str, list[BaseGeometry]]] = field(
        default_factory=lambda: {0: defaultdict(list), 1: defaultdict(list)})
    boundaries: list[BoundaryInfo] = field(default_factory=list)
    bad_geometry: int = 0


# ------------------------------------------------------------------ reading the extract

def boundary_candidate(tags: dict[str, str]) -> tuple[int, str] | None:
    """Decide whether tags describe a county-like boundary; return (tier, kind)."""
    kind = tags.get("boundary", "")
    level = tags.get("admin_level", "")
    border_type = tags.get("border_type", "")
    if kind == "administrative":
        if level in _ADMIN_LEVELS:
            return 0, "administrative"
        if level == "4" and region_for_name(tags.get("name")) == NI:
            return 0, "administrative"  # the "Northern Ireland" region polygon
        return None
    if kind in ("historic", "ceremonial") or border_type == "county":
        if border_type and border_type != "county":
            return None  # baronies, civil parishes ...
        if border_type == "county" or level in _ADMIN_LEVELS or not level:
            return 1, (kind if kind in ("historic", "ceremonial") else "county border")
    return None


def region_from_boundary_tags(tags: dict[str, str]) -> str | None:
    for key in ("name:en", "name", "official_name"):
        region = region_for_name(tags.get(key))
        if region:
            return region
    return None


def to_valid_polygons(geom: BaseGeometry) -> list[BaseGeometry]:
    geom = shapely.make_valid(geom) if not geom.is_valid else geom
    if isinstance(geom, (Polygon, MultiPolygon)):
        return [geom]
    return [g for g in getattr(geom, "geoms", []) if isinstance(g, (Polygon, MultiPolygon))]


def point_inside(geom: BaseGeometry) -> tuple[float, float]:
    """Centroid when it lies inside the shape, otherwise a guaranteed-inside point."""
    centre = geom.centroid
    if not geom.contains(centre):
        centre = geom.representative_point()
    return centre.x, centre.y


def read_extract(pbf: Path) -> tuple[Collected, str | None]:
    """Stream the extract once and collect candidate places and boundary polygons."""
    data = Collected()
    # flex_mem: osmium's automatic dense/sparse in-memory node index. The Geofabrik
    # Ireland+NI file has sparse global node ids, so it uses the sparse variant (~1-2 GB).
    processor = (
        osmium.FileProcessor(str(pbf))
        .with_locations("flex_mem")
        .with_areas(KeyFilter(*_FILTER_KEYS))   # only assemble relevant multipolygons
        .with_filter(KeyFilter(*_FILTER_KEYS))  # only hand relevant objects to Python
    )
    header_ts = processor.header.get("osmosis_replication_timestamp") or None
    wkb = osmium.geom.WKBFactory()

    for obj in processor:
        if obj.is_node():
            tags = {t.k: t.v for t in obj.tags}
            hit = classify(tags)
            if hit is None or not obj.location.valid():
                continue
            data.candidates.append(_candidate(tags, hit, obj.location.lat, obj.location.lon))
        elif obj.is_area():
            tags = {t.k: t.v for t in obj.tags}
            boundary = boundary_candidate(tags) if "boundary" in tags or "border_type" in tags else None
            hit = classify(tags)
            if boundary is None and hit is None:
                continue
            try:
                geom = shapely.from_wkb(wkb.create_multipolygon(obj))
            except (RuntimeError, ValueError, osmium.InvalidLocationError):
                data.bad_geometry += 1
                continue
            if boundary is not None:
                _add_boundary(data, obj, tags, geom, *boundary)
            if hit is not None:
                lon, lat = point_inside(geom)
                data.candidates.append(_candidate(tags, hit, lat, lon))
    return data, header_ts


def _candidate(tags: dict[str, str], hit: tuple[str, str], lat: float, lon: float) -> Candidate:
    return Candidate(
        category=hit[0], name=clean(tags["name"]), type_label=hit[1],
        address=make_address(tags), eircode=make_eircode(tags.get("addr:postcode")),
        lat=lat, lon=lon, addr_county=tags.get("addr:county"),
    )


def _add_boundary(data: Collected, obj, tags: dict[str, str], geom: BaseGeometry,
                  tier: int, kind: str) -> None:
    region = region_from_boundary_tags(tags)
    ref = f"{'way' if obj.from_way() else 'relation'} {obj.orig_id()}"
    data.boundaries.append(BoundaryInfo(
        ref, clean(tags.get("name") or tags.get("name:en") or tags.get("official_name")),
        tags.get("admin_level", "-"), kind, region))
    if region:
        data.polygons[tier][region].extend(to_valid_polygons(geom))


# ------------------------------------------------------------------ county assignment

class CountyLocator:
    """Point-in-polygon lookup.  Tier 0 (administrative) wins over tier 1 (historic)."""

    def __init__(self, polygons: dict[int, dict[str, list[BaseGeometry]]]) -> None:
        self.tiers: list[tuple[STRtree, list[BaseGeometry], list[str]]] = []
        for tier in (0, 1):
            keys = sorted(k for k, v in polygons[tier].items() if v)
            geoms = [shapely.union_all(polygons[tier][k]) for k in keys]
            for g in geoms:
                shapely.prepare(g)
            if keys:
                self.tiers.append((STRtree(geoms), geoms, keys))
        self.ambiguous = 0

    def locate(self, lons: np.ndarray, lats: np.ndarray) -> list[str | None]:
        result: list[str | None] = [None] * len(lons)
        pending = np.arange(len(lons))
        for tree, geoms, keys in self.tiers:
            if pending.size == 0:
                break
            x, y = lons[pending], lats[pending]
            point_idx, geom_idx = tree.query(shapely.points(x, y))  # bounding-box candidates
            hits: dict[int, set[str]] = defaultdict(set)
            for g in np.unique(geom_idx):
                sel = point_idx[geom_idx == g]
                inside = shapely.intersects_xy(geoms[g], x[sel], y[sel])
                for p in sel[inside]:
                    hits[int(p)].add(keys[g])
            for p, found in hits.items():
                if len(found) > 1:
                    self.ambiguous += 1
                result[int(pending[p])] = sorted(found)[0]  # deterministic tie-break
            pending = np.array([i for i in pending if result[int(i)] is None], dtype=int)
        return result


# ------------------------------------------------------------------ output

def _dump(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _generated() -> str:
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    now = dt.datetime.fromtimestamp(int(epoch), dt.timezone.utc) if epoch else dt.datetime.now(dt.timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def _sort_key(p: dict) -> tuple:
    return (p["n"].casefold(), p["n"], p["a"].casefold(), p["a"], p["t"], p["lat"], p["lon"])


@dataclass
class Stats:
    counts: dict[str, Counter] = field(default_factory=lambda: {s: Counter() for s in COUNTY_SLUGS})
    eircodes: int = 0
    total: int = 0
    candidates: int = 0
    ni_dropped: int = 0
    unassigned_dropped: int = 0
    via_addr_county: int = 0
    duplicates: int = 0


def build(candidates: list[Candidate], locator: CountyLocator) -> tuple[dict, Stats]:
    """Assign counties and group places: {county slug: {category slug: [place dicts]}}."""
    stats = Stats(candidates=len(candidates))
    lons = np.array([c.lon for c in candidates], dtype=float)
    lats = np.array([c.lat for c in candidates], dtype=float)
    regions = locator.locate(lons, lats) if candidates else []
    grouped: dict[str, dict[str, list[dict]]] = {s: defaultdict(list) for s in COUNTY_SLUGS}
    seen: set[tuple] = set()
    for cand, region in zip(candidates, regions):
        if region is None:
            region = region_for_name(cand.addr_county)
            if region is not None:
                stats.via_addr_county += 1
        if region == NI:
            stats.ni_dropped += 1
            continue
        if region is None:
            stats.unassigned_dropped += 1
            continue
        place = {"n": cand.name, "t": cand.type_label, "a": cand.address, "e": cand.eircode,
                 "lat": round(cand.lat, COORD_DP), "lon": round(cand.lon, COORD_DP)}
        key = (region, cand.category, place["n"].casefold(), place["t"], place["a"].casefold(),
               place["lat"], place["lon"])
        if key in seen:
            stats.duplicates += 1
            continue
        seen.add(key)
        grouped[region][cand.category].append(place)
        stats.counts[region][cand.category] += 1
        stats.total += 1
        stats.eircodes += bool(cand.eircode)
    return grouped, stats


def write_output(out: Path, grouped: dict, stats: Stats, extract_label: str, generated: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    # Remove stale generated files (only ours) so dropped places do not linger.
    for slug in COUNTY_SLUGS:
        folder = out / slug
        if folder.is_dir():
            for old in folder.glob("*.json"):
                old.unlink()
    for slug, county_name in COUNTIES:
        for cat_slug, cat_name in CATEGORIES:
            places = grouped[slug].get(cat_slug)
            if not places:
                continue
            places.sort(key=_sort_key)
            path = out / slug / f"{cat_slug}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_dump({"county": county_name, "category": cat_name, "places": places}),
                            encoding="utf-8")
    index = {
        "generated": generated,
        "source": SOURCE_TEXT,
        "extract": extract_label,
        "counties": [{"slug": s, "name": n, "total": sum(stats.counts[s].values())} for s, n in COUNTIES],
        "categories": [{"slug": s, "name": n} for s, n in CATEGORIES],
        "counts": {s: {c: stats.counts[s][c] for c, _ in CATEGORIES if stats.counts[s][c]}
                   for s in COUNTY_SLUGS},
        "eircodeCount": stats.eircodes,
        "total": stats.total,
    }
    (out / "index.json").write_text(_dump(index), encoding="utf-8")


def make_summary(stats: Stats, data: Collected, missing: list[str], extract_label: str,
                 generated: str, ambiguous: int) -> str:
    lines = [
        "iSEE places directory - run summary",
        f"Source: {SOURCE_TEXT}",
        f"Generated: {generated}",
        f"Extract: {extract_label}",
        "",
        f"Places written: {stats.total}",
        f"  with an Eircode in the open data: {stats.eircodes}",
        f"Candidate named places read: {stats.candidates}",
        f"  placed by addr:county fallback (no boundary polygon contained them): {stats.via_addr_county}",
        f"  dropped - Northern Ireland (out of scope): {stats.ni_dropped}",
        f"  dropped - could not be assigned to a county: {stats.unassigned_dropped}",
        f"  dropped - exact duplicates: {stats.duplicates}",
        f"  points inside polygons of more than one county (first slug used): {ambiguous}",
        f"Areas with unusable geometry (skipped): {data.bad_geometry}",
        "",
    ]
    if missing:
        lines += [f"!!! WARNING: no boundary polygon found for {len(missing)} of 26 counties: "
                  + ", ".join(COUNTY_NAMES[s] for s in missing),
                  "!!! Places in these counties can only be placed through addr:county.", ""]
    lines.append("Counts per county and category")
    for slug, name in COUNTIES:
        total = sum(stats.counts[slug].values())
        detail = ", ".join(f"{CATEGORY_NAMES[c]} {n}" for c, _ in CATEGORIES
                           if (n := stats.counts[slug][c]))
        lines.append(f"  {name}: {total}" + (f" ({detail})" if detail else ""))
    matched = [b for b in data.boundaries if b.region]
    unmatched = [b for b in data.boundaries if not b.region]
    lines += ["", f"Boundary relations/ways matched to a county or Northern Ireland: {len(matched)}"]
    for b in sorted(matched, key=lambda b: (b.region or "", b.osm_ref)):
        lines.append(f"  {b.osm_ref}  '{b.name}'  admin_level={b.admin_level}  {b.kind}  -> {b.region}")
    lines += ["", f"Boundary relations/ways with candidate tags but an unrecognised name: {len(unmatched)}"]
    for b in sorted(unmatched, key=lambda b: (b.name, b.osm_ref))[:MAX_LISTED_UNMATCHED]:
        lines.append(f"  {b.osm_ref}  '{b.name}'  admin_level={b.admin_level}  {b.kind}")
    if len(unmatched) > MAX_LISTED_UNMATCHED:
        lines.append(f"  ... and {len(unmatched) - MAX_LISTED_UNMATCHED} more")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ CLI

def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pbf", required=True, type=Path, help="OSM extract (.osm.pbf, or .osm)")
    ap.add_argument("--out", required=True, type=Path, help="output directory")
    ap.add_argument("--extract-label", help="text recorded as 'extract' in index.json")
    args = ap.parse_args(list(argv) if argv is not None else None)

    data, header_ts = read_extract(args.pbf)
    label = args.extract_label or (
        f"{args.pbf.name} (data as of {header_ts})" if header_ts else args.pbf.name)

    present = {r for tiers in data.polygons.values() for r, polys in tiers.items() if polys}
    matched_counties = [s for s in COUNTY_SLUGS if s in present]
    if not matched_counties:
        print("::error::No county boundary polygons matched; refusing to write an empty directory.")
        return 1
    missing = [s for s in COUNTY_SLUGS if s not in present]

    locator = CountyLocator(data.polygons)
    grouped, stats = build(data.candidates, locator)
    if stats.total == 0:
        print("::error::No places were assigned to any county; refusing to write an empty directory.")
        return 1

    generated = _generated()
    write_output(args.out, grouped, stats, label, generated)
    summary = make_summary(stats, data, missing, label, generated, locator.ambiguous)
    (args.out / "summary.txt").write_text(summary, encoding="utf-8")
    if missing:
        print(f"::warning::No boundary polygon for {len(missing)} counties: "
              + ", ".join(COUNTY_NAMES[s] for s in missing))
    print(f"Wrote {stats.total} places to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
