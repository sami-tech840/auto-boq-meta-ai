"""boq_math.py — Auto-BOQ: 2D floorplan segmentation -> itemized Indian BOQ (INR).

Pure Python maths (math / numpy only, no geometry libraries).
Pixel polygons are converted to real-world units using a single linear scale
(ft per pixel) obtained by calibrating one known reference area.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence, Tuple

# --------------------------------------------------------------------------- #
# Rate card defaults (INR, "standard" tier, Indian residential market)
# --------------------------------------------------------------------------- #
TIER_FACTORS: Dict[str, float] = {"economy": 0.75, "standard": 1.0, "premium": 1.45}

DEFAULT_RATES_INR: Dict[str, float] = {
    "flooring": 145.0,      # per Sq.Ft — vitrified tiles laid
    "paint": 38.0,          # per Sq.Ft — putty + primer + 2 coats emulsion
    "ceiling": 95.0,        # per Sq.Ft — gypsum false ceiling with GI framing
    "electrical": 85.0,     # per Sq.Ft — concealed conduit wiring points
    "kitchen": 1850.0,      # per RFT — modular kitchen cabinets
    "wardrobe": 1650.0,     # per RFT — bedroom wardrobe
    "door": 12500.0,        # per Nos — flush door + hardware
    "window": 6500.0,       # per Nos — UPVC window
}


# --------------------------------------------------------------------------- #
# 1. Pixel geometry
# --------------------------------------------------------------------------- #
def polygon_area_and_perimeter_px(
    polygon_points: List[List[float]],
) -> Tuple[float, float]:
    """Shoelace area (px^2) and closed-loop perimeter (px) of a polygon."""
    pts = [(float(p[0]), float(p[1])) for p in (polygon_points or []) if len(p) >= 2]
    n = len(pts)

    if n < 2:
        return 0.0, 0.0

    if n < 3:  # degenerate: a line segment
        perimeter = sum(
            math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
            for i in range(n - 1)
        )
        return 0.0, perimeter

    area2 = 0.0
    perimeter = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        area2 += x1 * y2 - x2 * y1
        perimeter += math.hypot(x2 - x1, y2 - y1)

    return abs(area2) / 2.0, perimeter


# --------------------------------------------------------------------------- #
# 2. Scale calibration
# --------------------------------------------------------------------------- #
def calibrate_scale(
    reference_polygon_px: List[List[float]], real_area_sqft: float
) -> float:
    """Return linear scale in feet-per-pixel from one known reference area."""
    area_px, _ = polygon_area_and_perimeter_px(reference_polygon_px)
    safe_area_px = max(area_px, 1.0)
    safe_real_area = max(float(real_area_sqft), 0.0)
    return math.sqrt(safe_real_area / safe_area_px)


# --------------------------------------------------------------------------- #
# 3. Kitchen counter (L-shaped modular kitchen, Running Feet)
# --------------------------------------------------------------------------- #
def estimate_kitchen_counter_rft(
    polygon_points: List[List[float]], linear_scale_ft_per_px: float
) -> float:
    """(longest edge + second longest edge) * 0.65, in Running Feet."""
    pts = [(float(p[0]), float(p[1])) for p in (polygon_points or []) if len(p) >= 2]
    n = len(pts)
    if n < 2:
        return 0.0

    edges_ft: List[float] = []
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        edges_ft.append(math.hypot(x2 - x1, y2 - y1) * linear_scale_ft_per_px)

    edges_ft.sort(reverse=True)
    while len(edges_ft) < 2:
        edges_ft.append(0.0)

    return (edges_ft[0] + edges_ft[1]) * 0.65


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _resolve_rate(material_rates: Dict[str, Any], key: str, tier: str) -> float:
    """Look up '<key>_<tier>', then '<key>', else the default rate × tier factor."""
    tier_key = str(tier or "standard").strip().lower()
    for candidate in (f"{key}_{tier_key}", key):
        value = (material_rates or {}).get(candidate)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return DEFAULT_RATES_INR.get(key, 0.0) * TIER_FACTORS.get(tier_key, 1.0)


def _line_item(
    category: str,
    description: str,
    unit: str,
    quantity: float,
    rate: float,
) -> Dict[str, Any]:
    quantity = round(float(quantity), 2)
    rate = round(float(rate), 2)
    return {
        "Category": category,
        "Item Description": description,
        "Unit": unit,
        "Quantity": quantity,
        "Rate (INR)": rate,
        "Amount (INR)": round(quantity * rate, 2),
    }


# --------------------------------------------------------------------------- #
# 4. Full BOQ
# --------------------------------------------------------------------------- #
def calculate_full_boq(
    segmented_data: Dict[str, Any],
    material_rates: Dict[str, Any],
    tier: str = "standard",
    linear_scale_ft_per_px: float = 0.04,
) -> Dict[str, Any]:
    """Build the room breakdown, summary and itemized line items for a floorplan."""
    material_rates = material_rates or {}
    scale = float(linear_scale_ft_per_px)
    scale_sq = scale * scale
    wall_height_ft = float(material_rates.get("wall_height_ft", 10.0))

    total_carpet_sqft = 0.0
    total_paint_sqft = 0.0
    total_kitchen_rft = 0.0
    total_wardrobe_rft = 0.0
    doors_count = 0
    windows_count = 0
    room_breakdown: List[Dict[str, Any]] = []

    for room in (segmented_data or {}).get("rooms", []) or []:
        poly = room.get("polygon") or []
        room_type = str(room.get("type", "")).strip().lower()

        area_px, perimeter_px = polygon_area_and_perimeter_px(poly)

        floor_sqft = round(area_px * scale_sq, 1)
        perimeter_ft = round(perimeter_px * scale, 1)
        wall_paint_sqft = round(max(0.0, (perimeter_ft * wall_height_ft) * 0.85), 1)

        kitchen_rft = (
            round(estimate_kitchen_counter_rft(poly, scale), 1)
            if room_type == "kitchen"
            else 0.0
        )
        wardrobe_rft = (
            round((perimeter_ft / 4.0) * 0.55, 1) if room_type == "bedroom" else 0.0
        )

        # One entry door per enclosed room; windows sized off the room perimeter.
        room_doors = 1
        room_windows = max(1, int(round(perimeter_ft / 10.0))) if perimeter_ft > 0 else 0

        total_carpet_sqft += floor_sqft
        total_paint_sqft += wall_paint_sqft
        total_kitchen_rft += kitchen_rft
        total_wardrobe_rft += wardrobe_rft
        doors_count += room_doors
        windows_count += room_windows

        room_breakdown.append(
            {
                "name": room.get("name", "Unnamed Room"),
                "type": room_type or "unknown",
                "floor_sqft": floor_sqft,
                "perimeter_ft": perimeter_ft,
                "wall_paint_sqft": wall_paint_sqft,
                "kitchen_rft": kitchen_rft,
                "wardrobe_rft": wardrobe_rft,
                "doors": room_doors,
                "windows": room_windows,
            }
        )

    total_carpet_sqft = round(total_carpet_sqft, 1)
    total_paint_sqft = round(total_paint_sqft, 1)
    total_kitchen_rft = round(total_kitchen_rft, 1)
    total_wardrobe_rft = round(total_wardrobe_rft, 1)

    specs: Sequence[Tuple[str, str, str, float, str]] = (
        ("Flooring", "Vitrified Flooring", "Sq.Ft", total_carpet_sqft, "flooring"),
        ("Painting", "Wall Putty & Emulsion Paint", "Sq.Ft", total_paint_sqft, "paint"),
        ("Ceiling", "Gypsum False Ceiling", "Sq.Ft", total_carpet_sqft, "ceiling"),
        ("Electrical", "Concealed Electrical Wiring", "Sq.Ft", total_carpet_sqft, "electrical"),
        ("Kitchen", "Modular Kitchen Cabinets", "RFT", total_kitchen_rft, "kitchen"),
        ("Wardrobe", "Bedroom Wardrobes", "RFT", total_wardrobe_rft, "wardrobe"),
        ("Doors", "Flush Doors & Hardware", "Nos", float(doors_count), "door"),
        ("Windows", "UPVC Windows", "Nos", float(windows_count), "window"),
    )

    line_items: List[Dict[str, Any]] = [
        _line_item(category, description, unit, quantity, _resolve_rate(material_rates, rate_key, tier))
        for category, description, unit, quantity, rate_key in specs
    ]

    grand_total = round(sum(item["Amount (INR)"] for item in line_items), 2)
    cost_per_sqft = (
        round(grand_total / total_carpet_sqft, 2) if total_carpet_sqft > 0 else 0.0
    )

    return {
        "summary": {
            "total_carpet_area_sqft": total_carpet_sqft,
            "total_paint_sqft": total_paint_sqft,
            "total_kitchen_rft": total_kitchen_rft,
            "total_wardrobe_rft": total_wardrobe_rft,
            "doors_count": doors_count,
            "windows_count": windows_count,
            "grand_total_inr": grand_total,
            "cost_per_sqft_inr": cost_per_sqft,
        },
        "room_breakdown": room_breakdown,
        "line_items": line_items,
    }


if __name__ == "__main__":  # tiny smoke test
    ref = [[0, 0], [100, 0], [100, 100], [0, 100]]
    scale_ft = calibrate_scale(ref, 100.0)  # 10x10 px == 100 sqft
    demo = {
        "rooms": [
            {"name": "Living Room", "type": "living", "polygon": ref},
            {"name": "Kitchen", "type": "kitchen", "polygon": [[0, 0], [80, 0], [80, 60], [0, 60]]},
            {"name": "Bedroom 1", "type": "bedroom", "polygon": [[0, 0], [90, 0], [90, 90], [0, 90]]},
        ]
    }
    boq = calculate_full_boq(demo, {"wall_height_ft": 10.0}, tier="standard",
                             linear_scale_ft_per_px=scale_ft)
    print(boq["summary"])
    for item in boq["line_items"]:
        print(item)