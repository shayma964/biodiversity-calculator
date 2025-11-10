# -*- coding: utf-8 -*-
"""
Created on Tue Nov  4 17:10:41 2025

@author: Test
"""

# main.py
# Unified Biodiversity app: Loss + Gain + Saved Results (no map generation)
# Place in biodiversity_app/ next to data/ and logos/ and run: python main.py

import os
import sys
import shutil
import csv
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk

import pandas as pd
import geopandas as gpd
import numpy as np
from shapely.validation import make_valid
from shapely.geometry import Polygon, mapping
import ezdxf

# -------------------- Configuration & Paths --------------------
def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent

BASE_DIR = get_base_dir()
DATA_DIR = BASE_DIR / "data"
LOGOS_DIR = BASE_DIR / "logos"

HABITATS_CSV = DATA_DIR / "all_habitats.csv"
YEARS_CSV = DATA_DIR / "target_year.csv"

# Use the more professional tint you preferred
MAIN_BG = "#f0f0f0"   # change to '#f5f5f5' if you prefer neutral gray

# Mappings
CONDITION_MAPPING = {"Good": 3.0, "Fairly Good": 2.5, "Moderate": 2.0, "Fairly poor": 1.5, "Poor": 1.0}
DIFFICULTY_MAPPING = {"Very high": 0.1, "High": 0.33, "Medium": 0.67, "Low": 1.0}
SPATIAL_MAPPING = {"On-site": 1.0, "Within same city": 0.75, "Somewhere further": 0.5}
STRATEGIC_MAPPING = {"High": 1.15, "Low": 1.0}
DISTINCTIVENESS_MAP = {"V.High": 8, "High": 6, "Medium": 4, "Low": 2, "V.Low": 0}

# -------------------- Logo Manager --------------------
class LogoManager:
    def __init__(self, logos_dir: Path):
        self.logos_dir = logos_dir
        self.cache = {}

    def load(self, name: str, max_w=160, max_h=80):
        if name in self.cache:
            return self.cache[name]
        exts = [".png", ".jpg", ".jpeg", ".gif", ".ico"]
        for e in exts:
            p = self.logos_dir / f"{name}{e}"
            if p.exists():
                try:
                    img = Image.open(p)
                    img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    self.cache[name] = photo
                    return photo
                except Exception as exc:
                    print(f"Error loading logo {p}: {exc}")
        self.cache[name] = None
        return None

# -------------------- Geospatial helpers (robust) --------------------
def force_polygon(geom):
    if geom is None or geom.is_empty:
        return None
    try:
        if geom.type in ["Polygon", "MultiPolygon"]:
            return geom
        if geom.type == "LineString":
            coords = list(geom.coords)
            if len(coords) >= 3:
                if coords[0] != coords[-1]:
                    coords.append(coords[0])
                if len(coords) >= 4:
                    poly = Polygon(coords)
                    if poly.is_valid:
                        return poly
        if geom.type == "MultiLineString":
            polys = []
            for line in geom.geoms:
                if line.type == "LineString":
                    coords = list(line.coords)
                    if len(coords) >= 3:
                        if coords[0] != coords[-1]:
                            coords.append(coords[0])
                        if len(coords) >= 4:
                            poly = Polygon(coords)
                            if poly.is_valid:
                                polys.append(poly)
            if polys:
                from shapely.geometry import MultiPolygon
                mp = MultiPolygon(polys)
                if mp.is_valid:
                    return mp
    except Exception as e:
        print(f"Warning force_polygon: {e}")
    return geom

def load_and_fix(path):
    """Load with geopandas and attempt to clean geometries robustly"""
    gdf = gpd.read_file(path)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
    if gdf.empty:
        raise RuntimeError("No valid geometries found")
    try:
        gdf["geometry"] = gdf.geometry.buffer(0)
    except Exception:
        pass
    try:
        gdf["geometry"] = gdf.geometry.apply(make_valid)
    except Exception:
        pass
    try:
        gdf["geometry"] = gdf.geometry.apply(force_polygon)
    except Exception:
        pass
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
    if gdf.empty:
        raise RuntimeError("All geometries invalid after cleaning")
    return gdf

