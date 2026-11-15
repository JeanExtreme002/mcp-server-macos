"""Tools that read, edit, merge, split, sign, redact and encrypt PDFs, from ``macos.pdf``."""

import re
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Callable, Dict, List, Literal, Optional, Sequence, Tuple, Union

import macos
from mcp.server.mcpserver import Image, MCPServer
from pydantic import BaseModel, Field

from .._registry import DESTRUCTIVE, READ_ONLY, REPLACING, add_tool

PdfPath = Annotated[str, Field(description="The path of the PDF.", min_length=1)]
Output = Annotated[
    str,
    Field(
        description="Where to save the resulting PDF. A file already there is replaced. The result isn't encrypted, "
        "even when the PDF was: save it apart from an encrypted original, and encrypt it again if it should be.",
        min_length=1,
    ),
]
Password = Annotated[Optional[str], Field(description="The password that opens the PDF, when it's encrypted.")]
Pages = Annotated[
    Optional[List[Annotated[int, Field(ge=1)]]],
    Field(description="The pages, numbered from 1. Every page by default."),
]
Color = Annotated[str, Field(description="A hex color, such as '#808080'.", pattern=r"^#[0-9a-fA-F]{6}$")]
Targets = Annotated[
    List[Annotated[str, Field(min_length=1)]],
    Field(
        description="The texts to look for, matched as whole words, in any case and whatever spacing or line break is "
        "between them ('Ana' isn't in 'Banana'). With regex, regular expressions instead.",
        min_length=1,
    ),
]
Regex = Annotated[
    bool,
    Field(description="True to take the texts as Python regular expressions, for what follows a shape (IDs, emails, phones)."),
]
Corner = Literal["bottom_right", "bottom_left", "top_right", "top_left"]
Position = Annotated[
    Optional[Union[Corner, Tuple[float, float]]],
    Field(
        description="Where on the page: a corner ('bottom_right', 'bottom_left', 'top_right', 'top_left', margin "
        "points from the edges), or [x, y] in points from the page's bottom-left corner (72 points are an inch)."
    ),
]
Near = Annotated[
    Optional[str],
    Field(description="Put it beside this text of the page instead, such as 'Signature:'. The first match is taken."),
]
Side = Annotated[
    Literal["right", "left", "above", "below"], Field(description="With near: which side of the text to put it.")
]


class PdfInfo(BaseModel):
    """What a PDF is."""

    pages: int = Field(description="How many pages it has.")
    title: Optional[str] = Field(description="Its title.")
    author: Optional[str] = Field(description="Its author.")
    subject: Optional[str] = Field(description="Its subject.")
    keywords: List[str] = Field(description="Its keywords.")
    creator: Optional[str] = Field(description="The app it was made in, such as 'Microsoft Word'.")
    producer: Optional[str] = Field(description="The software that wrote the PDF.")
    created: Optional[datetime] = Field(description="When it was made.")
    modified: Optional[datetime] = Field(description="When it was last changed.")


class PdfText(BaseModel):
    """The text of a PDF."""

    text: str = Field(
        description="The text, one page after another. Empty for scanned pages, which have no text: ocr_pdf adds it."
    )


class Saved(BaseModel):
    """A file that was written."""

    path: str = Field(description="The path of the file.")


class SavedFiles(BaseModel):
    """Files that were written."""

    paths: List[str] = Field(description="The paths of the files, page by page.")


class FormField(BaseModel):
    """A field of a PDF form."""

    name: str = Field(description="Its name, which fill_pdf_form takes.")
    kind: str = Field(description="'text', 'checkbox', 'radio', 'choice' (a list or a menu), 'button' or 'signature'.")
    value: Union[str, bool, None] = Field(
        description="What's filled in: the text or choice, whether a checkbox is ticked, the radio button chosen. "
        "Null when empty."
    )
    options: List[str] = Field(description="What a choice or a group of radio buttons offers. Empty for the others.")
    page: int = Field(description="The page it's on, from 1.")


class Bookmark(BaseModel):
    """An entry of a PDF's table of contents, as the sidebar shows it."""

    title: str = Field(description="Its title.")
    page: int = Field(description="The page it opens, from 1. 0 when it points nowhere in the document, as a heading.", ge=0)
    level: int = Field(description="How deep it sits: 0 for a chapter, 1 for its sections, and so on.", ge=0, default=0)


