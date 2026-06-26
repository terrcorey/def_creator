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

sys.path.insert(0, "/home/tcorey/Desktop/workspace/def_updater/")
import update_def_labels as udl

def slug_to_formula(slug):
    """
    Converts a slug (e.g., '1H2-2H_p') to a chemical formula (e.g., '(1H)2(2H)+').

    :param slug: The isotopologue slug to convert.
    :return: The corresponding chemical formula as a string.
    """
    logging.debug(f"slug_to_formula: converting '{slug}'")
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
    logging.debug(f"slug_to_formula: result '{formula}'")
    return formula


def decompress_files(dir):
    logging.info(f"decompress_files: scanning '{dir}'")
    for r, d, f in os.walk(dir):
        for file in f:
            if file.endswith(".bz2"):
                logging.debug(f"decompress_files: decompressing '{os.path.join(r, file)}'")
                with open(os.path.join(r, file), "rb") as f_in:
                    data = bz2.decompress(f_in.read())
                with open(os.path.join(r, file[:-4]), "wb") as f_out:
                    f_out.write(data)
                logging.debug(f"decompress_files: wrote '{f_out.name}'")
            if (file.endswith(".states") or file.endswith(".trans")) and file + ".bz2" not in f:
                logging.debug(f"decompress_files: compressing '{os.path.join(r, file)}'")
                with open(os.path.join(r, file), "rb") as f_in:
                    data = f_in.read()
                with open(os.path.join(r, file + ".bz2"), "wb") as f_out:
                    f_out.write(bz2.compress(data))
                logging.debug(f"decompress_files: wrote '{f_out.name}'")


def make_templates(dir, template_path):
    logging.info(f"make_templates: creating def.json templates in '{dir}' from '{template_path}'")
    for r, d, f in os.walk(dir):
        if not d and "output" not in r:
            dest = os.path.join(r, f"{iso_slug}__{ds_name}.def.json")
            logging.debug(f"make_templates: copying template to '{dest}'")
            shutil.copy(template_path, dest)
    logging.info("make_templates: done")

def log_to_def_dict(iso_slug, key, value):
    path = os.path.join(work_dir, ds_name, f"{iso_slug}__{ds_name}.def.json")
    logging.debug(f"log_to_def_dict: setting '{key}' = {value!r} in '{path}'")
    if not os.path.exists(path):
        logging.error(f"log_to_def_dict: skipped '{path}' — file does not exist")
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
        logging.error(f"log_to_def_dict: key '{key}' not found in '{path}'")
        return
    logging.debug(f"log_to_def_dict: successfully updated '{key}' in '{path}'")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def log_common_info(dir):
    logging.info(f"log_common_info: writing shared dataset fields to all def.json files in '{dir}'")
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
                logging.debug(f"log_common_info: updating '{os.path.join(r, file)}'")
                for key, value in info_dict.items():
                    log_to_def_dict(iso_slug, key, value)
    logging.info("log_common_info: done")


def calculate_iso_info(dir):
    logging.info(f"calculate_iso_info: processing isotopologue directories in '{dir}'")
    electron_mass = 0.000548579909 # in Daltons
    charge = 0
    for d in os.listdir(dir):
        iso_dir = os.path.join(dir, d)
        if os.path.isdir(iso_dir) and re.match(r'^\d', d):
            iso_slug = d
            logging.info(f"calculate_iso_info: processing isotopologue '{iso_slug}'")
            log_to_def_dict(iso_slug, "Iso-slug", iso_slug)
            log_to_def_dict(iso_slug, "IsoFormula", slug_to_formula(iso_slug))
            isotopes = iso_slug.split("-")
            if isotopes[-1].endswith("p"):
                isotopes[-1] = isotopes[-1].split("_")[0]
                charge = 1 # When ExoMol starts making doubly charged species, update this
                logging.debug(f"calculate_iso_info: '{iso_slug}' is a cation (charge=1)")

            expanded = []
            for element in isotopes:
                if element[-1].isnumeric():
                    multi = int(element[-1])
                    element = element[:-1]
                    expanded.extend([element] * multi)
                else:
                    expanded.append(element)
            isotopes = expanded
            logging.debug(f"calculate_iso_info: expanded isotope list: {isotopes}")
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
                logging.debug(f"calculate_iso_info: {symbol}-{mass_num}: mass={iso.mass:.8f} Da, spin={spin}, nuc_spin_deg={nuc_spin_deg}")
                isotope_info.append({
                    "Isotope number": mass_num,
                    "Element symbol": symbol
                })
            mass = mass - charge * electron_mass
            log_to_def_dict(iso_slug, "Isotope information", isotope_info)
            masses = f"{mass:.8f} {mass * 1.66053907e-27:.8e}"
            log_to_def_dict(iso_slug, "Isotopologue mass (Da) and (kg)", masses)
            logging.info(f"calculate_iso_info: {iso_slug}: mass={masses}, total_nuc_spin_deg={int(total_deg)}")

