from __future__ import annotations

from tb10.namespaces import parse_namespaced_command


def test_parse_namespaced_command_matches_expected_namespace() -> None:
    routed = parse_namespaced_command("/m_ping hello", namespace="m")
    assert routed is not None
    assert routed.command == "ping"
    assert routed.args == "hello"


def test_parse_namespaced_command_allows_bot_suffix() -> None:
    routed = parse_namespaced_command("/m_help@mycel_dev_bot", namespace="m")
    assert routed is not None
    assert routed.command == "help"
    assert routed.args == ""


def test_parse_namespaced_command_rejects_other_namespace() -> None:
    assert parse_namespaced_command("/oc_ping hello", namespace="m") is None


def test_parse_namespaced_command_rejects_non_command_text() -> None:
    assert parse_namespaced_command("hello there", namespace="m") is None


def test_parse_namespaced_command_rejects_non_prefixed_command() -> None:
    assert parse_namespaced_command("/ping hello", namespace="m") is None