class Match(BaseModel):
    """Where a text shows in a PDF."""

    page: int = Field(description="The page, from 1.")
    text: str = Field(description="The text, as the page has it.")
    box: List[float] = Field(
        description="[x, y, width, height] around it, in points from the page's bottom-left corner: what the position "
        "of sign_pdf and add_text_to_pdf takes."
    )
    font: Optional[str] = Field(description="The font it's written in, when PDFKit tells.")
    size: Optional[float] = Field(description="The font's size, in points, when PDFKit tells.")


class Changes(BaseModel):
    """What was changed in a PDF."""

    path: str = Field(description="The resulting PDF.")
    matches: Dict[str, int] = Field(description="How many times each text was found, by the text as given.")
    pages: Dict[str, int] = Field(
        description="The pages changed, by number, with how many matches each had: look them over before sharing the PDF."
    )


def _saved(path: Path) -> Saved:
    return Saved(path=str(path))


def _targets(texts: Sequence[str], regex: bool) -> List[Union[str, "re.Pattern[str]"]]:
    """The texts as pymacos takes them: as they are, or compiled, where a bad pattern is a ValueError."""
    if not regex:
        return list(texts)
    compiled: List[Union[str, "re.Pattern[str]"]] = []
    for text in texts:
        try:
            compiled.append(re.compile(text))
        except re.error as error:
            raise ValueError("{!r} isn't a valid regular expression: {}".format(text, error)) from None
    return compiled


def _changes(done: Any) -> Changes:
    return Changes(
        path=str(done.path),
        matches={str(target): count for target, count in done.matches.items()},
        pages={str(page): count for page, count in done.pages.items()},
    )


def _some(
    path: str, target: Union[str, "re.Pattern[str]"], occurrences: List[int], pages: Optional[List[int]], password: Optional[str]
) -> List[Any]:
    """The occurrences of one text that find_in_pdf numbers, from 1, as the matches pymacos takes."""
    found = macos.pdf.find(path, target, pages=pages, password=password)
    wrong = [number for number in occurrences if not 1 <= number <= len(found)]
    if wrong:
        raise ValueError(
            "occurrences must be from 1 to {}, the times the text shows, not {}".format(len(found), ", ".join(map(str, wrong)))
        )
    return [found[number - 1] for number in dict.fromkeys(occurrences)]


def _expanded(target: Union[str, "re.Pattern[str]"], found: str, new: str) -> str:
    """``new`` with the groups of ``target`` filled in from ``found``, the text one of its matches has."""
    if isinstance(target, str) or "\\" not in new:
        # Nothing to fill in: a replacement without a backslash has no group to refer to, and the text
        # found isn't matched again, which a pattern that looks around it (a lookbehind) may not do.
        return new
    # The match is found ignoring spacing and line breaks, which its text may have otherwise.
    matched = target.fullmatch(found) or target.fullmatch(" ".join(found.split())) or target.search(found)
    if matched is None:
        raise ValueError(
            "{!r} found {!r}, which it doesn't match as written: give the replacement without groups".format(
                target.pattern, found
            )
        )
    expanded: str = _template(lambda: matched.expand(new), new)
    return expanded


def _template(fill: Callable[[], Any], new: str) -> Any:
    """What ``fill`` gives, where a replacement that refers to a group the pattern hasn't is a ValueError."""
    try:
        return fill()
    except re.error as error:
        raise ValueError("{!r} isn't a valid replacement for the pattern: {}".format(new, error)) from None


def get_pdf_info(path: PdfPath, password: Password = None) -> PdfInfo:
    """Get how many pages a PDF has, and what it records about itself: title, author, keywords, dates, the apps that made it."""
    metadata = macos.pdf.metadata(path, password=password)
    return PdfInfo(
        pages=macos.pdf.page_count(path, password=password),
        title=metadata.title,
        author=metadata.author,
        subject=metadata.subject,
        keywords=list(metadata.keywords),
        creator=metadata.creator,
        producer=metadata.producer,
        created=metadata.created,
        modified=metadata.modified,
    )


