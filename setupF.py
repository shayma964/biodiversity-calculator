# -*- coding: utf-8 -*-
"""
Created on Thu Jun 19 16:29:31 2025

@author: Test
"""


"""
Optimized build script without Qt dependencies
"""
import os
import sys
from pathlib import Path

# === PROJ/GDAL PATH CONFIGURATION ===
def configure_proj_paths():
    """Set PROJ_LIB and PATH for both frozen and dev environments"""
    if getattr(sys, 'frozen', False):
        # Frozen application (built with cx_Freeze)
        base_path = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        proj_lib_path = Path(base_path) / "lib" / "share" / "proj"
        os.environ["PROJ_LIB"] = str(proj_lib_path)
        os.environ["PATH"] = str(Path(base_path) / "lib") + os.pathsep + os.environ["PATH"]
    else:
        # Development environment
        env_path = Path(sys.executable).parent
        os.environ["PROJ_LIB"] = str(env_path / "Library" / "share" / "proj")
        os.environ["PATH"] = str(env_path / "Library" / "bin") + os.pathsep + os.environ["PATH"]

# Configure paths BEFORE importing geopandas/fiona
configure_proj_paths()

# === IMPORTS ===
import certifi
import geopandas
import fiona
from cx_Freeze import setup, Executable

# === PATH SETUP ===
env_root = Path(sys.executable).parent
env_bin = env_root / "Library" / "bin"
geopandas_data = Path(geopandas.__file__).parent / "datasets"
proj_data = env_root / "Library" / "share" / "proj"
fiona_libs = Path(fiona.__file__).parent / ".libs"

# === INCLUDE FILES ===
include_files = []

# A) PROJ data
if proj_data.exists():
    include_files.extend(
        (str(f), f"lib/share/proj/{f.name}") 
        for f in proj_data.iterdir() 
        if f.is_file()
    )

# B) GDAL/PROJ DLLs
if env_bin.exists():
    required_dlls = {'gdal', 'proj', 'geos', 'sqlite3', 'spatialindex'}
    include_files.extend(
        (str(dll), f"lib/{dll.name}")
        for dll in env_bin.glob("*.dll")
        if any(name in dll.name.lower() for name in required_dlls)
    )

# C) Fiona .libs
if fiona_libs.exists():
    include_files.extend(
        (str(f), f"lib/fiona_libs/{f.name}") 
        for f in fiona_libs.iterdir()
    )

# D) GeoPandas datasets
if geopandas_data.exists():
    include_files.append((str(geopandas_data), "geopandas/datasets"))

# E) SSL certificates
include_files.append((certifi.where(), "lib/certifi/cacert.pem"))

# === BUILD OPTIONS ===
build_options = {
    "packages": [
        "tkinter", "PIL", "requests", "geopandas", 
        "numpy", "pandas", "shapely", "fiona",
        "pyproj", "rtree", "urllib3", "certifi"
    ],
    "include_files": include_files,
    "excludes": ["matplotlib", "PyQt5", "qtpy"],  # Explicitly exclude Qt
    "optimize": 2,
    "include_msvcr": True,
}

# === EXECUTABLE CONFIG ===
icon_path = "icon.ico" if Path("icon.ico").exists() else None
executables = [
    Executable(
        "modified_version_juneBio12.py",
        base="Win32GUI" if sys.platform == "win32" else None,
        target_name="BiodiversityCalculator1.exe",
        icon=icon_path
    )
]

# === SETUP ===
setup(
    name="Biodiversity Calculator",
    version="1.0",
    description="GUI for biodiversity analysis",
    options={"build_exe": build_options},
    executables=executables
)