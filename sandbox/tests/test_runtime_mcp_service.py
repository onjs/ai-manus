from app.services.runtime_mcp import RuntimeMCPService


def test_runtime_mcp_parse_function_name_prefers_connected_servers():
    service = RuntimeMCPService()
    service._clients = {  # noqa: SLF001
        "foo_bar": object(),
        "foo": object(),
    }

    server, tool = service._parse_function_name("mcp_foo_bar_ping")  # noqa: SLF001
    assert server == "foo_bar"
    assert tool == "ping"

    server2, tool2 = service._parse_function_name("foo_bar_status")  # noqa: SLF001
    assert server2 == "foo_bar"
    assert tool2 == "status"

