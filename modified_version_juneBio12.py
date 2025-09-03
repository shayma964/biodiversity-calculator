# -*- coding: utf-8 -*-
"""
Created on Tue Mar 25 17:48:04 2025

@author: Test
"""
import os
import sys
from pathlib import Path

# === FIX: Set PROJ_LIB and PATH when running from .exe ===
if getattr(sys, 'frozen', False):
    base_path = getattr(sys, '_MEIPASS', Path(sys.executable).parent)
    proj_path = Path(base_path) / "lib" / "share" / "proj"
    os.environ["PROJ_LIB"] = str(proj_path)
    os.environ["PATH"] = str(Path(base_path) / "lib") + os.pathsep + os.environ["PATH"]

    print("PROJ_LIB (runtime):", os.environ["PROJ_LIB"])  # Debug check

import tkinter as tk
from tkinter import filedialog, messagebox,ttk
from PIL import Image, ImageTk
import requests
from io import BytesIO
import json
import geopandas as gpd
import numpy as np
import pandas as pd
import csv

#%%
# Initialize global variables for shapefile paths

shapefile1_path = None
shapefile2_path = None

# ================ LOSS CALCULATOR FUNCTIONS ================
def process_shapefiles(significance_score):
    """Process shapefiles and calculate biodiversity loss"""
    try:
        # Check if files are selected (using global variables)
        if not shapefile1_path or not shapefile2_path:
            messagebox.showerror("Error", "Please select both files.")
            return

        # Read files with validation
        try:
            gdf1 = gpd.read_file(shapefile1_path)
            gdf2 = gpd.read_file(shapefile2_path)
        except Exception as e:
            messagebox.showerror("File Error", f"Failed to read shapefiles:\n{str(e)}")
            return

        # CRS check and conversion
        if gdf1.crs != gdf2.crs:
            gdf2 = gdf2.to_crs(gdf1.crs)

        # Add required columns
        gdf1['Condition score'] = np.nan
        gdf1['Distinctiveness score'] = np.nan
        gdf1['Biodiversity units'] = np.nan
        gdf1['Significance score'] = significance_score

        # Mapping dictionaries
        condition_mapping = {
            "1. Good": 3, "2. Fairly Good": 2.5, "3. Moderate": 2,
            "4. Fairly Poor": 1.5, "5. Poor": 1, "6. N/A - Other": 1
        }
        
        distinctiveness_mapping = {
            "V.Low": 0, "Low": 2, "Medium": 4, "High": 6, "V.High": 8
        }

        # Apply mappings with validation
        required_columns = ['Baseline Condition', 'Baseline Distinctiveness', 'Baseline Broad Habitat Type']
        missing_cols = [col for col in required_columns if col not in gdf1.columns]
        if missing_cols:
            messagebox.showerror("Missing Data", f"Required columns missing:\n{', '.join(missing_cols)}")
            return

        gdf1['Condition score'] = gdf1['Baseline Condition'].map(condition_mapping)
        gdf1['Distinctiveness score'] = gdf1['Baseline Distinctiveness'].map(distinctiveness_mapping)

        # Filter urban areas
        gdf1 = gdf1[gdf1['Baseline Broad Habitat Type'] != 'Urban']

        # Perform intersection
        intersection = gpd.overlay(gdf1, gdf2, how='intersection', keep_geom_type=False)
        intersection = intersection[intersection.geometry.type == 'Polygon']

        if intersection.empty:
            messagebox.showerror("Error", "No overlapping areas found between the shapefiles")
            return

        # Calculate results
        intersection['Loss area (ha)'] = round(intersection.geometry.area / 10000, 2)
        intersection['Biodiversity units'] = round(
            intersection['Loss area (ha)'] *
            intersection['Condition score'] *
            intersection['Significance score'] *
            intersection['Distinctiveness score'], 2
        )

        # Save outputs
        save_gdf_as_shapefile(intersection)
        save_df_as_csv(intersection[['Loss area (ha)', 'Biodiversity units']])

    except Exception as e:
        messagebox.showerror("Processing Error", f"An unexpected error occurred:\n{str(e)}")

