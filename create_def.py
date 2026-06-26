import argparse
import logging
import sys
from pathlib import Path

import context
from context import DefContext


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate ExoMol .def files from spectroscopy data files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Two-step workflow:\n"
            "  1. python create_def.py --init <work_dir>\n"
            "     Validates data files, extracts auto-derivable fields,\n"
            "     and writes a <ds_name>.inp template to fill in.\n\n"
            "  2. python create_def.py <work_dir>\n"
            "     Reads the filled .inp, merges with cached data,\n"
            "     and renders the .def file(s)."
        ),
    )
    parser.add_argument("work_dir", type=Path, help="Path to the dataset directory")
    parser.add_argument("--init", action="store_true", help="Run initialisation step")
    parser.add_argument(
        "--format", default="exomol", dest="format_name",
        help="Output template format (default: exomol)",
    )
    parser.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("def_creation.log"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    ctx = DefContext(work_dir=args.work_dir.resolve())
    logging.info(
        f"create_def: work_dir='{ctx.work_dir}', ds_name='{ctx.ds_name}', "
        f"format='{args.format_name}', init={args.init}"
    )

    if args.init:
        context.run_init(ctx, format_name=args.format_name)
    else:
        context.run_build(ctx, format_name=args.format_name)


if __name__ == "__main__":
    main()
