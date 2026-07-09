import argparse
import logging
import sys
from pathlib import Path

import context
from context import DefContext
from validator import ValidationError


def main() -> None:
    # argparse setup
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
        "--force", action="store_true",
        help="With --init: delete existing .inp and temp cache files before regenerating",
    )
    parser.add_argument(
        "--verbose-input", dest="verbose_input",
        action=argparse.BooleanOptionalAction, default=True,
        help="Include comments in the generated .inp file (default: true)",
    )
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

    #logging setup
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("def_creation.log"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    try:
        ctx = DefContext(work_dir=args.work_dir.resolve())
    except ValidationError as e:
        logging.error(str(e))
        sys.exit(1)
    logging.info(
        f"create_def: work_dir='{ctx.work_dir}', ds_name='{ctx.ds_name}', "
        f"iso_slugs={ctx.iso_slugs}, format='{args.format_name}', init={args.init}"
    )

    #call context.py for logic, add more if else blocks for other templates
    if args.init:
        context.run_init(ctx, verbose_input=args.verbose_input, force=args.force)
    else:
        context.run_build(ctx, format_name=args.format_name)


if __name__ == "__main__":
    main()
