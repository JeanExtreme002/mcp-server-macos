"""Tools for Finder: the Trash, tags, aliases, icons, archives, watching folders, and Finder's settings, from ``macos.finder``."""

from typing import Annotated, Any, Callable, Dict, List, Literal, Optional, Tuple

import macos
from mcp.server.mcpserver import Image, MCPServer
from pydantic import BaseModel, Field

from .._permissions import AUTOMATION
from .._registry import ADDITIVE, DESTRUCTIVE, LONGEST_WAIT, READ_ONLY, READ_ONLY_ONLINE, REPLACING, add_tool

ItemPath = Annotated[str, Field(description="The path of a file, a folder or an app.", min_length=1)]
Tags = Annotated[List[str], Field(description="The tags, by name, such as ['Red', 'Work'].")]
Pattern = Annotated[
    Optional[List[str]],
    Field(description="Keep only the files whose name matches one of these, in any case, such as ['*.pdf']."),
]
DesktopSort = Literal[
    "free",
    "snap_to_grid",
    "name",
    "kind",
    "date_added",
    "date_modified",
    "date_created",
    "date_last_opened",
    "size",
    "tags",
]


class ItemInfo(BaseModel):
    """What Finder knows of a file, a folder or an app."""

    tags: List[str] = Field(description="Its Finder tags.")
    is_alias: bool = Field(description="Whether it's a Finder alias, made with File › Make Alias.")
    alias_target: Optional[str] = Field(
        description="What it points to, following aliases and symbolic links. Its own path when it's neither."
    )
    has_custom_icon: bool = Field(description="Whether it has a custom icon, set in Get Info or with set_file_icon.")


class Saved(BaseModel):
    """A file that was written."""

    path: str = Field(description="The path of the file.")


class FileTags(BaseModel):
    """The tags of a file."""

    tags: List[str] = Field(description="Its Finder tags, after the change.")


class FolderChange(BaseModel):
    """A change in a watched folder."""

    path: str = Field(description="What changed.")
    kind: str = Field(
        description="'created', 'modified', 'deleted', 'renamed'... or 'rescan' when macOS lost track and the folder "
        "should be looked through again."
    )
    is_dir: bool = Field(description="Whether it's a folder.")


class FolderWait(BaseModel):
    """What happened while a folder was watched."""

    change: Optional[FolderChange] = Field(description="The change. Null when the time ran out first.")


class Selection(BaseModel):
    """What the user has in front of them in Finder."""

    selected: List[str] = Field(
        description="The files and folders selected in Finder's window in front, or on the Desktop."
    )
    current_folder: Optional[str] = Field(
        description="The folder Finder's window in front shows. Null without a window, or on Recents, AirDrop, a search."
    )


class LargeFile(BaseModel):
    """A large file."""

    path: str = Field(description="Its path.")
    size_bytes: int = Field(description="Its size, in bytes.")


class DesktopView(BaseModel):
    """How the desktop shows its icons."""

    icon_size: int = Field(description="The icons' size, in points.")
    grid_spacing: int = Field(description="The space between them.")
    text_size: int = Field(description="The size of the names, in points.")
    sort: str = Field(description="How they're kept in order: 'free' when placed freely, or what they're sorted by.")
    show_item_info: bool = Field(description="Whether a line of information shows under each name.")
    labels_on_bottom: bool = Field(description="Whether the names are below the icons, rather than to their right.")


class FinderSettings(BaseModel):
    """Finder's settings."""

    show_hidden_files: bool = Field(description="Whether hidden files (.git, .env...) show.")
    show_extensions: bool = Field(description="Whether every file name's extension shows.")
    show_path_bar: bool = Field(description="Whether windows show the path bar.")
    show_status_bar: bool = Field(description="Whether windows show the status bar.")
    show_desktop_icons: bool = Field(description="Whether the desktop shows its files, folders and disks.")
    show_library_folder: bool = Field(description="Whether the Library folder (~/Library) shows in Finder.")
    show_full_path_in_title: bool = Field(description="Whether windows show the folder's full path in their title.")
    default_view: str = Field(description="How folders show by default: 'icons', 'list', 'columns' or 'gallery'.")
    new_window_folder: Optional[str] = Field(description="The folder a new window opens. Null for Recents or Computer.")
    search_scope: str = Field(description="Where a search looks first: 'this_mac', 'current_folder' or 'previous'.")
    folders_first: bool = Field(description="Whether folders come before files when sorted by name.")
    extension_change_warning: bool = Field(description="Whether Finder asks before an extension is changed.")
    remove_old_trash_items: bool = Field(description="Whether items are deleted from the Trash after 30 days.")
    quit_menu: bool = Field(description="Whether Finder has a Quit item (⌘Q).")
    drives_on_desktop: Dict[str, bool] = Field(
        description="Which disks show on the desktop: internal, external, removable, servers."
    )
    desktop_view: DesktopView = Field(description="How the desktop shows its icons.")


