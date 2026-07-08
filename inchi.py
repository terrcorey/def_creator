"""
InChI/InChIKey derivation for ExoMol isotopologues.

The user supplies the base (non-isotopic) SMILES of the molecule once at the dataset
level.  For each isotopologue, derive_iso_inchi() assigns the isotope mass numbers from
the iso_slug and generates the isotopologue-specific InChI/InChIKey via RDKit — the user
never needs to fill in per-isotopologue InChI/InChIKey fields.
"""
import logging


def base_smiles_from_atoms(atoms: list[tuple[int, str]], charge: int) -> str | None:
    """
    Auto-generates the base (non-isotopic) SMILES for the molecule described by
    the iso_slug atom list, for pre-filling the [dataset] smiles field at --init time.

    Works for diatomics and molecules where all elements are distinct — uses a
    linear chain `[Symbol][Symbol]...` without mass numbers.
    Returns None for polyatomics with any repeated element (user must supply SMILES).

    The generated SMILES is always written to .inp for the user to verify.
    Common issues to mention to users: radicals need bracket atoms ([Al][H] not AlH);
    charged species need the charge on one atom; topology is assumed linear — correct
    if the actual molecule is not linear.
    """
    from collections import Counter

    n = len(atoms)
    element_counts = Counter(sym for _, sym in atoms)
    all_distinct = all(c == 1 for c in element_counts.values())

    if n > 2 and not all_distinct:
        return None

    parts = [f"[{s}]" for _, s in atoms]

    if charge != 0:
        charge_str = f"+{abs(charge)}" if abs(charge) > 1 and charge > 0 else \
                     f"-{abs(charge)}" if abs(charge) > 1 else \
                     "+" if charge > 0 else "-"
        last = parts[-1]
        parts[-1] = last[:-1] + charge_str + "]"

    return "".join(parts)


def smiles_from_inchi(inchi_str: str) -> str | None:
    """
    Derives a SMILES string from an InChI using RDKit.
    Used as a fallback when the user provides a base InChI instead of SMILES.
    Returns None if RDKit is unavailable or the InChI cannot be parsed.
    """
    try:
        from rdkit import Chem
        from rdkit.Chem.inchi import MolFromInchi
    except ImportError:
        logging.warning("inchi: RDKit not available — cannot derive SMILES from InChI")
        return None

    mol = MolFromInchi(inchi_str)
    if mol is None:
        logging.warning(f"inchi: RDKit could not parse InChI '{inchi_str[:50]}...'")
        return None

    return Chem.MolToSmiles(mol)


def derive_iso_inchi(
    base_smiles: str,
    atoms: list[tuple[int, str]],
    iso_slug: str = "",
) -> tuple[str, str] | None:
    """
    Derives the isotopologue InChI and InChIKey from the base (non-isotopic) SMILES and
    the atom list for a specific isotopologue.

    base_smiles : plain SMILES with no isotope mass numbers (e.g. '[Al][H]', 'O', 'N')
    atoms       : list of (mass_number, element_symbol) as from extractor.expand_slug_atoms()
    iso_slug    : used only in log messages

    Returns (inchi, inchikey) or None if RDKit is unavailable or any step fails.
    Radicals and non-octet molecules (e.g. AlH, NO) are handled via sanitize=False.
    """
    try:
        from rdkit import Chem
        from rdkit.Chem.inchi import MolToInchi, InchiToInchiKey
    except ImportError:
        logging.warning("inchi: RDKit not available — InChI/InChIKey derivation skipped")
        return None

    label = iso_slug or base_smiles

    mol = Chem.MolFromSmiles(base_smiles)
    if mol is None:
        mol = Chem.MolFromSmiles(base_smiles, sanitize=False)
        if mol is None:
            logging.warning(f"inchi: could not parse base SMILES '{base_smiles}' for '{label}'")
            return None

    mol = Chem.AddHs(mol)

    # Build element → mass number map; bail if the same element appears with different masses
    mass_by_element: dict[str, int] = {}
    for mass_num, symbol in atoms:
        if symbol in mass_by_element and mass_by_element[symbol] != mass_num:
            logging.warning(f"inchi: '{label}' has mixed isotopes of {symbol} — cannot auto-assign")
            return None
        mass_by_element[symbol] = mass_num

    for atom in mol.GetAtoms():
        if atom.GetSymbol() in mass_by_element:
            atom.SetIsotope(mass_by_element[atom.GetSymbol()])

    iso_inchi = MolToInchi(mol)
    if iso_inchi is None:
        logging.warning(f"inchi: RDKit failed to generate InChI for '{label}'")
        return None

    iso_inchikey = InchiToInchiKey(iso_inchi)
    return (iso_inchi, iso_inchikey) if iso_inchikey else None


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