def save_gdf_as_shapefile(gdf):
    """Save GeoDataFrame as shapefile"""
    output_file = filedialog.asksaveasfilename(
        title="Save Processed Shapefile", 
        defaultextension=".shp",
        filetypes=[("Shapefiles", "*.shp")]
    )
    if output_file:
        try:
            gdf.to_file(output_file)
            messagebox.showinfo("Success", f"Shapefile saved successfully at:\n{output_file}")
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save shapefile:\n{str(e)}")

def save_df_as_csv(df):
    """Save DataFrame as CSV"""
    csv_file = filedialog.asksaveasfilename(
        title="Save Biodiversity Loss Data",
        defaultextension=".csv",
        filetypes=[("CSV files", "*.csv")]
    )
    if csv_file:
        try:
            df.to_csv(csv_file, index=False)
            messagebox.showinfo("Success", f"CSV file saved successfully at:\n{csv_file}")
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save CSV file:\n{str(e)}")
#%%



   
#%%Gain calculator
# Load the habitats CSV file
url1= "https://raw.githubusercontent.com/shayma964/biodiversity-calculator/refs/heads/main/all_habitats.csv"
data = pd.read_csv(url1)

# Convert to JSON
json_habitatdata = data.to_json(orient="records", indent=4)

json_habitats = json.loads(json_habitatdata)
    #%%
# Load the targetyearCSV file
url2 = "https://raw.githubusercontent.com/shayma964/biodiversity-calculator/refs/heads/main/target_year.csv"
data = pd.read_csv(url2)

# Convert to JSON
json_yearsdata = data.to_json(orient="records", indent=4)


json_target_year=json.loads(json_yearsdata)


#%%
##create dictionary for Baseline condition score which the user select:
baseline_condition={"Good":2,
                        "Fairly Good":2.5,
                        "Moderate":2,
                        "Fairly poor":1.5,
                        "Poor":1}
###Difficulty dictionary with the user will select
Difficulty={"Very high":0.1,
            "High":0.33,
            "Medium":0.67,
            "Low":1}
###spatial risk dictionary
Spatial_risk={"Same Campus":1,
              "Within Gent":0.75,
              "Somewhere further":0.5}
##Compensation_units=available area X distinc.scoreXconditionX
## sig.scoreX difficulty X time discounter X spatial risk
# Mapping of categories to scores
score_mapping = {
    "V.High": 8,
    "High": 6,
    "Medium": 4,
    "Low": 2,
    "V.Low": 0
}

# Iterate over each record in the list
for record in json_habitats:  # json_habitats is a list of dictionaries
    category = record.get("Distinctiveness Category")  # Access category
    if category:  # Ensure category exists
        record["Distinctiveness Score"] = score_mapping.get(category, None)  # Map category to score
    else:
        record["Distinctiveness Score"] = None  # Handle missing category

#%%
# Extract unique Broad Habitat Types
broad_habitat_types = list({record["Broad Habitat Type"] for record in json_habitats})

# Create a function to update the Specific Habitat dropdown based on Broad Habitat selection
def update_specific_habitats(*args):
    selected_broad = broad_habitat_var.get()
    if selected_broad:
        # Filter Specific Habitat based on selected Broad Habitat Type
        specific_habitats = [
            record["Specific Habitat"]
            for record in json_habitats
            if record["Broad Habitat Type"] == selected_broad
        ]
        # Update Specific Habitat dropdown
        specific_habitat_menu["values"] = specific_habitats
        specific_habitat_var.set("")  # Reset Specific Habitat selection
    else:
        specific_habitat_menu["values"] = []  # Clear Specific Habitat dropdown

    update_score()  # Update the score in case selections have changed

# Create a function to display the Distinctiveness Score

def update_score(*args):
    selected_broad = broad_habitat_var.get()
    selected_specific = specific_habitat_var.get()

    if selected_broad and selected_specific:
        # Find the record that matches the selections
        for record in json_habitats:
            if (
                record["Broad Habitat Type"] == selected_broad
                and record["Specific Habitat"] == selected_specific
            ):
                score_label.config(
                    text=f"Distinctiveness Score: {record['Distinctiveness Score']}"
                )
                return
    score_label.config(text="Distinctiveness Score: Not found")  # Default if no match
    #%%create drop menu to target year:
# Ensure the years are in the same order as in json_target_year
target_years = list(dict.fromkeys(record["Years"] for record in json_target_year))