def get_finder_info(path: ItemPath) -> ItemInfo:
    """
    Get what Finder knows of a file, a folder or an app: its tags, whether it's an alias and to what, and
    whether it has a custom icon. Following an alias to a network share may mount the share.
    """
    alias = macos.finder.is_alias(path)
    try:
        target: Optional[str] = str(macos.finder.resolve_alias(path))
    except FileNotFoundError:
        target = None  # an alias whose original is gone
    return ItemInfo(
        tags=macos.finder.tags(path),
        is_alias=alias,
        alias_target=target,
        has_custom_icon=macos.finder.has_custom_icon(path),
    )


def get_file_thumbnail(
    path: ItemPath,
    size: Annotated[int, Field(description="The picture's largest side, in pixels.", ge=16, le=4096)] = 256,
) -> Image:
    """
    Get a preview of a file, like those Finder shows: its content for documents, images, videos and
    PDFs, its icon otherwise.
    """
    return Image(data=macos.finder.thumbnail(path, size=size), format="png")


def set_file_tags(path: ItemPath, tags: Tags) -> FileTags:
    """Replace the Finder tags of a file or a folder with these. An empty list takes them all away."""
    macos.finder.set_tags(path, tags)
    return FileTags(tags=macos.finder.tags(path))


def add_file_tags(
    path: ItemPath, tags: Annotated[List[str], Field(description="The tags to add.", min_length=1)]
) -> FileTags:
    """Add Finder tags to a file or a folder, keeping the ones it has."""
    return FileTags(tags=macos.finder.add_tags(path, *tags))


def remove_file_tags(
    path: ItemPath, tags: Annotated[List[str], Field(description="The tags to take away.", min_length=1)]
) -> FileTags:
    """Take Finder tags away from a file or a folder. Those it hasn't are ignored."""
    return FileTags(tags=macos.finder.remove_tags(path, *tags))


def move_to_trash(path: ItemPath) -> Saved:
    """
    Move a file or a folder to the Trash, and return where it ended up. Finder's Put Back restores it,
    until the Trash is emptied.
    """
    return Saved(path=str(macos.finder.trash(path)))


def reveal_in_finder(path: ItemPath) -> str:
    """Open a Finder window with a file or a folder selected, for the user to see where it is."""
    macos.finder.reveal(path)
    return "Revealed {}.".format(path)


def quick_look(path: ItemPath) -> str:
    """Show a file in Quick Look, the preview Space opens in Finder. It stays until the user closes it."""
    macos.finder.quick_look(path)
    return "Showing {}.".format(path)


def make_alias(
    target: ItemPath,
    alias: Annotated[
        Optional[str],
        Field(
            description="Where to make it: a path, or a folder to make it in. Next to the target by default, as '<name> alias'."
        ),
    ] = None,
) -> Saved:
    """
    Make a Finder alias of a file, a folder or an app, like File › Make Alias. Fails when something is
    already at the alias's path.
    """
    return Saved(path=str(macos.finder.make_alias(target, alias)))


def set_file_icon(
    path: ItemPath,
    image: Annotated[
        str,
        Field(
            description="An image file (PNG, JPEG, ICNS...), or any file, folder or app whose icon to copy.",
            min_length=1,
        ),
    ],
) -> str:
    """Give a file, a folder or an app a custom icon, like pasting one in Get Info. Finder may take a moment to show it."""
    macos.finder.set_icon(path, image)
    return "Icon set on {}.".format(path)


def remove_file_icon(path: ItemPath) -> str:
    """Take a custom icon away, so the item shows its usual one again."""
    macos.finder.remove_icon(path)
    return "Icon removed from {}.".format(path)


