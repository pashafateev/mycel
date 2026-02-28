from mycel.utils.namespaces import is_mycel_command, parse_namespaced_command


def test_parse_simple_command() -> None:
    parsed = parse_namespaced_command("/m_chat hello world")
    assert parsed is not None
    assert parsed.namespace == "m"
    assert parsed.command == "chat"
    assert parsed.args == "hello world"


def test_parse_command_with_bot_suffix() -> None:
    parsed = parse_namespaced_command("/m_help@mybot")
    assert parsed is not None
    assert parsed.namespace == "m"
    assert parsed.command == "help"
    assert parsed.args == ""


def test_parse_non_namespaced_command_returns_none() -> None:
    assert parse_namespaced_command("/start") is None
    assert parse_namespaced_command("hello") is None


def test_is_mycel_command() -> None:
    assert is_mycel_command("/m_help") is True
    assert is_mycel_command("/m_chat test") is True
    assert is_mycel_command("/x_help") is False