def partition_function_info(dir):
    logging.info(f"partition_function_info: searching for .pf files in '{dir}'")
    for r, d, f in os.walk(dir):
        for file in f:
            if file.endswith(".pf"):
                pf_path = os.path.join(r, file)
                logging.info(f"partition_function_info: reading '{pf_path}'")
                temperatures = []
                q_values = []
                with open(pf_path, "r", encoding="utf-8") as f_in:
                    for line in f_in:
                        temp, q = line.split()
                        temperatures.append(float(temp))
                        q_values.append(float(q))
                if temperatures and q_values:
                    max_temp_pf = max(temperatures)
                    step_size = min(t2 - t1 for t1, t2 in zip(temperatures[:-1], temperatures[1:]))
                    logging.info(f"partition_function_info: {len(temperatures)} rows, max_temp={max_temp_pf}, step={step_size}")
                    log_to_def_dict(iso_slug, "Maximum temperature of partition function", max_temp_pf)
                    log_to_def_dict(iso_slug, "Step size of temperature", step_size)
                else:
                    logging.warning(f"partition_function_info: '{pf_path}' appears empty")

def count_states_and_find_max_energy(dir):
    logging.info(f"count_states_and_find_max_energy: searching for .states files in '{dir}'")
    for r, d, f in os.walk(dir):
        for file in f:
            if file.endswith(".states"):
                states_path = os.path.join(r, file)
                logging.info(f"count_states_and_find_max_energy: reading '{states_path}'")
                num_lines = 0
                max_energy = 0.0
                with open(states_path, "r") as f_in:
                    for line in f_in:
                        num_lines += 1
                        val = float(line.split()[1])
                        if val > max_energy:
                            max_energy = val
                logging.info(f"count_states_and_find_max_energy: {num_lines} states, max energy = {max_energy} cm-1")
                log_to_def_dict(iso_slug, "No. of states in .states file", num_lines)
                log_to_def_dict(iso_slug, "Higher energy with complete set of transitions (in cm-1)", max_energy)
                
def count_trans_and_find_max_wavenumber(dir):
    logging.info(f"count_trans_and_find_max_wavenumber: searching for .trans files in '{dir}'")
    for r, d, f in os.walk(dir):
        trans_files = [file for file in f if file.endswith(".trans")]
        if not trans_files:
            continue
        logging.debug(f"count_trans_and_find_max_wavenumber: found {len(trans_files)} .trans file(s) in '{r}'")
        total_lines = 0
        max_energy = 0.0
        for file in trans_files:
            trans_path = os.path.join(r, file)
            logging.info(f"count_trans_and_find_max_wavenumber: reading '{trans_path}'")
            file_lines = 0
            with open(trans_path, "rt") as f_in:
                for line in f_in:
                    total_lines += 1
                    file_lines += 1
                    val = float(line.split()[1])
                    if val > max_energy:
                        max_energy = val
            logging.debug(f"count_trans_and_find_max_wavenumber: '{file}' has {file_lines} transitions")
        logging.info(f"count_trans_and_find_max_wavenumber: {total_lines} transitions total, max wavenumber = {max_energy} cm-1")
        log_to_def_dict(iso_slug, "Total number of transitions", total_lines)
        log_to_def_dict(iso_slug, "Maximum wavenumber (in cm-1)", max_energy)

