# -*- coding: utf-8 -*-
"""
Created on Mon Dec  2 15:40:44 2024

@author: Test
"""


import tkinter as tk 
from tkinter import filedialog, messagebox, Tk,ttk, Label, PhotoImage
from PIL import Image, ImageTk
import os
import json
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import csv
#%%Loss Calculator
# Initialize global variables for shapefile paths
shapefile1_path = None
shapefile2_path = None

#%%reading files and initiating new columns
def process_shapefiles(significance_score):
    """
    This function reads the shapefiles and store the attribute data in a geodataframe that
    can be analysed. Further, the function includes various modifications to the
    geodataframes such as adding columns, assigning scores in the new columns, 
    calculation of biodiversity units,and finally overlaying the shapefiles 
    to extract the areas that account for biodiversity loss.

    Parameters
    ----------
    significance_score : Float
        this number the user enters, it is a fixed value per campus

    Returns
    -------
    2 Geodataframes
    intersection datafram

    """
    try:
        # Ensure both shapefiles are loaded
        if not shapefile1_path or not shapefile2_path:
            messagebox.showerror("Error", "Please select both files.")
            return
        
        
        gdf1=gpd.read_file(shapefile1_path)
        gdf2 = gpd.read_file(shapefile2_path)
      
      # Ensure both are in the same coordinate reference system (CRS)
        if gdf1.crs != gdf2.crs:
          gdf2 = gdf2.to_crs(gdf1.crs)
        gdf1['Condition score']=np.nan
        gdf1['Distinctiveness score']=np.nan
        gdf1['Biodiversity units']=np.nan
        gdf1['Significance score']=significance_score
        
       
 #%%assign condition scores to all rows in gdf1
        gdf1.loc[gdf1['Baseline Condition']=="1. Good","Condition score"]=3
        gdf1.loc[gdf1['Baseline Condition']=="2. Fairly Good","Condition score"]=2.5
        gdf1.loc[gdf1['Baseline Condition']=="3. Moderate","Condition score"]=2
        gdf1.loc[gdf1['Baseline Condition']=="4. Fairly Poor","Condition score"]=1.5
        gdf1.loc[gdf1['Baseline Condition']=="5. Poor","Condition score"]=1
        gdf1.loc[gdf1['Baseline Condition']=="6. N/A - Other","Condition score"]=1  
#%%assign distinctiveness scores,based on habitat type
        gdf1.loc[gdf1['Baseline Distinctiveness']=="V.Low","Distinctiveness score"]=0
        gdf1.loc[gdf1['Baseline Distinctiveness']=="Low","Distinctiveness score"]=2
        gdf1.loc[gdf1['Baseline Distinctiveness']=="Medium","Distinctiveness score"]=4
        gdf1.loc[gdf1['Baseline Distinctiveness']=="High","Distinctiveness score"]=6
        gdf1.loc[gdf1['Baseline Distinctiveness']=="V.High","Distinctiveness score"]=8
#%%Biodiversity units”=area X condition X Strategic significance X distinctiveness 
        gdf1['Biodiversity units'] =round((
        gdf1['Area']/10000 * 
        gdf1['Condition score'] * 
        gdf1['Significance score'] * 
        gdf1['Distinctiveness score']),2
        )
#%%intersect the two shapefiles excluding urban areas from intersection
        gdf1 = gdf1[gdf1['Baseline Broad Habitat Type'] != 'Urban']
        intersection = gpd.overlay(gdf1, gdf2, how='intersection', keep_geom_type=False)
        intersection = intersection[intersection.geometry.type == 'Polygon']
        intersection['Loss area (ha)'] = round(intersection.area/10000,2)
        area_loss=pd.DataFrame(intersection['Loss area (ha)'])
        biodiversity_units=pd.DataFrame(intersection['Biodiversity units'])
        intersection_area_df=pd.concat([area_loss,biodiversity_units],axis=1)
        save_gdf_as_shapefile(intersection) 
        save_df_as_csv(intersection_area_df)
        
    except Exception as e:
        messagebox.showerror("Error", f"An error occurred during processing: {e}")


#%% Function to open file dialog for shapefile selection and get the significance score
def select_shapefile1():
    """
    This function is the command to be used for the graphical user interface button
    that asks the user to select a file, clicking the button triggers this funtion. 
    It dispays a file dialog to ask the user to select the first shapefile.
    Returns
    -------
    Message of success or failure of selecting a shapefile
    """
    global shapefile1_path
    shapefile1_path = filedialog.askopenfilename(title="Select First File (Habitat Baseline)", 
    filetypes=[("Supported Files", "*.shp *.gpkg"), ("Shapefiles", "*.shp"), ("GeoPackages", "*.gpkg")])
    if shapefile1_path:
        messagebox.showinfo("File Selected", f"Habitat file selected: {shapefile1_path}")

#%% Function to open file dialog for selecting shapefile2
def select_shapefile2():
    """
    This function is the command to be used for the graphical user interface button
    that asks the user to select a file, clicking the button triggers this funtion. 
    It dispays a file dialog to ask the user to select the second shapefile.
    Returns
    -------
    Message of success or failure of selecting a shapefile
    """
    global shapefile2_path
    shapefile2_path = filedialog.askopenfilename(title="Select Second Shapefile (Intersection Layer)", filetypes=[("Shapefiles", "*.shp")])
    if shapefile2_path:
        messagebox.showinfo("File Selected", f"Second shapefile selected: {shapefile2_path}")

#%% to save the output shapefile

