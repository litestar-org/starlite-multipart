import re
from typing import Optional

from starlite_multipart.constants import (
    BLANK_LINE_RE,
    LINE_BREAK,
    SEARCH_BUFFER_LENGTH,
    State,
)
from starlite_multipart.events import (
    DataEvent,
    EpilogueEvent,
    FieldEvent,
    FileEvent,
    MultipartMessageEvent,
    PreambleEvent,
)
from starlite_multipart.utils import (
    get_buffer_last_newline,
    parse_headers,
    parse_options_header,
)


class RequestEntityTooLarge(Exception):
    pass


class MultipartDecoder:
    __slots__ = (
        "buffer",
        "max_size",
        "processing_stage",
        "message_boundary",
        "search_position",
        "preamble_re",
        "boundary_re",
    )

    def __init__(
        self,
        boundary: bytes,
        max_size: Optional[int] = None,
    ) -> None:
        """A decoder for multipart messages.

        Args:
            boundary: The message message_boundary as specified by [RFC7578][https://www.rfc-editor.org/rfc/rfc7578]
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

    def _process_preamble(self) -> Optional[MultipartMessageEvent]:
        match = self.preamble_re.search(self.buffer, self.search_position)
        if match is not None:
            if match.group(1).startswith(b"--"):
                self.processing_stage = State.EPILOGUE
            else:
                self.processing_stage = State.PART

            data = bytes(self.buffer[: match.start()])
            del self.buffer[: match.end()]
            return PreambleEvent(data=data)
        return None

    def _process_part(self) -> Optional[MultipartMessageEvent]:
        match = BLANK_LINE_RE.search(self.buffer, self.search_position)
        if match is not None:
            headers = parse_headers(self.buffer[: match.start()])
            del self.buffer[: match.end()]

            content_disposition_header = headers.get("Content-Disposition") or headers.get("content-disposition")
            if not content_disposition_header:
                raise ValueError("Missing Content-Disposition header")

            _, extra = parse_options_header(content_disposition_header)
            if "filename" in extra:
                return FileEvent(
                    filename=extra["filename"],
                    headers=headers,
                    name=extra.get("name", ""),
                )
            return FieldEvent(
                headers=headers,
                name=extra.get("name", ""),
            )
        return None

    def _process_data(self) -> Optional[MultipartMessageEvent]:
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
            data_length = get_buffer_last_newline(self.buffer)
            data = bytes(self.buffer[:data_length])
            more_data = True
            del self.buffer[:data_length]
        return DataEvent(data=data, more_data=more_data) if data or not more_data else None

    def next_event(self) -> Optional[MultipartMessageEvent]:
        """Processes the data according the parser's processing_stage. The
        processing_stage is updated according to the parser's processing_stage
        machine logic. Thus calling this method updates the processing_stage as
        well.

        Returns:
            An optional event instance, depending on the processing_stage of the message processing.
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
                self.search_position = max(0, len(self.buffer) - SEARCH_BUFFER_LENGTH)
            return event

        if self.processing_stage == State.DATA:
            return self._process_data()

        event = EpilogueEvent(data=bytes(self.buffer))
        del self.buffer[:]
        self.processing_stage = State.COMPLETE
        return event
