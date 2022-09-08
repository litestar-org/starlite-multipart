import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote_to_bytes

_option_header_start_mime_type = re.compile(r",\s*([^;,\s]+)([;,]\s*.+)?")
_option_header_piece_re = re.compile(
    r"""
    ;\s*,?\s*  # newlines were replaced with commas
    (?P<key>
        "[^"\\]*(?:\\.[^"\\]*)*"  # quoted string
    |
        [^\s;,=*]+  # token
    )
    (?:\*(?P<count>\d+))?  # *1, optional continuation index
    \s*
    (?:  # optionally followed by =value
        (?:  # equals sign, possibly with encoding
            \*\s*=\s*  # * indicates extended notation
            (?:  # optional encoding
                (?P<encoding>[^\s]+?)
                '(?P<language>[^\s]*?)'
            )?
        |
            =\s*  # basic notation
        )
        (?P<value>
            "[^"\\]*(?:\\.[^"\\]*)*"  # quoted string
        |
            [^;,]+  # token
        )?
    )?
    \s*
    """,
    flags=re.VERBOSE,
)


def unquote_header_value(value: str, is_filename: bool = False) -> str:
    r"""Unquotes a header value.  (Reversal of :func:`quote_header_value`). This
    does not use the real unquoting but what browsers are actually using for
    quoting.

    .. versionadded:: 0.5
    :param value: the header value to unquote.
    :param is_filename: The value represents a filename or path.
    """
    if value and value[0] == value[-1] == '"':
        # this is not the real unquoting, but fixing this so that the
        # RFC is met will result in bugs with internet explorer and
        # probably some other browsers as well.  IE for example is
        # uploading files with "C:\foo\bar.txt" as filename
        value = value[1:-1]

        # if this is a filename and the starting characters look like
        # a UNC path, then just return the value without quotes.  Using the
        # replace sequence below on a UNC path has the effect of turning
        # the leading double slash into a single slash and then
        # _fix_ie_filename() doesn't work correctly.  See #458.
        if not is_filename or value[:2] != "\\\\":
            return value.replace("\\\\", "\\").replace('\\"', '"')
    return value


def parse_options_header(value: Optional[str]) -> Tuple[str, Dict[str, str]]:
    """Parse a ``Content-Type``-like header into a tuple with the value and any
    options:

    >>> parse_options_header('text/html; charset=utf8')
    ('text/html', {'charset': 'utf8'})
    This should is not for ``Cache-Control``-like headers, which use a
    different format. For those, use :func:`parse_dict_header`.
    :param value: The header value to parse.
    .. versionchanged:: 2.2
        Option names are always converted to lowercase.
    .. versionchanged:: 2.1
        The ``multiple`` parameter is deprecated and will be removed in
        Werkzeug 2.2.
    .. versionchanged:: 0.15
        :rfc:`2231` parameter continuations are handled.
    .. versionadded:: 0.5
    """
    if not value:
        return "", {}

    result: List[Any] = []

    value = "," + value.replace("\n", ",")
    while value:
        match = _option_header_start_mime_type.match(value)
        if not match:
            break
        result.append(match.group(1))  # mimetype
        options: Dict[str, str] = {}
        # Parse options
        rest = match.group(2)
        encoding: Optional[str]
        continued_encoding: Optional[str] = None
        while rest:
            optmatch = _option_header_piece_re.match(rest)
            if not optmatch:
                break
            option, count, encoding, language, option_value = optmatch.groups()
            # Continuations don't have to supply the encoding after the
            # first line. If we're in a continuation, track the current
            # encoding to use for subsequent lines. Reset it when the
            # continuation ends.
            if not count:
                continued_encoding = None
            else:
                if not encoding:
                    encoding = continued_encoding
                continued_encoding = encoding
            option = unquote_header_value(option).lower()

            if option_value is not None:
                option_value = unquote_header_value(option_value, option == "filename")

                if encoding is not None:
                    option_value = unquote_to_bytes(option_value).decode(encoding)

            if count:
                # Continuations append to the existing value. For
                # simplicity, this ignores the possibility of
                # out-of-order indices, which shouldn't happen anyway.
                if option_value is not None:
                    options[option] = options.get(option, "") + option_value
            else:
                options[option] = option_value  # type: ignore[assignment]

            rest = rest[optmatch.end() :]
        result.append(options)
        return tuple(result)  # type: ignore[return-value]

    return tuple(result) if result else ("", {})  # type: ignore[return-value]
