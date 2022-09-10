"""The contents of this file incorporate code adapted from
https://github.com/pallets/werkzeug.

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

from typing import cast

from starlite_multipart.constants import ProcessingStage
from starlite_multipart.events import (
    DataEvent,
    EpilogueEvent,
    FieldEvent,
    FileEvent,
    MultipartMessageEvent,
    PreambleEvent,
)


class MultipartEncoder:
    __slots__ = ("message_boundary", "processing_stage")

    def __init__(self, message_boundary: bytes) -> None:
        """Decodes a multipart event into a byte string.

        Args:
            message_boundary: The message message_boundary.
        """
        self.message_boundary = message_boundary
        self.processing_stage = ProcessingStage.PREAMBLE

    def send_event(self, event: MultipartMessageEvent) -> bytes:
        """Encodes an event into a byte string.

        Args:
            event: An event instance.

        Returns:
            An encoded byte string.
        """
        if isinstance(event, PreambleEvent) and self.processing_stage == ProcessingStage.PREAMBLE:
            self.processing_stage = ProcessingStage.PART
            return event.data
        if isinstance(event, (FieldEvent, FileEvent)) and self.processing_stage in {
            ProcessingStage.PREAMBLE,
            ProcessingStage.PART,
            ProcessingStage.DATA,
        }:
            self.processing_stage = ProcessingStage.DATA
            data = b"\r\n--" + self.message_boundary + b"\r\n"
            data += b'Content-Disposition: form-data; name="%s"' % event.name.encode("latin-1")
            if isinstance(event, FileEvent):
                data += b'; filename="%s"' % event.filename.encode("latin-1")
            data += b"\r\n"
            for name, value in cast("FieldEvent", event).headers.items():
                if name.lower() != "content-disposition":
                    data += f"{name}: {value}\r\n".encode("latin-1")
            data += b"\r\n"
            return data
        if isinstance(event, DataEvent) and self.processing_stage == ProcessingStage.DATA:
            return event.data
        if isinstance(event, EpilogueEvent):
            self.processing_stage = ProcessingStage.COMPLETE
            return b"\r\n--" + self.message_boundary + b"--\r\n" + event.data
        raise ValueError(f"Cannot generate {event} in processing_stage: {self.processing_stage}")
