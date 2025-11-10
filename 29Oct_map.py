
# -*- coding: utf-8 -*-
"""
Created on Wed Oct 29 18:12:42 2025

@author: Test
"""

# main.py
# Unified Biodiversity app: Loss + Gain + Saved Results + Map Visualization

import os
import sys
import subprocess
import shutil
from pathlib import Path

# === PROJ/GDAL PATH FIX ===
if getattr(sys, 'frozen', False):
    base_path = getattr(sys, '_MEIPASS', Path(sys.executable).parent)
    proj_path = Path(base_path) / "lib" / "share" / "proj"
    os.environ["PROJ_LIB"] = str(proj_path)
    os.environ["PATH"] = str(Path(base_path) / "lib") + os.pathsep + os.environ["PATH"]

# === MATPLOTLIB CONFIGURATION ===
import matplotlib
matplotlib.use('Agg')  # CRITICAL for frozen apps

# Basic configuration for frozen apps
if getattr(sys, 'frozen', False):
    try:
        import tempfile
        temp_config = Path(tempfile.gettempdir()) / "matplotlib_config"
        temp_config.mkdir(exist_ok=True)
        os.environ['MPLCONFIGDIR'] = str(temp_config)
        print(f"✅ Using temp config: {temp_config}")
    except Exception as e:
        print(f"⚠️ Config setup failed: {e}")

# Now import the rest of your packages
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import pandas as pd
import geopandas as gpd
import numpy as np
from shapely.validation import make_valid
from shapely.geometry import Polygon
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import csv
import tempfile
import time

# ---------- CONFIG ----------
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
LOGOS_DIR = BASE_DIR / "logos"

HABITATS_CSV = DATA_DIR / "all_habitats.csv"
YEARS_CSV = DATA_DIR / "target_year.csv"

MAIN_BG = "#f0f0f0"  # chosen color

# Mappings
CONDITION_MAPPING = {"Good": 3.0, "Fairly Good": 2.5, "Moderate": 2.0, "Fairly poor": 1.5, "Poor": 1.0}
DIFFICULTY_MAPPING = {"Very high": 0.1, "High": 0.33, "Medium": 0.67, "Low": 1.0}
SPATIAL_MAPPING = {"On-site": 1.0, "Within same city": 0.75, "Somewhere further": 0.5}
STRATEGIC_MAPPING = {"High": 1.15, "Low": 1.0}
DISTINCTIVENESS_MAP = {"V.High": 8, "High": 6, "Medium": 4, "Low": 2, "V.Low": 0}

# ---------- Utility: logo manager ----------
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

# ---------- Geospatial helpers ----------
def get_ogr2ogr_path():
    """Return path to ogr2ogr depending on environment (Windows/conda)"""
    if getattr(sys, "frozen", False):
        base_dir = getattr(sys, "_MEIPASS", Path(sys.executable).parent)
        candidate = Path(base_dir) / "lib" / "ogr2ogr.exe"
        if candidate.exists():
            return str(candidate)
    # try PATH
    ogr2ogr_path = shutil.which("ogr2ogr")
    if ogr2ogr_path:
        return ogr2ogr_path
    # try conda-style location
    env_root = Path(sys.executable).parent
    candidate = env_root / "Library" / "bin" / "ogr2ogr.exe"
    if candidate.exists():
        return str(candidate)
    return None

def force_polygon(geom):
    """Convert line-like geometries to polygons where sensical"""
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
    """Load file through geopandas and attempt to clean geometries robustly."""
    gdf = gpd.read_file(path)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
    if gdf.empty:
        raise RuntimeError("No valid geometries found")
    # buffer(0) attempt
    try:
        gdf["geometry"] = gdf.geometry.buffer(0)
    except Exception:
        pass
    # make_valid
    try:
        gdf["geometry"] = gdf.geometry.apply(make_valid)
    except Exception:
        pass
    # convert lines to polygons when possible
    try:
        gdf["geometry"] = gdf.geometry.apply(force_polygon)
    except Exception:
        pass
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
    if gdf.empty:
        raise RuntimeError("All geometries invalid after cleaning")
    return gdf

def convert_dxf_layers(input_path, output_shp):
    """Convert DXF to Shapefile using direct ezdxf processing (no layer selection)"""
    try:
        import ezdxf
        import warnings
        from shapely.geometry import Polygon
        
        warnings.filterwarnings("ignore")
        
        print(f"Processing DXF file: {input_path}")
        
        # Read DXF file
        doc = ezdxf.readfile(input_path)
        all_geometries = []
        
        # Process ALL polyline entities (no layer filtering)
        for entity in doc.modelspace():
            # Skip invalid entities
            if callable(entity) or not hasattr(entity, 'dxftype'):
                continue
                
            # Process any polyline (LWPOLYLINE or POLYLINE)
            if entity.dxftype() in ['LWPOLYLINE', 'POLYLINE']:
                
                points = []
                if entity.dxftype() == 'LWPOLYLINE':
                    raw_points = list(entity.get_points())
                    points = [(p[0], p[1]) for p in raw_points]
                elif entity.dxftype() == 'POLYLINE':
                    for vertex in entity.vertices:
                        points.append((vertex.dxf.location.x, vertex.dxf.location.y))
                
                # Create polygon (ensure it's closed)
                if len(points) >= 3:
                    if points[0] != points[-1]:
                        points.append(points[0])
                    
                    polygon = Polygon(points)
                    if polygon.is_valid:
                        all_geometries.append(polygon)
                        print(f"✓ Added {entity.dxftype()} from layer '{entity.dxf.layer}' with {len(points)} points")
        
        if not all_geometries:
            raise RuntimeError("No valid polyline geometries found in DXF file")
        
        # Save to shapefile - USE EPSG:31370
        gdf = gpd.GeoDataFrame(geometry=all_geometries, crs="EPSG:31370")
        gdf.to_file(output_shp)
        
        print(f"✅ Successfully converted {len(all_geometries)} polygons to {output_shp}")
        return output_shp
        
    except Exception as e:
        print(f"❌ DXF conversion failed: {e}")
        raise RuntimeError(f"Failed to convert DXF: {e}")

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

