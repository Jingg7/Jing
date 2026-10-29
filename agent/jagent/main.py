from __future__ import annotations

from pathlib import Path

from core.bootstrap import create_session
from core.config import AgentConfig
from tui.app import JAgentApp


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    config = AgentConfig.from_file(base_dir / "config.ini")
    session = create_session(config)
    JAgentApp(session).run()


if __name__ == "__main__":
    main()