def update_multiplier(*args):

    selected_year = selected_year_var.get()
        # Find the record that matches the selections
    for record in json_target_year:
            if (
                record["Years"] == selected_year
                
            ):
                score2_label.config(
                    text=f"Multiplier: {record['Multiplier']}"
                )
                return
    score2_label.config(text="Multiplier: Not found")  # Default if no match   
        
#function to select baseline condition
baseline_list = list(baseline_condition.keys())

def update_cond_score(*args):

    selected_condition = selected_condition_var.get()
                # Find the record that matches the selections
    if selected_condition in baseline_condition:  # Check if the condition exists in the dictionary
        condition_score = baseline_condition[selected_condition]  # Retrieve the value
        score3_label.config(
            text=f"Condition Score: {condition_score}"
        )
    else:
        score3_label.config(text="Condition Score: Not found")  #
#function to select difficulty
difficulty_list = list(Difficulty.keys())

def update_difficulty(*args):

    selected_difficulty = selected_difficulty_var.get()
                # Find the record that matches the selections
    if selected_difficulty in Difficulty:  # Check if the condition exists in the dictionary
        difficulty_score = Difficulty[selected_difficulty]  # Retrieve the value
        score4_label.config(
            text=f"Difficulty Multiplier: {difficulty_score}"
        )
    else:
        score4_label.config(text="Difficulty Multiplier: Not found")  #     
#function to select spatial risk
spatial_risk_list = list(Spatial_risk.keys())

def update_spRisk(*args):

    selected_spatial_risk = selected_spatial_risk_var.get()
                # Find the record that matches the selections
    if selected_spatial_risk  in Spatial_risk:  # Check if the condition exists in the dictionary
        spatial_risk_score = Spatial_risk[selected_spatial_risk]  # Retrieve the value
        score5_label.config(
            text=f"Spatial risk multiplier: {spatial_risk_score}"
        )
    else:
        score5_label.config(text="Spatial Risk Multiplier: Not found")  #              
         
#%%calculate biodiversity
def calculate_output():
    try:
        # Retrieve values from the score labels and entries
        distinctiveness_score = float(score_label.cget("text").split(":")[-1].strip())
       
        year_discounter=float(score2_label.cget("text").split(":")[-1].strip())
        condition_score = float(score3_label.cget("text").split(":")[-1].strip())
        difficulty_score=float(score4_label.cget("text").split(":")[-1].strip())
        spatial_risk_score=float(score5_label.cget("text").split(":")[-1].strip())
        strategic_significance = float(significance_entry.get())
        habitat_size = float(area_entry.get())
        
        # Perform the calculation (customize as needed)
        output_units = distinctiveness_score * condition_score * strategic_significance * habitat_size*spatial_risk_score*difficulty_score*year_discounter
        
        # Update the output label
        output_label.config(text=f"Biodiversity Units: {output_units:.2f}")
    except ValueError:
        # Handle cases where inputs are missing or invalid
        output_label.config(text="Error: Please ensure all inputs are valid numbers.")