# ---------- Map Visualization Functions ----------
def add_scale_bar(ax, gdf, location='lower left', length_km=None):
    """Add a scale bar to the map"""
    try:
        # Get the bounds of the data
        bounds = gdf.total_bounds  # [minx, miny, maxx, maxy]
        
        # Calculate appropriate scale bar length (auto-adjust based on map size)
        map_width_m = bounds[2] - bounds[0]
        if length_km is None:
            # Auto-calculate reasonable scale bar length
            if map_width_m > 5000:  # Large area
                length_km = 1.0
            elif map_width_m > 1000:  # Medium area
                length_km = 0.5
            else:  # Small area
                length_km = 0.1
        
        length_m = length_km * 1000  # Convert to meters
        
        # Set position (using relative coordinates) - LOWER LEFT for scale bar
        if location == 'lower left':
            x_rel = 0.05  # 5% from left
            y_rel = 0.08  # 8% from bottom (moved up slightly to avoid edge)
        elif location == 'lower right':
            x_rel = 0.95  # 95% from left  
            y_rel = 0.08  # 8% from bottom
        else:  # lower center
            x_rel = 0.5   # center
            y_rel = 0.08  # 8% from bottom
        
        # Convert relative to data coordinates
        x_data = bounds[0] + x_rel * map_width_m
        y_data = bounds[1] + y_rel * (bounds[3] - bounds[1])
        
        # Draw the main scale bar (thicker for better visibility)
        ax.plot([x_data, x_data + length_m], [y_data, y_data], 
               color='black', linewidth=6, solid_capstyle='butt')  # Increased linewidth
        
        # Add perpendicular ends (thicker)
        end_height = length_m * 0.15  # 15% of bar length (increased)
        ax.plot([x_data, x_data], [y_data - end_height/2, y_data + end_height/2], 
               color='black', linewidth=4)  # Thicker
        ax.plot([x_data + length_m, x_data + length_m], 
               [y_data - end_height/2, y_data + end_height/2], 
               color='black', linewidth=4)  # Thicker
        
        # Add scale text (larger font)
        if length_km >= 1:
            scale_text = f'{length_km:.0f} km'
        else:
            scale_text = f'{length_km * 1000:.0f} m'
        
        ax.text(x_data + length_m/2, y_data + end_height, scale_text,
               ha='center', va='bottom', fontsize=12, fontweight='bold',  # Increased font size
               bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.9, linewidth=1))
        
        print(f"✅ Added scale bar: {scale_text}")
        
    except Exception as e:
        print(f"⚠️ Could not add scale bar: {e}")

def add_north_arrow(ax, location='lower right', size=40):
    """Add a north arrow to the map - bigger and in lower right corner"""
    try:
        # Use relative coordinates for positioning
        if location == 'lower right':
            x = 0.93  # 93% from left (lower right)
            y = 0.08  # 8% from bottom (lower position)
        elif location == 'upper right':
            x = 0.95
            y = 0.95
        elif location == 'upper left':
            x = 0.05
            y = 0.95
        else:  # lower left
            x = 0.05
            y = 0.08
        
        # Create a larger north arrow using a triangle (more visible)
        arrow_size = size * 0.001  # Scale factor for arrow size
        
        # Draw a triangle for the north arrow
        arrow_points = [
            [x, y + arrow_size],           # Top point
            [x - arrow_size/2, y],         # Bottom left
            [x + arrow_size/2, y],         # Bottom right
            [x, y + arrow_size]            # Back to top (close triangle)
        ]
        
        arrow_patch = mpatches.Polygon(
            arrow_points,
            closed=True,
            facecolor='black',
            edgecolor='black',
            linewidth=2,
            transform=ax.transAxes
        )
        ax.add_patch(arrow_patch)
        
        # Add "N" text below the arrow (bigger and bolder)
        ax.text(x, y + arrow_size, 'N', 
               ha='center', va='top', 
               fontsize=16, fontweight='bold',  # Increased font size
               transform=ax.transAxes,
               bbox=dict(boxstyle="circle,pad=0.4", facecolor='white', edgecolor='black', linewidth=1))
        
        print("✅ Added BIG north arrow in lower right corner")
        
    except Exception as e:
        print(f"⚠️ Could not add north arrow: {e}")

