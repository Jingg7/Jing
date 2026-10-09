"""Entry point: `python -m pet_hospital_mcp`."""

from __future__ import annotations

import json
import sys

from .config import ConfigError, load_settings
from .errors import MCPToolError  # noqa: F401  (re-export for quick debugging)
from .logging_config import get_logger, setup_logging
from .server import build_server, describe


def main() -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(json.dumps({"error": {"code": "CONFIG_ERROR", "message": str(exc), "details": {}}},
                         ensure_ascii=False), file=sys.stderr)
        return 2

    logger = setup_logging(settings.log_level)
    server = build_server(settings)

    logger.info(
        "starting",
        extra={"payload": json.loads(describe(settings))},
    )
    try:
        server.run(
            transport="streamable-http",
            host=settings.host,
            port=settings.port,
            streamable_http_path="/mcp",
            json_response=settings.json_response,
            stateless_http=True,
        )
    except KeyboardInterrupt:  # pragma: no cover
        logger.info("stopped", extra={"payload": {"status": "shutdown"}})
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
