"""Tools that read, convert and edit images, HEIC included, and their metadata, from ``macos.image``."""

from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, Optional

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from .._registry import READ_ONLY, REPLACING, add_tool
from .._values import plain

ImagePath = Annotated[str, Field(description="The path of the image: any format macOS opens (JPEG, PNG, HEIC...).", min_length=1)]
Output = Annotated[
    str,
    Field(
        description="Where to save the result. Its extension picks the format: .jpg, .png, .heic, .tiff, .gif or .bmp. "
        "A file already there is replaced.",
        min_length=1,
    ),
]
Quality = Annotated[
    Optional[int],
    Field(description="For JPEG and HEIC: the quality, from 0 (smallest) to 100 (best). macOS's own by default.", ge=0, le=100),
]
Color = Annotated[str, Field(description="A hex color, such as '#ffffff'.", pattern=r"^#[0-9a-fA-F]{6}$")]


class ImageInfo(BaseModel):
    """What an image file contains."""

    width: int = Field(description="Its width, in pixels, as stored (before the orientation is applied).")
    height: int = Field(description="Its height, in pixels, as stored.")
    format: str = Field(description="A short name such as 'jpeg', 'png' or 'heic', or the type identifier for others.")
    has_alpha: bool = Field(description="Whether it has transparency.")
    orientation: int = Field(description="The EXIF orientation, from 1 to 8: 1 is upright, 6 and 8 are turned 90°.")
    dpi: Optional[float] = Field(description="Its dots per inch, when the file records it.")
    taken_at: Optional[datetime] = Field(
        description="When the photo was taken, from its EXIF data, by the camera's clock. Null when it doesn't say."
    )
    latitude: Optional[float] = Field(description="Where the photo was taken: the latitude. Null without GPS data.")
    longitude: Optional[float] = Field(description="Where the photo was taken: the longitude. Null without GPS data.")


class Saved(BaseModel):
    """A file that was written."""

    path: str = Field(description="The path of the file.")


def _saved(path: Path) -> Saved:
    return Saved(path=str(path))


def _quality(quality: Optional[int]) -> Optional[float]:
    return None if quality is None else quality / 100


def get_image_info(path: ImagePath) -> ImageInfo:
    """
    Get an image's size, format, transparency, orientation and DPI, and for a photo, when and where it
    was taken. iPhone photos record where they were taken: mind who sees it.
    """
    info = macos.image.info(path)
    location = macos.image.location(path)
    return ImageInfo(
        width=info.width,
        height=info.height,
        format=info.format,
        has_alpha=info.has_alpha,
        orientation=info.orientation,
        dpi=info.dpi,
        taken_at=macos.image.taken_at(path),
        latitude=None if location is None else location[0],
        longitude=None if location is None else location[1],
    )


def get_image_metadata(path: ImagePath) -> Dict[str, Any]:
    """
    Get all the metadata of an image, as macOS reads it: the top level (PixelWidth, Orientation...) and
    the standards, such as {Exif} (date, exposure, lens), {TIFF} (the camera) and {GPS} (the location).
    """
    metadata: Dict[str, Any] = plain(macos.image.metadata(path))
    return metadata


def get_image_colors(
    path: ImagePath,
    count: Annotated[int, Field(description="How many colors, at most.", ge=1, le=20)] = 5,
) -> List[str]:
    """Get the main colors of an image, as hex, the most present first. Transparent pixels are left out."""
    return macos.image.dominant_colors(path, count)


def remove_image_metadata(source: ImagePath, output: Output) -> Saved:
    """
    Save a copy of an image without its metadata: the location, the date, the camera, the software.
    For photos to share. Only the orientation is kept, so the picture still shows upright.
    """
    return _saved(macos.image.strip_metadata(source, output))


def set_image_date(
    path: ImagePath,
    when: Annotated[datetime, Field(description="When the photo was taken. With a time zone, it's recorded too.")],
    output: Annotated[Optional[str], Field(description="Save a changed copy here instead of changing the photo itself.")] = None,
) -> Saved:
    """
    Set when a photo was taken (its EXIF date), which apps such as Photos sort by: to fix a camera with
    the wrong clock. It changes the photo itself unless output is given.
    """
    return _saved(macos.image.set_taken_at(path, when, output=output))