def convert_dxf_layers(input_path, output_shp):
    """Convert DXF to Shapefile using ezdxf (polylines -> polygons)."""
    try:
        doc = ezdxf.readfile(input_path)
        all_geometries = []
        for entity in doc.modelspace():
            if not hasattr(entity, "dxftype"):
                continue
            if entity.dxftype() in ["LWPOLYLINE", "POLYLINE"]:
                points = []
                if entity.dxftype() == "LWPOLYLINE":
                    pts = list(entity.get_points())
                    points = [(p[0], p[1]) for p in pts]
                else:
                    for v in entity.vertices:
                        points.append((v.dxf.location.x, v.dxf.location.y))
                if len(points) >= 3:
                    if points[0] != points[-1]:
                        points.append(points[0])
                    poly = Polygon(points)
                    if poly.is_valid:
                        all_geometries.append(poly)
        if not all_geometries:
            raise RuntimeError("No valid polyline geometries found in DXF")
        # create geodataframe and save
        gdf = gpd.GeoDataFrame(geometry=all_geometries)
        # leave CRS unset - user must ensure consistent CRS for accurate areas
        gdf.to_file(output_shp)
        return output_shp
    except Exception as e:
        print(f"DXF conversion failed: {e}")
        raise RuntimeError(f"DXF conversion failed: {e}")

def convert_if_needed(input_path, is_baseline=False):
    ext = os.path.splitext(input_path)[1].lower()
    if is_baseline:
        if ext in (".shp", ".gpkg"):
            return input_path
        raise RuntimeError("Baseline must be .shp or .gpkg")
    else:
        if ext == ".dxf":
            out = os.path.splitext(input_path)[0] + "_conv.shp"
            return convert_dxf_layers(input_path, out)
        if ext == ".shp":
            return input_path
        raise RuntimeError("Planned development must be .shp or .dxf")

