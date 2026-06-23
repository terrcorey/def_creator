import logging
import os
import re
import bz2
import shutil
import json
import datetime
import sys
from typing import Literal
import pandas as pd
from mendeleev import isotope as md_isotope

sys.path.insert(0, "D:/git_repos/def_updater")
import update_def_labels as udl

def slug_to_formula(slug):
    """
    Converts a slug (e.g., '1H2-2H_p') to a chemical formula (e.g., '(1H)2(2H)+').
    
    :param slug: The isotopologue slug to convert.
    :return: The corresponding chemical formula as a string.
    """
    slug = slug.replace('_p', '+')  # Replace '_p' with '+' for compatibility
    parts = slug.split('-')
    formula = ''
    for part in parts:
        chars = list(part)
        chars.insert(0, '(')  # Insert '(' at the beginning
        chars.reverse()
        for i, c in enumerate(chars):
            if c.isalpha():
                first_alpha = i
                break
        chars.insert(i, ")")
        chars.reverse()
        formula = formula + ''.join(chars)
    formula = formula.replace('(cis)', 'cis-')
    formula = formula.replace('(trans)', 'trans-')
    return formula


def decompress_files(dir):
    for r, d, f in os.walk(dir):
        for file in f:
            if file.endswith(".bz2"):
                with open(os.path.join(r, file), "rb") as f_in:
                    data = bz2.decompress(f_in.read())
                with open(os.path.join(r, file[:-4]), "wb") as f_out:
                    f_out.write(data)
            if (file.endswith(".states") or file.endswith(".trans")) and file + ".bz2" not in f:
                with open(os.path.join(r, file), "rb") as f_in:
                    data = f_in.read()
                with open(os.path.join(r, file + ".bz2"), "wb") as f_out:
                    f_out.write(bz2.compress(data))


def make_templates(dir, template_path):
    for r, d, f in os.walk(dir):
        if not d and "output" not in r:
            shutil.copy(template_path, os.path.join(r, f"{iso_slug}__{ds_name}.def.json"))

def log_to_def_dict(iso_slug, key, value):
    path = os.path.join(work_dir, ds_name, f"{iso_slug}__{ds_name}.def.json")
    if not os.path.exists(path):
        logging.error(f"Skipped {path} as it does not exist.")
        return
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    def search_and_update_key(d, key, value) -> bool:
        """Recursively searches for a key in a nested dictionary and updates its value."""
        if key in d:
            d[key] = value
            return True
        for k, v in d.items():
            if isinstance(v, dict):
                if search_and_update_key(v, key, value):
                    return True
        return False
    if not search_and_update_key(data, key, value):
        logging.error(f"Key '{key}' not found in {path}")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def log_common_info(dir):
    qn_labels = [
            {
                "Quantum label": "+/-",
                "Format quantum label": "",
                "Description quantum label": ""
            },
            {
                "Quantum label": "e/f",
                "Format quantum label": "",
                "Description quantum label": ""
            }
        ]
    aux_labels = [
            {
                "Auxiliary title": "SourceType",
                "Format title": "A2 %2s",
                "Description title": "Ma=MARVEL,Ca=Calculated,EH=Effective Hamiltonian,IE=Isotopologue extrapolation"
            },
            {
                "Auxiliary title": "Ecal",
                "Format title": "F12.6 %12.6f",
                "Description title": "Calculated energy in cm-1"
            }
        ]
    info_dict = {
        "ID": "EXOMOL.DEF",
        "Isotopologue dataset name": ds_name,
        "Version number with format YYYYMMDD": datetime.datetime.now().strftime("%Y%m%d"),
        "Number of atoms": None,
        "Symmetry group": sym_group,
        "Number of irreducible representations": num_irreps,
        "Maximum temperature of linelist": max_temp,
        "Maximum wavenumber (in cm-1)": None,
        "Higher energy with complete set of transitions (in cm-1)": None,
        "Maximum temperature of partition function": None,
        "Step size of temperature": None,
        "No. of pressure broadeners available": num_broadeners,
        "Cooling function availability (1=yes, 0=no)": cf_bool,
        "Specific heat availability (1=yes, 0=no)": cp_bool,
        "Photo-absorption continuum cross-sections availability (1=yes, 0=no)": photo_bool,
        "No. of states in .states file": None,
        "bools": {
            "Hyperfine resolved dataset": hyperfine_bool,
            "Lifetime availability": lifetime_bool,
            "Uncertainty availability": uncertainty_bool,
            "Lande g-factor availability": lande_bool
        },
        "Quantum case label": quantum_case_label,
        "No. of quantum number types": None,
        "No. of quanta defined": None,
        "Quantum labels": qn_labels,
        "Auxiliary labels": aux_labels,
        "No. of transition files": None
    }
    for r, d, f in os.walk(dir):
        for file in f:
            if file.endswith("def_dict.json"):
                for key, value in info_dict.items():
                    log_to_def_dict(iso_slug, key, value)


