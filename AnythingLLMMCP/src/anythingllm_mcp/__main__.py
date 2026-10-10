from __future__ import annotations

import asyncio
import sys

from anythingllm_mcp.config import Settings
from anythingllm_mcp.server import serve


def main() -> None:
    try:
        asyncio.run(serve(Settings.from_env()))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