# -------------------- App Class --------------------
class BiodiversityApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Biodiversity Tool")
        self.root.geometry("1100x760")
        self.root.configure(bg=MAIN_BG)

        # icon (try logos/biodiversity.ico inside logos folder or base dir)
        ico_try = LOGOS_DIR / "biodiversity.ico"
        try:
            if ico_try.exists():
                self.root.iconbitmap(str(ico_try))
            else:
                alt = BASE_DIR / "biodiversity.ico"
                if alt.exists():
                    self.root.iconbitmap(str(alt))
        except Exception:
            pass

        self.logo_manager = LogoManager(LOGOS_DIR)

        # load CSVs for gain calculator
        self.habitats_df = self._load_habitats()
        self.years_df = self._load_years()

        # saved results list
        self.saved_rows = []

        # build UI
        self._build_ui()

    def _load_habitats(self):
        if HABITATS_CSV.exists():
            try:
                df = pd.read_csv(HABITATS_CSV, dtype=str).fillna("")
                # Validate expected headers
                if "Specific Habitat" not in df.columns or "Broad Habitat Type" not in df.columns:
                    print("habitats.csv missing expected headers, using fallback sample")
                    raise Exception("missing headers")
                if "Distinctiveness Category" not in df.columns:
                    df["Distinctiveness Category"] = ""
                df["Distinctiveness Score"] = df["Distinctiveness Category"].map(DISTINCTIVENESS_MAP).fillna(0).astype(float)
                return df
            except Exception as e:
                print("Reading habitats failed:", e)
        # fallback
        sample = pd.DataFrame([
            {"Broad Habitat Type": "Grassland", "Specific Habitat": "Improved grassland", "Distinctiveness Category": "Medium"},
            {"Broad Habitat Type": "Woodland", "Specific Habitat": "Broadleaved woodland", "Distinctiveness Category": "High"},
        ])
        sample["Distinctiveness Score"] = sample["Distinctiveness Category"].map(DISTINCTIVENESS_MAP).fillna(0).astype(float)
        return sample

    def _load_years(self):
        if YEARS_CSV.exists():
            try:
                df = pd.read_csv(YEARS_CSV, dtype=str).fillna("")
                if "Multiplier" in df.columns:
                    df["Multiplier"] = pd.to_numeric(df["Multiplier"], errors="coerce").fillna(1.0)
                else:
                    df["Multiplier"] = 1.0
                return df
            except Exception as e:
                print("Reading years failed:", e)
        return pd.DataFrame([{"Years": "5", "Multiplier": 1.05}, {"Years": "10", "Multiplier": 1.0}])

    def _build_ui(self):
        # Notebook and tabs
        style = ttk.Style()
        style.theme_use("default")
        style.configure("TNotebook", background=MAIN_BG)
        style.configure("TFrame", background=MAIN_BG)
        style.configure("Card.TFrame", background=MAIN_BG)
        style.configure("TLabel", background=MAIN_BG)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(8, 6))

        self.tab_loss = ttk.Frame(self.notebook)
        self.tab_gain = ttk.Frame(self.notebook)
        self.tab_saved = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_loss, text="🏞️ Loss Calculator")
        self.notebook.add(self.tab_gain, text="📈 Gain Calculator")
        self.notebook.add(self.tab_saved, text="📋 Saved Results")

        # Build each tab
        self._build_loss_tab()
        self._build_gain_tab()
        self._build_saved_tab()

        # Footer logos (bottom left & right)
        bottom = tk.Frame(self.root, bg=MAIN_BG)
        bottom.pack(side="bottom", fill="x", pady=6)

        left_logo = self.logo_manager.load("university", max_w=140, max_h=70)
        right_logo = self.logo_manager.load("office", max_w=140, max_h=70)
        if left_logo:
            lbl = tk.Label(bottom, image=left_logo, bg=MAIN_BG)
            lbl.image = left_logo
            lbl.pack(side="left", padx=12, pady=4)
        else:
            ttk.Label(bottom, text="University", background=MAIN_BG).pack(side="left", padx=12, pady=8)
        if right_logo:
            lbl2 = tk.Label(bottom, image=right_logo, bg=MAIN_BG)
            lbl2.image = right_logo
            lbl2.pack(side="right", padx=12, pady=4)
        else:
            ttk.Label(bottom, text="Office", background=MAIN_BG).pack(side="right", padx=12, pady=8)

    # ---------------- Loss Tab ----------------
    def _build_loss_tab(self):
        main = ttk.Frame(self.tab_loss)
        main.pack(fill="both", expand=True, padx=16, pady=12)

        # File selection card
        card = ttk.Frame(main, style="Card.TFrame", padding=12)
        card.pack(fill="x", padx=6, pady=6)

        ttk.Label(card, text="File Selection", font=("Segoe UI", 12, "bold"), background=MAIN_BG).pack(anchor="w", pady=(0,8))

        # Baseline
        baseline_frame = ttk.Frame(card)
        baseline_frame.pack(fill="x", pady=4)
        ttk.Label(baseline_frame, text="Baseline Habitat File:").pack(side="left", padx=(0,12))
        self.loss_baseline_path = tk.StringVar()
        ttk.Entry(baseline_frame, textvariable=self.loss_baseline_path, width=60).pack(side="left", padx=(0,8))
        ttk.Button(baseline_frame, text="Browse", command=lambda: self._browse_file(self.loss_baseline_path, [("Shapefiles", "*.shp"), ("GeoPackage", "*.gpkg")])).pack(side="left")

        # Planned
        planned_frame = ttk.Frame(card)
        planned_frame.pack(fill="x", pady=4)
        ttk.Label(planned_frame, text="Planned Development File:").pack(side="left", padx=(0,12))
        self.loss_planned_path = tk.StringVar()
        ttk.Entry(planned_frame, textvariable=self.loss_planned_path, width=60).pack(side="left", padx=(0,8))
        ttk.Button(planned_frame, text="Browse", command=lambda: self._browse_file(self.loss_planned_path, [("Shapefiles", "*.shp"), ("DXF Files", "*.dxf")])).pack(side="left")

        # Significance
        sig_frame = ttk.Frame(card)
        sig_frame.pack(fill="x", pady=4)
        ttk.Label(sig_frame, text="Strategic Significance:").pack(side="left", padx=(0,12))
        self.loss_significance = tk.StringVar(value="1.0")
        ttk.Entry(sig_frame, textvariable=self.loss_significance, width=12).pack(side="left", padx=(0,8))
        ttk.Label(sig_frame, text="(1.0 = Low, 1.15 = High)").pack(side="left")

        # Process button
        ttk.Button(card, text="Calculate Biodiversity Loss", command=self._process_and_export_loss).pack(pady=10)

        # Results card
        results_card = ttk.Frame(main, style="Card.TFrame", padding=12)
        results_card.pack(fill="both", expand=True, padx=6, pady=6)
        ttk.Label(results_card, text="Results", font=("Segoe UI", 12, "bold"), background=MAIN_BG).pack(anchor="w", pady=(0,8))
        self.loss_results_text = tk.Text(results_card, height=14, wrap="word")
        self.loss_results_text.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(results_card, orient="vertical", command=self.loss_results_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.loss_results_text.configure(yscrollcommand=scrollbar.set)

    def _browse_file(self, var: tk.StringVar, filetypes):
        fn = filedialog.askopenfilename(filetypes=filetypes)
        if fn:
            var.set(fn)

    def _process_and_export_loss(self):
        base = self.loss_baseline_path.get().strip()
        plan = self.loss_planned_path.get().strip()
        sig = self.loss_significance.get().strip()
        if not base or not plan:
            messagebox.showerror("Missing files", "Please select both baseline and planned development files.")
            return
        try:
            sig_val = float(sig) if sig else 1.0
        except Exception:
            messagebox.showerror("Invalid significance", "Strategic significance must be numeric.")
            return

        try:
            shp1 = convert_if_needed(base, is_baseline=True)
            shp2 = convert_if_needed(plan, is_baseline=False)
            gdf1 = load_and_fix(shp1)
            gdf2 = load_and_fix(shp2)

            # CRS handling (clean, explicit)
            if gdf1.crs is None:
                # Warn user but continue
                messagebox.showwarning(
                    "CRS missing",
                    "Baseline layer has no CRS. Proceeding, but areas may be wrong; ensure your layers use a projected CRS."
                )

            if gdf2.crs is None and gdf1.crs is not None:
                # Assign baseline CRS to second layer
                gdf2 = gdf2.set_crs(gdf1.crs, allow_override=True)

            if gdf1.crs is not None and gdf1.crs != gdf2.crs:
                # Reproject planned layer to baseline CRS
                gdf2 = gdf2.to_crs(gdf1.crs)

            # Keep polygon geometries only
            gdf1 = gdf1[gdf1.geometry.type.isin(["Polygon", "MultiPolygon"])]
            gdf2 = gdf2[gdf2.geometry.type.isin(["Polygon", "MultiPolygon"])]

            if gdf1.empty:
                messagebox.showerror("Error", "Baseline contains no polygons after cleaning.")
                return
            if gdf2.empty:
                messagebox.showerror("Error", "Planned development contains no polygons after cleaning.")
                return

            # Calculate areas
            gdf1["area_m2"] = gdf1.geometry.area
            total_baseline_ha = gdf1["area_m2"].sum() / 10000.0

            # Mapping functions (flexible)
            def flexible_condition_map(val):
                if pd.isna(val): return np.nan
                s = str(val).strip().lower()
                if "good" == s or "good" in s and "fairly" not in s: return 3.0
                if "fairly good" in s or "2.5" in s: return 2.5
                if "moderate" in s: return 2.0
                if "fairly poor" in s or "fairly" in s and "poor" in s: return 1.5
                if "poor" in s and "fairly" not in s: return 1.0
                return np.nan

            def flexible_distinct_map(val):
                if pd.isna(val): return np.nan
                s = str(val).strip().lower()
                if "v.high" in s or "very high" in s or "8" in s: return 8
                if "high" in s and "very" not in s: return 6
                if "medium" in s: return 4
                if "low" in s and "very" not in s: return 2
                if "v.low" in s or "very low" in s: return 0
                return np.nan

            # Create required columns and map
            gdf1["Condition score"] = gdf1.get("Baseline Condition", pd.Series([np.nan]*len(gdf1))).apply(flexible_condition_map)
            gdf1["Distinctiveness score"] = gdf1.get("Baseline Distinctiveness", pd.Series([np.nan]*len(gdf1))).apply(flexible_distinct_map)
            gdf1["Significance score"] = sig_val

            # Filter out Urban if present
            if "Baseline Broad Habitat Type" in gdf1.columns:
                gdf1 = gdf1[gdf1["Baseline Broad Habitat Type"].astype(str).str.lower() != "urban"]

            # Check mapping success
            nan_cond = int(gdf1["Condition score"].isna().sum())
            nan_dist = int(gdf1["Distinctiveness score"].isna().sum())
            if nan_cond > 0 or nan_dist > 0:
                messagebox.showwarning("Mapping issues",
                    f"Some values couldn't be mapped:\nCondition unmapped: {nan_cond}\nDistinctiveness unmapped: {nan_dist}\nCheck console for details.")

            # intersection
            intersection = gpd.overlay(gdf1, gdf2, how="intersection", keep_geom_type=True)
            intersection = intersection[intersection.geometry.type.isin(["Polygon", "MultiPolygon"])]
            if intersection.empty:
                messagebox.showerror("No overlap", "No overlap between baseline and planned development after cleaning.")
                return

            intersection["Loss area (ha)"] = (intersection.geometry.area / 10000.0).round(4)
            intersection["Biodiversity units"] = (
                intersection["Loss area (ha)"] *
                intersection.get("Condition score", 0).fillna(0) *
                intersection.get("Significance score", sig_val).fillna(sig_val) *
                intersection.get("Distinctiveness score", 0).fillna(0)
            ).round(4)

            total_loss_ha = float(intersection["Loss area (ha)"].sum())
            total_biodiv = float(intersection["Biodiversity units"].sum())

            # show summary
            lines = [
                f"Baseline total area (ha): {total_baseline_ha:,.3f}",
                f"Total overlap / loss area (ha): {total_loss_ha:,.3f}",
                f"Total biodiversity units (loss): {total_biodiv:,.3f}",
                "",
                "Top 10 loss features (Loss area, Biodiversity units):",
                intersection[["Loss area (ha)", "Biodiversity units"]].head(10).to_string(index=False)
            ]
            self.loss_results_text.delete("1.0", "end")
            self.loss_results_text.insert("end", "\n".join(lines))

            # Ask to save shapefile and CSV
            if messagebox.askyesno("Save results", "Save intersection shapefile and CSV of results?"):
                # Shapefile
                shp_path = filedialog.asksaveasfilename(defaultextension=".shp", filetypes=[("Shapefile", "*.shp")],
                                                        title="Intersection shapefile (choose .shp filename)")
                if shp_path:
                    try:
                        intersection.to_file(shp_path)
                        messagebox.showinfo("Saved", f"Intersection shapefile saved to: {shp_path}")
                    except Exception as e:
                        messagebox.showerror("Save error", f"Failed to save shapefile: {e}")

                # CSV
                csv_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")],
                                                        title="CSV of loss results")
                if csv_path:
                    try:
                        cols = ["Loss area (ha)", "Condition score", "Distinctiveness score", "Significance score", "Biodiversity units"]
                        intersection[cols].to_csv(csv_path, index=False)
                        messagebox.showinfo("Saved", f"CSV saved to: {csv_path}")
                    except Exception as e:
                        messagebox.showerror("Save error", f"Failed to save CSV: {e}")

        except Exception as ex:
            messagebox.showerror("Processing Error", f"An unexpected error occurred:\n{str(ex)}")

    # ---------------- Gain Tab ----------------
    def _build_gain_tab(self):
        card = ttk.Frame(self.tab_gain, padding=12, relief="raised")
        card.pack(fill="both", expand=True, padx=10, pady=8)

        frm = ttk.Frame(card)
        frm.pack(fill="both", expand=True)

        # column headers
        ttk.Label(frm, text="Parameter", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, padx=8, pady=6, sticky="w")
        ttk.Label(frm, text="Explanation", font=("Segoe UI", 10, "bold")).grid(row=0, column=1, padx=8, pady=6, sticky="w")
        ttk.Label(frm, text="Selection", font=("Segoe UI", 10, "bold")).grid(row=0, column=2, padx=8, pady=6, sticky="w")
        ttk.Label(frm, text="Multiplier / Score", font=("Segoe UI", 10, "bold")).grid(row=0, column=3, padx=8, pady=6, sticky="w")

        # variables
        self.var_broad = tk.StringVar()
        self.var_specific = tk.StringVar()
        self.var_year = tk.StringVar()
        self.var_condition = tk.StringVar()
        self.var_difficulty = tk.StringVar()
        self.var_spatial = tk.StringVar()
        self.var_strategic = tk.StringVar()
        self.var_area = tk.StringVar()

        r = 1
        def add_row(label_text, explanation_text, widget):
            nonlocal r
            ttk.Label(frm, text=label_text).grid(row=r, column=0, sticky="w", padx=8, pady=(6,2))
            ttk.Label(frm, text=explanation_text, font=("Segoe UI", 9, "italic"), foreground="#444").grid(row=r, column=1, sticky="w", padx=8, pady=(6,2))
            widget.grid(row=r, column=2, sticky="w", padx=8, pady=(6,2))
            this_row = r
            r += 1
            return this_row

        # Broad
        broad_vals = sorted(self.habitats_df["Broad Habitat Type"].unique().tolist())
        cb_broad = ttk.Combobox(frm, textvariable=self.var_broad, values=broad_vals, state="readonly", width=44)
        row_b = add_row("Broad Habitat Type:", "General habitat classification.", cb_broad)

        # Specific
        cb_specific = ttk.Combobox(frm, textvariable=self.var_specific, values=[], state="readonly", width=44)
        row_s = add_row("Specific Habitat:", "Detailed habitat type (filtered by broad type).", cb_specific)

        # Year
        year_vals = [str(x) for x in self.years_df["Years"].tolist()]
        cb_year = ttk.Combobox(frm, textvariable=self.var_year, values=year_vals, state="readonly", width=20)
        row_y = add_row("Time to target (years):", "How long until habitat reaches target ecological value.", cb_year)

        # Condition
        cb_condition = ttk.Combobox(frm, textvariable=self.var_condition, values=list(CONDITION_MAPPING.keys()), state="readonly", width=28)
        row_c = add_row("Baseline condition:", "State of habitat vs other sites (use Fairly Good–Fairly Poor).", cb_condition)

        # Difficulty
        cb_difficulty = ttk.Combobox(frm, textvariable=self.var_difficulty, values=list(DIFFICULTY_MAPPING.keys()), state="readonly", width=28)
        row_d = add_row("Difficulty category:", "Uncertainty in effectiveness of compensation techniques.", cb_difficulty)

        # Spatial
        cb_spatial = ttk.Combobox(frm, textvariable=self.var_spatial, values=list(SPATIAL_MAPPING.keys()), state="readonly", width=28)
        row_sp = add_row("Spatial risk category:", "Location risk for habitat creation (closer is better).", cb_spatial)

        # Strategic
        cb_strat = ttk.Combobox(frm, textvariable=self.var_strategic, values=list(STRATEGIC_MAPPING.keys()), state="readonly", width=28)
        row_st = add_row("Strategic significance:", "High = matches mapped plan; Low = different location or habitat type.", cb_strat)

        # Area
        ent_area = ttk.Entry(frm, textvariable=self.var_area, width=18)
        row_a = add_row("Area (ha):", "Enter parcel area in hectares (e.g., 2.5).", ent_area)

        # multiplier labels in column 3 aligned with rows
        self.lbl_distinct = ttk.Label(frm, text="Distinctiveness: -")
        self.lbl_distinct.grid(row=row_s, column=3, sticky="w", padx=6)
        self.lbl_yearmult = ttk.Label(frm, text="Year multiplier: -")
        self.lbl_yearmult.grid(row=row_y, column=3, sticky="w", padx=6)
        self.lbl_cond = ttk.Label(frm, text="Condition score: -")
        self.lbl_cond.grid(row=row_c, column=3, sticky="w", padx=6)
        self.lbl_diff = ttk.Label(frm, text="Difficulty multiplier: -")
        self.lbl_diff.grid(row=row_d, column=3, sticky="w", padx=6)
        self.lbl_spat = ttk.Label(frm, text="Spatial multiplier: -")
        self.lbl_spat.grid(row=row_sp, column=3, sticky="w", padx=6)
        self.lbl_strat = ttk.Label(frm, text="Strategic multiplier: -")
        self.lbl_strat.grid(row=row_st, column=3, sticky="w", padx=6)
        self.lbl_area = ttk.Label(frm, text="Area: -")
        self.lbl_area.grid(row=row_a, column=3, sticky="w", padx=6)

        # Buttons and result
        btn_frame = ttk.Frame(card)
        btn_frame.pack(fill="x", pady=10)
        ttk.Button(btn_frame, text="Calculate", command=self._calculate_gain).pack(side="left", padx=8)
        ttk.Button(btn_frame, text="Save selection (CSV & saved results)", command=self._save_gain_selection).pack(side="left", padx=8)
        self.gain_result = ttk.Label(card, text="Biodiversity Units: -", font=("Segoe UI", 12, "bold"))
        self.gain_result.pack(anchor="w", pady=(6,0), padx=6)

        # Binds
        cb_broad.bind("<<ComboboxSelected>>", lambda e: self._on_broad_change(cb_specific))
        cb_specific.bind("<<ComboboxSelected>>", lambda e: self._on_specific_change())
        cb_year.bind("<<ComboboxSelected>>", lambda e: self._on_year_change())
        cb_condition.bind("<<ComboboxSelected>>", lambda e: self._on_condition_change())
        cb_difficulty.bind("<<ComboboxSelected>>", lambda e: self._on_difficulty_change())
        cb_spatial.bind("<<ComboboxSelected>>", lambda e: self._on_spatial_change())
        cb_strat.bind("<<ComboboxSelected>>", lambda e: self._on_strategic_change())

    def _on_broad_change(self, cb_specific):
        b = self.var_broad.get()
        specifics = self.habitats_df[self.habitats_df["Broad Habitat Type"] == b]["Specific Habitat"].dropna().unique().tolist()
        cb_specific["values"] = specifics
        self.var_specific.set("")
        self.lbl_distinct.config(text="Distinctiveness: -")
        self.gain_result.config(text="Biodiversity Units: -")

    def _on_specific_change(self):
        s = self.var_specific.get()
        row = self.habitats_df[self.habitats_df["Specific Habitat"] == s]
        if not row.empty:
            score = float(row.iloc[0].get("Distinctiveness Score", 0.0))
            self.lbl_distinct.config(text=f"Distinctiveness: {score}")
        else:
            self.lbl_distinct.config(text="Distinctiveness: -")
        self.gain_result.config(text="Biodiversity Units: -")

    def _on_year_change(self):
        y = self.var_year.get()
        row = self.years_df[self.years_df["Years"].astype(str) == str(y)]
        if not row.empty:
            mult = float(row.iloc[0]["Multiplier"])
            self.lbl_yearmult.config(text=f"Year multiplier: {mult}")
        else:
            self.lbl_yearmult.config(text="Year multiplier: -")
        self.gain_result.config(text="Biodiversity Units: -")

    def _on_condition_change(self):
        v = CONDITION_MAPPING.get(self.var_condition.get(), "-")
        self.lbl_cond.config(text=f"Condition score: {v}")
        self.gain_result.config(text="Biodiversity Units: -")

    def _on_difficulty_change(self):
        v = DIFFICULTY_MAPPING.get(self.var_difficulty.get(), "-")
        self.lbl_diff.config(text=f"Difficulty multiplier: {v}")
        self.gain_result.config(text="Biodiversity Units: -")

    def _on_spatial_change(self):
        v = SPATIAL_MAPPING.get(self.var_spatial.get(), "-")
        self.lbl_spat.config(text=f"Spatial multiplier: {v}")
        self.gain_result.config(text="Biodiversity Units: -")

    def _on_strategic_change(self):
        v = STRATEGIC_MAPPING.get(self.var_strategic.get(), "-")
        self.lbl_strat.config(text=f"Strategic multiplier: {v}")
        self.gain_result.config(text="Biodiversity Units: -")

    def _calculate_gain(self):
        missing = []
        if not self.var_broad.get(): missing.append("Broad habitat")
        if not self.var_specific.get(): missing.append("Specific habitat")
        if not self.var_year.get(): missing.append("Target year")
        if not self.var_condition.get(): missing.append("Condition")
        if not self.var_difficulty.get(): missing.append("Difficulty")
        if not self.var_spatial.get(): missing.append("Spatial risk")
        if not self.var_strategic.get(): missing.append("Strategic significance")
        try:
            area = float(self.var_area.get())
            if area <= 0:
                missing.append("Area (positive number)")
        except Exception:
            missing.append("Area (positive number)")
        if missing:
            messagebox.showwarning("Missing fields", "Please complete: " + ", ".join(missing))
            return
        # numeric values
        distinct = 0.0
        row = self.habitats_df[self.habitats_df["Specific Habitat"] == self.var_specific.get()]
        if not row.empty:
            distinct = float(row.iloc[0].get("Distinctiveness Score", 0.0))
        year_mult = 1.0
        rowy = self.years_df[self.years_df["Years"].astype(str) == str(self.var_year.get())]
        if not rowy.empty:
            year_mult = float(rowy.iloc[0]["Multiplier"])
        cond = float(CONDITION_MAPPING.get(self.var_condition.get(), 0.0))
        diff = float(DIFFICULTY_MAPPING.get(self.var_difficulty.get(), 0.0))
        spat = float(SPATIAL_MAPPING.get(self.var_spatial.get(), 0.0))
        strat = float(STRATEGIC_MAPPING.get(self.var_strategic.get(), 0.0))
        area = float(self.var_area.get())
        units = distinct * cond * strat * area * spat * diff * year_mult
        self.gain_result.config(text=f"Biodiversity Units: {units:.3f}")

    def _save_gain_selection(self):
        self._calculate_gain()
        txt = self.gain_result.cget("text")
        if "Biodiversity Units:" not in txt:
            messagebox.showerror("No result", "Calculate before saving.")
            return
        units = txt.split(":")[1].strip()
        row = {
            "Timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "Broad Habitat": self.var_broad.get(),
            "Specific Habitat": self.var_specific.get(),
            "Distinctiveness": self.lbl_distinct.cget("text").split(":")[1].strip(),
            "Years": self.var_year.get(),
            "Year Multiplier": self.lbl_yearmult.cget("text").split(":")[1].strip(),
            "Condition": self.var_condition.get(),
            "Condition Score": self.lbl_cond.cget("text").split(":")[1].strip(),
            "Difficulty": self.var_difficulty.get(),
            "Difficulty Score": self.lbl_diff.cget("text").split(":")[1].strip(),
            "Spatial Risk": self.var_spatial.get(),
            "Spatial Multiplier": self.lbl_spat.cget("text").split(":")[1].strip(),
            "Strategic Significance": self.var_strategic.get(),
            "Strategic Multiplier": self.lbl_strat.cget("text").split(":")[1].strip(),
            "Area (ha)": self.var_area.get(),
            "Biodiversity Units": units
        }
        # default timestamped filename in app folder
        default_name = f"gain_selection_{time.strftime('%Y%m%d_%H%M%S')}.csv"
        default_path = BASE_DIR / default_name
        savepath = filedialog.asksaveasfilename(initialfile=default_name, defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not savepath:
            # if user cancelled, still write default inside app folder (asked earlier you wanted automatic timestamped save)
            try:
                with open(default_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=list(row.keys()))
                    writer.writeheader()
                    writer.writerow(row)
                messagebox.showinfo("Saved", f"No path chosen — saved to default: {default_path}")
            except Exception as e:
                messagebox.showerror("Save error", f"Failed to save CSV: {e}")
                return
        else:
            try:
                with open(savepath, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=list(row.keys()))
                    writer.writeheader()
                    writer.writerow(row)
                messagebox.showinfo("Saved", f"Selection saved to: {savepath}")
            except Exception as e:
                messagebox.showerror("Save error", f"Failed to save CSV: {e}")
                return
        # also add to saved rows and refresh
        self.saved_rows.append(row)
        self._refresh_saved_table()

    # ---------------- Saved Results ----------------
    def _build_saved_tab(self):
        card = ttk.Frame(self.tab_saved, padding=12)
        card.pack(fill="both", expand=True, padx=10, pady=8)
        cols = ["Timestamp", "Broad Habitat", "Specific Habitat", "Area (ha)", "Biodiversity Units"]
        self.saved_tree = ttk.Treeview(card, columns=cols, show="headings", height=14)
        for c in cols:
            self.saved_tree.heading(c, text=c)
            self.saved_tree.column(c, width=160, anchor="w")
        self.saved_tree.pack(fill="both", expand=True)
        btns = ttk.Frame(card)
        btns.pack(fill="x", pady=6)
        ttk.Button(btns, text="Export All to CSV", command=self._export_saved_all).pack(side="left", padx=6)
        ttk.Button(btns, text="Clear Saved Rows", command=self._clear_saved).pack(side="left", padx=6)

    def _refresh_saved_table(self):
        for i in self.saved_tree.get_children():
            self.saved_tree.delete(i)
        for row in self.saved_rows:
            self.saved_tree.insert("", "end", values=(row.get("Timestamp"), row.get("Broad Habitat"), row.get("Specific Habitat"), row.get("Area (ha)"), row.get("Biodiversity Units")))

    def _export_saved_all(self):
        if not self.saved_rows:
            messagebox.showinfo("No data", "No saved rows to export.")
            return
        p = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not p:
            return
        try:
            keys = list(self.saved_rows[0].keys())
            with open(p, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                for r in self.saved_rows:
                    writer.writerow(r)
            messagebox.showinfo("Exported", f"Saved results exported to {p}")
        except Exception as e:
            messagebox.showerror("Export error", f"Failed to export: {e}")

    def _clear_saved(self):
        if messagebox.askyesno("Confirm", "Clear all saved rows?"):
            self.saved_rows = []
            self._refresh_saved_table()

# -------------------- Run --------------------
def main():
    root = tk.Tk()
    root.configure(bg=MAIN_BG)
    # attempt set icon from logos
    try:
        ico_path = LOGOS_DIR / "biodiversity.ico"
        if ico_path.exists():
            root.iconbitmap(str(ico_path))
        else:
            alt = BASE_DIR / "biodiversity.ico"
            if alt.exists():
                root.iconbitmap(str(alt))
    except Exception:
        pass
    app = BiodiversityApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
