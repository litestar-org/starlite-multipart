from typing import Dict

from src.constants import RFC2231_HEADER_CONTINUATION_RE


def get_buffer_last_newline(buffer: bytearray) -> int:
    """Returns the position of the last new line break. Handles malformed new
    line formatting.

    Notes:
        - This function makes use of rindex specifically because -1 is also used. Hence, using find cannot work.
        -  Multipart line breaks MUST be CRLF (\r\n) by RFC-7578, except that many implementations break this and either
            use CR or LF alone.

    Returns:
        Last new line index.
    """
    try:
        last_nl = buffer.rindex(b"\n")
    except ValueError:
        last_nl = len(buffer)
    try:
        last_cr = buffer.rindex(b"\r")
    except ValueError:
        last_cr = len(buffer)

    return min(last_nl, last_cr)


def parse_headers(data: bytes) -> Dict[str, str]:
    """Given a message byte string, parse the headers component of it and
    return a dictionary of normalized key/value pairs.

    Args:
        data: A byte string.

    Returns:
        A string / string dictionary of parsed values.
    """
    data = RFC2231_HEADER_CONTINUATION_RE.sub(b" ", data)

    headers: Dict[str, str] = {}
    for name, value in [line.decode("latin-1").split(":", 1) for line in data.splitlines() if line.strip() != b""]:
        headers[name.strip()] = value.strip()

    return headers