def save_gdf_as_shapefile(gdf):
    """
    This function shows a window to save the geodataframe as a shapefile, and then shows 
    a message of success or failure of the saving.

    Parameters
    ----------
    gdf : Geodataframe
        

    Returns
    -------
    None.

    """
 
    # Save file dialog to choose save location
    output_file = filedialog.asksaveasfilename(
        title="Save Processed Shapefile",
        defaultextension=".shp",
        filetypes=[("Shapefiles", "*.shp")]
    )
    if output_file:
        try:
            gdf.to_file(output_file)
            messagebox.showinfo("Success", f"Shapefile saved successfully at {output_file}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save shapefile: {e}")
    else:
        messagebox.showinfo("Cancelled", "Save operation was cancelled.")
#%% to save the output csv file
def save_df_as_csv(df):
    """
    This function shows a window to save the required dataframe, and then shows 
    a message of success or failure of the saving the dataframe as csv file.

    Parameters
    ----------
    gdf : Dataframe
        

    Returns
    -------
    None.

    """
    
    csv_file=filedialog.asksaveasfilename(
        title="Save areas of biodiversity loss",
        defaultextension=".csv",
        filetypes=[("CSV files","*.csv")]
                                          )
    if csv_file:
        try: 
            df.to_csv(csv_file, index=True)
            messagebox.showinfo("Success",f"table saved successfully at{csv_file}")
        except Exception as e:
            messagebox.showerror("Error",f"Failed to save csv file:{e}")
    else:
        messagebox.showinfo("Cancelled","Save operation was cancelled")
#%%Gain calculator
# Load the habitats CSV file
file_path1 = 'C:/Users/Test/Downloads/QGIS project/all_habitats.csv'
data = pd.read_csv(file_path1)

# Convert to JSON
json_habitatdata = data.to_json(orient="records", indent=4)

# Save to a file (optional, for reference)
json_file_path1 = 'C:/Users/Test/Downloads/QGIS project/all_habitats.json'
with open(json_file_path1, 'w') as json_file:
    json_file.write(json_habitatdata)

# Later: Read the JSON file and load it as a Python object
with open(json_file_path1, 'r') as json_file:
    json_habitats= json.load(json_file)
    #%%
# Load the targetyearCSV file
file_path2 = 'C:/Users/Test/Downloads/QGIS project/target_year.csv'
data = pd.read_csv(file_path2)

# Convert to JSON
json_yearsdata = data.to_json(orient="records", indent=4)


# Save to a file (optional, for reference)
json_file_path2 = 'C:/Users/Test/Downloads/QGIS project/targetYearJson.json'
with open(json_file_path2, 'w') as json_file:
    json_file.write(json_yearsdata)
    
with open(json_file_path2, 'r') as json_file:
    json_target_year= json.load(json_file)


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
# Create main application window for both calculators:
root = tk.Tk()
root.title("Biodiversity Calculator")
root.config(bg='white')
root.iconbitmap('C:/Users/Test/Downloads/QGIS project/biodiversity.ico')


#create tabs:
notebook = ttk.Notebook(root)
notebook.pack(expand=True, fill="both")  # Allow tabs to fill the entire window
#%%
 #Load the logo image
try:
    logo_image = Image.open("C:/Users/Test/Downloads/QGIS project/logo_ugent.png").resize((80,80))  # Adjust logo size
    logo_tk = ImageTk.PhotoImage(logo_image)
except FileNotFoundError:
    logo_tk = None
#load another logo
try:
    logo_image2 = Image.open("C:/Users/Test/Downloads/QGIS project/go_logo.png").resize((80,50))  # Adjust logo size
    logo_tk2 = ImageTk.PhotoImage(logo_image2)
except FileNotFoundError:
    logo_tk2 = None
    
#%%

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

#%%
tab1 = ttk.Frame(notebook,style="Custom.TFrame")
tab1.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
notebook.add(tab1,text="Loss Calulator")

tab2 = ttk.Frame(notebook,style="Custom.TFrame")
tab2.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
notebook.add(tab2,text="Gain Calulator")
#%%
if logo_tk:
    logo_label1 = tk.Label(tab1, image=logo_tk, bg="white")  # Set background to match tab's styling
    logo_label1.place(x=10, rely=1.0, anchor="sw")  # Position logo in top-left corner of Tab 1
# Add a logo to Tab 2
if logo_tk:
    logo_label2 = tk.Label(tab2, image=logo_tk, bg="white")
    logo_label2.place(x=10, rely=1.0, anchor="sw")  # Position logo in top-left corner of Tab 2
if logo_tk2:
    logo_label3 = tk.Label(tab1, image=logo_tk2, bg="white")  # Set background to match tab's styling
    logo_label3.place(relx=1.0,rely=1.0, anchor="se")  # Position logo in top-left corner of Tab 1
# Add a logo to Tab 2
if logo_tk:
    logo_label4 = tk.Label(tab2, image=logo_tk2, bg="white")
    logo_label4.place(relx=1.0,rely=1.0, anchor="se")  # Position l
#%%

#loss tab1
# Instruction label
label = tk.Label(tab1, text="Select shapefiles to process",background="white",  # Match the frame's background
foreground="darkgreen",   # Text color
font=( 'Helvetica',12, "bold"))
label.pack(pady=10)


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

# Button to select second shapefile
select_button2 = tk.Button(tab1, text="Select Planned Development", command=select_shapefile2,bg="darkgreen",  # Button background color
fg="black",    # Button text color
font=("Helvetica", 12,"bold"),
activebackground="#f57c00",  # Background color when pressed
activeforeground="darkgreen")
select_button2.pack(pady=5)

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


