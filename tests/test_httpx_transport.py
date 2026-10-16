"""`HttpxTransport` beyond what the transport suite of `pathapi` holds every
transport to: the client it is given or makes, what it adds and what it keeps
to the first server, and what its errors say."""

from __future__ import annotations

import gc
import json
import ssl
import subprocess
import sys
import textwrap

import httpx
import pytest

import pathapi.http as http
from pathapi.http import HTTPClient
from pathapi_httpx import HttpxTransport
from transport_wire import Reply, Wire, make_authority, refusing_port, response

TIMEOUT = (5, 5)


def send(transport, url, method="GET", headers=None, **kwargs):
    kwargs.setdefault("timeout", TIMEOUT)
    return transport.send(method, url, headers=headers or {}, **kwargs)


def redirect(location, status=302):
    return response(status, {"Location": location}, reason="Found")


# --- what the package loads and how pathapi finds it ------------------------------


def test_importing_the_package_does_not_load_httpx():
    code = textwrap.dedent("""
        import json, sys
        import pathapi_httpx
        print(json.dumps(sorted({"httpx", "httpcore", "h11"} & set(sys.modules))))
        """)
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []


def test_pathapi_finds_the_transport_by_name_and_through_the_variable(monkeypatch):
    assert "httpx" in http.transport_names()
    assert http.get_transport("httpx") is HttpxTransport
    monkeypatch.setenv("PATHAPI_HTTP_TRANSPORT", "httpx")
    with HTTPClient() as client:
        assert type(client.transport) is HttpxTransport


def test_a_client_of_the_made_transport_sends_through_httpx():
    with Wire() as wire, HTTPClient(HttpxTransport()) as client:
        assert client.request("GET", wire.url + "/x").read() == b"ok"
    assert wire.requests[0].target == "/x"


# --- the client ---------------------------------------------------------------


def test_a_client_that_is_given_stays_open():
    with httpx.Client() as given:
        transport = HttpxTransport(given)
        assert transport.client is given
        transport.close()
        transport.close()
        assert not given.is_closed


def test_a_client_that_is_made_is_closed_by_close_and_when_collected():
    transport = HttpxTransport()
    made = transport.client
    transport.close()
    transport.close()
    assert made.is_closed

    dropped = HttpxTransport()
    kept = dropped.client
    del dropped
    gc.collect()
    assert kept.is_closed


def test_the_arguments_of_a_client_are_the_ones_of_httpx():
    seen = []

    def handler(request):
        seen.append((request.method, str(request.url)))
        return httpx.Response(204)

    with HttpxTransport(transport=httpx.MockTransport(handler)) as made:
        reply = send(made, "http://files.example.org/a?b=1", "DELETE")
    assert reply.status == 204
    assert seen == [("DELETE", "http://files.example.org/a?b=1")]


def test_arguments_for_a_client_with_a_client_are_a_type_error():
    with httpx.Client() as given:
        with pytest.raises(TypeError):
            HttpxTransport(given, verify=False)


@pytest.mark.parametrize("client", [object(), 3, "client"])
def test_a_client_is_an_object_with_a_send_method(client):
    with pytest.raises(TypeError):
        HttpxTransport(client)


def test_the_representation_shows_nothing_of_the_client():
    with HttpxTransport(auth=("user", "S3CRET")) as made:
        assert repr(made) == "HttpxTransport()"


# --- what is sent -------------------------------------------------------------


def test_only_the_headers_it_is_given_are_sent_not_those_of_the_client():
    with httpx.Client(
        headers={"X-Default": "1", "User-Agent": "someone/1"}, cookies={"sid": "abc"}
    ) as given:
        with Wire() as wire:
            send(HttpxTransport(given), wire.url + "/", headers={"X-Own": "2"}).read()
    (request,) = wire.requests
    names = {name.lower() for name, _ in request.headers}
    assert request.header("X-Own") == "2"
    assert not names & {"x-default", "user-agent", "cookie"}
    assert names <= {"host", "x-own", "accept-encoding"}


def test_a_redirect_is_returned_whatever_the_client_is_told_to_follow():
    with httpx.Client(follow_redirects=True) as given:
        with Wire(lambda r: redirect("/elsewhere")) as wire:
            reply = send(HttpxTransport(given), wire.url + "/start")
            assert (reply.status, reply.headers["Location"]) == (302, "/elsewhere")
            reply.close()
    assert [r.target for r in wire.requests] == ["/start"]


