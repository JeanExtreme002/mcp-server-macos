"""The tools of mcp_server_macos.tools.maps, with macos.maps faked: no service is asked, and Maps isn't opened."""

import threading
from typing import Any, Dict, List

import macos
import pytest
from mcp import Client

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio

EIFFEL = macos.maps.Place(
    name="Eiffel Tower",
    street="5 Avenue Anatole France",
    city="Paris",
    state="Île-de-France",
    postal_code="75007",
    country="France",
    country_code="FR",
    latitude=48.8584,
    longitude=2.2945,
    time_zone="Europe/Paris",
)
OCEAN = macos.maps.Place(
    name="Atlantic Ocean",
    street=None,
    city=None,
    state=None,
    postal_code=None,
    country=None,
    country_code=None,
    latitude=0.0,
    longitude=-30.0,
    time_zone=None,
)
LISTED = {
    "name": "Eiffel Tower",
    "street": "5 Avenue Anatole France",
    "city": "Paris",
    "state": "Île-de-France",
    "postal_code": "75007",
    "country": "France",
    "country_code": "FR",
    "latitude": 48.8584,
    "longitude": 2.2945,
    "time_zone": "Europe/Paris",
}


async def test_geocode_address(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.maps, "geocode", recorder.function("geocode", [EIFFEL, OCEAN]))

    result = await client.call_tool("geocode_address", {"address": "Eiffel Tower"})

    assert not result.is_error
    assert result.structured_content is not None
    first, second = result.structured_content["result"]
    assert first == LISTED
    assert (second["name"], second["city"], second["longitude"]) == ("Atlantic Ocean", None, -30.0)
    assert recorder.calls == [("geocode", ("Eiffel Tower",), {})]


@pytest.mark.parametrize("found, limit, count", [([EIFFEL] * 8, None, 5), ([EIFFEL] * 8, 2, 2), ([], None, 0)])
async def test_geocode_address_returns_a_few_places(
    client: Client, monkeypatch: pytest.MonkeyPatch, found: List[Any], limit: Any, count: int
) -> None:
    monkeypatch.setattr(macos.maps, "geocode", lambda address: found)
    arguments = {"address": "Springfield"} if limit is None else {"address": "Springfield", "limit": limit}

    result = await client.call_tool("geocode_address", arguments)

    assert not result.is_error
    assert result.structured_content is not None
    assert len(result.structured_content["result"]) == count


@pytest.mark.parametrize("found, expected", [(EIFFEL, LISTED), (None, None)])
async def test_reverse_geocode(client: Client, monkeypatch: pytest.MonkeyPatch, found: Any, expected: Any) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.maps, "reverse_geocode", recorder.function("reverse_geocode", found))

    result = await client.call_tool("reverse_geocode", {"latitude": 48.8584, "longitude": 2.2945})

    assert not result.is_error
    assert result.structured_content == {"place": expected}
    assert recorder.calls == [("reverse_geocode", (48.8584, 2.2945), {})]


async def test_geocoder_is_asked_on_the_main_thread(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    # macOS only answers it there, and pymacos refuses elsewhere: a tool run on a worker thread, as
    # the others are, would always fail.
    threads = []

    def geocode(address: str) -> List[Any]:
        threads.append(threading.current_thread())
        return []

    def reverse_geocode(latitude: float, longitude: float) -> None:
        threads.append(threading.current_thread())

    monkeypatch.setattr(macos.maps, "geocode", geocode)
    monkeypatch.setattr(macos.maps, "reverse_geocode", reverse_geocode)

    await client.call_tool("geocode_address", {"address": "Paris"})
    await client.call_tool("reverse_geocode", {"latitude": 0, "longitude": 0})

    assert threads == [threading.main_thread(), threading.main_thread()]


async def test_geocoder_that_does_not_answer(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    error = macos.WaitTimeoutError("the geocoder didn't answer within 15 seconds")
    monkeypatch.setattr(macos.maps, "geocode", Recorder().function("geocode", error=error))

    result = await client.call_tool("geocode_address", {"address": "Paris"})

    assert result.is_error
    assert "WaitTimeoutError" in text(result)


@pytest.mark.parametrize(
    "place, given",
    [
        ("20 W 34th St, New York, NY", "20 W 34th St, New York, NY"),
        ("Eiffel Tower", "Eiffel Tower"),
        ("48.8584,2.2945", (48.8584, 2.2945)),
        (" -23.55 , -46.63 ", (-23.55, -46.63)),
        ("+10, 20", (10.0, 20.0)),
        ("1600, Pennsylvania Avenue", "1600, Pennsylvania Avenue"),  # an address with a comma, not coordinates
        ("12,34,56", "12,34,56"),
    ],
)
async def test_show_in_maps(client: Client, monkeypatch: pytest.MonkeyPatch, place: str, given: Any) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.maps, "open", recorder.function("open"))

    result = await client.call_tool("show_in_maps", {"place": place})

    assert not result.is_error
    assert text(result) == "Showing {} in Maps.".format(place)
    assert recorder.calls == [("open", (given,), {})]


@pytest.mark.parametrize(
    "arguments, call",
    [
        ({"to": "Aeroporto de Congonhas"}, (("Aeroporto de Congonhas", None), {"by": "car"})),
        (
            {"to": "48.8584,2.2945", "start": "Gare du Nord, Paris", "by": "walk"},
            (((48.8584, 2.2945), "Gare du Nord, Paris"), {"by": "walk"}),
        ),
        ({"to": "Paris", "start": "51.5,-0.12", "by": "transit"}, (("Paris", (51.5, -0.12)), {"by": "transit"})),
    ],
)
async def test_show_directions_in_maps(
    client: Client, monkeypatch: pytest.MonkeyPatch, arguments: Dict[str, Any], call: Any
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.maps, "directions", recorder.function("directions"))

    result = await client.call_tool("show_directions_in_maps", arguments)

    assert not result.is_error
    assert text(result) == "Showing the route to {} in Maps.".format(arguments["to"])
    assert recorder.calls == [("directions", *call)]


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("geocode_address", {}),
        ("geocode_address", {"address": ""}),
        ("geocode_address", {"address": "Paris", "limit": 0}),
        ("reverse_geocode", {"latitude": 48.8}),
        ("reverse_geocode", {"latitude": 91, "longitude": 0}),
        ("reverse_geocode", {"latitude": 0, "longitude": -181}),
        ("show_in_maps", {}),
        ("show_in_maps", {"place": ""}),
        ("show_directions_in_maps", {"start": "Paris"}),
        ("show_directions_in_maps", {"to": "Paris", "by": "bike"}),
    ],
)
async def test_maps_tools_need_a_place(
    client: Client, monkeypatch: pytest.MonkeyPatch, tool: str, arguments: Dict[str, Any]
) -> None:
    recorder = Recorder()
    for name in ("geocode", "reverse_geocode", "open", "directions"):
        monkeypatch.setattr(macos.maps, name, recorder.function(name))

    result = await client.call_tool(tool, arguments)

    assert result.is_error
    assert recorder.calls == []