def calculate_iso_info(dir):
    electron_mass = 0.000548579909 # in Daltons
    charge = 0
    for d in os.listdir(dir):
        iso_dir = os.path.join(dir, d)
        if os.path.isdir(iso_dir) and re.match(r'^\d', d):
            iso_slug = d
            log_to_def_dict(iso_slug, "Iso-slug", iso_slug)
            log_to_def_dict(iso_slug, "IsoFormula", slug_to_formula(iso_slug))
            isotopes = iso_slug.split("-")
            if isotopes[-1].endswith("p"):
                isotopes[-1] = isotopes[-1].split("_")[0]
                charge = 1 # When ExoMol starts making doubly charged species, update this

            expanded = []
            for element in isotopes:
                if element[-1].isnumeric():
                    multi = int(element[-1])
                    element = element[:-1]
                    expanded.extend([element] * multi)
                else:
                    expanded.append(element)
            isotopes = expanded
            mass = 0
            isotope_info = []
            total_deg = 1
            for i in isotopes:
                mass_num, symbol = re.match(r'^(\d+)([A-Za-z]+)$', i).groups()
                mass_num = int(mass_num)
                iso = md_isotope(symbol, mass_num)
                raw_spin = iso.spin
                if raw_spin is None:
                    spin = 0
                elif "/" in str(raw_spin):
                    num, den = str(raw_spin).split("/")
                    spin = int(num) / int(den)
                else:
                    spin = int(raw_spin)
                nuc_spin_deg = 2 * spin + 1
                total_deg *= nuc_spin_deg
                mass += iso.mass
                isotope_info.append({
                    "Isotope number": mass_num,
                    "Element symbol": symbol
                })
            mass = mass - charge * electron_mass
            log_to_def_dict(iso_slug, "Isotope information", isotope_info)
            masses = f"{mass:.8f} {mass * 1.66053907e-27:.8e}"
            log_to_def_dict(iso_slug, "Isotopologue mass (Da) and (kg)", masses)
            print(f"{iso_slug}: {masses}, {int(total_deg)}")

def partition_function_info(dir):
    for r, d, f in os.walk(dir):
        for file in f:
            if file.endswith(".pf"):
                print("Extracting partition function info from", os.path.join(r, file))
                temperatures = []
                q_values = []
                with open(os.path.join(r, file), "r", encoding="utf-8") as f_in:
                    for line in f_in:
                        temp, q = line.split()
                        temperatures.append(float(temp))
                        q_values.append(float(q))
                if temperatures and q_values:
                    log_to_def_dict(iso_slug, "Maximum temperature of partition function", max(temperatures))
                    log_to_def_dict(iso_slug, "Step size of temperature", min(t2 - t1 for t1, t2 in zip(temperatures[:-1], temperatures[1:])))

def count_states_and_find_max_energy(dir):
    for r, d, f in os.walk(dir):
        for file in f:
            if file.endswith(".states.bz2"):
                print("Counting states in", os.path.join(r, file))
                num_lines = 0
                max_energy = 0.0
                with bz2.open(os.path.join(r, file), "rt") as f_in:
                    for line in f_in:
                        num_lines += 1
                        val = float(line.split()[1])
                        if val > max_energy:
                            max_energy = val
                log_to_def_dict(iso_slug, "No. of states in .states file", num_lines)
                log_to_def_dict(iso_slug, "Higher energy with complete set of transitions (in cm-1)", max_energy)
                print(f"  {num_lines} states, max energy = {max_energy} cm-1")
                
def count_trans_and_find_max_wavenumber(dir):
    for r, d, f in os.walk(dir):
        trans_files = [file for file in f if file.endswith(".trans.bz2")]
        if not trans_files:
            continue
        total_lines = 0
        max_energy = 0.0
        for file in trans_files:
            print("Counting transitions in", os.path.join(r, file))
            with bz2.open(os.path.join(r, file), "rt") as f_in:
                for line in f_in:
                    total_lines += 1
                    val = float(line.split()[1])
                    if val > max_energy:
                        max_energy = val
        log_to_def_dict(iso_slug, "Total number of transitions", total_lines)
        log_to_def_dict(iso_slug, "Maximum wavenumber (in cm-1)", max_energy)
        print(f"  {total_lines} transitions total, max wavenumber = {max_energy} cm-1")

def make_def_files(dir):
    for r, d, f in os.walk(dir):
        for file in f:
            if file.endswith("def_dict.json"):
                with open(os.path.join(r, file), "r", encoding="utf-8") as f_in:
                    def_dict = json.load(f_in)
                iso_slug = r.split(os.sep)[-2]
                def_structure_file_path = os.path.join("D:/git_repos/def_updater/other_materials/lib/def_structure.txt")
                def_file_path = os.path.join(r, f"{iso_slug}__{ds_name}.def")
                udl.update_def(def_file_path, def_structure_file_path, def_dict)
                
