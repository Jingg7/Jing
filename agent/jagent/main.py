from __future__ import annotations

from pathlib import Path

from core.bootstrap import create_session
from core.config import CONFIG_FILENAME, AgentConfig, ensure_config_file
from tui.app import JAgentApp
from tui.first_run import ConfigNoticeApp


def main() -> None:
    config_path = Path.cwd() / CONFIG_FILENAME
    resolved_path, created = ensure_config_file(config_path)
    if created:
        ConfigNoticeApp(resolved_path).run()
        return
    config = AgentConfig.from_file(resolved_path)
    session = create_session(config)
    JAgentApp(session, config=config).run()


if __name__ == "__main__":
    main()