def create_loss_map_as_png(baseline_gdf, intersection_gdf, output_png, preview_mode=False):
    """Create PNG map - can be used for both high-quality save and fast preview"""
    try:
        print("🔍 Starting PNG map creation...")
        
        # Clear matplotlib cache
        plt.close('all')
        import gc
        gc.collect()
        
        # Different settings for preview vs save
        if preview_mode:
            # PREVIEW SETTINGS - Fast rendering
            figsize = (14, 8)  # Smaller
            dpi = 100          # Lower quality
            fontsize = 10      # Smaller text
            linewidth = 1.0    # Thinner lines
        else:
            # SAVE SETTINGS - High quality
            figsize = (20, 12) # Larger
            dpi = 300          # Higher quality  
            fontsize = 12      # Normal text
            linewidth = 1.5    # Thicker lines
        
        fig, (ax_map, ax_table) = plt.subplots(1, 2, figsize=figsize,
                                              gridspec_kw={'width_ratios': [2, 1]})
        
        # Step 1: Define nature-inspired color palette
        nature_colors = {
            'Grassland': '#9ACD32', 'Woodland': '#228B22', 'Forest': '#006400',
            'Heathland and shrub': '#DAA520', 'Cropland': '#8B4513',
            'Wetland': '#20B2AA', 'Urban': '#A9A9A9', 'Other': '#FFD700'
        }
        
        # Step 2: Plot baseline habitats
        color_map = {}
        if 'Baseline Broad Habitat Type' in baseline_gdf.columns:
            # Get unique habitat types
            habitat_types = baseline_gdf['Baseline Broad Habitat Type'].unique()
            
            # Assign colors
            for habitat_type in habitat_types:
                clean_habitat = str(habitat_type).strip()
                if clean_habitat in nature_colors:
                    color_map[habitat_type] = nature_colors[clean_habitat]
                else:
                    color_map[habitat_type] = '#FF6B35'
            
            # Plot baseline with light colors
            for habitat_type, color in color_map.items():
                subset = baseline_gdf[baseline_gdf['Baseline Broad Habitat Type'] == habitat_type]
                subset.plot(ax=ax_map, color=color, alpha=0.3, edgecolor='gray', linewidth=0.5)
        else:
            # Fallback if no habitat type column
            baseline_gdf.plot(ax=ax_map, color='lightgray', alpha=0.5, edgecolor='gray', linewidth=0.5)
        
        # Step 3: Plot intersection/loss areas
        if 'Baseline Broad Habitat Type' in intersection_gdf.columns:
            intersection_gdf = intersection_gdf.copy()
            intersection_gdf['color'] = intersection_gdf['Baseline Broad Habitat Type'].map(color_map)
            intersection_gdf['color'] = intersection_gdf['color'].fillna('#FF6B35')
            
            intersection_gdf.plot(ax=ax_map, 
                                color=intersection_gdf['color'], 
                                alpha=0.8, 
                                edgecolor='black', 
                                linewidth=linewidth)
        else:
            intersection_gdf.plot(ax=ax_map, color='red', alpha=0.8, edgecolor='black', linewidth=linewidth)
        
        # Step 4: Create summary table
        if 'Baseline Broad Habitat Type' in intersection_gdf.columns:
            summary_data = []
            for habitat_type in intersection_gdf['Baseline Broad Habitat Type'].unique():
                habitat_data = intersection_gdf[intersection_gdf['Baseline Broad Habitat Type'] == habitat_type]
                total_area = habitat_data['Loss area (ha)'].sum()
                total_biodiversity = habitat_data['Biodiversity units'].sum()
                
                if preview_mode:
                    # Truncate long names for preview
                    display_name = habitat_type[:12] + '...' if len(habitat_type) > 12 else habitat_type
                    summary_data.append([display_name, f"{total_area:.1f}", f"{total_biodiversity:.1f}"])
                else:
                    summary_data.append([habitat_type, f"{total_area:.2f}", f"{total_biodiversity:.2f}"])
            
            # Create table
            if summary_data:
                if preview_mode:
                    col_labels = ['Habitat', 'Area', 'Loss']
                else:
                    col_labels = ['Habitat Type', 'Area (ha)', 'Biodiversity Loss']
                    
                table = ax_table.table(cellText=summary_data,
                                     colLabels=col_labels,
                                     loc='center',
                                     cellLoc='center',
                                     colColours=['#E8F5E8', '#E8F5E8', '#E8F5E8'])
                
                table.auto_set_font_size(False)
                table.set_fontsize(fontsize-2)
                table.scale(1, 1.5)
        
        # Step 5: Create legend
        if color_map:
            legend_patches = []
            items = list(color_map.items())
            if preview_mode:
                items = items[:5]  # Limit to 5 items for preview
                
            for habitat_type, color in items:
                patch = mpatches.Patch(color=color, label=habitat_type, alpha=0.8)
                legend_patches.append(patch)
            
            ax_map.legend(handles=legend_patches, 
                         title='Habitat Types',
                         loc='upper right',
                         fontsize=fontsize-2,
                         framealpha=0.9)
        
        # Step 6: Add Scale Bar and North Arrow
        try:
            add_scale_bar(ax_map, baseline_gdf)
            add_north_arrow(ax_map)
        except Exception as e:
            print(f"⚠️ Map elements failed: {e}")
        
        # Step 7: Customize map appearance
        ax_map.set_title('Biodiversity Loss Map', fontsize=fontsize+2, fontweight='bold', pad=20)
        ax_table.set_title('Loss Summary', fontsize=fontsize, fontweight='bold', pad=20)
        ax_table.axis('off')
        
        # Calculate and display totals
        total_biodiversity_loss = intersection_gdf['Biodiversity units'].sum() if 'Biodiversity units' in intersection_gdf.columns else 0
        total_area_loss = intersection_gdf['Loss area (ha)'].sum() if 'Loss area (ha)' in intersection_gdf.columns else 0
        
        stats_text = f"Total Biodiversity Loss: {total_biodiversity_loss:,.1f} units\nTotal Area Impacted: {total_area_loss:,.1f} ha"
        
        ax_map.text(0.02, 0.98, stats_text, 
                   transform=ax_map.transAxes, 
                   fontsize=fontsize, 
                   fontweight='bold',
                   verticalalignment='top',
                   bbox=dict(boxstyle="round,pad=0.5", facecolor='white', alpha=0.9))
        
        # Remove axis ticks from map
        ax_map.set_xticks([])
        ax_map.set_yticks([])
        
        # Add grid for better spatial reference
        ax_map.grid(True, alpha=0.3)
        
        # Save with appropriate quality
        plt.tight_layout()
        plt.savefig(output_png, dpi=dpi, bbox_inches='tight', 
                   facecolor='white', edgecolor='none',
                   format='png', transparent=False)
        plt.close('all')
        gc.collect()
        
        print(f"✅ PNG saved successfully (preview_mode: {preview_mode})")
        return True
        
    except Exception as e:
        print(f"💥 Map creation error: {e}")
        import traceback
        traceback.print_exc()
        plt.close('all')
        return False

