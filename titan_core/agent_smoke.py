from __future__ import annotations

from titan_core.agent import plan_agent_action, validate_agent_action


def run() -> None:
    refresh = plan_agent_action("refresh sitrep")
    assert refresh is not None
    assert refresh.name == "refresh_sitrep"
    assert validate_agent_action(refresh) is True

    read = plan_agent_action("read sitrep")
    assert read is not None
    assert read.name == "read_sitrep"
    assert validate_agent_action(read) is True

    vscode = plan_agent_action("open vscode")
    assert vscode is not None
    assert vscode.name == "open_vscode"
    assert vscode.payload == {"app": "vscode"}
    assert validate_agent_action(vscode) is True

    edge = plan_agent_action("open edge")
    assert edge is not None
    assert edge.name == "open_edge"
    assert edge.payload == {"app": "edge"}
    assert validate_agent_action(edge) is True

    normal = plan_agent_action("what should I study next")
    assert normal is None
    assert validate_agent_action(normal) is False

    print("agent smoke ok")


if __name__ == "__main__":
    run()