def set_image_location(
    path: ImagePath,
    latitude: Annotated[float, Field(description="The latitude, in degrees: negative for the south.", ge=-90, le=90)],
    longitude: Annotated[float, Field(description="The longitude, in degrees: negative for the west.", ge=-180, le=180)],
    output: Annotated[Optional[str], Field(description="Save a changed copy here instead of changing the photo itself.")] = None,
) -> Saved:
    """Set where a photo was taken (its GPS position). It changes the photo itself unless output is given."""
    return _saved(macos.image.set_location(path, latitude, longitude, output=output))


def convert_image(source: ImagePath, output: Output, quality: Quality = None) -> Saved:
    """
    Convert an image to another format, such as HEIC to JPEG, keeping its metadata. Animated GIFs and
    multi-page TIFFs keep every frame as GIF or TIFF; other formats get the first one.
    """
    return _saved(macos.image.convert(source, output, quality=_quality(quality)))


def resize_image(
    source: ImagePath,
    output: Output,
    width: Annotated[Optional[int], Field(description="The most it may be wide, in pixels.", gt=0)] = None,
    height: Annotated[Optional[int], Field(description="The most it may be high, in pixels.", gt=0)] = None,
    quality: Quality = None,
) -> Saved:
    """
    Scale an image down to fit a width, a height or both, keeping its proportions. It's only scaled
    down: a larger size keeps the original one. A photo is turned upright first.
    """
    return _saved(macos.image.resize(source, output, width=width, height=height, quality=_quality(quality)))


def crop_image(
    source: ImagePath,
    output: Output,
    x: Annotated[int, Field(description="The left edge of the part to keep, in pixels from the left.", ge=0)],
    y: Annotated[int, Field(description="The top edge of the part to keep, in pixels from the top.", ge=0)],
    width: Annotated[int, Field(description="The width of the part to keep, in pixels.", gt=0)],
    height: Annotated[int, Field(description="The height of the part to keep, in pixels.", gt=0)],
    quality: Quality = None,
) -> Saved:
    """Save a part of an image, measured on the upright picture, as it shows on screen."""
    return _saved(macos.image.crop(source, output, (x, y, width, height), quality=_quality(quality)))


def rotate_image(
    source: ImagePath,
    output: Output,
    degrees: Annotated[
        Literal[90, 180, 270, -90, -180, -270],
        Field(description="How far to turn it clockwise: 90, 180 or 270. Negative turns counter-clockwise."),
    ],
    quality: Quality = None,
) -> Saved:
    """Turn an image by a quarter turn or more, keeping its metadata."""
    return _saved(macos.image.rotate(source, output, degrees, quality=_quality(quality)))


def flip_image(
    source: ImagePath,
    output: Output,
    direction: Annotated[
        Literal["horizontal", "vertical"],
        Field(description="'horizontal' swaps left and right, 'vertical' turns it upside down."),
    ] = "horizontal",
    quality: Quality = None,
) -> Saved:
    """Mirror an image, left to right or upside down, keeping its metadata."""
    return _saved(macos.image.flip(source, output, direction=direction, quality=_quality(quality)))


def straighten_image(source: ImagePath, output: Output, quality: Quality = None) -> Saved:
    """
    Level a photo whose horizon is tilted: it's turned, and cropped to the largest part with the same
    proportions. A photo without a tilted horizon is saved unchanged.
    """
    return _saved(macos.image.straighten(source, output, quality=_quality(quality)))


def enhance_image(source: ImagePath, output: Output, quality: Quality = None) -> Saved:
    """Improve a photo automatically, like the Enhance button of Photos: exposure, contrast, colors and red eyes."""
    return _saved(macos.image.enhance(source, output, quality=_quality(quality)))


def apply_image_effect(
    source: ImagePath,
    output: Output,
    effect: Annotated[
        Literal["noir", "mono", "tonal", "chrome", "fade", "instant", "process", "transfer"],
        Field(
            description="The filter of the Photos app: 'noir', 'mono' or 'tonal' (black and white), or 'chrome', "
            "'fade', 'instant', 'process' or 'transfer' (vintage colors)."
        ),
    ],
    quality: Quality = None,
) -> Saved:
    """Apply one of the Photos app's filters to an image."""
    return _saved(macos.image.effect(source, output, effect, quality=_quality(quality)))


def blur_faces_in_image(source: ImagePath, output: Output, quality: Quality = None) -> Saved:
    """
    Save a copy of a photo with every face pixelated, before sharing a photo of other people. A photo
    without faces is saved unchanged. Its metadata (the location) is kept: remove it too, to share.
    """
    return _saved(macos.image.blur_faces(source, output, quality=_quality(quality)))