def test_a_made_client_returns_a_redirect_whose_location_httpx_cannot_read():
    with Wire(lambda r: redirect("javascript:alert(1)")) as wire:
        with HttpxTransport() as made:
            reply = send(made, wire.url + "/start")
            assert reply.status == 302
            assert reply.headers["Location"] == "javascript:alert(1)"
            reply.close()


def test_a_given_client_fails_on_a_location_it_cannot_read_as_a_bad_reply():
    import errno

    with (
        httpx.Client() as given,
        Wire(lambda r: redirect("javascript:alert(1)")) as wire,
    ):
        with pytest.raises(OSError) as excinfo:
            send(HttpxTransport(given), wire.url + "/start")
    assert excinfo.value.errno == errno.EIO
    assert len(wire.requests) == 1


# --- credentials belong to one server -----------------------------------------


def test_the_auth_of_the_client_goes_to_the_first_server_and_to_no_other():
    with Wire() as home, Wire() as other:
        with httpx.Client(auth=("user", "pw")) as given:
            transport = HttpxTransport(given)
            send(transport, home.url + "/a").read()
            send(transport, other.url + "/b").read()
            send(transport, home.url + "/c").read()
    assert [r.header("Authorization") is not None for r in home.requests] == [
        True,
        True,
    ]
    assert other.requests[0].header("Authorization") is None


def test_the_authorization_a_request_is_given_goes_to_any_server():
    headers = {"Authorization": "Bearer T"}
    with Wire() as home, Wire() as other:
        with httpx.Client(auth=("user", "pw")) as given:
            transport = HttpxTransport(given)
            send(transport, home.url + "/a").read()
            send(transport, other.url + "/b", headers=headers).read()
    assert other.requests[0].header("Authorization") == "Bearer T"


def test_a_client_with_no_auth_sends_the_authorization_it_is_given():
    with Wire() as wire, HttpxTransport() as made:
        send(made, wire.url + "/", headers={"Authorization": "Bearer T"}).read()
    assert wire.requests[0].header("Authorization") == "Bearer T"


# --- errors ---------------------------------------------------------------------


def test_an_error_names_neither_the_url_nor_its_cause():
    url = f"http://127.0.0.1:{refusing_port()}/private/path?token=S3CRET"
    with HttpxTransport() as made:
        with pytest.raises(ConnectionError) as excinfo:
            send(made, url)
    text = str(excinfo.value)
    assert "S3CRET" not in text and "private" not in text
    assert excinfo.value.__cause__ is None and excinfo.value.__suppress_context__


def test_an_error_while_reading_the_body_is_one_of_the_contract():
    def script(request):
        return Reply(b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\nshort", True)

    with Wire(script) as wire, HttpxTransport() as made:
        reply = send(made, wire.url + "/", stream=True)
        with pytest.raises(OSError) as excinfo:
            reply.read()
        assert type(excinfo.value) is OSError
        reply.close()


def test_the_exception_of_a_request_body_that_fails_is_not_wrapped():
    class Failing:
        def __iter__(self):
            yield b"first"
            raise PermissionError("no more")

    with Wire() as wire, HttpxTransport() as made:
        with pytest.raises(PermissionError):
            send(made, wire.url + "/", "PUT", body=Failing())


def test_a_reply_with_too_many_header_fields_is_an_io_error_and_closes_the_connection():
    import errno

    fields = "".join(f"X-{i}: v\r\n" for i in range(101))
    raw = f"HTTP/1.1 200 OK\r\n{fields}Content-Length: 0\r\n\r\n".encode()
    with Wire(lambda r: Reply(raw)) as wire, HttpxTransport() as made:
        with pytest.raises(OSError) as excinfo:
            send(made, wire.url + "/")
        assert excinfo.value.errno == errno.EIO


# --- TLS ----------------------------------------------------------------------


def test_https_is_verified_against_the_context_given_as_verify(tmp_path):
    authority = make_authority(tmp_path, "127.0.0.1")
    with Wire(tls=authority.server_context()) as wire:
        with HttpxTransport(verify=authority.client_context()) as trusting:
            assert send(trusting, wire.url + "/").read() == b"ok"
        with HttpxTransport(verify=ssl.create_default_context()) as strict:
            with pytest.raises(ssl.SSLError):
                send(strict, wire.url + "/")


def test_the_auth_of_the_client_wins_over_an_authorization_header_on_the_first_server():
    with Wire() as wire, httpx.Client(auth=("user", "pw")) as given:
        headers = {"Authorization": "Bearer T"}
        send(HttpxTransport(given), wire.url + "/", headers=headers).read()
    assert wire.requests[0].header("Authorization").startswith("Basic ")
