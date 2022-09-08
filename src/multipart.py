import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, cast

from starlette.datastructures import Headers

from src.header_parser import parse_options_header


class RequestEntityTooLarge(Exception):
    pass


@dataclass
class Event:
    __slots__ = ()


@dataclass
class Preamble(Event):
    __slots__ = ("data",)

    data: bytes


@dataclass
class Field(Event):
    __slots__ = (
        "name",
        "headers",
    )

    name: str
    headers: Headers


@dataclass
class File(Event):
    __slots__ = (
        "name",
        "headers",
        "filename",
    )

    name: str
    filename: str
    headers: Headers


@dataclass
class Data(Event):
    __slots__ = (
        "data",
        "more_data",
    )

    data: bytes
    more_data: bool


@dataclass
class Epilogue(Event):
    __slots__ = ("data",)
    data: bytes


class State(str, Enum):
    PREAMBLE = "PREAMBLE"
    PART = "PART"
    DATA = "DATA"
    EPILOGUE = "EPILOGUE"
    COMPLETE = "COMPLETE"


# Multipart line breaks MUST be CRLF (\r\n) by RFC-7578, except that
# many implementations break this and either use CR or LF alone.
LINE_BREAK = b"(?:\r\n|\n|\r)"
BLANK_LINE_RE = re.compile(b"(?:\r\n\r\n|\r\r|\n\n)", re.MULTILINE)
LINE_BREAK_RE = re.compile(LINE_BREAK, re.MULTILINE)
# Header values can be continued via a space or tab after the linebreak, as
# per RFC2231
HEADER_CONTINUATION_RE = re.compile(b"%s[ \t]" % LINE_BREAK, re.MULTILINE)
# This must be long enough to contain any line breaks plus any
# additional boundary markers (--) such that they will be found in a
# subsequent search
SEARCH_EXTRA_LENGTH = 8