def read_pdf_text(path: PdfPath, pages: Pages = None, password: Password = None) -> PdfText:
    """Get the text of a PDF, or of some of its pages."""
    return PdfText(text=macos.pdf.text(path, pages, password=password))


def find_in_pdf(
    path: PdfPath,
    text: Annotated[str, Field(description="The text to look for, as find_in_pdf matches it.", min_length=1)],
    regex: Regex = False,
    pages: Pages = None,
    password: Password = None,
) -> List[Match]:
    """
    Find where a text shows in a PDF, page by page, in reading order, with the box around each place:
    as whole words, in any case. Only the text a PDF holds as text is found, not the words in a scan.
    """
    (target,) = _targets([text], regex)
    return [
        Match(page=match.page, text=match.text, box=list(match.box), font=match.font, size=match.size)
        for match in macos.pdf.find(path, target, pages=pages, password=password)
    ]


def render_pdf_page(
    path: PdfPath,
    page: Annotated[int, Field(description="The page, from 1.", ge=1)] = 1,
    size: Annotated[int, Field(description="The longest side of the picture, in pixels.", ge=16, le=4096)] = 1024,
    password: Password = None,
) -> Image:
    """Draw a page of a PDF as a picture, to look at it: its layout, a scan, what a tool changed."""
    return Image(data=macos.pdf.render(path, page, size=size, password=password), format="png")


def list_pdf_bookmarks(path: PdfPath, password: Password = None) -> List[Bookmark]:
    """Get a PDF's table of contents, in order, sections under their chapter. Empty when it has none."""
    return [Bookmark(title=mark.title, page=mark.page, level=mark.level) for mark in macos.pdf.bookmarks(path, password=password)]


def list_pdf_form_fields(path: PdfPath, password: Password = None) -> List[FormField]:
    """Get the fields of a PDF form, in page order, with what's filled in."""
    return [
        FormField(name=field.name, kind=field.kind, value=field.value, options=list(field.options), page=field.page)
        for field in macos.pdf.form_fields(path, password=password)
    ]


def merge_pdfs(
    inputs: Annotated[List[str], Field(description="The PDFs, in order.", min_length=1)],
    output: Output,
    password: Annotated[Optional[str], Field(description="The password of the encrypted inputs: they must share it.")] = None,
) -> Saved:
    """Join PDFs, one after another, into one. The result isn't encrypted."""
    return _saved(macos.pdf.merge(inputs, output, password=password))


def extract_pdf_pages(
    path: PdfPath,
    output: Output,
    pages: Annotated[
        List[Annotated[int, Field(ge=1)]], Field(description="The pages to keep, from 1, in the order wanted.", min_length=1)
    ],
    password: Password = None,
) -> Saved:
    """Save some pages of a PDF as a new one: to split a PDF, or put its pages in another order."""
    return _saved(macos.pdf.extract(path, output, pages, password=password))


def rotate_pdf_pages(
    path: PdfPath,
    output: Output,
    degrees: Annotated[
        Literal[90, 180, 270, -90, -180, -270],
        Field(description="How far to turn clockwise: 90, 180 or 270. Negative turns counter-clockwise."),
    ],
    pages: Pages = None,
    password: Password = None,
) -> Saved:
    """Turn the pages of a PDF, or some of them: for scans that came out sideways."""
    return _saved(macos.pdf.rotate(path, output, degrees, pages=pages, password=password))


def encrypt_pdf(
    path: PdfPath,
    output: Annotated[
        str,
        Field(description="Where to save the encrypted PDF. A file already there is replaced.", min_length=1),
    ],
    password: Annotated[
        str,
        Field(description="The password that will open it: letters without accents, digits and punctuation only.", min_length=1),
    ],
    current_password: Annotated[
        Optional[str], Field(description="The password of a PDF already encrypted, to change it.")
    ] = None,
    owner_password: Annotated[
        Optional[str],
        Field(description="The other password, meant to guard printing, copying and editing. The same as password by default."),
    ] = None,
) -> Saved:
    """Save a copy of a PDF that asks for a password to open, in Preview, Acrobat and browsers alike."""
    return _saved(
        macos.pdf.encrypt(path, output, password, current_password=current_password, owner_password=owner_password)
    )


