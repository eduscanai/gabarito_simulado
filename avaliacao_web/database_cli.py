from __future__ import annotations

import argparse
import json

from .config import ASSESSMENTS_DIR
from .database import database_status, initialize_database
from .repository import database_counts, sync_all_assessments


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Configuração do banco local do Corretor OMR."
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=("init", "import-json", "status"),
        default="status",
    )
    args = parser.parse_args()

    if args.command == "init":
        initialize_database()
        result = {
            "message": "Banco criado ou verificado.",
            "database": database_status(),
        }
    elif args.command == "import-json":
        initialize_database()
        result = {
            "message": "Importação concluída.",
            "migration": sync_all_assessments(
                ASSESSMENTS_DIR
            ),
            "counts": database_counts(),
            "database": database_status(),
        }
    else:
        initialize_database()
        result = {
            "database": database_status(),
            "counts": database_counts(),
        }

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
