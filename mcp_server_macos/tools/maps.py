"""Tools that turn addresses into coordinates and back, and open the Maps app, from ``macos.maps``."""

import re
from typing import Annotated, List, Literal, Optional, Tuple, Union

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from .._registry import ADDITIVE, READ_ONLY_ONLINE, add_tool

Where = Annotated[
    str,
    Field(
        description="A place: an address, whole or in part ('20 W 34th St, New York'), a name ('Eiffel Tower'), or "
        "coordinates as 'latitude,longitude' ('48.8584,2.2945').",
        min_length=1,
    ),
]

_COORDINATES = re.compile(r"\s*([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)\s*")


class Place(BaseModel):
    """A place. The parts macOS doesn't know are null."""

    name: Optional[str] = Field(description="Its name, such as 'Eiffel Tower' or '1 Infinite Loop'.")
    street: Optional[str] = Field(description="The street, with the number when there's one.")
    city: Optional[str] = Field(description="The city.")
    state: Optional[str] = Field(description="The state or the region.")
    postal_code: Optional[str] = Field(description="The postal code.")
    country: Optional[str] = Field(description="The country, in the system's language.")
    country_code: Optional[str] = Field(description="The country's ISO 3166 code, such as 'BR'.")
    latitude: float = Field(description="The latitude, in degrees.")
    longitude: float = Field(description="The longitude, in degrees.")
    time_zone: Optional[str] = Field(description="The time zone, such as 'America/Sao_Paulo'.")


class PlaceFound(BaseModel):
    """A place that was looked for."""

    place: Optional[Place] = Field(description="The place. Null when macOS finds nothing there.")


def _place(place: "macos.maps.Place") -> Place:
    return Place(
        name=place.name,
        street=place.street,
        city=place.city,
        state=place.state,
        postal_code=place.postal_code,
        country=place.country,
        country_code=place.country_code,
        latitude=place.latitude,
        longitude=place.longitude,
        time_zone=place.time_zone,
    )


def _where(place: str) -> Union[str, Tuple[float, float]]:
    """An address as it is, and 'latitude,longitude' as the two numbers pymacos takes."""
    coordinates = _COORDINATES.fullmatch(place)
    if coordinates is None:
        return place
    return float(coordinates.group(1)), float(coordinates.group(2))


def geocode_address(
    address: Annotated[
        str, Field(description="An address, whole or in part, or a place's name, in any language.", min_length=1)
    ],
    limit: Annotated[int, Field(description="How many places to return, at most.", ge=1, le=20)] = 5,
) -> List[Place]:
    """
    Find the places matching an address, the likeliest first, with their coordinates: empty when none
    does. It asks Apple's geocoding service, which guesses rather than give up: for a vague address,
    check the city or the country it answers with.
    """
    return [_place(place) for place in macos.maps.geocode(address)[:limit]]


def reverse_geocode(
    latitude: Annotated[float, Field(description="The latitude, in degrees.", ge=-90, le=90)],
    longitude: Annotated[float, Field(description="The longitude, in degrees.", ge=-180, le=180)],
) -> PlaceFound:
    """
    Find the address at coordinates, with Apple's geocoding service. The place is null when there's
    nothing there; out at sea, it's the ocean's name.
    """
    place = macos.maps.reverse_geocode(latitude, longitude)
    return PlaceFound(place=None if place is None else _place(place))


def show_in_maps(place: Where) -> str:
    """Show a place in the Maps app, which opens."""
    macos.maps.open(_where(place))
    return "Showing {} in Maps.".format(place)


def show_directions_in_maps(
    to: Where,
    start: Annotated[
        Optional[str],
        Field(
            description="Where the route starts, written like the destination. Where the Mac is by default, which "
            "Maps asks the user's location for."
        ),
    ] = None,
    by: Annotated[Literal["car", "walk", "transit"], Field(description="How to go: 'car', 'walk' or 'transit'.")] = "car",
) -> str:
    """Open the Maps app with the route to a place. The route is shown to the user, not returned."""
    macos.maps.directions(_where(to), None if start is None else _where(start), by=by)
    return "Showing the route to {} in Maps.".format(to)


def register(server: MCPServer) -> None:
    # macOS only answers the geocoder on the main thread, and the answer comes from Apple's servers.
    add_tool(server, geocode_address, title="Find an address's coordinates", annotations=READ_ONLY_ONLINE, main_thread=True)
    add_tool(server, reverse_geocode, title="Find the address at coordinates", annotations=READ_ONLY_ONLINE, main_thread=True)
    add_tool(server, show_in_maps, title="Show a place in Maps", annotations=ADDITIVE)
    add_tool(server, show_directions_in_maps, title="Show a route in Maps", annotations=ADDITIVE)
