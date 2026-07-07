"""
SMILES generation and InChI/InChIKey derivation for ExoMol isotopologues.

Two functions:
  smiles_from_atoms  — builds a SMILES string from the atom list in the iso_slug
  inchi_from_smiles  — derives InChI and InChIKey from a SMILES string via RDKit
"""
import logging
from collections import Counter


def smiles_from_atoms(atoms: list[tuple[int, str]], charge: int) -> str | None:
    """
    Auto-generates an isotopologue SMILES from (mass_number, element_symbol) atoms.

    Rules:
    - Diatomic (2 atoms): chain SMILES [massSymbol][massSymbol]
    - Polyatomic, all distinct elements: same chain SMILES
    - Polyatomic with any repeated element: returns None — user must supply SMILES

    The molecular charge (0 or ±1, ...) is added to the last atom's bracket.
    The generated SMILES always goes into .inp for the user to verify and correct.
    """
    n = len(atoms)
    element_counts = Counter(sym for _, sym in atoms)
    all_distinct = all(c == 1 for c in element_counts.values())

    if n > 2 and not all_distinct:
        return None

    parts = [f"[{m}{s}]" for m, s in atoms]

    if charge != 0:
        charge_str = f"+{abs(charge)}" if abs(charge) > 1 and charge > 0 else \
                     f"-{abs(charge)}" if abs(charge) > 1 else \
                     "+" if charge > 0 else "-"
        last = parts[-1]
        parts[-1] = last[:-1] + charge_str + "]"

    return "".join(parts)


def inchikey_from_inchi(inchi_str: str) -> str | None:
    """
    Derives the InChIKey from a pre-existing InChI string using RDKit.
    Useful when the user supplies inchi manually but leaves inchikey blank.
    Returns the InChIKey string, or None if RDKit is unavailable or the InChI is invalid.
    """
    try:
        from rdkit.Chem.inchi import InchiToInchiKey
    except ImportError:
        logging.warning("inchi: RDKit not available — InChIKey derivation skipped")
        return None
    result = InchiToInchiKey(inchi_str)
    if not result:
        logging.warning(f"inchi: RDKit could not derive InChIKey from InChI '{inchi_str[:40]}...'")
    return result or None


def inchi_from_smiles(smiles: str, iso_slug: str = "") -> tuple[str, str] | None:
    """
    Derives (InChI, InChIKey) from a SMILES string using RDKit.
    Falls back to sanitize=False for radicals / non-octet molecules.
    Returns None if RDKit is unavailable or generation fails.
    """
    try:
        from rdkit import Chem
        from rdkit.Chem.inchi import MolToInchi, InchiToInchiKey
    except ImportError:
        logging.warning("inchi: RDKit not available — InChI/InChIKey derivation skipped")
        return None

    label = iso_slug or smiles

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        mol = Chem.MolFromSmiles(smiles, sanitize=False)
        if mol is None:
            logging.warning(f"inchi: RDKit could not parse SMILES '{smiles}' for '{label}'")
            return None

    inchi_str = MolToInchi(mol)
    if inchi_str is None:
        logging.warning(f"inchi: RDKit failed to generate InChI for '{label}'")
        return None

    inchikey_str = InchiToInchiKey(inchi_str)
    return (inchi_str, inchikey_str) if inchikey_str else None
