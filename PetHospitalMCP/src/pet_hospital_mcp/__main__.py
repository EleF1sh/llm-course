from __future__ import annotations

import asyncio
import sys

from pet_hospital_mcp.config import Settings
from pet_hospital_mcp.server import serve


def main() -> None:
    settings = Settings.from_env()
    try:
        asyncio.run(serve(settings))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
