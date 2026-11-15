"""Tools that understand images with Apple's Vision framework, offline: text, codes, faces, poses, from ``macos.vision``."""

from pathlib import Path
from typing import Annotated, Dict, List, Optional

import macos
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from .._registry import DESTRUCTIVE, READ_ONLY, add_tool

ImagePath = Annotated[
    str,
    Field(
        description="The path of the image: any format macOS opens (PNG, JPEG, HEIC...). For a PDF, draw its page first.",
        min_length=1,
    ),
]
Images = Annotated[List[str], Field(description="The paths of the images.", min_length=1)]
PngOutput = Annotated[
    str, Field(description="Where to save the result, as a PNG. A file already there is replaced.", min_length=1)
]
Languages = Annotated[
    Optional[List[str]],
    Field(
        description="The languages to expect, most likely first, such as ['pt-BR', 'en-US']: list_text_languages lists "
        "them. Detected by default; give them for Chinese, Japanese, Cyrillic..."
    ),
]
Fast = Annotated[bool, Field(description="True to read faster, and less accurately.")]
Box = List[float]
BOX = "[x, y, width, height] as fractions of the image's size, from its top-left corner."


class ImageText(BaseModel):
    """The text of an image."""

    text: str = Field(description="The text, one line per line found. Empty when there's none.")


class TextLine(BaseModel):
    """A line of text found in an image."""

    text: str = Field(description="The line's text.")
    confidence: float = Field(description="How sure the reading is, from 0 to 1.")
    box: Box = Field(description=BOX)


class Barcode(BaseModel):
    """A barcode or QR code found in an image."""

    payload: Optional[str] = Field(description="What it encodes, such as an address. Null for binary content.")
    kind: str = Field(description="Its symbology, such as 'QR', 'EAN13', 'Code128' or 'PDF417'.")
    box: Box = Field(description=BOX)


class Label(BaseModel):
    """Something an image shows, or a sound has."""

    label: str = Field(description="What it is, in English, from Apple's own list: 'dog', 'beach', 'document'...")
    confidence: float = Field(description="How sure it is, from 0 to 1.")


class Animal(BaseModel):
    """A cat or a dog found in an image."""

    kind: str = Field(description="'cat' or 'dog', the only animals Vision recognizes.")
    confidence: float = Field(description="How sure it is, from 0 to 1.")
    box: Box = Field(description=BOX)


class Distance(BaseModel):
    """How different two images look."""

    distance: float = Field(
        description="0 for the same picture, growing as they differ: a resized or re-saved copy scores below 0.15, "
        "unrelated photos around 0.7 to 0.9."
    )


class BestShot(BaseModel):
    """The photo where the faces look best."""

    path: Optional[str] = Field(description="The photo, one of those given. Null when none has a face.")


class Horizon(BaseModel):
    """How tilted a photo's horizon is."""

    degrees: Optional[float] = Field(
        description="The tilt, positive when it rises to the right. Null when there's no horizon, when it's level "
        "(under about 1.5°) or tilted too much to tell (over about 10°)."
    )


class Aesthetics(BaseModel):
    """How good a photo looks, as Photos judges it."""

    score: float = Field(description="From -1 (poor) to 1 (great): focus, exposure, composition...")
    utility: bool = Field(description="Whether it's a utility picture, such as a screenshot, a receipt or a document.")


class Pose(BaseModel):
    """The body of one person in an image."""

    joints: Dict[str, List[float]] = Field(
        description="Each joint found, by name (nose, left_shoulder, right_wrist, left_knee...), as [x, y, confidence], "
        "x and y as fractions of the image from its top-left corner."
    )
    confidence: float = Field(description="How sure it is, from 0 to 1.")


class Hand(BaseModel):
    """One hand in an image."""

    side: Optional[str] = Field(description="'left' or 'right', the person's own. Null when Vision can't tell.")
    joints: Dict[str, List[float]] = Field(
        description="The wrist and each finger's joints and tip (thumb_tip, index_tip...), as [x, y, confidence]."
    )
    confidence: float = Field(description="How sure it is, from 0 to 1.")