def compress_to_zip(
    path: ItemPath,
    output: Annotated[
        Optional[str], Field(description="Where to save the .zip. Next to it, as '<name>.zip', by default.")
    ] = None,
) -> Saved:
    """
    Zip a file or a folder, like Finder's Compress, keeping what plain zip tools lose: tags, extended
    attributes, permissions. An archive already there is replaced once the new one is whole.
    """
    return Saved(path=str(macos.finder.compress(path, output)))


def extract_zip(
    archive: Annotated[str, Field(description="The .zip to unzip.", min_length=1)],
    destination: Annotated[
        Optional[str], Field(description="The folder to unzip into. The archive's own by default.")
    ] = None,
    overwrite: Annotated[
        bool,
        Field(description="True to write over the files of the same name already there. They're refused by default."),
    ] = False,
) -> Saved:
    """
    Unzip an archive, keeping the attributes and permissions it stores. Files already there are refused,
    unless overwrite is true.
    """
    return Saved(path=str(macos.finder.extract(archive, destination, overwrite=overwrite)))


def wait_for_folder_change(
    folder: Annotated[str, Field(description="The folder to watch, such as '~/Downloads'.", min_length=1)],
    pattern: Pattern = None,
    recursive: Annotated[bool, Field(description="False to leave out what happens in its subfolders.")] = True,
    timeout_seconds: Annotated[float, Field(description="How long to wait, in seconds.", gt=0, le=LONGEST_WAIT)] = 60.0,
) -> FolderWait:
    """
    Wait until something changes in a folder, and say what: for a download or an export to show up.
    The change is null when the time runs out first.
    """
    found = macos.finder.wait_for_change(folder, pattern=pattern, recursive=recursive, timeout=timeout_seconds)
    return FolderWait(
        change=None if found is None else FolderChange(path=str(found.path), kind=found.kind, is_dir=found.is_dir)
    )


def get_finder_selection() -> Selection:
    """
    Get the files and folders the user selected in Finder, and the folder its window in front shows:
    what they have in front of them.
    """
    folder = macos.finder.current_folder()
    return Selection(
        selected=[str(path) for path in macos.finder.selection()],
        current_folder=None if folder is None else str(folder),
    )


def find_largest_files(
    folder: Annotated[str, Field(description="The folder to look in, with its subfolders, such as '~'.", min_length=1)],
    count: Annotated[int, Field(description="How many files, at most.", ge=1, le=500)] = 20,
    at_least_bytes: Annotated[
        int, Field(description="Leave out the files smaller than this, in bytes.", ge=0)
    ] = 1_000_000,
) -> List[LargeFile]:
    """
    Find the largest files in a folder and its subfolders, the biggest first: what takes the disk's room.
    It asks Spotlight, so it's quick even for the home folder; a folder Spotlight doesn't index is walked,
    which is slower, up to a minute.
    """
    return [
        LargeFile(path=str(path), size_bytes=size)
        for path, size in macos.finder.largest(folder, count, at_least=at_least_bytes)
    ]


def get_finder_settings() -> FinderSettings:
    """
    Get Finder's settings: what it shows (hidden files, extensions, bars, the desktop), how it opens and
    searches, the Trash, the desktop's view.
    """
    view = macos.finder.desktop_view()
    folder = macos.finder.new_window_folder()
    return FinderSettings(
        show_hidden_files=macos.finder.show_hidden_files(),
        show_extensions=macos.finder.show_extensions(),
        show_path_bar=macos.finder.show_path_bar(),
        show_status_bar=macos.finder.show_status_bar(),
        show_desktop_icons=macos.finder.show_desktop_icons(),
        show_library_folder=macos.finder.show_library_folder(),
        show_full_path_in_title=macos.finder.show_full_path_in_title(),
        default_view=macos.finder.default_view(),
        new_window_folder=None if folder is None else str(folder),
        search_scope=macos.finder.search_scope(),
        folders_first=macos.finder.folders_first(),
        extension_change_warning=macos.finder.extension_change_warning(),
        remove_old_trash_items=macos.finder.remove_old_trash_items(),
        quit_menu=macos.finder.quit_menu(),
        drives_on_desktop=macos.finder.drives_on_desktop(),
        desktop_view=DesktopView(
            icon_size=int(view["icon_size"]),  # type: ignore[call-overload]
            grid_spacing=int(view["grid_spacing"]),  # type: ignore[call-overload]
            text_size=int(view["text_size"]),  # type: ignore[call-overload]
            sort="free" if view["sort"] is None else str(view["sort"]),
            show_item_info=bool(view["show_item_info"]),
            labels_on_bottom=bool(view["labels_on_bottom"]),
        ),
    )


