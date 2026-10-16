"""`AsyncHttpxTransport` beyond what the transport suite of `pathapi` holds
every async transport to: the client it is given or makes, what runs off the
event loop, what it keeps to the first server, and what its errors say."""

from __future__ import annotations

import asyncio
import errno
import io
import threading

import httpx
import pytest

import pathapi.http as http
from pathapi.http import AsyncHTTPClient
from pathapi_httpx import AsyncHttpxTransport
from transport_wire import Hang, Wire, refusing_port, response

TIMEOUT = (5, 5)


async def send(transport, url, method="GET", headers=None, **kwargs):
    kwargs.setdefault("timeout", TIMEOUT)
    return await transport.send(method, url, headers=headers or {}, **kwargs)


def redirect(location, status=302):
    return response(status, {"Location": location}, reason="Found")


# --- how pathapi finds it ---------------------------------------------------------


def test_pathapi_finds_the_transport_by_name_and_through_the_variable(monkeypatch):
    assert "httpx" in http.async_transport_names()
    assert http.get_async_transport("httpx") is AsyncHttpxTransport
    monkeypatch.setenv("PATHAPI_HTTP_ASYNC_TRANSPORT", "httpx")

    async def scenario():
        async with AsyncHTTPClient() as client:
            assert type(client.transport) is AsyncHttpxTransport

    asyncio.run(scenario())


def test_a_client_of_the_made_transport_sends_through_httpx(run_async):
    async def scenario(transport):
        async with AsyncHTTPClient(transport) as client:
            reply = await client.request("GET", wire.url + "/x")
            return await reply.read()

    with Wire() as wire:
        assert run_async(scenario) == b"ok"
    assert wire.requests[0].target == "/x"


# --- the client -------------------------------------------------------------------


def test_a_client_that_is_given_stays_open():
    async def scenario():
        async with httpx.AsyncClient() as given:
            transport = AsyncHttpxTransport(given)
            assert transport.client is given
            await transport.aclose()
            await transport.aclose()
            assert not given.is_closed

    asyncio.run(scenario())


def test_a_client_that_is_made_is_closed_by_aclose(run_async):
    async def scenario(transport):
        made = transport.client
        await transport.aclose()
        await transport.aclose()
        assert made.is_closed

    run_async(scenario)


def test_arguments_for_a_client_with_a_client_are_a_type_error():
    async def scenario():
        async with httpx.AsyncClient() as given:
            with pytest.raises(TypeError):
                AsyncHttpxTransport(given, verify=False)

    asyncio.run(scenario())


@pytest.mark.parametrize("client", [object(), 3, httpx.Client()])
def test_a_client_is_an_object_with_an_async_send_method(client):
    with pytest.raises(TypeError):
        AsyncHttpxTransport(client)


def test_the_arguments_of_a_client_are_the_ones_of_httpx():
    seen = []

    def handler(request):
        seen.append((request.method, str(request.url)))
        return httpx.Response(204)

    async def scenario():
        async with AsyncHttpxTransport(transport=httpx.MockTransport(handler)) as made:
            reply = await send(made, "http://files.example.org/a?b=1", "DELETE")
            assert reply.status == 204

    asyncio.run(scenario())
    assert seen == [("DELETE", "http://files.example.org/a?b=1")]


def test_the_representation_shows_nothing_of_the_client():
    assert repr(AsyncHttpxTransport()) == "AsyncHttpxTransport()"


# --- what is sent ----------------------------------------------------------------


def test_only_the_headers_it_is_given_are_sent_not_those_of_the_client():
    async def scenario():
        async with httpx.AsyncClient(
            headers={"X-Default": "1", "User-Agent": "someone/1"},
            cookies={"sid": "abc"},
        ) as given:
            transport = AsyncHttpxTransport(given)
            await (await send(transport, wire.url + "/", headers={"X-Own": "2"})).read()

    with Wire() as wire:
        asyncio.run(scenario())
    (request,) = wire.requests
    names = {name.lower() for name, _ in request.headers}
    assert request.header("X-Own") == "2"
    assert not names & {"x-default", "user-agent", "cookie"}
    assert names <= {"host", "x-own", "accept-encoding"}


def test_a_redirect_is_returned_whatever_the_client_is_told_to_follow():
    async def scenario():
        async with httpx.AsyncClient(follow_redirects=True) as given:
            reply = await send(AsyncHttpxTransport(given), wire.url + "/start")
            assert (reply.status, reply.headers["Location"]) == (302, "/elsewhere")
            await reply.aclose()

    with Wire(lambda r: redirect("/elsewhere")) as wire:
        asyncio.run(scenario())
    assert [r.target for r in wire.requests] == ["/start"]