class Saved(BaseModel):
    """A file that was written."""

    path: str = Field(description="The path of the file.")


def _save(output: str, data: Optional[bytes], nothing: str) -> Saved:
    if data is None:
        raise ToolError(nothing)
    saved = Path(output).expanduser()
    saved.write_bytes(data)
    return Saved(path=str(saved.absolute()))


def read_text_in_image(image: ImagePath, languages: Languages = None, fast: Fast = False) -> ImageText:
    """
    Read the text in an image (OCR), one line per line found, offline, with the engine of Live Text: a
    screenshot, a photo of a sign, a scan. For where each line is, see find_text_lines_in_image.
    """
    return ImageText(text=macos.vision.text(image, languages=languages, fast=fast))


def find_text_lines_in_image(image: ImagePath, languages: Languages = None, fast: Fast = False) -> List[TextLine]:
    """Find the lines of text in an image, top to bottom, with where each is and how sure the reading is."""
    return [
        TextLine(text=line.text, confidence=line.confidence, box=list(line.box))
        for line in macos.vision.lines(image, languages=languages, fast=fast)
    ]


def list_text_languages(fast: Fast = False) -> List[str]:
    """List the languages text can be read in, as codes such as 'en-US' or 'pt-BR'."""
    return macos.vision.languages(fast=fast)


def find_barcodes(image: ImagePath) -> List[Barcode]:
    """Find the QR codes and barcodes in an image (EAN, UPC, Code 128, PDF417, Aztec, Data Matrix...), and what they say."""
    return [Barcode(payload=code.payload, kind=code.kind, box=list(code.box)) for code in macos.vision.barcodes(image)]


def classify_image(
    image: ImagePath,
    limit: Annotated[int, Field(description="How many labels, at most.", ge=1, le=50)] = 5,
    min_confidence: Annotated[
        float, Field(description="Leave out the labels less sure than this, from 0 to 1.", ge=0, le=1)
    ] = 0.1,
) -> List[Label]:
    """Say what an image shows, most likely first, from over a thousand categories: 'beach', 'dog', 'food', 'document'..."""
    return [
        Label(label=label, confidence=confidence)
        for label, confidence in macos.vision.classify(image, limit=limit, min_confidence=min_confidence)
    ]


def find_faces(image: ImagePath) -> List[Box]:
    """
    Find the faces in an image, as [x, y, width, height] fractions of it from its top-left corner. It
    doesn't tell who they are.
    """
    return [list(face) for face in macos.vision.faces(image)]


def find_animals(image: ImagePath) -> List[Animal]:
    """Find the cats and dogs in an image."""
    return [
        Animal(kind=animal.kind, confidence=animal.confidence, box=list(animal.box))
        for animal in macos.vision.animals(image)
    ]


def remove_image_subject(
    image: ImagePath,
    output: PngOutput,
    crop: Annotated[
        bool, Field(description="True to trim the result to the subject. The image's size is kept by default.")
    ] = False,
) -> Saved:
    """
    Cut out the subject of a photo (a person, an animal, an object) onto a transparent background, like
    Photos' "lift subject from background". Fails when no subject stands out.
    """
    return _save(output, macos.vision.remove_background(image, crop=crop), "No subject stands out of the background.")


def scan_document_photo(image: ImagePath, output: PngOutput) -> Saved:
    """
    Turn a photo of a document (a page, a receipt, a card) into a flat, straight scan, like the scanner
    of Notes: its edges are found, the rest cropped away and the perspective fixed. Fails when no
    document is found.
    """
    return _save(output, macos.vision.scan_document(image), "No document was found in the photo.")


def smart_crop_image(
    image: ImagePath,
    output: PngOutput,
    width: Annotated[int, Field(description="The width wanted, in pixels.", ge=1, le=8192)],
    height: Annotated[int, Field(description="The height wanted, in pixels.", ge=1, le=8192)],
) -> Saved:
    """
    Crop and scale an image to a size, centred on its most interesting part (a face, an animal, the main
    object) rather than its middle: for thumbnails and avatars. It's never scaled up.
    """
    return _save(output, macos.vision.smart_crop(image, width, height), "Nothing was cropped.")