def decrypt_pdf(
    path: PdfPath,
    output: Output,
    password: Annotated[
        Optional[str],
        Field(
            description="The password that opens the PDF, or its owner's. Not needed for one that opens without a "
            "password and only restricts printing, copying or editing."
        ),
    ] = None,
) -> Saved:
    """
    Save a copy of an encrypted PDF that asks for no password, and has no restrictions on printing,
    copying or editing. The pages, metadata and bookmarks are kept.
    """
    return _saved(macos.pdf.decrypt(path, output, password))


def ocr_pdf(
    path: PdfPath,
    output: Output,
    languages: Annotated[
        Optional[List[str]],
        Field(description="The languages to read, such as ['pt-BR', 'en-US']. Detected by default."),
    ] = None,
    redo: Annotated[
        bool,
        Field(
            description="True to read again the pages that have text already, replacing it: they become pictures of "
            "what they show."
        ),
    ] = False,
    password: Password = None,
) -> Saved:
    """
    Make a scanned PDF searchable: the text read on each page is added, invisibly, so it can be
    selected, copied and searched. The pages look the same; forms, notes and links don't stay editable.
    """
    return _saved(macos.pdf.ocr(path, output, languages=languages, redo=redo, password=password))


def watermark_pdf(
    path: PdfPath,
    output: Output,
    text: Annotated[str, Field(description="The text, such as 'CONFIDENTIAL', 'DRAFT' or a name.", min_length=1)],
    color: Color = "#808080",
    opacity: Annotated[float, Field(description="From 0 (invisible) to 1.", ge=0, le=1)] = 0.25,
    password: Password = None,
) -> Saved:
    """Write a text across every page of a PDF, diagonally and see-through. Forms, notes and links don't stay editable."""
    return _saved(macos.pdf.watermark(path, output, text, color=color, opacity=opacity, password=password))


def compress_pdf(path: PdfPath, output: Output, password: Password = None) -> Saved:
    """
    Save a smaller copy of a PDF, like Preview's Reduce File Size: images are scaled down, text stays
    sharp. Photos lose detail, so keep the original. A PDF of text alone can't get smaller.
    """
    return _saved(macos.pdf.compress(path, output, password=password))


def grayscale_pdf(path: PdfPath, output: Output, password: Password = None) -> Saved:
    """Save a copy of a PDF in shades of gray, for printing without color."""
    return _saved(macos.pdf.grayscale(path, output, password=password))


def images_to_pdf(
    images: Annotated[List[str], Field(description="The images, one per page, in order: JPEG, PNG, HEIC...", min_length=1)],
    output: Output,
) -> Saved:
    """Make a PDF with one page per image, each the size of its image: photos of documents become a scan."""
    return _saved(macos.pdf.from_images(images, output))


def extract_pdf_images(
    path: PdfPath,
    folder: Annotated[str, Field(description="The folder to save the pictures into.", min_length=1)],
    pages: Pages = None,
    password: Password = None,
) -> SavedFiles:
    """Save the pictures embedded in a PDF into a folder. To save whole pages as pictures, see render_pdf_page."""
    return SavedFiles(paths=[str(saved) for saved in macos.pdf.images(path, folder, pages=pages, password=password)])


def fill_pdf_form(
    path: PdfPath,
    output: Output,
    values: Annotated[
        Dict[str, Union[bool, str]],
        Field(
            description="The values by field name, as list_pdf_form_fields gives them: text for text fields and "
            "choices, true or false for checkboxes, the option to choose for radio buttons."
        ),
    ],
    password: Password = None,
) -> Saved:
    """Fill in a PDF form's fields. They stay editable. An unknown name or option is refused before anything is written."""
    return _saved(macos.pdf.fill_form(path, output, values, password=password))