def test_a_made_client_returns_a_redirect_whose_location_httpx_cannot_read(run_async):
    async def scenario(transport):
        reply = await send(transport, wire.url + "/start")
        assert reply.status == 302
        assert reply.headers["Location"] == "javascript:alert(1)"
        await reply.aclose()

    with Wire(lambda r: redirect("javascript:alert(1)")) as wire:
        run_async(scenario)


def test_a_given_client_fails_on_a_location_it_cannot_read_as_a_bad_reply():
    async def scenario():
        async with httpx.AsyncClient() as given:
            with pytest.raises(OSError) as excinfo:
                await send(AsyncHttpxTransport(given), wire.url + "/start")
            assert excinfo.value.errno == errno.EIO

    with Wire(lambda r: redirect("javascript:alert(1)")) as wire:
        asyncio.run(scenario())
    assert len(wire.requests) == 1


def test_a_file_body_is_read_on_a_worker_thread_not_on_the_loop(run_async):
    threads = []

    class Recording(io.BytesIO):
        def read(self, *args):
            threads.append(threading.get_ident())
            return super().read(*args)

    async def scenario(transport):
        loop_thread = threading.get_ident()
        body = Recording(b"x" * 200_000)
        await (await send(transport, wire.url + "/f", "PUT", body=body)).read()
        return loop_thread

    with Wire() as wire:
        loop_thread = run_async(scenario)
    assert wire.requests[0].body == b"x" * 200_000
    assert threads and loop_thread not in threads


def test_a_body_from_an_iterable_is_sent_whole_and_chunked(run_async):
    async def scenario(transport):
        pieces = (piece for piece in (b"in ", b"pieces"))
        await (await send(transport, wire.url + "/g", "PUT", body=pieces)).read()

    with Wire() as wire:
        run_async(scenario)
    request = wire.requests[0]
    assert request.body == b"in pieces"
    assert request.header("Transfer-Encoding") == "chunked"


# --- credentials belong to one server -----------------------------------------


def test_the_auth_of_the_client_goes_to_the_first_server_and_to_no_other():
    async def scenario():
        async with httpx.AsyncClient(auth=("user", "pw")) as given:
            transport = AsyncHttpxTransport(given)
            for server in (home, other, home):
                await (await send(transport, server.url + "/")).read()

    with Wire() as home, Wire() as other:
        asyncio.run(scenario())
    assert [r.header("Authorization") is not None for r in home.requests] == [
        True,
        True,
    ]
    assert other.requests[0].header("Authorization") is None


def test_the_authorization_a_request_is_given_goes_to_any_server():
    async def scenario():
        async with httpx.AsyncClient(auth=("user", "pw")) as given:
            transport = AsyncHttpxTransport(given)
            await (await send(transport, home.url + "/")).read()
            headers = {"Authorization": "Bearer T"}
            await (await send(transport, other.url + "/", headers=headers)).read()

    with Wire() as home, Wire() as other:
        asyncio.run(scenario())
    assert other.requests[0].header("Authorization") == "Bearer T"


# --- errors and cancellation ------------------------------------------------------


def test_an_error_names_neither_the_url_nor_its_cause(run_async):
    url = f"http://127.0.0.1:{refusing_port()}/private/path?token=S3CRET"

    async def scenario(transport):
        with pytest.raises(ConnectionError) as excinfo:
            await send(transport, url)
        return excinfo.value

    error = run_async(scenario)
    assert "S3CRET" not in str(error) and "private" not in str(error)
    assert error.__cause__ is None and error.__suppress_context__


def test_a_cancelled_request_leaves_the_transport_usable(run_async):
    async def scenario(transport):
        task = asyncio.ensure_future(
            send(transport, wire.url + "/hang", timeout=(5, 30))
        )
        for _ in range(500):
            if wire.requests:
                break
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        reply = await send(transport, wire.url + "/after")
        return await reply.read()

    def script(request):
        return Hang() if request.target == "/hang" else response(body=b"fine")

    with Wire(script) as wire:
        assert run_async(scenario) == b"fine"
    assert [r.target for r in wire.requests] == ["/hang", "/after"]


def test_requests_in_flight_on_one_loop_share_the_client_pool(run_async):
    gate = threading.Barrier(4, timeout=10)

    def script(request):
        gate.wait()
        return response(body=request.target.encode())

    async def scenario(transport):
        replies = await asyncio.gather(
            *(send(transport, f"{wire.url}/{n}") for n in range(4))
        )
        return sorted([await reply.read() for reply in replies])

    with Wire(script) as wire:
        assert run_async(scenario) == [b"/0", b"/1", b"/2", b"/3"]
    assert wire.connections == 4