def save_with_visualization(baseline_gdf, intersection_gdf, significance_score):
    """Save shapefile and CSV, plus offer PNG map as extra"""
    
    # First, save shapefile and CSV
    shp_path = filedialog.asksaveasfilename(
        title="Save intersection shapefile (choose .shp filename)", 
        defaultextension=".shp", 
        filetypes=[("Shapefile", "*.shp")]
    )
    if shp_path:
        try:
            intersection_gdf.to_file(shp_path)
            messagebox.showinfo("Saved", f"Intersection shapefile saved to: {shp_path}")
        except Exception as e:
            messagebox.showerror("Save error", f"Failed to save shapefile: {e}")

    # CSV of results
    csv_path = filedialog.asksaveasfilename(
        title="Save CSV summary", 
        defaultextension=".csv", 
        filetypes=[("CSV", "*.csv")]
    )
    if csv_path:
        try:
            out_cols = ["Loss area (ha)", "Condition score", "Distinctiveness score", "Significance score", "Biodiversity units"]
            intersection_gdf[out_cols].to_csv(csv_path, index=False)
            messagebox.showinfo("Saved", f"CSV saved to: {csv_path}")
        except Exception as e:
            messagebox.showerror("Save error", f"Failed to save CSV: {e}")
    
    # THEN offer the PNG map as an optional extra
    if messagebox.askyesno("Map Visualization", 
                         "Would you like to create a high-quality map image?"):
        
        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
        default_dir = desktop_path
        
        png_path = filedialog.asksaveasfilename(
            title="Save Biodiversity Loss Map",
            defaultextension=".png",
            filetypes=[("PNG files", "*.png"), ("All files", "*.*")],
            initialdir=default_dir
        )
        
        if png_path:
            try:
                # Use high-quality mode (preview_mode=False)
                success = create_loss_map_as_png(baseline_gdf, intersection_gdf, png_path, preview_mode=False)
                
                if success:
                    messagebox.showinfo("Success", f"High-quality map saved to:\n{png_path}")
                else:
                    messagebox.showerror("Error", "Failed to create map image")
                    
            except Exception as e:
                print(f"❌ Map creation failed: {e}")
                messagebox.showerror("Map Creation Error", f"Failed to create map:\n{str(e)}")

# ---------- UI helpers ----------
def create_modern_header(parent, colors, logo_manager):
    """Creates a clean, minimal header area without colored background."""
    header = ttk.Frame(parent)
    header.pack(fill="x", pady=(8, 2))
    
    # Simple neutral separator (modern subtle touch)
    separator = ttk.Separator(header, orient="horizontal")
    separator.pack(fill="x", pady=(0, 4))
    
    return header

def create_card(parent, pad_x=20, pad_y=10):
    card = ttk.Frame(parent, padding=12)
    card.pack(fill="both", expand=False, padx=pad_x, pady=pad_y)
    return card