def sign_pdf(
    path: PdfPath,
    output: Output,
    image: Annotated[
        str,
        Field(
            description="The picture of the signature, a stamp or a logo: a PNG with a transparent background looks best.",
            min_length=1,
        ),
    ],
    page: Annotated[Optional[int], Field(description="The page, from 1. The last one by default.", ge=1)] = None,
    position: Position = None,
    near: Near = None,
    side: Side = "right",
    width: Annotated[
        float, Field(description="Its width, in points (72 are an inch). The height keeps its proportions.", gt=0)
    ] = 150,
    password: Password = None,
) -> Saved:
    """
    Put the picture of a signature on a page, at the bottom right by default. It's a picture, not a
    cryptographic signature. The pages are redrawn as they look: fill a form first, with fill_pdf_form.
    """
    return _saved(
        macos.pdf.sign(path, output, image, page=page, position=position, near=near, side=side, width=width, password=password)
    )


def add_text_to_pdf(
    path: PdfPath,
    output: Output,
    text: Annotated[str, Field(description="The text. Lines break at \\n.", min_length=1)],
    page: Annotated[Optional[int], Field(description="The page, from 1. The first one by default.", ge=1)] = None,
    position: Position = None,
    near: Near = None,
    side: Side = "right",
    size: Annotated[float, Field(description="Its size, in points.", gt=0, le=500)] = 12,
    color: Color = "#000000",
    font: Annotated[Optional[str], Field(description="A font's name, such as 'Helvetica-Bold'. The system's by default.")] = None,
    password: Password = None,
) -> Saved:
    """Write a text on a page of a PDF, as a text box that can still be edited or moved in Preview. At the top left by default."""
    return _saved(
        macos.pdf.add_text(
            path,
            output,
            text,
            page=page,
            position=position,
            near=near,
            side=side,
            size=size,
            color=color,
            font=font,
            password=password,
        )
    )


def set_pdf_bookmarks(
    path: PdfPath,
    output: Output,
    bookmarks: Annotated[
        List[Bookmark],
        Field(
            description="The table of contents, in order. A level may go at most one deeper than the entry before. "
            "Empty takes it away."
        ),
    ],
    password: Password = None,
) -> Saved:
    """Give a PDF a table of contents, in place of the one it has."""
    # As pymacos's own bookmarks: a page 0 is a heading that opens nothing only in that form, where a
    # tuple's 0 is taken for a mistake. So a table of contents list_pdf_bookmarks gave is written back.
    marks = [macos.pdf.Bookmark(title=mark.title, page=mark.page, level=mark.level) for mark in bookmarks]
    return _saved(macos.pdf.set_bookmarks(path, output, marks, password=password))


def redact_pdf(
    path: PdfPath,
    output: Output,
    targets: Targets,
    regex: Regex = False,
    password: Password = None,
) -> Changes:
    """
    Black out texts in a PDF for good: the text is removed, not covered, from the pages, the form
    fields, the comments, the metadata and the bookmarks. A text that isn't found at all is an error,
    so a redaction that missed doesn't look like it worked. Text in pictures (a scan, a logo) stays:
    look the result over before sharing it.
    """
    return _changes(macos.pdf.redact(path, output, _targets(targets, regex), password=password))


def erase_from_pdf(
    path: PdfPath,
    output: Output,
    targets: Targets,
    regex: Regex = False,
    occurrences: Annotated[
        Optional[List[int]],
        Field(
            description="With a single text: which of the places it shows to erase, numbered from 1 as find_in_pdf "
            "gives them. Every place by default.",
            min_length=1,
        ),
    ] = None,
    background: Color = "#ffffff",
    pages: Pages = None,
    password: Password = None,
) -> Changes:
    """
    Take texts out of a PDF's pages, painting the background where they were. Each page with a match
    becomes a picture of what it shows: the rest of its text can't be selected or searched any more.
    For editing: to make sure a text can't be recovered from the file, use redact_pdf.
    """
    found = _targets(targets, regex)
    if occurrences is not None:
        if len(found) != 1:
            raise ValueError("occurrences goes with a single text: give one")
        chosen: List[Any] = _some(path, found[0], occurrences, pages, password)
        return _changes(macos.pdf.erase(path, output, chosen, background=background, password=password))
    return _changes(macos.pdf.erase(path, output, found, background=background, pages=pages, password=password))