def make_def_files(dir):
    logging.info(f"make_def_files: generating .def files from def_dict.json files in '{dir}'")
    for r, d, f in os.walk(dir):
        for file in f:
            if file.endswith("def_dict.json"):
                dict_path = os.path.join(r, file)
                logging.debug(f"make_def_files: loading '{dict_path}'")
                with open(dict_path, "r", encoding="utf-8") as f_in:
                    def_dict = json.load(f_in)
                iso_slug = r.split(os.sep)[-2]
                def_structure_file_path = os.path.join("D:/git_repos/def_updater/other_materials/lib/def_structure.txt")
                def_file_path = os.path.join(r, f"{iso_slug}__{ds_name}.def")
                logging.info(f"make_def_files: writing '{def_file_path}'")
                udl.update_def(def_file_path, def_structure_file_path, def_dict)
                logging.info(f"make_def_files: wrote '{def_file_path}'")
                
def fill_label_desc(dir):
    logging.info(f"fill_label_desc: filling quantum label formats/descriptions in '{dir}'")
    with open("D:/git_repos/def_updater/other_materials/lib/standard_label_structure.json", "r", encoding="utf-8") as f:
        standard_labels: list[dict] = json.load(f)
        standard_label_list = [label["Quantum label"] for label in standard_labels]
    logging.debug(f"fill_label_desc: loaded {len(standard_labels)} standard labels")
    for r, d, f in os.walk(dir):
        for file in f:
            if file == "def_dict.json":
                dict_path = os.path.join(r, file)
                logging.debug(f"fill_label_desc: processing '{dict_path}'")
                with open(dict_path, "r", encoding="utf-8") as f_in:
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
                        logging.debug(f"fill_label_desc: matched '{label['Quantum label']}' -> lookup='{lookup}'")
                    else:
                        logging.warning(f"fill_label_desc: no standard match for quantum label '{label['Quantum label']}' in '{dict_path}'")
                with open(dict_path, "w", encoding="utf-8") as f_out:
                    json.dump(def_dict, f_out, indent=4)
                logging.debug(f"fill_label_desc: saved '{dict_path}'")

def verify_files(dir):
    logging.info(f"verify_files: verifying file structure in '{dir}'")
    for iso_slug in os.listdir(dir):
        logging.info(f"verify_files: checking isotopologue '{iso_slug}'")
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

        logging.debug(f"verify_files: '{iso_slug}' file counts before decompression: "
                      f"bz2={len(files_by_type['bz2'])}, states={len(files_by_type['states'])}, "
                      f"trans={len(files_by_type['trans'])}, pf={len(files_by_type['pf'])}")

        for path in files_by_type["bz2"]:
            logging.debug(f"verify_files: decompressing '{os.path.basename(path)}' for validation")
            with open(path, "rb") as f_in:
                data = bz2.decompress(f_in.read())
            decompressed_path = path.replace(".bz2", "")
            with open(decompressed_path, "wb") as f_out:
                f_out.write(data)
            ext = f_out.name.split(".")[-1]
            if ext in files_by_type:
                files_by_type[ext].append(decompressed_path)
                logging.debug(f"verify_files: registered decompressed file '{f_out.name}' as .{ext}")

        states_count = len(files_by_type["states"])
        trans_count = len(files_by_type["trans"])
        pf_count = len(files_by_type["pf"])
        logging.debug(f"verify_files: '{iso_slug}' final counts: states={states_count}, trans={trans_count}, pf={pf_count}")

        for path in files_by_type["states"]:
            states_file = os.path.basename(path)
            logging.debug(f"verify_files: spot-checking .states file '{states_file}'")
            try:
                test_states = pd.read_csv(path, sep=r"\s+", header = None, nrows = 5)
                logging.debug(f"verify_files: '{path}' OK ({len(test_states.columns)} columns)")
                # Add extra tests later if needed, e.g., check for expected number of columns, data types, etc.
            except Exception as e:
                logging.error(f"verify_files: failed to read '{path}': {e}")
                sys.exit(1)

        for path in files_by_type["trans"]:
            trans_file = os.path.basename(path)
            logging.debug(f"verify_files: spot-checking .trans file '{trans_file}'")
            try:
                test_trans = pd.read_csv(path, sep=r"\s+", header = None, nrows = 5)
                assert len(test_trans.columns) >= 3, logging.error(f"Expected 3 columns or more in {trans_file}")
                logging.debug(f"verify_files: '{path}' OK ({len(test_trans.columns)} columns)")
                # Add extra tests later if needed, e.g., check for expected number of columns, data types, etc.
            except Exception as e:
                logging.error(f"verify_files: failed to read '{path}': {e}")
                sys.exit(1)

        if states_count != 1:
            logging.error(f"verify_files: expected 1 .states file for '{iso_slug}', found {states_count}")
            sys.exit(1)
        if pf_count != 1:
            logging.error(f"verify_files: expected 1 .pf file for '{iso_slug}', found {pf_count}")
            sys.exit(1)
        if trans_count < 1:
            logging.error(f"verify_files: expected at least 1 .trans file for '{iso_slug}', found {trans_count}")
            sys.exit(1)
        logging.info(f"verify_files: '{iso_slug}' passed verification")

