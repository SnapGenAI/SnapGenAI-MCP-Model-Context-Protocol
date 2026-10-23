from snapgen_mcp.server import transport_security_for


def test_loopback_binding_keeps_host_checking_for_loopback_names_only():
    s = transport_security_for("127.0.0.1")
    assert s.enable_dns_rebinding_protection
    assert s.allowed_hosts == ["127.0.0.1:*", "localhost:*", "[::1]:*"]


def test_hosted_binding_without_allow_list_accepts_any_host_header():
    # Behind a proxy the Host header is the public domain; a loopback-only list would reject every request.
    for host in ("0.0.0.0", "::", "10.1.2.3"):
        assert not transport_security_for(host).enable_dns_rebinding_protection


def test_hosted_binding_with_allow_list_enforces_exactly_those_hosts():
    s = transport_security_for("0.0.0.0", ["mcp.example.com", " ", ""])
    assert s.enable_dns_rebinding_protection
    assert s.allowed_hosts == ["mcp.example.com", "mcp.example.com:*"]
    assert "127.0.0.1:*" not in s.allowed_hosts
    assert "https://mcp.example.com" in s.allowed_origins


def test_loopback_binding_can_add_extra_hosts():
    s = transport_security_for("localhost", ["mcp.example.com"])
    assert "localhost:*" in s.allowed_hosts and "mcp.example.com" in s.allowed_hosts