def set_finder_settings(
    show_hidden_files: Annotated[
        Optional[bool], Field(description="True to show hidden files (.git, .env...).")
    ] = None,
    show_extensions: Annotated[Optional[bool], Field(description="True to show every file name's extension.")] = None,
    show_path_bar: Annotated[Optional[bool], Field(description="True to show the path bar in windows.")] = None,
    show_status_bar: Annotated[Optional[bool], Field(description="True to show the status bar in windows.")] = None,
    show_desktop_icons: Annotated[
        Optional[bool], Field(description="False to hide the desktop's icons, for a clean screen. The files stay.")
    ] = None,
    show_library_folder: Annotated[
        Optional[bool], Field(description="True to show the Library folder in Finder.")
    ] = None,
    show_full_path_in_title: Annotated[
        Optional[bool], Field(description="True to show the full path in windows' title.")
    ] = None,
    default_view: Annotated[
        Optional[Literal["icons", "list", "columns", "gallery"]], Field(description="How folders show by default.")
    ] = None,
    new_window_folder: Annotated[
        Optional[str], Field(description="The folder new windows open, such as '~/Downloads'.")
    ] = None,
    search_scope: Annotated[
        Optional[Literal["this_mac", "current_folder", "previous"]], Field(description="Where a search looks first.")
    ] = None,
    folders_first: Annotated[
        Optional[bool], Field(description="True to keep folders before files when sorted by name.")
    ] = None,
    extension_change_warning: Annotated[
        Optional[bool], Field(description="False to rename a file's extension without being asked.")
    ] = None,
    remove_old_trash_items: Annotated[
        Optional[bool],
        Field(description="True to delete items from the Trash after 30 days. They're gone for good then."),
    ] = None,
    quit_menu: Annotated[
        Optional[bool],
        Field(description="True to give Finder a Quit item (⌘Q). Quitting it hides the desktop's icons."),
    ] = None,
    drives_on_desktop: Annotated[
        Optional[Dict[Literal["internal", "external", "removable", "servers"], bool]],
        Field(
            description="Which disks to show on the desktop (true) or not (false): internal, external, removable, servers."
        ),
    ] = None,
) -> str:
    """
    Change Finder's settings. Give only the settings to change: the others stay as they are. Finder
    relaunches once, at the end. The desktop's view has its own tool, set_desktop_view.
    """
    # The folder goes first: it's the one setting that can be refused (a folder that isn't there), and
    # nothing is written back when one is, so it must be refused before any other setting is changed.
    setters: Tuple[Tuple[Any, Callable[[Any], Any], str], ...] = (
        (new_window_folder, macos.finder.set_new_window_folder, "new window folder"),
        (show_hidden_files, macos.finder.set_show_hidden_files, "hidden files"),
        (show_extensions, macos.finder.set_show_extensions, "extensions"),
        (show_path_bar, macos.finder.set_show_path_bar, "path bar"),
        (show_status_bar, macos.finder.set_show_status_bar, "status bar"),
        (show_desktop_icons, macos.finder.set_show_desktop_icons, "desktop icons"),
        (show_library_folder, macos.finder.set_show_library_folder, "Library folder"),
        (show_full_path_in_title, macos.finder.set_show_full_path_in_title, "full path in title"),
        (default_view, macos.finder.set_default_view, "default view"),
        (search_scope, macos.finder.set_search_scope, "search scope"),
        (folders_first, macos.finder.set_folders_first, "folders first"),
        (extension_change_warning, macos.finder.set_extension_change_warning, "extension warning"),
        (remove_old_trash_items, macos.finder.set_remove_old_trash_items, "old Trash items"),
        (quit_menu, macos.finder.set_quit_menu, "Quit menu"),
        (
            drives_on_desktop or None,
            lambda drives: macos.finder.set_show_drives_on_desktop(**drives),
            "drives on desktop",
        ),
    )
    given = [(value, setter, name) for value, setter, name in setters if value is not None]
    if not given:
        raise ValueError("no setting was given: say which one to change")
    with macos.settings.batch():
        for value, setter, _ in given:
            setter(value)
    return "Changed: {}.".format(", ".join(name for _, _, name in given))


