from typing import AsyncGenerator, List, Mapping, Optional, Tuple, Union

from starlite_multipart.datastructures import UploadFile
from starlite_multipart.decoder import MultipartDecoder
from starlite_multipart.events import DataEvent, EpilogueEvent, FieldEvent, FileEvent
from starlite_multipart.utils import parse_options_header


class MultipartFormDataParser:
    __slots__ = ("headers", "stream", "decoder", "charset")

    def __init__(
        self,
        headers: Mapping[str, str],
        stream: AsyncGenerator[bytes, None],
        max_file_size: Optional[int],
        charset: str = "utf-8",
    ) -> None:
        """Parses multipart/formdata.

        Args:
            headers: A mapping of headers.
            stream: An async generator yielding a stream.
            max_file_size: Max file size allowed.
            charset: Charset used to encode the data.
        """
        _, options = parse_options_header(headers["Content-Type"])
        self.headers = headers
        self.stream = stream
        self.decoder = MultipartDecoder(message_boundary=options["boundary"], max_file_size=max_file_size)
        self.charset = options.get("charset", charset)

    async def _parse_chunk(self) -> List[Tuple[str, Union[str, UploadFile]]]:
        """Parses a chunk into a list of items.

        Returns:
            A list of tuples, each containing the field name and its value - either a string or an upload file datum.
        """
        items: List[Tuple[str, Union[str, UploadFile]]] = []

        field_name = ""
        data = bytearray()
        upload_file: Optional[UploadFile] = None
        while True:
            event = self.decoder.next_event()
            if not event or isinstance(event, EpilogueEvent):
                break
            if isinstance(event, FieldEvent):
                field_name = event.name
                continue
            if isinstance(event, FileEvent):
                field_name = event.name
                upload_file = UploadFile(
                    filename=event.filename,
                    content_type=event.headers.get("Content-Type", "") or event.headers.get("content-type", ""),
                    headers=event.headers,
                )
                continue
            if isinstance(event, DataEvent):
                if upload_file is None:
                    data.extend(event.data)
                    if not event.more_data:
                        items.append((field_name, data.decode(self.charset)))
                        data.clear()
                else:
                    await upload_file.write(event.data)
                    if not event.more_data:
                        await upload_file.seek(0)
                        items.append((field_name, upload_file))
                        upload_file = None
        return items

    async def __call__(self) -> List[Tuple[str, Union[str, UploadFile]]]:
        """Asynchronously parses the stream data.

        Returns:
            A list of tuples, each containing the field name and its value - either a string or an upload file datum.
        """
        parse_result: List[Tuple[str, Union[str, UploadFile]]] = []
        async for chunk in self.stream:
            self.decoder(chunk)
            parse_result.extend(await self._parse_chunk())
        return parse_result
