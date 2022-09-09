"""The contents of this file were adapted from https://github.com/pallets/werkz
eug/blob/main/src/werkzeug/sansio/multipart.py.

Copyright 2007 Pallets

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are
met:

1.  Redistributions of source code must retain the above copyright
    notice, this list of conditions and the following disclaimer.

2.  Redistributions in binary form must reproduce the above copyright
    notice, this list of conditions and the following disclaimer in the
    documentation and/or other materials provided with the distribution.

3.  Neither the name of the copyright holder nor the names of its
    contributors may be used to endorse or promote products derived from
    this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
"AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED
TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, cast

from src.constants import BLANK_LINE_RE, LINE_BREAK, SEARCH_BUFFER_LENGTH
from src.header_parser import parse_options_header
from src.utils import get_buffer_last_newline, parse_headers


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
    headers: Dict[str, str]


@dataclass
class File(Event):
    __slots__ = (
        "name",
        "headers",
        "filename",
    )

    name: str
    filename: str
    headers: Dict[str, str]


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


class MultipartDecoder:
    def __init__(
        self,
        boundary: bytes,
        max_size: Optional[int] = None,
    ) -> None:
        """A decoder for multipart messages.

        Args:
            boundary: The message boundary as specified by [RFC7578][https://www.rfc-editor.org/rfc/rfc7578]
            max_size: Maximum number of bytes allowed for the message.
        """
        self.buffer = bytearray()
        self.max_size = max_size
        self.processing_stage = State.PREAMBLE
        self.message_boundary = boundary
        self.search_position = 0

        # The preamble must end with a message_boundary where the message_boundary is prefixed by a line break, RFC2046.
        self.preamble_re = re.compile(
            rb"%s?--%s(--[^\S\n\r]*%s?|[^\S\n\r]*%s)" % (LINE_BREAK, re.escape(boundary), LINE_BREAK, LINE_BREAK),
            re.MULTILINE,
        )
        # A message_boundary must include a line break prefix and suffix, and may include trailing whitespace.
        self.boundary_re = re.compile(
            rb"%s--%s(--[^\S\n\r]*%s?|[^\S\n\r]*%s)" % (LINE_BREAK, re.escape(boundary), LINE_BREAK, LINE_BREAK),
            re.MULTILINE,
        )

    def __call__(self, data: Optional[bytes] = None) -> None:
        if data:
            if self.max_size is not None and len(self.buffer) + len(data) > self.max_size:
                raise RequestEntityTooLarge()
            self.buffer.extend(data)

    def _process_preamble(self) -> Optional[Event]:
        match = self.preamble_re.search(self.buffer, self.search_position)
        if match is not None:
            if match.group(1).startswith(b"--"):
                self.processing_stage = State.EPILOGUE
            else:
                self.processing_stage = State.PART

            data = bytes(self.buffer[: match.start()])
            del self.buffer[: match.end()]
            return Preamble(data=data)
        return None

    def _process_part(self) -> Optional[Event]:
        match = BLANK_LINE_RE.search(self.buffer, self.search_position)
        if match is not None:
            headers = parse_headers(self.buffer[: match.start()])
            del self.buffer[: match.end()]

            content_disposition_header = headers.get("Content-Disposition") or headers.get("content-disposition")
            if not content_disposition_header:
                raise ValueError("Missing Content-Disposition header")

            _, extra = parse_options_header(content_disposition_header)
            if "filename" in extra:
                return File(
                    filename=extra["filename"],
                    headers=headers,
                    name=extra.get("name", ""),
                )
            return Field(
                headers=headers,
                name=extra.get("name", ""),
            )
        return None

    def _process_data(self) -> Optional[Event]:
        match = self.boundary_re.search(self.buffer) if self.buffer.find(b"--" + self.message_boundary) != -1 else None
        if match is not None:
            if match.group(1).startswith(b"--"):
                self.processing_stage = State.EPILOGUE
            else:
                self.processing_stage = State.PART
            data = bytes(self.buffer[: match.start()])
            more_data = False
            del self.buffer[: match.end()]
        else:
            # There is no 'is_finished' message_boundary in the buffer, but there might be
            # a partial message_boundary at the end.
            data_length = get_buffer_last_newline(self.buffer)
            data = bytes(self.buffer[:data_length])
            more_data = True
            del self.buffer[:data_length]
        return Data(data=data, more_data=more_data) if data or not more_data else None

    def next_event(self) -> Optional[Event]:
        """Processes the data according the parser's state. The state is
        updated according to the parser's state machine logic. Thus calling
        this method updates the state as well.

        Returns:
            An optional event instance, depending on the state of the message processing.
        """
        if self.processing_stage == State.COMPLETE:
            return None

        if self.processing_stage == State.PREAMBLE:
            event = self._process_preamble()
            if event:
                self.search_position = 0
            else:
                self.search_position = max(0, len(self.buffer) - len(self.message_boundary) - SEARCH_BUFFER_LENGTH)
            return event

        if self.processing_stage == State.PART:
            event = self._process_part()
            if event:
                self.search_position = 0
                self.processing_stage = State.DATA
            else:
                # Update the search start position to be equal to the
                # current buffer length (already searched) minus a
                # safe buffer for part of the search target.
                self.search_position = max(0, len(self.buffer) - SEARCH_BUFFER_LENGTH)
            return event

        if self.processing_stage == State.DATA:
            return self._process_data()

        event = Epilogue(data=bytes(self.buffer))
        del self.buffer[:]
        self.processing_stage = State.COMPLETE
        return event


class MultipartEncoder:
    def __init__(self, boundary: bytes) -> None:
        self.boundary = boundary
        self.state = State.PREAMBLE

    def send_event(self, event: Event) -> bytes:
        """Encodes an event into a byte string.

        Args:
            event: An event instance.

        Returns:
            An encoded byte string.
        """
        if isinstance(event, Preamble) and self.state == State.PREAMBLE:
            self.state = State.PART
            return event.data
        if isinstance(event, (Field, File)) and self.state in {
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
        if isinstance(event, Data) and self.state == State.DATA:
            return event.data
        if isinstance(event, Epilogue):
            self.state = State.COMPLETE
            return b"\r\n--" + self.boundary + b"--\r\n" + event.data
        raise ValueError(f"Cannot generate {event} in state: {self.state}")