def compare_images(first: ImagePath, second: ImagePath) -> Distance:
    """Say how different two images look: whether one is a copy, a resized or re-saved version, of the other."""
    return Distance(distance=macos.vision.image_distance(first, second))


def find_duplicate_images(
    images: Images,
    threshold: Annotated[
        float,
        Field(
            description="How alike two images must be to go together: raise it to group similar shots too.", gt=0, le=2
        ),
    ] = 0.3,
) -> List[List[str]]:
    """
    Group the images that look like the same picture: copies, resized or re-saved versions, burst shots.
    Only the groups of two or more are returned. Every image is compared with every other, so thousands
    take a while.
    """
    return [[str(image) for image in group] for group in macos.vision.duplicates(images, threshold=threshold)]


def pick_best_shot(images: Images) -> BestShot:
    """Pick the photo where the faces look best: sharp, well lit, eyes open, facing the camera. To keep one photo of a burst."""
    best = macos.vision.best_shot(images)
    return BestShot(path=None if best is None else str(best))


def get_horizon_tilt(image: ImagePath) -> Horizon:
    """Say how tilted a photo's horizon is. straighten_image levels it."""
    return Horizon(degrees=macos.vision.horizon(image))


def score_image_aesthetics(image: ImagePath) -> Aesthetics:
    """Score how good a photo looks, and tell a real photo from a screenshot, a receipt or a document. Needs macOS 15."""
    scored = macos.vision.aesthetics(image)
    return Aesthetics(score=scored.score, utility=scored.utility)


def detect_body_poses(image: ImagePath) -> List[Pose]:
    """
    Find the people in an image and where their joints are: head, shoulders, elbows, wrists, hips,
    knees, ankles. It doesn't tell who they are.
    """
    return [
        Pose(joints={name: list(joint) for name, joint in pose.joints.items()}, confidence=pose.confidence)
        for pose in macos.vision.body_pose(image)
    ]


def detect_hand_poses(
    image: ImagePath,
    max_hands: Annotated[int, Field(description="How many hands to find, at most.", ge=1, le=20)] = 4,
) -> List[Hand]:
    """Find the hands in an image, with the wrist and each finger's joints and tip: to read a gesture, such as a thumbs-up."""
    return [
        Hand(
            side=hand.side,
            joints={name: list(joint) for name, joint in hand.joints.items()},
            confidence=hand.confidence,
        )
        for hand in macos.vision.hand_pose(image, max_hands=max_hands)
    ]


def register(server: MCPServer) -> None:
    for reader, title in (
        (read_text_in_image, "Read the text in an image"),
        (find_text_lines_in_image, "Find the lines of text in an image"),
        (list_text_languages, "List the languages text is read in"),
        (find_barcodes, "Find barcodes and QR codes"),
        (classify_image, "Say what an image shows"),
        (find_faces, "Find faces in an image"),
        (find_animals, "Find cats and dogs in an image"),
        (compare_images, "Compare two images"),
        (find_duplicate_images, "Find duplicate images"),
        (pick_best_shot, "Pick the best photo"),
        (get_horizon_tilt, "Get a photo's horizon tilt"),
        (score_image_aesthetics, "Score a photo"),
        (detect_body_poses, "Find people's poses"),
        (detect_hand_poses, "Find hands' poses"),
    ):
        add_tool(server, reader, title=title, annotations=READ_ONLY)
    # They make a PNG from the image, and the output may be the source: done again, they crop, cut out or
    # flatten it again. Not idempotent, then, and they write over a file.
    for writer, title in (
        (remove_image_subject, "Cut the subject out of a photo"),
        (scan_document_photo, "Scan a photo of a document"),
        (smart_crop_image, "Crop an image on its subject"),
    ):
        add_tool(server, writer, title=title, annotations=DESTRUCTIVE)