def fill_label_desc(dir):
    with open("D:/git_repos/def_updater/other_materials/lib/standard_label_structure.json", "r", encoding="utf-8") as f:
        standard_labels: list[dict] = json.load(f)
        standard_label_list = [label["Quantum label"] for label in standard_labels]
    for r, d, f in os.walk(dir):
        for file in f:
            if file == "def_dict.json":
                with open(os.path.join(r, file), "r", encoding="utf-8") as f_in:
                    def_dict = json.load(f_in)
                for label in def_dict["Quantum labels"]:
                    if ":" in label["Quantum label"]:
                        base_label = label["Quantum label"].split(":")[1]
                    else:
                        base_label = ""
                    if label["Quantum label"] in standard_label_list or (":" in label["Quantum label"] and base_label in standard_label_list):
                        lookup = base_label if ":" in label["Quantum label"] and base_label in standard_label_list else label["Quantum label"]
                        standard_label = next(item for item in standard_labels if item["Quantum label"] == lookup)
                        label["Format quantum label"] = standard_label["Format quantum label"]
                        label["Description quantum label"] = standard_label["Description quantum label"]
                with open(os.path.join(r, file), "w", encoding="utf-8") as f_out:
                    json.dump(def_dict, f_out, indent=4)

def verify_files(dir):
    for iso_slug in os.listdir(dir):
        files_by_type = {
        "bz2": [],
        "states": [],
        "trans": [],
        "pf": []
        }
        for r, d, f in os.walk(os.path.join(dir, iso_slug)):
            for file in f:
                ext = file.split(".")[-1]
                if ext in files_by_type:
                    files_by_type[ext].append(os.path.join(r, file))

        for file in files_by_type["bz2"]:
            with open(file, "rb") as f_in:
                data = bz2.decompress(f_in.read())
            os.makedirs(os.path.join(r, file.replace(".bz2", "")), exist_ok=True)
            with open(os.path.join(r, file.replace(".bz2", "")), "wb") as f_out:
                f_out.write(data)
            ext = f_out.name.split(".")[-1]
            if ext in files_by_type:
                files_by_type[ext].append(f_out.name)
        states_count = len(files_by_type["states"])
        trans_count = len(files_by_type["trans"])
        pf_count = len(files_by_type["pf"])
        for file in files_by_type["states"]:
            states_file = os.path.join(r, file)
            try:
                test_states = pd.read_csv(states_file, sep=r"\s+", header = None, nrows = 5)
                # Add extra tests later if needed, e.g., check for expected number of columns, data types, etc.
            except Exception as e:
                logging.error(f"Error reading {states_file}: {e}")
                sys.exit(1)

        for file in files_by_type["trans"]:
            trans_file = os.path.join(r, file)
            try:
                test_trans = pd.read_csv(trans_file, sep=r"\s+", header = None, nrows = 5)
                assert len(test_trans.columns) >= 3, logging.error(f"Expected 3 columns or more in {trans_file}")
                # Add extra tests later if needed, e.g., check for expected number of columns, data types, etc.
            except Exception as e:
                logging.error(f"Error reading {trans_file}: {e}")
                sys.exit(1)
        
        if states_count != 1:
            logging.error(f"Expected 1 .states file for isotopologue {iso_slug}, found {states_count}")
            sys.exit(1)
        if pf_count != 1:
            logging.error(f"Expected 1 .pf file for isotopologue {iso_slug}, found {pf_count}")
            sys.exit(1)
        if trans_count < 1:
            logging.error(f"Expected at least 1 .trans file for isotopologue {iso_slug}, found {trans_count}")
            sys.exit(1)

def make_input(dir):
    os.makedirs(os.path.join(dir, f"{ds_name}_input.inp"), exist_ok=True)

def verify_input(dir):
    pass

if __name__ == "__main__":
    os.chdir(os.path.dirname(__file__))
    global ds_name

    logging.basicConfig(filename='def_creation.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    args = [arg for arg in sys.argv if not arg.startswith("--")]
    opt_args = [arg for arg in sys.argv if arg.startswith("--")]
    work_dir = args[1]
    ds_name = os.path.basename(work_dir)

    verify_files(work_dir) # Verifies .states, .trans and .pf files
    template_path = os.path.join(os.path.dirname(__file__), "def_templates", "exomol.json")

    if "--init" in opt_args:
        make_templates(work_dir, template_path) # Creates empty def dicts for each isotopologue
        for iso_slug in os.listdir(work_dir):
            iso_dir = os.path.join(work_dir, iso_slug)
            log_to_def_dict(iso_slug, "Isotopologue dataset name", ds_name)
            calculate_iso_info(iso_dir) # Logs information about isotopologues, including mass and nuclear spin degeneracy
            partition_function_info(iso_dir) # Extracts partition function information from .pf files
            count_states_and_find_max_energy(iso_dir) # Counts the number of states and finds the maximum energy in .states files
            count_trans_and_find_max_wavenumber(iso_dir) # Counts the number of transitions and finds the maximum wavenumber in .trans files
        make_input(iso_dir) # Creates input file
    else:
        verify_input(work_dir) # Verifies input files for each isotopologue

        log_common_info(work_dir) # Logs information that are common to all isotopologues
        fill_label_desc(work_dir) # Fills in the format and description for quantum labels in def dicts
        make_def_files(work_dir) # Creates .def files for each isotopologue based on the def dicts