def replace_in_pdf(
    path: PdfPath,
    output: Output,
    replacements: Annotated[
        Dict[str, str],
        Field(
            description="What to write in place of each text: {\"DRAFT\": \"FINAL\", \"2026\": \"2027\"}. With regex, "
            "the keys are regular expressions, whose groups the values may refer to (\\\\1).",
            min_length=1,
        ),
    ],
    regex: Regex = False,
    occurrences: Annotated[
        Optional[List[int]],
        Field(
            description="With a single replacement: which of the places the text shows to replace, numbered from 1 as "
            "find_in_pdf gives them. Every place by default.",
            min_length=1,
        ),
    ] = None,
    color: Color = "#000000",
    background: Color = "#ffffff",
    font: Annotated[
        Optional[str], Field(description="The font to write in, such as 'Arial-BoldMT'. The old text's by default.")
    ] = None,
    size: Annotated[
        Optional[float], Field(description="The size to write at, in points. The old text's by default.", gt=0)
    ] = None,
    pages: Pages = None,
    password: Password = None,
) -> Changes:
    """
    Write new texts where a PDF's pages say old ones, in the old text's font and size. Each page with a
    match becomes a picture of what it shows, with the new texts on it: the rest of its text can't be
    selected, searched or replaced any more, so give every replacement in one call, and keep the
    original. A longer text runs past where the old one was: look the result over. A text that isn't
    found is an error.
    """
    if occurrences is not None:
        if len(replacements) != 1:
            raise ValueError("occurrences goes with a single replacement: give one")
        ((old, new),) = replacements.items()
        (target,) = _targets([old], regex)
        chosen = _some(path, target, occurrences, pages, password)
        # pymacos writes the text given as it is in place of a match: the groups of a pattern are filled
        # in here, for each match, from the text it found.
        written: Dict[Any, str] = {match: _expanded(target, match.text, new) for match in chosen}
        done = macos.pdf.replace(
            path, output, written, color=color, background=background, font=font, size=size, password=password
        )
        return _changes(done)
    compiled: Dict[Any, str] = dict(zip(_targets(list(replacements), regex), replacements.values()))
    # pymacos fills the groups in itself here: a reference to a group the pattern hasn't fails there.
    done = _template(
        lambda: macos.pdf.replace(
            path, output, compiled, color=color, background=background, font=font, size=size, pages=pages, password=password
        ),
        ", ".join(replacements.values()),
    )
    return _changes(done)


def register(server: MCPServer) -> None:
    for tool, title in (
        (get_pdf_info, "Get a PDF's information"),
        (read_pdf_text, "Read a PDF's text"),
        (find_in_pdf, "Find a text in a PDF"),
        (render_pdf_page, "Draw a page of a PDF"),
        (list_pdf_bookmarks, "Get a PDF's table of contents"),
        (list_pdf_form_fields, "Get a PDF form's fields"),
    ):
        add_tool(server, tool, title=title, annotations=READ_ONLY)
    # These set something, or make a file from scratch: doing it again gives the same file.
    for setter, title in (
        (encrypt_pdf, "Encrypt a PDF"),
        (decrypt_pdf, "Decrypt a PDF"),
        (grayscale_pdf, "Make a PDF grayscale"),
        (images_to_pdf, "Make a PDF from images"),
        (extract_pdf_images, "Save a PDF's pictures"),
        (fill_pdf_form, "Fill in a PDF form"),
        (set_pdf_bookmarks, "Set a PDF's table of contents"),
        (redact_pdf, "Redact a PDF"),
    ):
        add_tool(server, setter, title=title, annotations=REPLACING)
    # These change the pages, and the output may be the source: done again, they turn, mark, sign or
    # shrink it again. Not idempotent, then, and they write over a file.
    for transform, title in (
        (merge_pdfs, "Merge PDFs"),
        (extract_pdf_pages, "Extract pages of a PDF"),
        (rotate_pdf_pages, "Rotate pages of a PDF"),
        (ocr_pdf, "Make a scanned PDF searchable"),
        (watermark_pdf, "Watermark a PDF"),
        (compress_pdf, "Compress a PDF"),
        (sign_pdf, "Sign a PDF with a picture"),
        (add_text_to_pdf, "Write text on a PDF"),
        (erase_from_pdf, "Erase text from a PDF"),
        (replace_in_pdf, "Replace text in a PDF"),
    ):
        add_tool(server, transform, title=title, annotations=DESTRUCTIVE)