def make_input(dir):
    os.makedirs(os.path.join(dir, f"{ds_name}_input.inp"), exist_ok=True)

def verify_input(dir):
    pass

if __name__ == "__main__":
    os.chdir(os.path.dirname(__file__))
    global ds_name

    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('def_creation.log'),
            logging.StreamHandler(sys.stdout),
        ]
    )

    args = [arg for arg in sys.argv if not arg.startswith("--")]
    opt_args = [arg for arg in sys.argv if arg.startswith("--")]
    work_dir = args[1]
    ds_name = os.path.basename(work_dir)

    logging.info(f"Starting def_creator: work_dir='{work_dir}', ds_name='{ds_name}', options={opt_args}")

    template_path = os.path.join(os.path.dirname(__file__), "def_templates", "exomol.json")
    logging.debug(f"Template path: '{template_path}'")

    logging.info("Step: verify_files")
    verify_files(work_dir) # Verifies .states, .trans and .pf files

    if "--init" in opt_args:
        logging.info("Mode: --init")
        logging.info("Step: make_templates")
        make_templates(work_dir, template_path) # Creates empty def dicts for each isotopologue
        for iso_slug in os.listdir(work_dir):
            iso_dir = os.path.join(work_dir, iso_slug)
            logging.info(f"Processing isotopologue '{iso_slug}' in '{iso_dir}'")
            log_to_def_dict(iso_slug, "Isotopologue dataset name", ds_name)
            logging.info("Step: calculate_iso_info")
            calculate_iso_info(iso_dir) # Logs information about isotopologues, including mass and nuclear spin degeneracy
            logging.info("Step: partition_function_info")
            partition_function_info(iso_dir) # Extracts partition function information from .pf files
            logging.info("Step: count_states_and_find_max_energy")
            count_states_and_find_max_energy(iso_dir) # Counts the number of states and finds the maximum energy in .states files
            logging.info("Step: count_trans_and_find_max_wavenumber")
            count_trans_and_find_max_wavenumber(iso_dir) # Counts the number of transitions and finds the maximum wavenumber in .trans files
        logging.info("Step: make_input")
        make_input(iso_dir) # Creates input file
        logging.info("--init complete")
    else:
        logging.info("Mode: standard (no --init)")
        logging.info("Step: verify_input")
        verify_input(work_dir) # Verifies input files for each isotopologue
        logging.info("Step: log_common_info")
        log_common_info(work_dir) # Logs information that are common to all isotopologues
        logging.info("Step: fill_label_desc")
        fill_label_desc(work_dir) # Fills in the format and description for quantum labels in def dicts
        logging.info("Step: make_def_files")
        make_def_files(work_dir) # Creates .def files for each isotopologue based on the def dicts
        logging.info("Done")