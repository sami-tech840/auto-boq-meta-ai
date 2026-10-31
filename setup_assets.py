"""setup_assets.py

Generates the sample asset bundle for the floorplan estimator:
  sample_assets/floorplans/*.png              (5 synthetic plans if folder empty)
  sample_assets/material_rates.json
  sample_assets/floorplans_manifest.json
  sample_assets/preset_cache.json

Run: python setup_assets.py
"""

import os
import json
from PIL import Image, ImageDraw

BASE_DIR = "sample_assets"
FLOORPLAN_DIR = os.path.join(BASE_DIR, "floorplans")
IMAGE_EXTS = (".png", ".jpg", ".jpeg")

TITLES = [
    "2BHK Modern Apartment (1,150 Sq.Ft)",
    "3BHK Corner Villa (1,680 Sq.Ft)",
    "1BHK Compact Studio (620 Sq.Ft)",
    "3BHK Luxury Duplex (2,450 Sq.Ft)",
    "2BHK Vastu-Compliant Flat (980 Sq.Ft)",
]

# (room name, room type, relative rect (x1, y1, x2, y2) in 0..1 space)
ROOM_LAYOUT = [
    ("Master Bedroom",  "bedroom", (0.03, 0.06, 0.42, 0.48)),
    ("Bedroom 2",       "bedroom", (0.45, 0.06, 0.72, 0.42)),
    ("Living & Dining", "living",  (0.03, 0.52, 0.55, 0.94)),
    ("Kitchen",         "kitchen", (0.58, 0.52, 0.80, 0.78)),
    ("Bath 1",          "bath",    (0.75, 0.06, 0.94, 0.30)),
    ("Bath 2",          "bath",    (0.83, 0.52, 0.97, 0.72)),
]

MATERIAL_RATES = {
    "wall_height_ft": 10.0,
    "tiers": {
        "economy": {
            "flooring_per_sqft": 85,
            "painting_per_sqft": 28,
            "false_ceiling_per_sqft": 95,
            "electrical_per_sqft": 110,
            "modular_kitchen_per_rft": 8500,
            "wardrobe_per_rft": 6500,
            "door_unit_cost": 8500,
            "window_unit_cost": 6000,
        },
        "standard": {
            "flooring_per_sqft": 145,
            "painting_per_sqft": 45,
            "false_ceiling_per_sqft": 135,
            "electrical_per_sqft": 160,
            "modular_kitchen_per_rft": 12500,
            "wardrobe_per_rft": 9500,
            "door_unit_cost": 14000,
            "window_unit_cost": 9500,
        },
        "luxury": {
            "flooring_per_sqft": 320,
            "painting_per_sqft": 85,
            "false_ceiling_per_sqft": 210,
            "electrical_per_sqft": 240,
            "modular_kitchen_per_rft": 22000,
            "wardrobe_per_rft": 16500,
            "door_unit_cost": 28000,
            "window_unit_cost": 18000,
        },
    },
}

CALIBRATION_ANCHOR = {
    "room_label": "Master Bedroom",
    "printed_dimension_text": "12'0\" x 14'0\"",
    "real_area_sqft": 168.0,
}


def _draw_synthetic_plan(path, index):
    """Create one clean 1200x800 synthetic floorplan PNG."""
    w, h = 1200, 800
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, w - 1, h - 1], outline=(30, 30, 30), width=6)
    draw.text((24, 12), "FLOORPLAN %02d  -  SAMPLE SYNTHETIC PLAN" % (index + 1), fill=(0, 0, 0))
    for name, _rtype, (x1, y1, x2, y2) in ROOM_LAYOUT:
        box = [int(x1 * w), int(y1 * h), int(x2 * w), int(y2 * h)]
        draw.rectangle(box, outline=(70, 70, 70), width=3)
        draw.text((box[0] + 10, box[1] + 10), name, fill=(20, 20, 20))
        draw.text((box[0] + 10, box[1] + 26), "12'0\" x 14'0\"", fill=(110, 110, 110))
    img.save(path)


def ensure_floorplans():
    """Return the list of floorplan image filenames, generating samples if empty."""
    os.makedirs(FLOORPLAN_DIR, exist_ok=True)
    files = sorted(
        f for f in os.listdir(FLOORPLAN_DIR) if f.lower().endswith(IMAGE_EXTS)
    )
    if not files:
        print("No floorplans found - generating 5 synthetic 1200x800 plans...")
        for i in range(5):
            _draw_synthetic_plan(
                os.path.join(FLOORPLAN_DIR, "floorplan_%02d.png" % (i + 1)), i
            )
        files = sorted(
            f for f in os.listdir(FLOORPLAN_DIR) if f.lower().endswith(IMAGE_EXTS)
        )
    return files


def _scale_rect(rel, w, h):
    x1, y1, x2, y2 = rel
    return [
        int(round(x1 * w)),
        int(round(y1 * h)),
        int(round(x2 * w)),
        int(round(y2 * h)),
    ]


def _polygon(rect):
    x1, y1, x2, y2 = rect
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def _edge_points(rects, count):
    """Deterministic door/window marker points distributed along room edges."""
    points = []
    for i in range(count):
        r = rects[i % len(rects)]
        if i % 2 == 0:
            points.append([(r[0] + r[2]) // 2, r[1]])
        else:
            points.append([r[0], (r[1] + r[3]) // 2])
    return points


def build_preset(width, height):
    """Build a 6-room non-overlapping rectangular layout scaled to the image."""
    rooms = []
    rects = []
    for name, rtype, rel in ROOM_LAYOUT:
        rect = _scale_rect(rel, width, height)
        rects.append(rect)
        rooms.append({"name": name, "type": rtype, "polygon": _polygon(rect)})
    return {
        "rooms": rooms,
        "doors_count": 7,
        "windows_count": 5,
        "door_coords": _edge_points(rects, 7),
        "window_coords": _edge_points(rects, 5),
    }


def write_json(filename, payload):
    path = os.path.join(BASE_DIR, filename)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return path


def main():
    os.makedirs(BASE_DIR, exist_ok=True)
    files = ensure_floorplans()

    manifest = []
    presets = {}

    for index, filename in enumerate(files):
        plan_id = "plan_%02d" % (index + 1)
        abs_path = os.path.join(FLOORPLAN_DIR, filename)

        with Image.open(abs_path) as img:
            width, height = img.size

        manifest.append(
            {
                "id": plan_id,
                "title": TITLES[index % len(TITLES)],
                "file_path": abs_path.replace(os.sep, "/"),
                "resolution": {"width": width, "height": height},
                "calibration_anchor": dict(CALIBRATION_ANCHOR),
            }
        )
        presets[plan_id] = build_preset(width, height)

    written = [
        write_json("material_rates.json", MATERIAL_RATES),
        write_json("floorplans_manifest.json", manifest),
        write_json("preset_cache.json", presets),
    ]

    print("")
    print("Sample assets ready in '%s/'" % BASE_DIR)
    print("  Floorplans processed : %d" % len(files))
    print("  Rooms per preset     : %d" % len(ROOM_LAYOUT))
    for path in written:
        print("  Created              : %s" % path.replace(os.sep, "/"))
    print("Done.")


if __name__ == "__main__":
    main()