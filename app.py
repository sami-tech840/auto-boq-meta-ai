import os
import json
import inspect
import streamlit as st
import pandas as pd
from PIL import Image

from boq_math import calibrate_scale, calculate_full_boq
from meta_client import MetaBOQPipeline
from exporter import (
    draw_sam_segmentation_overlay,
    generate_excel_boq_bytes,
    format_whatsapp_quote,
)

st.set_page_config(page_title="Auto-BOQ | Meta AI Spatial Estimator", layout="wide")

# 1. Load JSON Assets Safely
MANIFEST_PATH = "sample_assets/floorplans_manifest.json"
RATES_PATH = "sample_assets/material_rates.json"

if not os.path.exists(MANIFEST_PATH):
    try:
        import setup_assets  # noqa: F401
    except Exception:
        pass

with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
    raw_manifest = json.load(f)
presets = (
    raw_manifest
    if isinstance(raw_manifest, list)
    else raw_manifest.get("presets", raw_manifest.get("samples", []))
)

with open(RATES_PATH, "r", encoding="utf-8") as f:
    material_rates = json.load(f)

# 2. Top Header Banner
st.markdown(
    """
    <div style="padding:14px 20px;background:linear-gradient(90deg,#0f172a,#1e293b);border-radius:10px;border:1px solid #334155;margin-bottom:16px;">
        <h2 style="margin:0;color:#f8fafc;">🏗️ Auto-BOQ — Zero-Shot Blueprint to Construction Cost Engine</h2>
        <p style="margin:4px 0 0 0;color:#94a3b8;font-size:14px;">
            <b>Meta AI 4-Model Pipeline:</b> SAM 3.1 (Spatial Masks) → Muse Spark 1.3 (Scale & RFT Math) → Muse Image 1.0 (3D Render) → Muse Code (BOQ Export)
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

col_left, col_center, col_right = st.columns([1.05, 1.75, 1.5])

# ---------------- LEFT COLUMN ----------------
with col_left:
    st.subheader("⚙️ Controls & Calibration")
    brand = st.text_input("Studio / Contractor Brand Name", value="Crescent Design & Build")
    api_key = st.text_input(
        "Meta Model API Key",
        value=os.getenv("MODEL_API_KEY", ""),
        type="password",
        help="Leave blank to use $0 cached presets or local stage fallback.",
    )

    mode = st.radio(
        "Floorplan Source",
        ["Preset Sample Floorplans ($0 Cached)", "Upload Custom Floorplan (PNG/JPG)"],
    )

    selected_preset = presets[0] if presets else {}
    image_source = None
    preset_id = None

    if mode.startswith("Preset"):
        preset_map = {
            f"{p.get('id', f'plan_{i+1}')} — {p.get('title', 'Floorplan')}": p
            for i, p in enumerate(presets)
        }
        choice = st.selectbox("Select Preset Floorplan", list(preset_map.keys()))
        selected_preset = preset_map[choice]
        preset_id = selected_preset.get("id", "plan_01")
        image_source = selected_preset.get("file_path")
    else:
        uploaded = st.file_uploader("Upload Blueprint (PNG/JPG)", type=["png", "jpg", "jpeg"])
        if uploaded:
            temp_path = "sample_assets/temp_upload.png"
            Image.open(uploaded).save(temp_path)
            image_source = temp_path
        elif presets:
            image_source = presets[0].get("file_path")
            preset_id = presets[0].get("id", "plan_01")

    tier = st.selectbox("Material Tier", ["economy", "standard", "luxury"], index=1)

    # Run MetaBOQPipeline safely regardless of method name
    pipeline = MetaBOQPipeline(api_key=api_key if api_key else None)
    if hasattr(pipeline, "analyze_floorplan"):
        segmented_data = pipeline.analyze_floorplan(image_source, preset_id=preset_id)
    elif hasattr(pipeline, "analyze"):
        segmented_data = pipeline.analyze(image_source, preset_id=preset_id)
    else:
        segmented_data = {"rooms": [], "doors_count": 6, "windows_count": 5}

    # Auto-calibrate scale from first room polygon
    default_scale = 0.045
    try:
        rooms_list = segmented_data.get("rooms", [])
        anchor = selected_preset.get("calibration_anchor", {})
        ref_area = float(anchor.get("real_area_sqft", 168.0))
        if rooms_list and rooms_list[0].get("polygon"):
            calc_s = float(calibrate_scale(rooms_list[0]["polygon"], ref_area))
            if 0.015 <= calc_s <= 0.12:
                default_scale = round(calc_s, 4)
    except Exception:
        pass

    scale_ft_per_px = st.slider(
        "Scale Calibration (ft / px)",
        min_value=0.015,
        max_value=0.120,
        value=float(default_scale),
        step=0.001,
        format="%.3f",
    )
    st.caption(f"🎯 Reference Anchor: Master Bedroom = 168 Sq.Ft ({scale_ft_per_px:.3f} ft/px)")

# ---------------- BOQ MATH ADAPTER ----------------
sig = inspect.signature(calculate_full_boq)
kwargs = {}
for param in sig.parameters:
    if param in ("segmented_data", "segmentation", "data"):
        kwargs[param] = segmented_data
    elif param in ("material_rates", "rates"):
        kwargs[param] = material_rates
    elif param in ("tier", "material_tier"):
        kwargs[param] = tier
    elif param in ("linear_scale_ft_per_px", "scale_ft_per_px", "scale"):
        kwargs[param] = scale_ft_per_px

boq_result = calculate_full_boq(**kwargs)
summary = boq_result.get("summary", {})

# ---------------- CENTER COLUMN ----------------
with col_center:
    st.subheader("🎯 SAM 3.1 Spatial Segmentation Canvas")
    c1, c2 = st.columns(2)
    show_rooms = c1.checkbox("Show SAM 3.1 Room Polygons", value=True)
    show_openings = c2.checkbox("Show Door/Window Detections", value=True)

    if image_source and os.path.exists(str(image_source)):
        try:
            overlay_img = draw_sam_segmentation_overlay(
                image_source, segmented_data, show_rooms=show_rooms, show_openings=show_openings
            )
        except TypeError:
            overlay_img = draw_sam_segmentation_overlay(image_source, segmented_data)
        st.image(overlay_img, use_container_width=True)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Carpet Area", f"{summary.get('total_carpet_area_sqft', 0):,.0f} Sq.Ft")
    m2.metric("Kitchen Counter", f"{summary.get('total_kitchen_rft', 0):,.1f} RFT")
    m3.metric("Wardrobes", f"{summary.get('total_wardrobe_rft', 0):,.1f} RFT")
    m4.metric(
        "Doors / Windows",
        f"{summary.get('doors_count', segmented_data.get('doors_count', 7))} / {summary.get('windows_count', segmented_data.get('windows_count', 5))}",
    )

    with st.expander("✨ Generate Instant 3D Client Room Concept (Muse Image 1.0)"):
        room_choice = st.selectbox("Select Room to Render", ["Modular Kitchen", "Master Bedroom", "Living & Dining"])
        if st.button("Generate 3D Concept Render", use_container_width=True):
            res = pipeline.generate_room_concept_render(room_choice, tier)
            img_url = res.get("image_url") if isinstance(res, dict) else str(res)
            st.image(img_url, caption=f"Muse Image 1.0 Concept — {room_choice} ({tier.title()} Tier)", use_container_width=True)

# ---------------- RIGHT COLUMN ----------------
with col_right:
    st.subheader("💰 Live Editable Rate Card & BOQ")
    raw_items = boq_result.get("line_items", [])
    df = pd.DataFrame(raw_items)

    # Normalize column names dynamically so live editing always works
    qty_col = next((c for c in df.columns if "qty" in c.lower() or "quant" in c.lower()), None)
    rate_col = next((c for c in df.columns if "rate" in c.lower()), None)
    amt_col = next((c for c in df.columns if "amount" in c.lower() or "total" in c.lower()), None)

    edited_df = st.data_editor(df, use_container_width=True, hide_index=True, num_rows="dynamic")

    if qty_col and rate_col and amt_col:
        edited_df[amt_col] = (
            pd.to_numeric(edited_df[qty_col], errors="coerce").fillna(0)
            * pd.to_numeric(edited_df[rate_col], errors="coerce").fillna(0)
        ).round(0)
        grand_total = float(edited_df[amt_col].sum())
    else:
        grand_total = float(summary.get("grand_total_inr", 0))

    carpet = max(float(summary.get("total_carpet_area_sqft", 1)), 1.0)
    cost_per_sqft = grand_total / carpet

    k1, k2 = st.columns(2)
    k1.metric("Grand Total Estimate", f"₹{grand_total:,.0f}")
    k2.metric("Effective Rate", f"₹{cost_per_sqft:,.0f} / Sq.Ft")

    project_title = selected_preset.get("title", "Custom Floorplan BOQ")
    try:
        excel_sig = inspect.signature(generate_excel_boq_bytes)
        if len(excel_sig.parameters) == 4:
            excel_bytes = generate_excel_boq_bytes(boq_result, edited_df, brand, project_title)
        else:
            boq_result["line_items"] = edited_df.to_dict(orient="records")
            excel_bytes = generate_excel_boq_bytes(boq_result, brand, project_title)

        st.download_button(
            label="📥 Download Multi-Sheet Excel BOQ (.xlsx)",
            data=excel_bytes,
            file_name=f"Auto_BOQ_{preset_id or 'custom'}_{tier}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True,
        )
    except Exception as exc:
        st.warning(f"Excel export note: {exc}")

    with st.expander("📲 Copy Instant WhatsApp Client Quote"):
        quote_text = (
            f"🏗️ *{brand} — Instant AI Interior Estimate*\n"
            f"📐 *Layout:* {project_title}\n"
            f"🏠 *Carpet Area:* {carpet:,.0f} Sq.Ft | *Tier:* {tier.title()}\n"
            f"🍳 *Modular Kitchen:* {summary.get('total_kitchen_rft', 0):.1f} RFT\n"
            f"🚪 *Wardrobes:* {summary.get('total_wardrobe_rft', 0):.1f} RFT\n"
            f"💰 *Grand Total Estimate:* ₹{grand_total:,.0f} (₹{cost_per_sqft:,.0f}/Sq.Ft)\n"
            f"✅ _Generated in 60s via Auto-BOQ (Meta SAM 3.1 + Muse Spark)_"
        )
        st.code(quote_text, language="text")