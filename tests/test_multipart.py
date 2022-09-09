from src.multipart import (
    Data,
    Epilogue,
    Field,
    File,
    MultipartDecoder,
    MultipartEncoder,
    Preamble,
)


def test_decoder_simple() -> None:
    boundary = b"---------------------------9704338192090380615194531385$"
    decoder = MultipartDecoder(boundary)
    data = """
-----------------------------9704338192090380615194531385$
Content-Disposition: form-data; name="fname"

ß∑œß∂ƒå∂
-----------------------------9704338192090380615194531385$
Content-Disposition: form-data; name="lname"; filename="bob"

asdasd
-----------------------------9704338192090380615194531385$--
    """.replace(
        "\n", "\r\n"
    ).encode(
        "utf-8"
    )
    decoder(data)
    decoder(None)
    events = [decoder.next_event()]
    while not isinstance(events[-1], Epilogue) and len(events) < 6:
        events.append(decoder.next_event())
    assert events == [
        Preamble(data=b""),
        Field(
            name="fname",
            headers={"Content-Disposition": 'form-data; name="fname"'},
        ),
        Data(data="ß∑œß∂ƒå∂".encode(), more_data=False),
        File(
            name="lname",
            filename="bob",
            headers={"Content-Disposition": 'form-data; name="lname"; filename="bob"'},
        ),
        Data(data=b"asdasd", more_data=False),
        Epilogue(data=b"    "),
    ]
    encoder = MultipartEncoder(boundary)
    result = b""
    for event in events:
        assert event
        result += encoder.send_event(event)
    assert data == result


def test_chunked_boundaries() -> None:
    boundary = b"--message_boundary"
    decoder = MultipartDecoder(boundary)
    decoder(b"--")
    assert decoder.next_event() is None
    decoder(b"--message_boundary\r\n")
    assert isinstance(decoder.next_event(), Preamble)
    decoder(b"Content-Disposition: form-data;")
    assert decoder.next_event() is None
    decoder(b'name="fname"\r\n\r\n')
    assert isinstance(decoder.next_event(), Field)
    decoder(b"longer than the message_boundary")
    assert isinstance(decoder.next_event(), Data)
    decoder(b"also longer, but includes a linebreak\r\n--")
    assert isinstance(decoder.next_event(), Data)
    assert decoder.next_event() is None
    decoder(b"--message_boundary--\r\n")
    event = decoder.next_event()
    assert isinstance(event, Data)
    assert not event.more_data
    decoder(None)
    assert isinstance(decoder.next_event(), Epilogue)