class MultipartDecoder:
    """Decodes a multipart message as bytes into Python events.

    The part data is returned as available to allow the caller to save
    the data from memory to disk, if desired.
    """

    def __init__(
        self,
        boundary: bytes,
        max_form_memory_size: Optional[int] = None,
    ) -> None:
        self.buffer = bytearray()
        self.complete = False
        self.max_form_memory_size = max_form_memory_size
        self.state = State.PREAMBLE
        self.boundary = boundary

        # The preamble must end with a boundary where the boundary is
        # prefixed by a line break, RFC2046.
        self.preamble_re = re.compile(
            rb"%s?--%s(--[^\S\n\r]*%s?|[^\S\n\r]*%s)" % (LINE_BREAK, re.escape(boundary), LINE_BREAK, LINE_BREAK),
            re.MULTILINE,
        )
        # A boundary must include a line break prefix and suffix, and
        # may include trailing whitespace.
        self.boundary_re = re.compile(
            rb"%s--%s(--[^\S\n\r]*%s?|[^\S\n\r]*%s)" % (LINE_BREAK, re.escape(boundary), LINE_BREAK, LINE_BREAK),
            re.MULTILINE,
        )
        self._search_position = 0

    def last_newline(self) -> int:
        try:
            last_nl = self.buffer.rindex(b"\n")
        except ValueError:
            last_nl = len(self.buffer)
        try:
            last_cr = self.buffer.rindex(b"\r")
        except ValueError:
            last_cr = len(self.buffer)

        return min(last_nl, last_cr)

    def receive_data(self, data: Optional[bytes]) -> None:
        if data is None:
            self.complete = True
        elif self.max_form_memory_size is not None and len(self.buffer) + len(data) > self.max_form_memory_size:
            raise RequestEntityTooLarge()
        else:
            self.buffer.extend(data)

    def next_event(self) -> Event:
        event: Optional[Event] = None

        if self.state == State.PREAMBLE:
            match = self.preamble_re.search(self.buffer, self._search_position)
            if match is not None:
                if match.group(1).startswith(b"--"):
                    self.state = State.EPILOGUE
                else:
                    self.state = State.PART
                data = bytes(self.buffer[: match.start()])
                del self.buffer[: match.end()]
                event = Preamble(data=data)
                self._search_position = 0
            else:
                # Update the search start position to be equal to the
                # current buffer length (already searched) minus a
                # safe buffer for part of the search target.
                self._search_position = max(0, len(self.buffer) - len(self.boundary) - SEARCH_EXTRA_LENGTH)

        elif self.state == State.PART:
            match = BLANK_LINE_RE.search(self.buffer, self._search_position)
            if match is not None:
                headers = self._parse_headers(self.buffer[: match.start()])
                del self.buffer[: match.end()]

                content_disposition_header = headers.get("content-disposition")
                if not content_disposition_header:
                    raise ValueError("Missing Content-Disposition header")

                disposition, extra = parse_options_header(content_disposition_header)
                name = cast(str, extra.get("name"))
                filename = extra.get("filename")
                if filename is not None:
                    event = File(
                        filename=filename,
                        headers=headers,
                        name=name,
                    )
                else:
                    event = Field(
                        headers=headers,
                        name=name,
                    )
                self.state = State.DATA
                self._search_position = 0
            else:
                # Update the search start position to be equal to the
                # current buffer length (already searched) minus a
                # safe buffer for part of the search target.
                self._search_position = max(0, len(self.buffer) - SEARCH_EXTRA_LENGTH)

        elif self.state == State.DATA:
            if self.buffer.find(b"--" + self.boundary) == -1:
                # No complete boundary in the buffer, but there may be
                # a partial boundary at the end. As the boundary
                # starts with either a nl or cr find the earliest and
                # return up to that as data.
                data_length = del_index = self.last_newline()
                more_data = True
            else:
                match = self.boundary_re.search(self.buffer)
                if match is not None:
                    if match.group(1).startswith(b"--"):
                        self.state = State.EPILOGUE
                    else:
                        self.state = State.PART
                    data_length = match.start()
                    del_index = match.end()
                else:
                    data_length = del_index = self.last_newline()
                more_data = match is None

            data = bytes(self.buffer[:data_length])
            del self.buffer[:del_index]
            if data or not more_data:
                event = Data(data=data, more_data=more_data)

        elif self.state == State.EPILOGUE and self.complete:
            event = Epilogue(data=bytes(self.buffer))
            del self.buffer[:]
            self.state = State.COMPLETE

        if self.complete and event is None:
            raise ValueError(f"Invalid form-data cannot parse beyond {self.state}")

        return cast("Event", event)

    @staticmethod
    def _parse_headers(data: bytes) -> Headers:
        headers: Dict[str, str] = {}
        # Merge the continued headers into one line
        data = HEADER_CONTINUATION_RE.sub(b" ", data)
        # Now there is one header per line
        for name, value in [line.decode("latin-1").split(":", 1) for line in data.splitlines() if line.strip() != b""]:
            headers[name.strip()] = value.strip()
        return Headers(headers)


class MultipartEncoder:
    def __init__(self, boundary: bytes) -> None:
        self.boundary = boundary
        self.state = State.PREAMBLE

    def send_event(self, event: Event) -> bytes:
        if isinstance(event, Preamble) and self.state == State.PREAMBLE:
            self.state = State.PART
            return event.data
        elif isinstance(event, (Field, File)) and self.state in {
            State.PREAMBLE,
            State.PART,
            State.DATA,
        }:
            self.state = State.DATA
            data = b"\r\n--" + self.boundary + b"\r\n"
            data += b'Content-Disposition: form-data; name="%s"' % event.name.encode("latin-1")
            if isinstance(event, File):
                data += b'; filename="%s"' % event.filename.encode("latin-1")
            data += b"\r\n"
            for name, value in cast("Field", event).headers.items():
                if name.lower() != "content-disposition":
                    data += f"{name}: {value}\r\n".encode("latin-1")
            data += b"\r\n"
            return data
        elif isinstance(event, Data) and self.state == State.DATA:
            return event.data
        elif isinstance(event, Epilogue):
            self.state = State.COMPLETE
            return b"\r\n--" + self.boundary + b"--\r\n" + event.data
        else:
            raise ValueError(f"Cannot generate {event} in state: {self.state}")