def set_desktop_view(
    icon_size: Annotated[Optional[int], Field(description="The icons' size, in points.", ge=16, le=128)] = None,
    grid_spacing: Annotated[Optional[int], Field(description="The space between them.", ge=1, le=100)] = None,
    text_size: Annotated[Optional[int], Field(description="The size of the names, in points.", ge=10, le=16)] = None,
    sort: Annotated[
        Optional[DesktopSort],
        Field(
            description="How to keep them in order: 'free' to place them freely, 'snap_to_grid', or what to sort by."
        ),
    ] = None,
    show_item_info: Annotated[
        Optional[bool], Field(description="True to add a line of information under each name.")
    ] = None,
    labels_on_bottom: Annotated[
        Optional[bool], Field(description="False to put the names to the right of the icons.")
    ] = None,
) -> str:
    """
    Change how the desktop shows its icons, like its View › Show View Options. The options left out stay
    as they are. Finder relaunches.
    """
    options: Dict[str, Any] = {
        name: value
        for name, value in (
            ("icon_size", icon_size),
            ("grid_spacing", grid_spacing),
            ("text_size", text_size),
            ("show_item_info", show_item_info),
            ("labels_on_bottom", labels_on_bottom),
        )
        if value is not None
    }
    if sort is not None:
        options["sort"] = None if sort == "free" else sort
    if not options:
        raise ValueError("no option was given: say which one to change")
    macos.finder.set_desktop_view(**options)
    return "Changed: {}.".format(", ".join(name.replace("_", " ") for name in options))


def restart_finder() -> str:
    """Relaunch Finder, so it reads its settings again: when it shows something stale."""
    macos.finder.restart()
    return "Finder relaunched."


def register(server: MCPServer) -> None:
    # Following an alias to a network share may mount the share: it reaches beyond this Mac.
    add_tool(server, get_finder_info, title="Get what Finder knows of an item", annotations=READ_ONLY_ONLINE)
    for reader, title in (
        (get_file_thumbnail, "Get a file's preview"),
        (wait_for_folder_change, "Wait for a folder to change"),
        (find_largest_files, "Find the largest files"),
        (get_finder_settings, "Get Finder's settings"),
    ):
        add_tool(server, reader, title=title, annotations=READ_ONLY)
    # The selection is asked of Finder through AppleScript, which macOS asks the user to allow.
    add_tool(server, get_finder_selection, title="Get Finder's selection", annotations=READ_ONLY, permission=AUTOMATION)
    # These show something, or add without replacing: a tag already there, an alias made where none is.
    for adder, title in (
        (reveal_in_finder, "Reveal in Finder"),
        (quick_look, "Show in Quick Look"),
        (add_file_tags, "Add tags to a file"),
        (make_alias, "Make an alias"),
    ):
        add_tool(server, adder, title=title, annotations=ADDITIVE)
    # These set something to a value, or write a file made from scratch: doing it again gives the same.
    for setter, title in (
        (set_file_tags, "Set a file's tags"),
        (remove_file_tags, "Remove tags from a file"),
        (set_file_icon, "Set a custom icon"),
        (remove_file_icon, "Remove a custom icon"),
        (set_finder_settings, "Change Finder's settings"),
        (set_desktop_view, "Change the desktop's view"),
        (restart_finder, "Relaunch Finder"),
    ):
        add_tool(server, setter, title=title, annotations=REPLACING)
    # These take a file away, or may write over files: done again, they fail or write over again. Zipping
    # may be told to write over the .zip it zips, which a second call wraps in another ZIP.
    add_tool(server, compress_to_zip, title="Zip a file or a folder", annotations=DESTRUCTIVE)
    add_tool(server, move_to_trash, title="Move to the Trash", annotations=DESTRUCTIVE)
    add_tool(server, extract_zip, title="Unzip an archive", annotations=DESTRUCTIVE)
