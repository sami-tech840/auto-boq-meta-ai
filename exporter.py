# exporter.py
import io
from typing import Union

import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter


# ---------------------------------------------------------------------------
# 1. SAM Segmentation Overlay
# ---------------------------------------------------------------------------

_ROOM_COLORS = {
    "bedroom": {"fill": (59, 130, 246, 95), "outline": (37, 99, 235, 240)},
    "kitchen": {"fill": (245, 158, 11, 110), "outline": (217, 119, 6, 240)},
    "living": {"fill": (16, 185, 129, 95), "outline": (5, 150, 105, 240)},
    "bath": {"fill": (168, 85, 247, 95), "outline": (126, 34, 206, 240)},
}
_DEFAULT_COLOR = {"fill": (148, 163, 184, 95), "outline": (100, 116, 139, 240)}


def _polygon_centroid(points):
    """Compute centroid of a polygon (list of (x, y))."""
    if not points:
        return (0, 0)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def draw_sam_segmentation_overlay(
    image_source,
    segmented_data: dict,
    show_rooms: bool = True,
    show_openings: bool = True,
) -> Image.Image:
    """Draw room polygons and opening markers over an image."""
    base = Image.open(image_source).convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    if show_rooms:
        for room in segmented_data.get("rooms", []):
            pts = [tuple(p) for p in room.get("polygon", [])]
            if len(pts) < 3:
                continue
            rtype = str(room.get("type", "")).lower()
            colors = _ROOM_COLORS.get(rtype, _DEFAULT_COLOR)
            draw.polygon(pts, fill=colors["fill"], outline=colors["outline"])

            # Centroid pill with room name
            cx, cy = _polygon_centroid(pts)
            name = str(room.get("name", "Room"))
            try:
                bbox = draw.textbbox((0, 0), name, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            except Exception:
                tw, th = len(name) * 6, 10

            pad_x, pad_y = 6, 3
            x0, y0 = cx - tw / 2 - pad_x, cy - th / 2 - pad_y
            x1, y1 = cx + tw / 2 + pad_x, cy + th / 2 + pad_y
            draw.rounded_rectangle(
                [x0, y0, x1, y1], radius=4, fill=(15, 23, 42, 210)
            )
            draw.text((cx - tw / 2, cy - th / 2), name, fill=(255, 255, 255, 255), font=font)

    if show_openings:
        for coord in segmented_data.get("door_coords", []):
            x, y = coord[0], coord[1]
            r = 6
            draw.ellipse([x - r, y - r, x + r, y + r], fill=(239, 68, 68, 230))
        for coord in segmented_data.get("window_coords", []):
            x, y = coord[0], coord[1]
            r = 6
            draw.ellipse([x - r, y - r, x + r, y + r], fill=(6, 182, 212, 230))

    composited = Image.alpha_composite(base, overlay)
    return composited.convert("RGB")


# ---------------------------------------------------------------------------
# 2. Excel BOQ Export
# ---------------------------------------------------------------------------

def _autofit_columns(ws, min_width=10, max_width=50):
    for col_cells in ws.columns:
        length = 0
        letter = get_column_letter(col_cells[0].column)
        for cell in col_cells:
            val = str(cell.value) if cell.value is not None else ""
            length = max(length, len(val))
        ws.column_dimensions[letter].width = max(min_width, min(max_width, length + 2))


def _write_dataframe(ws, df: pd.DataFrame, start_row: int = 1):
    """Write a DataFrame starting at start_row, returns next free row."""
    if df is None or df.empty:
        return start_row
    for j, col in enumerate(df.columns, start=1):
        c = ws.cell(row=start_row, column=j, value=str(col))
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1E3A8A")
        c.alignment = Alignment(horizontal="center", vertical="center")
    for i, row in enumerate(df.itertuples(index=False), start=start_row + 1):
        for j, val in enumerate(row, start=1):
            ws.cell(row=i, column=j, value=val)
    return start_row + 1 + len(df)


def generate_excel_boq_bytes(
    boq_result: dict,
    line_items_df: pd.DataFrame,
    studio_name: str,
    project_title: str,
) -> bytes:
    """Generate an in-memory Excel BOQ workbook and return its bytes."""
    wb = Workbook()

    # ---- Sheet 1: Itemized_BOQ ----
    ws1 = wb.active
    ws1.title = "Itemized_BOQ"

    grand_total = boq_result.get("grand_total", 0)
    cost_per_sqft = boq_result.get("cost_per_sqft", 0)

    ws1["A1"] = "Studio"
    ws1["B1"] = studio_name
    ws1["A2"] = "Project"
    ws1["B2"] = project_title
    ws1["A3"] = "Grand Total (INR)"
    ws1["B3"] = grand_total
    ws1["B3"].number_format = '₹#,##0.00'
    ws1["A4"] = "Cost / Sq.Ft (INR)"
    ws1["B4"] = cost_per_sqft
    ws1["B4"].number_format = '₹#,##0.00'

    for r in range(1, 5):
        ws1.cell(row=r, column=1).font = Font(bold=True)
    for r in (3, 4):
        ws1.cell(row=r, column=2).font = Font(bold=True, color="1E3A8A")

    header_row = 6
    _write_dataframe(ws1, line_items_df, start_row=header_row)

    _autofit_columns(ws1)

    # ---- Sheet 2: Room_Wise_Measurements ----
    ws2 = wb.create_sheet("Room_Wise_Measurements")
    room_df = pd.DataFrame(boq_result.get("room_breakdown", []))

    expected_cols = [
        ("room", "Room"),
        ("floor_sqft", "Floor Sq.Ft"),
        ("paint_sqft", "Paint Sq.Ft"),
        ("kitchen_rft", "Kitchen RFT"),
        ("wardrobe_rft", "Wardrobe RFT"),
    ]
    if not room_df.empty:
        rename_map = {}
        ordered = []
        for key, label in expected_cols:
            if key in room_df.columns:
                rename_map[key] = label
                ordered.append(label)
        # keep extra columns untouched
        extra = [c for c in room_df.columns if c not in rename_map]
        room_df = room_df.rename(columns=rename_map)[ordered + extra]
    else:
        room_df = pd.DataFrame(columns=[label for _, label in expected_cols])

    _write_dataframe(ws2, room_df, start_row=1)
    _autofit_columns(ws2)

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


# ---------------------------------------------------------------------------
# 3. WhatsApp Quote Formatter
# ---------------------------------------------------------------------------

def format_whatsapp_quote(
    boq_result: dict,
    studio_name: str,
    project_title: str,
    tier: str,
) -> str:
    """Return an emoji-formatted WhatsApp quote summary."""
    total_area = boq_result.get("total_carpet_area", 0)
    kitchen_rft = boq_result.get("total_kitchen_rft", 0)
    grand_total = boq_result.get("grand_total", 0)
    room_count = len(boq_result.get("room_breakdown", []) or [])

    message = (
        f"*🏠 {studio_name} — Project Quote*\n"
        f"📋 *Project:* {project_title}\n"
        f"⭐ *Tier:* {tier}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📐 *Carpet Area:* {total_area:,.2f} sq.ft\n"
        f"🍳 *Kitchen:* {kitchen_rft:,.2f} RFT\n"
        f"🚪 *Rooms:* {room_count}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 *Grand Total:* ₹{grand_total:,.2f}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"_Quote generated by Auto-BOQ_\n"
        f"📞 Ready to discuss — reply to this message!"
    )
    return message