def blur_image_background(
    source: ImagePath,
    output: Output,
    strength: Annotated[float, Field(description="How blurry: 1 by default, 2 twice as blurry.", gt=0, le=10)] = 1.0,
    quality: Quality = None,
) -> Saved:
    """Blur what's behind the people in a photo, like Portrait mode. Fails for a photo that shows no person."""
    return _saved(macos.image.blur_background(source, output, strength=strength, quality=_quality(quality)))


def replace_image_background(
    source: ImagePath,
    background: Annotated[
        str, Field(description="The picture to put behind the people. It's scaled to fill the photo.", min_length=1)
    ],
    output: Output,
    quality: Quality = None,
) -> Saved:
    """
    Put the people of a photo in front of another picture, like a virtual background. Fails for a photo
    that shows no person.
    """
    return _saved(macos.image.replace_background(source, background, output, quality=_quality(quality)))


def watermark_image(
    source: ImagePath,
    output: Output,
    text: Annotated[str, Field(description="The text, such as a name, 'SAMPLE' or '© 2026 Alice'.", min_length=1)],
    color: Color = "#ffffff",
    opacity: Annotated[float, Field(description="From 0 (invisible) to 1.", ge=0, le=1)] = 0.35,
    quality: Quality = None,
) -> Saved:
    """Write a text across a photo, diagonally and see-through, sized to the photo."""
    return _saved(macos.image.watermark(source, output, text, color=color, opacity=opacity, quality=_quality(quality)))


def make_contact_sheet(
    images: Annotated[List[str], Field(description="The images, in order.", min_length=1)],
    output: Output,
    columns: Annotated[int, Field(description="How many columns.", ge=1, le=50)] = 4,
    size: Annotated[int, Field(description="The side of the square each thumbnail fits, in pixels.", ge=16, le=2048)] = 256,
    gap: Annotated[int, Field(description="The space between thumbnails, in pixels.", ge=0, le=512)] = 8,
    background: Color = "#ffffff",
) -> Saved:
    """Lay images out as thumbnails in a grid, on one picture: to see many photos, or a video's frames, at a glance."""
    return _saved(macos.image.contact_sheet(images, output, columns, size=size, gap=gap, background=background))


def make_qr_code(
    content: Annotated[str, Field(description="What the code holds: an address, some text...", min_length=1)],
    output: Annotated[str, Field(description="Where to save the PNG. A file already there is replaced.", min_length=1)],
    size: Annotated[int, Field(description="Its side, in pixels.", ge=32, le=4096)] = 512,
    correction: Annotated[
        Literal["L", "M", "Q", "H"],
        Field(description="Its error correction: 'L', 'M', 'Q' or 'H'. Higher survives more damage, but holds less."),
    ] = "M",
) -> Saved:
    """Make a QR code for an address or a text, as a PNG."""
    saved = Path(output).expanduser()
    saved.write_bytes(macos.image.qr_code(content, size=size, correction=correction))
    return _saved(saved.absolute())


def register(server: MCPServer) -> None:
    add_tool(server, get_image_info, title="Get an image's information", annotations=READ_ONLY)
    add_tool(server, get_image_metadata, title="Get an image's metadata", annotations=READ_ONLY)
    add_tool(server, get_image_colors, title="Get an image's main colors", annotations=READ_ONLY)
    # The others write a file, over the one that may be there; two change the photo itself.
    for tool, title in (
        (remove_image_metadata, "Remove an image's metadata"),
        (set_image_date, "Set when a photo was taken"),
        (set_image_location, "Set where a photo was taken"),
        (convert_image, "Convert an image"),
        (resize_image, "Resize an image"),
        (crop_image, "Crop an image"),
        (rotate_image, "Rotate an image"),
        (flip_image, "Flip an image"),
        (straighten_image, "Straighten a photo"),
        (enhance_image, "Enhance a photo"),
        (apply_image_effect, "Apply a photo filter"),
        (blur_faces_in_image, "Blur the faces in a photo"),
        (blur_image_background, "Blur a photo's background"),
        (replace_image_background, "Replace a photo's background"),
        (watermark_image, "Watermark an image"),
        (make_contact_sheet, "Make a contact sheet"),
        (make_qr_code, "Make a QR code"),
    ):
        add_tool(server, tool, title=title, annotations=REPLACING)
