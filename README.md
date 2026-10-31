# Auto-BOQ: Zero-Shot Architectural Blueprint to Construction Cost Engine

## 1. One-Line Pitch & Problem Statement

**Auto-BOQ** turns a raw 2D blueprint into a fully-costed Bill of Quantities in seconds—no manual measuring, no spreadsheets, no guesswork.

Today, contractors and interior designers spend **8–15 hours manually measuring 2D PDFs/images** to quote a single project, only for **70% of leads to ghost**. Auto-BOQ collapses that 8–15 hour grind into a **zero-shot pipeline** that segments the plan, calibrates real-world scale, separates Carpet Area from Modular RFT, and visualizes the result—so teams quote faster, win more, and stop wasting hours on dead leads.

---

## 2. How We Chain 4 Meta AI Tools (25% Tooling Rubric)

| Tool | Role in the Pipeline |
|------|----------------------|
| **`SAM 3.1`** | **Zero-shot spatial segmentation** of rooms, structural walls, doors, and windows directly from 2D floor plans—no fine-tuning, no labeled training set. |
| **`Muse Spark 1.3 (Meta Model API)`** | **OCR dimension scale calibration** (reads printed measurements + scale bars) and **geometric separation** of *Carpet Area (Sq.Ft)* vs. *Modular Kitchen/Wardrobe Running Feet (RFT)*. |
| **`Muse Image 1.0`** | **Instant photorealistic room concept visualization**, matched to the selected budget tier (**Economy / Standard / Luxury**) so clients see what they're paying for. |
| **`Muse Code CLI`** | **Architected, refactored, and orchestrated** the multi-module Python pipeline: `boq_math.py`, `meta_client.py`, `exporter.py`, `app.py`. |

---

## 3. System Architecture & Mathematical Formulas

```
Blueprint (PDF/Image)
        │
        ▼
┌────────────────────┐
│  SAM 3.1           │  → room / wall / door / window masks
└────────────────────┘
        │
        ▼
┌────────────────────┐
│  Muse Spark 1.3    │  → OCR scale calibration + area/RFT separation
└────────────────────┘
        │
        ▼
┌────────────────────┐
│  boq_math.py       │  → Shoelace area, RFT derivation, cost rollup
└────────────────────┘
        │
        ├──────────────► Muse Image 1.0  (budget-tier concept render)
        ▼
┌────────────────────┐
│  exporter.py       │  → BOQ (CSV/XLSX/PDF)
└────────────────────┘
        │
        ▼
   app.py (Streamlit UI)
```

### Pixel-to-Sq.Ft Calibration (Shoelace Formula)

Given a segmented room polygon with vertices $(x_i, y_i)$ in **pixel space**, the signed area is:

$$
A_{\text{px}} = \frac{1}{2}\left|\sum_{i=1}^{n}\left(x_i\,y_{i+1} - x_{i+1}\,y_i\right)\right|, \quad (x_{n+1}, y_{n+1}) = (x_1, y_1)
$$

Scale is recovered from the OCR'd real-world reference dimension (e.g. a labeled wall of $L_{\text{real}}$ ft spanning $L_{\text{px}}$ pixels):

$$
s = \frac{L_{\text{real}}}{L_{\text{px}}} \quad\Rightarrow\quad A_{\text{sq.ft}} = A_{\text{px}} \cdot s^2
$$

### L-Shaped Kitchen Running Feet (RFT)

An L-shaped modular kitchen is decomposed into two orthogonal legs $L_1$ and $L_2$ (measured along the wall run, in feet), with counter depth $d$ excluded from RFT. The running feet is the linear cabinet run:

$$
\text{RFT} = L_1 + L_2 - c
$$

where $c$ is the corner overlap correction (the shared corner counted once). Cost is then:

$$
\text{Cost} = \text{RFT} \times \text{Rate}_{\text{tier}} \;+\; A_{\text{carpet}} \times \text{Rate}_{\text{floor,tier}}
$$

---

## 4. Quickstart (2 Commands to Run)

```bash
python setup_assets.py
streamlit run app.py
```

> `setup_assets.py` provisions model assets and the sample blueprint set. `app.py` launches the Streamlit UI.