"""Tools that list the printers, print files and follow the print queue, from ``macos.printer``."""

from datetime import datetime
from typing import Annotated, List, Optional

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from .._registry import ADDITIVE, DESTRUCTIVE, READ_ONLY, REPLACING, add_tool

PrinterName = Annotated[
    Optional[str],
    Field(description="The printer, by its queue name or the name System Settings shows. The default printer otherwise."),
]


class Printer(BaseModel):
    """A printer set up on this Mac."""

    name: str = Field(description="Its queue name, which the other tools take, such as 'Office_LaserJet'.")
    description: str = Field(description="The name System Settings shows, such as 'Office LaserJet'.")
    model: Optional[str] = Field(description="Its model.")
    location: Optional[str] = Field(description="Where it is, as set up.")
    is_default: bool = Field(description="Whether files go to it when no printer is named.")
    state: Optional[str] = Field(
        description="'idle', 'printing' or 'stopped'. Null when the printer doesn't say, as network printers often don't."
    )


class Printers(BaseModel):
    """The printers set up on this Mac."""

    printers: List[Printer] = Field(description="Every printer, the default one first.")
    default: Optional[str] = Field(description="The queue name of the printer files go to by default. Null when there's none.")


class PrintJob(BaseModel):
    """A file sent to a printer."""

    id: int = Field(description="The job's ID, which cancel_print_job takes.")
    printer: str = Field(description="The printer's queue name.")
    title: str = Field(description="The job's name in the queue.")
    user: str = Field(description="Who sent it.")
    state: str = Field(
        description="'pending', 'held', 'processing', 'stopped', 'canceled', 'aborted' or 'completed'."
    )
    size_kilobytes: int = Field(description="Its size, in kilobytes.")
    created: Optional[datetime] = Field(description="When it was sent.")


def _printer(printer: "macos.printer.Printer") -> Printer:
    return Printer(
        name=printer.name,
        description=printer.description,
        model=printer.model,
        location=printer.location,
        is_default=printer.is_default,
        state=printer.state,
    )


def _job(job: "macos.printer.PrintJob") -> PrintJob:
    return PrintJob(
        id=job.id,
        printer=job.printer,
        title=job.title,
        user=job.user,
        state=job.state,
        size_kilobytes=job.size,
        created=job.created,
    )


def list_printers() -> Printers:
    """List the printers set up on this Mac, with which one files go to by default and whether each is busy."""
    default = macos.printer.default()
    return Printers(
        printers=[_printer(printer) for printer in macos.printer.printers()],
        default=None if default is None else default.name,
    )


def set_default_printer(
    printer: Annotated[str, Field(description="The printer, by its queue name or the name System Settings shows.", min_length=1)],
) -> str:
    """Make a printer the one files go to when none is named, for this user."""
    macos.printer.set_default(printer)
    return "{} is the default printer.".format(printer)


def print_file(
    path: Annotated[str, Field(description="The file to print: a PDF, an image, a text file...", min_length=1)],
    printer: PrinterName = None,
    copies: Annotated[int, Field(description="How many copies.", ge=1, le=100)] = 1,
    pages: Annotated[Optional[str], Field(description="Which pages, as a range like '1-3,7'. All of them by default.")] = None,
    two_sided: Annotated[bool, Field(description="True to print on both sides of the paper.")] = False,
    black_and_white: Annotated[bool, Field(description="True to print in black and white.")] = False,
    paper: Annotated[
        Optional[str], Field(description="The paper size, such as 'A4' or 'Letter'. The printer's own by default.")
    ] = None,
    title: Annotated[Optional[str], Field(description="The job's name in the queue. The file's name by default.")] = None,
) -> PrintJob:
    """
    Print a file, and return the job once it's queued, not printed: follow it with list_print_jobs.
    It uses paper and ink: print what the user asked for, as many copies as they said.
    """
    return _job(
        macos.printer.print_file(
            path,
            printer,
            copies=copies,
            pages=pages,
            two_sided=two_sided,
            black_and_white=black_and_white,
            paper=paper,
            title=title,
        )
    )


def list_print_jobs(
    printer: Annotated[Optional[str], Field(description="Keep one printer's jobs. Every printer's by default.")] = None,
    finished: Annotated[bool, Field(description="True to include the jobs done, canceled or aborted.")] = False,
) -> List[PrintJob]:
    """List the print jobs waiting or printing, oldest first."""
    return [_job(job) for job in macos.printer.jobs(printer, finished=finished)]


def cancel_print_job(
    job_id: Annotated[int, Field(description="The job's ID, as list_print_jobs gives it.", ge=1)],
    printer: Annotated[Optional[str], Field(description="The printer the job is on.")] = None,
) -> str:
    """Take a print job out of the queue, or stop it if it's printing."""
    macos.printer.cancel(job_id, printer)
    return "Print job {} canceled.".format(job_id)


def register(server: MCPServer) -> None:
    add_tool(server, list_printers, title="List the printers", annotations=READ_ONLY)
    add_tool(server, set_default_printer, title="Set the default printer", annotations=REPLACING)
    add_tool(server, print_file, title="Print a file", annotations=ADDITIVE)
    add_tool(server, list_print_jobs, title="List the print jobs", annotations=READ_ONLY)
    add_tool(server, cancel_print_job, title="Cancel a print job", annotations=DESTRUCTIVE)
