"""The contents of this file incorporate code adapted from
https://github.com/encode/starlette.

Copyright © 2018, [Encode OSS Ltd](https://www.encode.io/).
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.

* Neither the name of the copyright holder nor the names of its
  contributors may be used to endorse or promote products derived from
  this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

from tempfile import SpooledTemporaryFile
from typing import BinaryIO, Dict, Optional

from anyio.to_thread import run_sync


class UploadFile:
    __slots__ = ("filename", "file", "content_type", "headers", "is_in_memory")

    def __init__(
        self,
        filename: str,
        content_type: str,
        headers: Optional[Dict[str, str]] = None,
        spool_max_size: int = 1024 * 1024,
        file: Optional[BinaryIO] = None,
    ) -> None:
        """Upload file container.

        Args:
            filename: The filename.
            content_type: Content type for the file.
            headers: Any attached headers.
            spool_max_size: Max value to allocate for temporary files.
            file: Optional file data.
        """
        self.filename = filename
        self.content_type = content_type
        self.file = file or SpooledTemporaryFile(max_size=spool_max_size)  # pylint: disable=consider-using-with
        self.headers = headers or {}
        self.is_in_memory = not getattr(self.file, "_rolled", True)

    async def write(self, data: bytes) -> None:
        """Async proxy for data writing.

        Args:
            data: Byte string to write.

        Returns:
            None
        """
        if self.is_in_memory:
            self.file.write(data)
        else:
            await run_sync(self.file.write, data)

    async def read(self, size: int = -1) -> bytes:
        """Async proxy for data reading.

        Args:
            size: position from which to read.

        Returns:
            Byte string.
        """
        if self.is_in_memory:
            return self.file.read(size)
        return await run_sync(self.file.read, size)

    async def seek(self, offset: int) -> None:
        """Async proxy for file seek.

        Args:
            offset: start position..

        Returns:
            None.
        """
        if self.is_in_memory:
            self.file.seek(offset)
        else:
            await run_sync(self.file.seek, offset)

    async def close(self) -> None:
        """Async proxy for file close.

        Returns:
            None.
        """
        if self.is_in_memory:
            self.file.close()
        else:
            await run_sync(self.file.close)
