from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote_to_bytes

from src.constants import OPTION_HEADER_PIECE_RE, OPTION_HEADER_START_MIME_RE


def unquote_header_value(value: str, is_filename: bool = False) -> str:
    """Unquotes a header value. This does not use the real unquoting but what
    browsers are actually using for quoting.

    Args:
        value: Value to unquoted.
        is_filename: Boolean flag dictating whether the value is a filename.

    Returns:
        The unquoted value.
    """
    if value and value[0] == value[-1] == '"':
        value = value[1:-1]
        if not is_filename or value[:2] != "\\\\":
            return value.replace("\\\\", "\\").replace('\\"', '"')
    return value


def parse_options_header(value: Optional[str]) -> Tuple[str, Dict[str, str]]:
    """Parses a 'Content-Disposition' header, returning the header value and
    any options as a dictionary.

    Args:
        value: An optional header string.

    Returns:
        A tuple with the parsed value and a dictionary containing any options send in it.
    """
    if not value:
        return "", {}

    result: List[str] = []

    value = "," + value.replace("\n", ",")
    while value:
        match = OPTION_HEADER_START_MIME_RE.match(value)
        if not match:
            break

        result.append(match.group(1))  # mimetype

        options: Dict[str, str] = {}
        rest = match.group(2)
        encoding: Optional[str]
        continued_encoding: Optional[str] = None
        while rest:
            optmatch = OPTION_HEADER_PIECE_RE.match(rest)
            if not optmatch:
                break

            option, count, encoding, _, option_value = optmatch.groups()
            if count and encoding:
                continued_encoding = encoding
            elif count:
                encoding = continued_encoding
            else:
                continued_encoding = None

            option = unquote_header_value(option).lower()

            if option_value is not None:
                option_value = unquote_header_value(option_value, option == "filename")

                if encoding is not None:
                    option_value = unquote_to_bytes(option_value).decode(encoding)

            if not count:
                options[option] = option_value or ""
            elif option_value is not None:
                options[option] = options.get(option, "") + option_value

            rest = rest[optmatch.end() :]
        return result[0], options

    return result[0] if result else "", {}