# ---------- App ----------
class BiodiversityApp:
    def __init__(self, root):
        self.root = root
        self.root.configure(bg=MAIN_BG)
        self.root.geometry("1200x800")  # Increased size for map display
        self.root.title("Biodiversity Tool")
        # load logos
        self.logo_manager = LogoManager(LOGOS_DIR)
        # load CSVs
        self.habitats_df = self._load_habitats()
        self.years_df = self._load_years()
        # saved results in-memory list
        self.saved_rows = []
        # map data storage
        self.current_baseline_gdf = None
        self.current_intersection_gdf = None
        # build UI
        self._build_ui()

    def _load_habitats(self):
        if HABITATS_CSV.exists():
            try:
                df = pd.read_csv(HABITATS_CSV, dtype=str).fillna("")
                df["Distinctiveness Category"] = df.get("Distinctiveness Category", df.columns[-1])
                df["Distinctiveness Score"] = df["Distinctiveness Category"].map(DISTINCTIVENESS_MAP).fillna(0).astype(float)
                return df
            except Exception as e:
                print("Reading habitats failed:", e)
        # fallback sample
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
        # fallback
        return pd.DataFrame([{"Years": "5", "Multiplier": 1.05}, {"Years": "10", "Multiplier": 1.0}])

    def _build_ui(self):
        # Notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(8,60))
        # tabs
        self.tab_loss = ttk.Frame(self.notebook)
        self.tab_gain = ttk.Frame(self.notebook)
        self.tab_saved = ttk.Frame(self.notebook)
        self.tab_map = ttk.Frame(self.notebook)  # NEW MAP TAB
        
        self.notebook.add(self.tab_loss, text="🏞️ Loss Calculator")
        self.notebook.add(self.tab_gain, text="📈 Gain Calculator")
        self.notebook.add(self.tab_saved, text="📋 Saved Results")
        self.notebook.add(self.tab_map, text="🗺️ Map View")

        # Loss tab
        create_modern_header(self.tab_loss, {"bg": MAIN_BG}, self.logo_manager)
        self._build_loss_tab()

        # Gain tab
        create_modern_header(self.tab_gain, {"bg": MAIN_BG}, self.logo_manager)
        self._build_gain_tab()

        # Saved results tab
        create_modern_header(self.tab_saved, {"bg": MAIN_BG}, self.logo_manager)
        self._build_saved_tab()

        # Map View tab
        create_modern_header(self.tab_map, {"bg": MAIN_BG}, self.logo_manager)
        self._build_map_tab()

        # bottom logos area
        self._build_bottom_logos()

    # ---------- Loss tab ----------
    def _build_loss_tab(self):
        # Main container
        main_frame = ttk.Frame(self.tab_loss)
        main_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        # File selection section
        file_frame = create_card(main_frame)
        ttk.Label(file_frame, text="File Selection", font=("Arial", 12, "bold")).pack(anchor="w", pady=(0, 10))
        
        # Baseline file selection
        baseline_frame = ttk.Frame(file_frame)
        baseline_frame.pack(fill="x", pady=5)
        ttk.Label(baseline_frame, text="Baseline Habitat File:").pack(side="left", padx=(0, 10))
        self.loss_baseline_path = tk.StringVar()
        ttk.Entry(baseline_frame, textvariable=self.loss_baseline_path, width=50).pack(side="left", padx=(0, 10))
        ttk.Button(baseline_frame, text="Browse", 
                  command=lambda: self._browse_file(self.loss_baseline_path, [("Shapefiles", "*.shp"), ("GeoPackage", "*.gpkg")])).pack(side="left")
        
        # Planned development file selection
        planned_frame = ttk.Frame(file_frame)
        planned_frame.pack(fill="x", pady=5)
        ttk.Label(planned_frame, text="Planned Development File:").pack(side="left", padx=(0, 10))
        self.loss_planned_path = tk.StringVar()
        ttk.Entry(planned_frame, textvariable=self.loss_planned_path, width=50).pack(side="left", padx=(0, 10))
        ttk.Button(planned_frame, text="Browse", 
                  command=lambda: self._browse_file(self.loss_planned_path, [("Shapefiles", "*.shp"), ("DXF Files", "*.dxf")])).pack(side="left")
        
        # Significance input
        sig_frame = ttk.Frame(file_frame)
        sig_frame.pack(fill="x", pady=5)
        ttk.Label(sig_frame, text="Strategic Significance:").pack(side="left", padx=(0, 10))
        self.loss_significance = tk.StringVar(value="1.0")
        ttk.Entry(sig_frame, textvariable=self.loss_significance, width=10).pack(side="left", padx=(0, 10))
        ttk.Label(sig_frame, text="(1.0 = Low, 1.15 = High)").pack(side="left")
        
        # Process button
        ttk.Button(file_frame, text="Calculate Biodiversity Loss", 
                  command=self._process_and_export_loss, style="Accent.TButton").pack(pady=10)
        
        # Results section
        results_frame = create_card(main_frame)
        ttk.Label(results_frame, text="Results", font=("Arial", 12, "bold")).pack(anchor="w", pady=(0, 10))
        
        # Results text area
        self.loss_results_text = tk.Text(results_frame, height=15, width=80, wrap="word")
        scrollbar = ttk.Scrollbar(results_frame, orient="vertical", command=self.loss_results_text.yview)
        self.loss_results_text.configure(yscrollcommand=scrollbar.set)
        self.loss_results_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def _browse_file(self, path_var, filetypes):
        """Open file dialog and set the path variable"""
        filename = filedialog.askopenfilename(filetypes=filetypes)
        if filename:
            path_var.set(filename)

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
            # convert if needed
            shp1 = convert_if_needed(base, is_baseline=True)
            shp2 = convert_if_needed(plan, is_baseline=False)
            gdf1 = load_and_fix(shp1)
            gdf2 = load_and_fix(shp2)

            # USE EPSG:31370 consistently
            target_crs = "EPSG:31370"
            
            # Reproject both files to the same CRS
            if gdf1.crs is not None and gdf1.crs != target_crs:
                gdf1 = gdf1.to_crs(target_crs)
            elif gdf1.crs is None:
                gdf1.set_crs(target_crs, inplace=True)
                
            if gdf2.crs is not None and gdf2.crs != target_crs:
                gdf2 = gdf2.to_crs(target_crs)
            elif gdf2.crs is None:
                gdf2.set_crs(target_crs, inplace=True)

            print(f"Final CRS - Baseline: {gdf1.crs}, Planned: {gdf2.crs}")
            print(f"Final bounds - Baseline: {gdf1.total_bounds}")
            print(f"Final bounds - Planned: {gdf2.total_bounds}")

            # Check if files overlap
            baseline_center_x = (gdf1.total_bounds[0] + gdf1.total_bounds[2]) / 2
            baseline_center_y = (gdf1.total_bounds[1] + gdf1.total_bounds[3]) / 2
            planned_center_x = (gdf2.total_bounds[0] + gdf2.total_bounds[2]) / 2
            planned_center_y = (gdf2.total_bounds[1] + gdf2.total_bounds[3]) / 2
            
            distance_x = abs(baseline_center_x - planned_center_x)
            distance_y = abs(baseline_center_y - planned_center_y)
            
            print(f"Center distance - X: {distance_x:.0f}m, Y: {distance_y:.0f}m")
            
            # If centers are more than 10km apart, they're probably wrong
            if distance_x > 10000 or distance_y > 10000:
                messagebox.showerror(
                    "Spatial Mismatch", 
                    f"The selected files are in different locations!\n\n"
                    f"Baseline center: ({baseline_center_x:.0f}, {baseline_center_y:.0f})\n"
                    f"Planned center: ({planned_center_x:.0f}, {planned_center_y:.0f})\n"
                    f"Distance: {max(distance_x, distance_y):.0f}m apart\n\n"
                    "Please select files that cover the same geographic area."
                )
                return

            # keep polygons only
            gdf1 = gdf1[gdf1.geometry.type.isin(["Polygon", "MultiPolygon"])]
            gdf2 = gdf2[gdf2.geometry.type.isin(["Polygon", "MultiPolygon"])]

            if gdf1.empty:
                messagebox.showerror("Error", "Baseline contains no polygons after cleaning.")
                return
            if gdf2.empty:
                messagebox.showerror("Error", "Planned development contains no polygons after cleaning.")
                return
            
            gdf1["area_m2"] = gdf1.geometry.area
            total_baseline_ha = gdf1["area_m2"].sum() / 10000.0
            
            # compute totals and intersections
            gdf1['Condition score'] = np.nan
            gdf1['Distinctiveness score'] = np.nan
            gdf1['Biodiversity units'] = np.nan
            gdf1['Significance score'] = sig_val

            # Check required columns
            required_columns = ['Baseline Condition', 'Baseline Distinctiveness', 'Baseline Broad Habitat Type']
            missing_cols = [col for col in required_columns if col not in gdf1.columns]
            if missing_cols:
                messagebox.showerror("Missing Data", f"Required columns missing:\n{', '.join(missing_cols)}")
                return

            # Map using flexible mapping functions
            def flexible_condition_map(val):
                if pd.isna(val):
                    return np.nan
                val_str = str(val).strip().lower()
                
                if any(x in val_str for x in ['good', '3']):
                    return 3.0
                elif any(x in val_str for x in ['fairly good', '2.5']):
                    return 2.5
                elif any(x in val_str for x in ['moderate', '2']):
                    return 2.0
                elif any(x in val_str for x in ['fairly poor', '1.5']):
                    return 1.5
                elif any(x in val_str for x in ['poor', '1']):
                    return 1.0
                else:
                    print(f"Could not map condition value: '{val}'")
                    return np.nan
            
            def flexible_distinctiveness_map(val):
                if pd.isna(val):
                    return np.nan
                val_str = str(val).strip().lower()
                
                if any(x in val_str for x in ['v.high', 'very high', '8']):
                    return 8
                elif any(x in val_str for x in ['high', '6']):
                    return 6
                elif any(x in val_str for x in ['medium', '4']):
                    return 4
                elif any(x in val_str for x in ['low', '2']):
                    return 2
                elif any(x in val_str for x in ['v.low', 'very low', '0']):
                    return 0
                else:
                    print(f"Could not map distinctiveness value: '{val}'")
                    return np.nan
            
            gdf1['Condition score'] = gdf1['Baseline Condition'].apply(flexible_condition_map)
            gdf1['Distinctiveness score'] = gdf1['Baseline Distinctiveness'].apply(flexible_distinctiveness_map)
            gdf1 = gdf1[gdf1['Baseline Broad Habitat Type'] != 'Urban']
            
            # Check if mapping worked
            nan_condition = gdf1['Condition score'].isna().sum()
            nan_distinctiveness = gdf1['Distinctiveness score'].isna().sum()
            
            if nan_condition > 0 or nan_distinctiveness > 0:
                messagebox.showwarning("Mapping Issues", 
                                     f"Could not map all values:\n"
                                     f"- {nan_condition} condition values\n"
                                     f"- {nan_distinctiveness} distinctiveness values\n"
                                     f"Check console for details.")

            # Overlay intersection
            intersection = gpd.overlay(gdf1, gdf2, how='intersection', keep_geom_type=True)
            intersection = intersection[intersection.geometry.type.isin(['Polygon', 'MultiPolygon'])]

            if intersection.empty:
                messagebox.showerror("Error", "No overlapping areas found between the shapefiles")
                return

            # Calculate biodiversity loss
            intersection['Loss area (ha)'] = round(intersection.geometry.area / 10000, 2)
            intersection['Biodiversity units'] = round(
                intersection['Loss area (ha)'] *
                intersection['Condition score'] *
                intersection['Significance score'] *
                intersection['Distinctiveness score'], 2
            )

            # SUMMARIZE RESULTS
            total_loss_ha = intersection["Loss area (ha)"].sum()
            total_biodiv_units = intersection["Biodiversity units"].sum()
            txt = []
            txt.append(f"Baseline total area (ha): {total_baseline_ha:,.3f}")
            txt.append(f"Total overlap / loss area (ha): {total_loss_ha:,.3f}")
            txt.append(f"Total biodiversity units (loss): {total_biodiv_units:,.3f}")
            txt.append("\nTop 10 loss features (first columns):")
            preview = intersection.head(10)[["Loss area (ha)", "Biodiversity units"]].copy()
            txt.append(preview.to_string(index=False))
            self.loss_results_text.delete("1.0", "end")
            self.loss_results_text.insert("end", "\n".join(txt))

            # STORE DATA FOR MAP DISPLAY
            self.current_baseline_gdf = gdf1.copy()
            self.current_intersection_gdf = intersection.copy()
            
            # Auto-switch to map tab and refresh
            self.notebook.select(3)  # Switch to map tab
            self._refresh_map_display()

            # Ask to save shapefile and CSV
            if messagebox.askyesno("Save results", "Do you want to save the intersection shapefile and CSV summary?"):
                save_with_visualization(gdf1, intersection, sig_val)

        except Exception as e:
            messagebox.showerror("Processing Error", f"An unexpected error occurred:\n{str(e)}")

    # ---------- NEW MAP VIEW TAB ----------
    def _build_map_tab(self):
        # Main container
        main_frame = ttk.Frame(self.tab_map)
        main_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        # Control panel
        control_frame = create_card(main_frame)
        ttk.Label(control_frame, text="Map Display", font=("Arial", 12, "bold")).pack(anchor="w", pady=(0, 10))
        
        # Status label
        self.map_status_label = ttk.Label(control_frame, text="No map data available. Run Loss Calculator first.", 
                                         foreground="red", font=("Arial", 10))
        self.map_status_label.pack(anchor="w", pady=5)
        
        # Buttons frame
        btn_frame = ttk.Frame(control_frame)
        btn_frame.pack(fill="x", pady=10)
        
        ttk.Button(btn_frame, text="Refresh Map", 
                  command=self._refresh_map_display).pack(side="left", padx=(0, 10))
        ttk.Button(btn_frame, text="Save Map as PNG", 
                  command=self._save_current_map).pack(side="left", padx=(0, 10))
        ttk.Button(btn_frame, text="Clear Map", 
                  command=self._clear_map_display).pack(side="left")
        
        # Map display area
        map_frame = create_card(main_frame)
        ttk.Label(map_frame, text="Biodiversity Loss Map", font=("Arial", 11, "bold")).pack(anchor="w", pady=(0, 10))
        
        # Create a canvas for the map
        self.map_canvas = tk.Canvas(map_frame, bg="white", width=800, height=500, 
                                   relief="solid", bd=1)
        self.map_canvas.pack(fill="both", expand=True, pady=10)
        
        # Map info panel
        info_frame = ttk.Frame(map_frame)
        info_frame.pack(fill="x", pady=5)
        
        self.map_info_label = ttk.Label(info_frame, text="", font=("Arial", 9))
        self.map_info_label.pack(anchor="w")

    def _refresh_map_display(self):
        """Refresh the map display with current data using preview mode"""
        if self.current_baseline_gdf is None or self.current_intersection_gdf is None:
            self.map_status_label.config(text="No map data available. Run Loss Calculator first.", foreground="red")
            self.map_canvas.delete("all")
            self.map_canvas.create_text(400, 250, text="No map data available\nRun Loss Calculator first", 
                                       fill="gray", font=("Arial", 14), justify="center")
            self.map_info_label.config(text="")
            return
        
        try:
            # Create a temporary PNG file
            temp_dir = tempfile.gettempdir()
            temp_png = os.path.join(temp_dir, "biodiversity_map_preview.png")
            
            # USE THE MAIN FUNCTION WITH PREVIEW MODE
            success = create_loss_map_as_png(
                self.current_baseline_gdf, 
                self.current_intersection_gdf, 
                temp_png, 
                preview_mode=True  # Fast preview mode
            )
            
            if success and os.path.exists(temp_png):
                # Load and display the image
                img = Image.open(temp_png)
                # Resize to fit canvas while maintaining aspect ratio
                canvas_width = self.map_canvas.winfo_width() - 20
                canvas_height = self.map_canvas.winfo_height() - 20
                
                if canvas_width > 1 and canvas_height > 1:
                    img.thumbnail((canvas_width, canvas_height), Image.Resampling.LANCZOS)
                
                self.map_photo = ImageTk.PhotoImage(img)
                
                # Clear canvas and display image
                self.map_canvas.delete("all")
                self.map_canvas.create_image(10, 10, anchor="nw", image=self.map_photo)
                
                # Update status
                total_loss = self.current_intersection_gdf['Biodiversity units'].sum() if 'Biodiversity units' in self.current_intersection_gdf.columns else 0
                total_area = self.current_intersection_gdf['Loss area (ha)'].sum() if 'Loss area (ha)' in self.current_intersection_gdf.columns else 0
                
                self.map_status_label.config(text="Map display updated successfully", foreground="green")
                self.map_info_label.config(text=f"Total Biodiversity Loss: {total_loss:,.2f} units | Total Area Impacted: {total_area:,.2f} ha")
                
            else:
                self.map_status_label.config(text="Failed to generate map preview", foreground="red")
                
        except Exception as e:
            print(f"Error refreshing map: {e}")
            self.map_status_label.config(text=f"Error displaying map: {str(e)}", foreground="red")

    def _save_current_map(self):
        """Save high-quality map using the main function"""
        if self.current_baseline_gdf is None or self.current_intersection_gdf is None:
            messagebox.showwarning("No Data", "No map data available to save.")
            return
        
        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
        png_path = filedialog.asksaveasfilename(
            title="Save Biodiversity Loss Map",
            defaultextension=".png",
            filetypes=[("PNG files", "*.png"), ("All files", "*.*")],
            initialdir=desktop_path
        )
        
        if png_path:
            try:
                # USE THE MAIN FUNCTION WITHOUT PREVIEW MODE (high quality)
                success = create_loss_map_as_png(
                    self.current_baseline_gdf,
                    self.current_intersection_gdf, 
                    png_path
                    # preview_mode=False by default = high quality
                )
                
                if success:
                    messagebox.showinfo("Success", f"High-quality map saved to:\n{png_path}")
                else:
                    messagebox.showerror("Error", "Failed to save map image")
                    
            except Exception as e:
                print(f"❌ Map save failed: {e}")
                messagebox.showerror("Save Error", f"Failed to save map:\n{str(e)}")

    def _clear_map_display(self):
        """Clear the map display"""
        self.map_canvas.delete("all")
        self.map_canvas.create_text(400, 250, text="Map display cleared\nRun Loss Calculator to generate new map", 
                                   fill="gray", font=("Arial", 14), justify="center")
        self.map_status_label.config(text="Map display cleared", foreground="blue")
        self.map_info_label.config(text="")

    # ---------- Gain tab ----------
    def _build_gain_tab(self):
        card = create_card(self.tab_gain)
        # We'll build a 3-column layout inside card using grid
        frm = ttk.Frame(card)
        frm.pack(fill="both", expand=True, padx=4, pady=4)

        # labels for columns
        ttk.Label(frm, text="Parameter & Selector", background=MAIN_BG).grid(row=0, column=0, padx=8, pady=6, sticky="w")
        ttk.Label(frm, text="Explanation", background=MAIN_BG).grid(row=0, column=1, padx=8, pady=6, sticky="w")
        ttk.Label(frm, text="Value / Multiplier", background=MAIN_BG).grid(row=0, column=2, padx=8, pady=6, sticky="w")

        # variables
        self.var_broad = tk.StringVar()
        self.var_specific = tk.StringVar()
        self.var_year = tk.StringVar()
        self.var_condition = tk.StringVar()
        self.var_difficulty = tk.StringVar()
        self.var_spatial = tk.StringVar()
        self.var_strategic = tk.StringVar()
        self.var_area = tk.StringVar()

        # row index
        r = 1
        # helper to add rows
        def add_row(label_text, explanation_text, widget):
            nonlocal r
            lbl = ttk.Label(frm, text=label_text)
            lbl.grid(row=r, column=0, sticky="w", padx=8, pady=(6,2))
            expl = ttk.Label(frm, text=explanation_text, font=("Segoe UI", 9, "italic"), foreground="#444")
            expl.grid(row=r, column=1, sticky="w", padx=8, pady=(6,2))
            widget.grid(row=r, column=2, sticky="w", padx=8, pady=(6,2))
            r += 1
            return lbl, expl

        # Broad habitat
        broad_vals = sorted(self.habitats_df["Broad Habitat Type"].unique().tolist())
        cb_broad = ttk.Combobox(frm, textvariable=self.var_broad, values=broad_vals, state="readonly", width=40)
        add_row("Broad Habitat Type:", "Select the general habitat classification.", cb_broad)

        # Specific habitat (will be populated on broad change)
        cb_specific = ttk.Combobox(frm, textvariable=self.var_specific, values=[], state="readonly", width=40)
        add_row("Specific Habitat:", "Select the detailed habitat type (filtered by broad type).", cb_specific)

        # Target year
        year_vals = [str(x) for x in self.years_df["Years"].tolist()]
        cb_year = ttk.Combobox(frm, textvariable=self.var_year, values=year_vals, state="readonly", width=20)
        add_row("Time to target (years):", "How long until habitat reaches its target ecological value.", cb_year)

        # Baseline condition
        cb_condition = ttk.Combobox(frm, textvariable=self.var_condition, values=list(CONDITION_MAPPING.keys()), state="readonly", width=30)
        add_row("Baseline condition:", "State compared with other sites (use Fairly Good–Fairly Poor commonly).", cb_condition)

        # Difficulty
        cb_difficulty = ttk.Combobox(frm, textvariable=self.var_difficulty, values=list(DIFFICULTY_MAPPING.keys()), state="readonly", width=30)
        add_row("Difficulty category:", "Uncertainty in effectiveness of compensation techniques.", cb_difficulty)

        # Spatial risk
        cb_spatial = ttk.Combobox(frm, textvariable=self.var_spatial, values=list(SPATIAL_MAPPING.keys()), state="readonly", width=30)
        add_row("Spatial risk category:", "Location risk for habitat creation (closer is better).", cb_spatial)

        # Strategic significance
        cb_strat = ttk.Combobox(frm, textvariable=self.var_strategic, values=list(STRATEGIC_MAPPING.keys()), state="readonly", width=30)
        add_row("Strategic significance:", "High = matches mapped plan exactly; Low = different location or habitat.", cb_strat)

        # Area
        ent_area = ttk.Entry(frm, textvariable=self.var_area, width=18)
        add_row("Area (ha):", "Enter parcel area in hectares (e.g., 2.5).", ent_area)

        # Create labels for multipliers
        self.lbl_distinct = ttk.Label(frm, text="Distinctiveness: -")
        self.lbl_distinct.grid(row=1, column=3, sticky="w", padx=6)
        self.lbl_yearmult = ttk.Label(frm, text="Year multiplier: -")
        self.lbl_yearmult.grid(row=3, column=3, sticky="w", padx=6)
        self.lbl_cond = ttk.Label(frm, text="Condition score: -")
        self.lbl_cond.grid(row=4, column=3, sticky="w", padx=6)
        self.lbl_diff = ttk.Label(frm, text="Difficulty multiplier: -")
        self.lbl_diff.grid(row=5, column=3, sticky="w", padx=6)
        self.lbl_spat = ttk.Label(frm, text="Spatial multiplier: -")
        self.lbl_spat.grid(row=6, column=3, sticky="w", padx=6)
        self.lbl_strat = ttk.Label(frm, text="Strategic multiplier: -")
        self.lbl_strat.grid(row=7, column=3, sticky="w", padx=6)
        self.lbl_area = ttk.Label(frm, text="Area: -")
        self.lbl_area.grid(row=8, column=3, sticky="w", padx=6)

        # Buttons and result
        btn_frame = ttk.Frame(card)
        btn_frame.pack(fill="x", pady=10)
        ttk.Button(btn_frame, text="Calculate", command=self._calculate_gain).pack(side="left", padx=8)
        ttk.Button(btn_frame, text="Save selection (CSV & add to Saved Results)", command=self._save_gain_selection).pack(side="left", padx=8)
        self.gain_result = ttk.Label(card, text="Biodiversity Units: -", font=("Segoe UI", 12, "bold"))
        self.gain_result.pack(anchor="w", pady=(6,0), padx=6)

        # bind events
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
            score = row.iloc[0].get("Distinctiveness Score", 0.0)
            self.lbl_distinct.config(text=f"Distinctiveness: {score}")
        else:
            self.lbl_distinct.config(text="Distinctiveness: -")
        self.gain_result.config(text="Biodiversity Units: -")

    def _on_year_change(self):
        y = self.var_year.get()
        row = self.years_df[self.years_df["Years"].astype(str) == str(y)]
        if not row.empty:
            mult = row.iloc[0]["Multiplier"]
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
        # validation
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

        # get numeric values
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
        # run calculate first
        self._calculate_gain()
        txt = self.gain_result.cget("text")
        if "Biodiversity Units:" not in txt:
            messagebox.showerror("No result", "Calculate before saving.")
            return
        units = txt.split(":")[1].strip()
        # build row
        row = {
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
            "Biodiversity Units": units,
            "Timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        # Save to CSV file (ask user) and also append to Saved Results table
        savepath = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if savepath:
            try:
                with open(savepath, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(list(row.keys()))
                    writer.writerow(list(row.values()))
                messagebox.showinfo("Saved", f"Selection saved to: {savepath}")
            except Exception as e:
                messagebox.showerror("Save error", f"Failed to save CSV: {e}")
                return
        # also add to in-memory saved rows and update table
        self.saved_rows.append(row)
        self._refresh_saved_table()

    # ---------- Saved Results tab ----------
    def _build_saved_tab(self):
        card = create_card(self.tab_saved)
        # treeview
        cols = ["Timestamp", "Broad Habitat", "Specific Habitat", "Area (ha)", "Biodiversity Units"]
        self.saved_tree = ttk.Treeview(card, columns=cols, show="headings", height=12)
        for c in cols:
            self.saved_tree.heading(c, text=c)
            self.saved_tree.column(c, width=150, anchor="w")
        self.saved_tree.pack(fill="both", expand=True, padx=8, pady=6)
        # buttons
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
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            keys = list(self.saved_rows[0].keys())
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                for r in self.saved_rows:
                    writer.writerow(r)
            messagebox.showinfo("Exported", f"Saved results exported to {path}")
        except Exception as e:
            messagebox.showerror("Export error", f"Failed to export: {e}")

    def _clear_saved(self):
        if messagebox.askyesno("Confirm", "Clear all saved rows from the in-memory table?"):
            self.saved_rows = []
            self._refresh_saved_table()

    # ---------- Bottom logos ----------
    def _build_bottom_logos(self):
        bottom = ttk.Frame(self.root)
        bottom.pack(side="bottom", fill="x", pady=6)
        left_logo = self.logo_manager.load("university", max_w=150, max_h=80)
        right_logo = self.logo_manager.load("office", max_w=150, max_h=80)
        left_lbl = tk.Label(bottom, image=left_logo if left_logo else None, bg=MAIN_BG, text="" if left_logo else "[UNIVERSITY]")
        left_lbl.image = left_logo
        left_lbl.pack(side="left", padx=12)
        right_lbl = tk.Label(bottom, image=right_logo if right_logo else None, bg=MAIN_BG, text="" if right_logo else "[OFFICE]")
        right_lbl.image = right_logo
        right_lbl.pack(side="right", padx=12)

# ---------- Run ----------
def main():
    root = tk.Tk()
    # configure root background to be consistent
    root.configure(bg=MAIN_BG)
    try:
       root.iconbitmap("biodiversity.ico")
    except Exception as e:
       print(f"Icon not found or failed to load: {e}")
    app = BiodiversityApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()