#%%Save selection in a file
def save_selection():
 selected_data = {
        "Broad Habitat Type": broad_habitat_var.get(),
        "Specific Habitat": specific_habitat_var.get(),
        "Distinctiveness score":float(score_label.cget("text").split(":")[-1].strip()),
        "Target Year": selected_year_var.get(),
        "Year Multiplier":float(score2_label.cget("text").split(":")[-1].strip()),
        "Condition": selected_condition_var.get(),
        "Condition Score":float(score3_label.cget("text").split(":")[-1].strip()),
        "Difficulty": selected_difficulty_var.get(),
        "Difficulty Score":float(score4_label.cget("text").split(":")[-1].strip()),
        "Spatial Risk": selected_spatial_risk_var.get(),
        "Spatial Multiplier":float(score5_label.cget("text").split(":")[-1].strip()),
        "Area":float(area_entry.get()),
        "Strategic Significance": float(significance_entry.get()),
        "Biodiversity Units":float(output_label.cget("text").split(":")[-1].strip())
    }
             
 output_path=filedialog.asksaveasfilename( defaultextension=".csv",
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
 if output_path:
     with open(output_path,mode="w",newline="") as file:
         writer=csv.writer(file)
         writer.writerow(["Category","Selection"])
         for key, value in selected_data.items():
             writer.writerow([key,value])
         try:
             messagebox.showinfo("Success", f"Selection saved successfully at {output_path}")
         except Exception as e:
             messagebox.showerror("Error", f"Failed to save selection: {e}")
 else:
         messagebox.showinfo("Cancelled", "Save operation was cancelled.")
         #%%
def fetch_image_from_url(url, resize_to=None):
    try:
        response = requests.get(url)
        response.raise_for_status()
        image_data = BytesIO(response.content)
        image = Image.open(image_data)
        if resize_to:
            image = image.resize(resize_to, Image.Resampling.LANCZOS)
        print(f"Successfully fetched and resized image from {url}")
        return image
    except Exception as e:
        print(f"Error fetching image from {url}: {e}")
        return None

# Main application
root = tk.Tk()
root.title("Biodiversity Calculator")
root.config(bg='white')

# Dictionary to hold persistent image references
root.image_references = {}

# Fetch and set icon from URL
icon_url = "https://raw.githubusercontent.com/shayma964/biodiversity-calculator/main/biodiversity.ico"
icon_image = fetch_image_from_url(icon_url)
if icon_image:
    try:
        icon_photo = ImageTk.PhotoImage(icon_image)
        root.iconphoto(False, icon_photo)
        root.image_references['icon'] = icon_photo  # Store reference
    except Exception as e:
        print(f"Error setting icon: {e}")
else:
    print("Failed to fetch icon image.")

# Create tabs
notebook = ttk.Notebook(root)
notebook.pack(expand=True, fill="both")

# Load logo images from URLs
logo_url_1 = "https://raw.githubusercontent.com/shayma964/biodiversity-calculator/main/logo_ugent.png"
logo_url_2 = "https://raw.githubusercontent.com/shayma964/biodiversity-calculator/main/go_logo.png"

logo_image_1 = fetch_image_from_url(logo_url_1, resize_to=(80, 80))
logo_image_2 = fetch_image_from_url(logo_url_2, resize_to=(80, 50))

# Store PhotoImage references
root.image_references['logo_tk_1'] = ImageTk.PhotoImage(logo_image_1) if logo_image_1 else None
root.image_references['logo_tk_2'] = ImageTk.PhotoImage(logo_image_2) if logo_image_2 else None

#create style
style = ttk.Style()
style.configure("Custom.TFrame", background="white", relief="ridge", borderwidth=2)
style.configure(
    "Custom1.TLabel",
    background="white",  # Match the frame's background
    foreground="darkgreen",   # Text color
    font=( 'Helvetica',12, "bold")  # Font styling
)
style=ttk.Style()
style.configure("Custom2.TLabel",
background="white",  # Match the frame's background
foreground="black",   # Text color
font=( 'Helvetica',10, "bold") 
)

##

# Create tabs
tab1 = ttk.Frame(notebook,style="Custom.TFrame")
tab2 = ttk.Frame(notebook,style="Custom.TFrame")
notebook.add(tab1, text="Loss Calculator")
notebook.add(tab2, text="Gain Calculator")

# Add logo to Tab 1
if root.image_references['logo_tk_1']:
    logo_label_1 = tk.Label(tab1, image=root.image_references['logo_tk_1'], bg="white")
    logo_label_1.place(x=10, rely=0.95, anchor="sw")

if root.image_references['logo_tk_2']:
    logo_label_2 = tk.Label(tab1, image=root.image_references['logo_tk_2'], bg="white")
    logo_label_2.place(relx=0.95, rely=0.95, anchor="se")

# Add logo to Tab 2
if root.image_references['logo_tk_1']:
    logo_label_3 = tk.Label(tab2, image=root.image_references['logo_tk_1'], bg="white")
    logo_label_3.place(x=10, rely=0.95, anchor="sw")

if root.image_references['logo_tk_2']:
    logo_label_4 = tk.Label(tab2, image=root.image_references['logo_tk_2'], bg="white")
    logo_label_4.place(relx=0.95, rely=0.95, anchor="se")



#%%

#loss tab1
# Instruction label
label = tk.Label(tab1, text="Select shapefiles to process",background="white",  # Match the frame's background
foreground="darkgreen",   # Text color
font=( 'Helvetica',12, "bold"))
label.pack(pady=10)

# ====== File Selection Functions ======
def select_shapefile1():
    """Select Baseline Habitat file and update display."""
    global shapefile1_path 
    filepath = filedialog.askopenfilename(title="Select First File (Habitat Baseline)", 
    filetypes=[("Supported Files", "*.shp *.gpkg"),
               ("Shapefiles", "*.shp"), ("GeoPackages", "*.gpkg")]
    )

    if filepath:
        shapefile1_path = filepath  
        baseline_display.config(text=filepath)

def select_shapefile2():
    """Select Planned Development file and update display."""
    global shapefile2_path
    filepath = filedialog.askopenfilename(
        title="Select Planned Development Shapefile",
        filetypes=[("Shapefiles", "*.shp")]
    )
    if filepath:
        shapefile2_path= filepath
        planned_display.config(text=filepath)

# Entry for Strategic Significance
significance_label = tk.Label(tab1, text="Strategic Significance:",background="white",  # Match the frame's background
foreground="darkgreen",   # Text color
font=( 'Arial',12, "bold"))
significance_label.pack(pady=5)
significance_entry = tk.Entry(tab1)
significance_entry.pack(pady=5)
select_button1 = tk.Button(tab1, text="Select Baseline Habitat", command=select_shapefile1,bg="darkgreen",  # Button background color
fg="black",    # Button text color
font=("Helvetica", 12,"bold"),
activebackground="#f57c00",  # Background color when pressed
activeforeground="darkgreen")
select_button1.pack(pady=5)
# File display frame (to group label and path)
baseline_frame = tk.Frame(tab1, background="white")
baseline_frame.pack()

# "Selected file:" label
tk.Label(baseline_frame, text="Selected file:", 
        background="white", foreground="black",
        font=("Helvetica", 10)).pack(side=tk.LEFT)

# File display label (below Baseline button)
baseline_display = tk.Label(tab1, text="No file selected", 
                          background="white", foreground="black",
                          font=("Helvetica", 10), wraplength=400)
baseline_display.pack(pady=(0, 10))  # Reduced bottom margin


# Button to select second shapefile
select_button2 = tk.Button(tab1, text="Select Planned Development", command=select_shapefile2,bg="darkgreen",  # Button background color
fg="black",    # Button text color
font=("Helvetica", 12,"bold"),
activebackground="#f57c00",  # Background color when pressed
activeforeground="darkgreen")
select_button2.pack(pady=5)
# File display frame
planned_frame = tk.Frame(tab1, background="white")
planned_frame.pack()

# "Selected file:" label
tk.Label(planned_frame, text="Selected file:", 
        background="white", foreground="black",
        font=("Helvetica", 10)).pack(side=tk.LEFT)
# File display label (below Planned Dev button)
planned_display = tk.Label(tab1, text="No file selected", 
                         background="white", foreground="black",
                         font=("Helvetica", 10), wraplength=400)
planned_display.pack(pady=(0, 10))
# Button to start processing shapefiles
process_button = tk.Button(
    tab1,
    text="Process Shapefiles",bg="darkgreen",fg="black",
    font=("Helvetica", 12,"bold"),
    command=lambda: process_shapefiles(float(significance_entry.get()) if significance_entry.get() else 1.0)
)
process_button.pack(pady=10)


# Add Strategic Significance input
significance_label = tk.Label(tab2, text="Strategic Significance:",background="white",foreground="darkgreen",font=('Arial',12, "bold"))
significance_label.grid(row=7, column=0, padx=10, pady=5, sticky="w")
significance_entry = tk.Entry(tab2)
significance_entry.grid(row=7, column=1, padx=10, pady=5)

# Add Habitat Parcel Size input
area_label = tk.Label(tab2, text="Size of habitat parcel (ha):",background="white",foreground="darkgreen",font=('Arial',12, "bold"))
area_label.grid(row=6, column=0, padx=10, pady=5, sticky="w")
area_entry = tk.Entry(tab2)
area_entry.grid(row=6, column=1, padx=10, pady=5)
##frame

# Create variables to hold user selections
broad_habitat_var = tk.StringVar()
specific_habitat_var = tk.StringVar()
selected_year_var=tk.StringVar()
selected_condition_var=tk.StringVar()
selected_difficulty_var=tk.StringVar()
selected_spatial_risk_var=tk.StringVar()
# Trace changes to the dropdown variables
broad_habitat_var.trace("w", update_specific_habitats)
specific_habitat_var.trace("w", update_score)
selected_year_var.trace("w",update_multiplier)
selected_condition_var.trace("w",update_cond_score)
selected_difficulty_var.trace("w",update_difficulty)
selected_spatial_risk_var.trace("w",update_spRisk)
# Create and place dropdown menus
ttk.Label(tab2, text="Select Broad Habitat Type:", style="Custom1.TLabel").grid(row=0, column=0, padx=10, pady=10,sticky="w")
broad_habitat_menu = ttk.Combobox(tab2, textvariable=broad_habitat_var, state="readonly")
broad_habitat_menu["values"] = broad_habitat_types
broad_habitat_menu.grid(row=0, column=1, padx=10, pady=10)

ttk.Label(tab2, text="Select Specific Habitat:", style="Custom1.TLabel").grid(row=1, column=0, padx=10, pady=10,sticky="w")
specific_habitat_menu = ttk.Combobox(tab2, textvariable=specific_habitat_var, state="readonly")
specific_habitat_menu.grid(row=1, column=1, padx=10, pady=10)

ttk.Label(tab2, text="Select time to target condition:", style="Custom1.TLabel").grid(row=2, column=0, padx=10, pady=10,sticky="w")
selected_year_menu = ttk.Combobox(tab2, textvariable=selected_year_var, state="readonly")
selected_year_menu["values"] = target_years
selected_year_menu.grid(row=2, column=1, padx=10, pady=10)

ttk.Label(tab2, text="Select Baseline condition:", style="Custom1.TLabel").grid(row=3, column=0, padx=10, pady=10,sticky="w")
selected_condition_menu = ttk.Combobox(tab2, textvariable=selected_condition_var, state="readonly")
selected_condition_menu["values"] = baseline_list
selected_condition_menu.grid(row=3, column=1, padx=10, pady=10)

ttk.Label(tab2, text="Select difficulty category:", style="Custom1.TLabel").grid(row=4, column=0, padx=10, pady=10,sticky="w")
selected_difficulty_menu = ttk.Combobox(tab2, textvariable=selected_difficulty_var, state="readonly")
selected_difficulty_menu["values"] = difficulty_list
selected_difficulty_menu.grid(row=4, column=1, padx=10, pady=10)

ttk.Label(tab2, text="Select Spatial risk category:", style="Custom1.TLabel").grid(row=5, column=0, padx=10, pady=10,sticky="w")
selected_spatial_risk_menu = ttk.Combobox(tab2, textvariable=selected_spatial_risk_var, state="readonly")
selected_spatial_risk_menu["values"] = spatial_risk_list
selected_spatial_risk_menu.grid(row=5, column=1, padx=10, pady=10)
calculate_button = tk.Button(tab2, text="Calculate biodiveristy units", command=calculate_output,
                              bg="darkgreen",  # Button background color
                             fg="black",    # Button text color

                             font=("Helvetica", 12,"bold"),
                             activebackground="#f57c00",  # Background color when pressed
                             activeforeground="darkgreen")
calculate_button.grid(row=8, column=0, columnspan=2, pady=10)
output_label = ttk.Label(tab2, text="Biodiversity gain:",style="Custom2.TLabel")
# Label to display the score
score_label = ttk.Label(tab2, text="", style="Custom2.TLabel")
score_label.grid(row=1, column=2, columnspan=2, pady=10)
score2_label = ttk.Label(tab2, text="", style="Custom2.TLabel")
score2_label.grid(row=2, column=2, columnspan=2, pady=10)
score3_label = ttk.Label(tab2,text="", style="Custom2.TLabel")
score3_label.grid(row=3, column=2, columnspan=2, pady=10)
score4_label = ttk.Label(tab2, text="", style="Custom2.TLabel")
score4_label.grid(row=4, column=2, columnspan=2, pady=10)
score5_label = ttk.Label(tab2, text="", style="Custom2.TLabel")
score5_label.grid(row=5, column=2, columnspan=2, pady=10)

output_label.grid(row=9, column=0, columnspan=2, pady=10)

save_button = tk.Button(tab2, text="Save Selections", command=save_selection, bg="darkgreen",  # Button background color
fg="black",    # Button text color

font=("Helvetica", 12,"bold"),
activebackground="#f57c00",  # Background color when pressed
activeforeground="darkgreen")
save_button.grid(row=10, column=0, columnspan=2, pady=10)

# Run the application
root.mainloop()
                             
