ExoMol databases definition file creator

Working directory structure:
/<dataset_name>/
    /<isotopologue_1>/
        /<iso_slug>__<dataset_name>.states (can be in bz2 format)
        /<iso_slug>__<dataset_name>.trans  (can be in bz2 format)
        /<iso_slug>__<dataset_name>.pf
    /<isotopologue_2>/

Instructions for use:
    1. Put your line list files in your working directory, with the structure as above.
    2. Run the following console line to generate an input file
    console> python3 /path/to/create_def.py --init /path/to/working/directory/
    3. Fill in the input file, which will generate within the /<dataset_name>/ directory
    4. Run the following console line to generate the definition files
    console> python3 /path/to/create_def.py /path/to/working/directory/