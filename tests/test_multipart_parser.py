"""Tests in this file have been adapted from Starlette."""

import os
from os.path import abspath, dirname, join
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Mapping, Tuple, Union

import pytest
from starlette.datastructures import ImmutableMultiDict
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from starlite_multipart import MultipartFormDataParser
from starlite_multipart.datastructures import UploadFile

if TYPE_CHECKING:
    from starlette.types import Receive, Scope, Send


class FormData(ImmutableMultiDict[str, Union[UploadFile, str]]):
    """An immutable multidict, containing both file uploads and text input."""

    def __init__(
        self,
        *args: Union[
            "FormData",
            Mapping[str, Union[str, UploadFile]],
            List[Tuple[str, Union[str, UploadFile]]],
        ],
        **kwargs: Union[str, UploadFile],
    ) -> None:
        super().__init__(*args, **kwargs)

    async def close(self) -> None:
        for _, value in self.multi_items():
            if isinstance(value, UploadFile):
                await value.close()


class Request(StarletteRequest):
    async def form(self) -> FormData:  # type: ignore
        parser = MultipartFormDataParser(headers=self.headers, stream=self.stream(), max_file_size=None)
        return FormData(await parser())


class ForceMultipartDict(dict):  # type: ignore
    def __bool__(self) -> bool:
        return True


@pytest.fixture()
def test_client_factory() -> Callable[[Any], TestClient]:
    return lambda x: TestClient(app=x)


FORCE_MULTIPART = ForceMultipartDict()


async def standard_app(scope: "Scope", receive: "Receive", send: "Send") -> None:
    request = Request(scope, receive)
    data = await request.form()
    output = {}
    for key, value in data.items():
        if isinstance(value, UploadFile):
            content = await value.read()
            output[key] = {
                "filename": value.filename,
                "content": content.decode(),
                "content_type": value.content_type,
            }
        else:
            output[key] = value  # type: ignore
    await request.close()
    response = JSONResponse(output)
    await response(scope, receive, send)


async def multi_items_app(scope: "Scope", receive: "Receive", send: "Send") -> None:
    request = Request(scope, receive)
    data = await request.form()
    output: Dict[str, list] = {}  # type: ignore
    for key, value in data.multi_items():
        if key not in output:
            output[key] = []
        if isinstance(value, UploadFile):
            content = await value.read()
            output[key].append(
                {
                    "filename": value.filename,
                    "content": content.decode(),
                    "content_type": value.content_type,
                }
            )
        else:
            output[key].append(value)
    await request.close()
    response = JSONResponse(output)
    await response(scope, receive, send)


async def app_with_headers(scope: "Scope", receive: "Receive", send: "Send") -> None:
    request = Request(scope, receive)
    data = await request.form()
    output = {}
    for key, value in data.items():
        if isinstance(value, UploadFile):
            content = await value.read()
            output[key] = {
                "filename": value.filename,
                "content": content.decode(),
                "content_type": value.content_type,
                "headers": list(value.headers.items()),
            }
        else:
            output[key] = value  # type: ignore
    await request.close()
    response = JSONResponse(output)
    await response(scope, receive, send)


async def app_read_body(scope: "Scope", receive: "Receive", send: "Send") -> None:
    request = Request(scope, receive)
    await request.body()
    data = await request.form()
    output = {}
    for key, value in data.items():
        output[key] = value
    await request.close()
    response = JSONResponse(output)
    await response(scope, receive, send)


def test_multipart_request_data(test_client_factory: Callable[[Any], TestClient]) -> None:
    client = test_client_factory(standard_app)
    response = client.post("/", data={"some": "data"}, files=FORCE_MULTIPART)
    assert response.json() == {"some": "data"}


def test_multipart_request_files(tmpdir: Any, test_client_factory: Callable[[Any], TestClient]) -> None:
    path = os.path.join(tmpdir, "test.txt")
    with open(path, "wb") as file:
        file.write(b"<file content>")

    client = test_client_factory(standard_app)
    with open(path, "rb") as f:
        response = client.post("/", files={"test": f})
        assert response.json() == {
            "test": {
                "filename": "test.txt",
                "content": "<file content>",
                "content_type": "text/plain",
            }
        }


def test_multipart_request_files_with_content_type(
    tmpdir: Any, test_client_factory: Callable[[Any], TestClient]
) -> None:
    path = os.path.join(tmpdir, "test.txt")
    with open(path, "wb") as file:
        file.write(b"<file content>")

    client = test_client_factory(standard_app)
    with open(path, "rb") as f:
        response = client.post("/", files={"test": ("test.txt", f, "text/plain")})
        assert response.json() == {
            "test": {
                "filename": "test.txt",
                "content": "<file content>",
                "content_type": "text/plain",
            }
        }


def test_multipart_request_multiple_files(tmpdir: Any, test_client_factory: Callable[[Any], TestClient]) -> None:
    path1 = os.path.join(tmpdir, "test1.txt")
    with open(path1, "wb") as file:
        file.write(b"<file1 content>")

    path2 = os.path.join(tmpdir, "test2.txt")
    with open(path2, "wb") as file:
        file.write(b"<file2 content>")

    client = test_client_factory(standard_app)
    with open(path1, "rb") as f1, open(path2, "rb") as f2:
        response = client.post("/", files={"test1": f1, "test2": ("test2.txt", f2, "text/plain")})
        assert response.json() == {
            "test1": {
                "filename": "test1.txt",
                "content": "<file1 content>",
                "content_type": "text/plain",
            },
            "test2": {
                "filename": "test2.txt",
                "content": "<file2 content>",
                "content_type": "text/plain",
            },
        }


def test_multipart_request_multiple_files_with_headers(
    tmpdir: Any, test_client_factory: Callable[[Any], TestClient]
) -> None:
    path1 = os.path.join(tmpdir, "test1.txt")
    with open(path1, "wb") as file:
        file.write(b"<file1 content>")

    path2 = os.path.join(tmpdir, "test2.txt")
    with open(path2, "wb") as file:
        file.write(b"<file2 content>")

    client = test_client_factory(app_with_headers)
    with open(path1, "rb") as f1, open(path2, "rb") as f2:
        response = client.post(
            "/",
            files=[
                ("test1", (None, f1)),
                ("test2", ("test2.txt", f2, "text/plain", {"x-custom": "f2"})),
            ],
        )
        assert response.json() == {
            "test1": "<file1 content>",
            "test2": {
                "filename": "test2.txt",
                "content": "<file2 content>",
                "content_type": "text/plain",
                "headers": [
                    ["Content-Disposition", 'form-data; name="test2"; filename="test2.txt"'],
                    ["x-custom", "f2"],
                    ["Content-Type", "text/plain"],
                ],
            },
        }


def test_multi_items(tmpdir: Any, test_client_factory: Callable[[Any], TestClient]) -> None:
    path1 = os.path.join(tmpdir, "test1.txt")
    with open(path1, "wb") as file:
        file.write(b"<file1 content>")

    path2 = os.path.join(tmpdir, "test2.txt")
    with open(path2, "wb") as file:
        file.write(b"<file2 content>")

    client = test_client_factory(multi_items_app)
    with open(path1, "rb") as f1, open(path2, "rb") as f2:
        response = client.post(
            "/",
            data={"test1": "abc"},
            files=[("test1", f1), ("test1", ("test2.txt", f2, "text/plain"))],
        )
        assert response.json() == {
            "test1": [
                "abc",
                {
                    "filename": "test1.txt",
                    "content": "<file1 content>",
                    "content_type": "text/plain",
                },
                {
                    "filename": "test2.txt",
                    "content": "<file2 content>",
                    "content_type": "text/plain",
                },
            ]
        }


def test_multipart_request_mixed_files_and_data(test_client_factory: Callable[[Any], TestClient]) -> None:
    client = test_client_factory(standard_app)
    response = client.post(
        "/",
        data=(
            # data
            b"--a7f7ac8d4e2e437c877bb7b8d7cc549c\r\n"
            b'Content-Disposition: form-data; name="field0"\r\n\r\n'
            b"value0\r\n"
            # file
            b"--a7f7ac8d4e2e437c877bb7b8d7cc549c\r\n"
            b'Content-Disposition: form-data; name="file"; filename="file.txt"\r\n'
            b"Content-Type: text/plain\r\n\r\n"
            b"<file content>\r\n"
            # data
            b"--a7f7ac8d4e2e437c877bb7b8d7cc549c\r\n"
            b'Content-Disposition: form-data; name="field1"\r\n\r\n'
            b"value1\r\n"
            b"--a7f7ac8d4e2e437c877bb7b8d7cc549c--\r\n"
        ),
        headers={"Content-Type": ("multipart/form-data; boundary=a7f7ac8d4e2e437c877bb7b8d7cc549c")},
    )
    assert response.json() == {
        "file": {
            "filename": "file.txt",
            "content": "<file content>",
            "content_type": "text/plain",
        },
        "field0": "value0",
        "field1": "value1",
    }


def test_multipart_request_with_charset_for_filename(test_client_factory: Callable[[Any], TestClient]) -> None:
    client = test_client_factory(standard_app)
    response = client.post(
        "/",
        data=(
            # file
            b"--a7f7ac8d4e2e437c877bb7b8d7cc549c\r\n"
            b'Content-Disposition: form-data; name="file"; filename="\xe6\x96\x87\xe6\x9b\xb8.txt"\r\n'
            b"Content-Type: text/plain\r\n\r\n"
            b"<file content>\r\n"
            b"--a7f7ac8d4e2e437c877bb7b8d7cc549c--\r\n"
        ),
        headers={"Content-Type": ("multipart/form-data; charset=utf-8; boundary=a7f7ac8d4e2e437c877bb7b8d7cc549c")},
    )
    assert response.json() == {
        "file": {
            "filename": "文書.txt",
            "content": "<file content>",
            "content_type": "text/plain",
        }
    }


def test_multipart_request_without_charset_for_filename(test_client_factory: Callable[[Any], TestClient]) -> None:
    client = test_client_factory(standard_app)
    response = client.post(
        "/",
        data=(
            # file
            b"--a7f7ac8d4e2e437c877bb7b8d7cc549c\r\n"
            b'Content-Disposition: form-data; name="file"; filename="\xe7\x94\xbb\xe5\x83\x8f.jpg"\r\n'
            b"Content-Type: image/jpeg\r\n\r\n"
            b"<file content>\r\n"
            b"--a7f7ac8d4e2e437c877bb7b8d7cc549c--\r\n"
        ),
        headers={"Content-Type": ("multipart/form-data; boundary=a7f7ac8d4e2e437c877bb7b8d7cc549c")},
    )
    assert response.json() == {
        "file": {
            "filename": "画像.jpg",
            "content": "<file content>",
            "content_type": "image/jpeg",
        }
    }


def test_multipart_request_with_encoded_value(test_client_factory: Callable[[Any], TestClient]) -> None:
    client = test_client_factory(standard_app)
    response = client.post(
        "/",
        data=(
            b"--20b303e711c4ab8c443184ac833ab00f\r\n"
            b"Content-Disposition: form-data; "
            b'name="value"\r\n\r\n'
            b"Transf\xc3\xa9rer\r\n"
            b"--20b303e711c4ab8c443184ac833ab00f--\r\n"
        ),
        headers={"Content-Type": ("multipart/form-data; charset=utf-8; boundary=20b303e711c4ab8c443184ac833ab00f")},
    )
    assert response.json() == {"value": "Transférer"}


def test_no_request_data(test_client_factory: Callable[[Any], TestClient]) -> None:
    client = test_client_factory(standard_app)
    response = client.post("/")
    assert response.json() == {}


def test_multipart_multi_field_app_reads_body(test_client_factory: Callable[[Any], TestClient]) -> None:
    client = test_client_factory(app_read_body)
    response = client.post("/", data={"some": "data", "second": "key pair"}, files=FORCE_MULTIPART)
    assert response.json() == {"some": "data", "second": "key pair"}


def test_postman_multipart_form_data(test_client_factory: Callable[[Any], TestClient]) -> None:
    postman_body = b'----------------------------850116600781883365617864\r\nContent-Disposition: form-data; name="attributes"; filename="test-attribute_5.tsv"\r\nContent-Type: text/tab-separated-values\r\n\r\n"Campaign ID"\t"Plate Set ID"\t"No"\n\r\n----------------------------850116600781883365617864\r\nContent-Disposition: form-data; name="fasta"; filename="test-sequence_correct_5.fasta"\r\nContent-Type: application/octet-stream\r\n\r\n>P23G01_IgG1-1411:H:Q10C3:1/1:NID18\r\nCAGGTATTGAA\r\n\r\n----------------------------850116600781883365617864--\r\n'  # noqa: E501
    postman_headers = {
        "content-type": "multipart/form-data; boundary=--------------------------850116600781883365617864",  # noqa: E501
        "user-agent": "PostmanRuntime/7.26.0",
        "accept": "*/*",
        "cache-control": "no-cache",
        "host": "10.0.5.13:80",
        "accept-encoding": "gzip, deflate, br",
        "connection": "keep-alive",
        "content-length": "2455",
    }

    client = test_client_factory(standard_app)
    response = client.post("/", data=postman_body, headers=postman_headers)
    assert response.json() == {
        "attributes": {
            "filename": "test-attribute_5.tsv",
            "content": '"Campaign ID"\t"Plate Set ID"\t"No"\n',
            "content_type": "text/tab-separated-values",
        },
        "fasta": {
            "filename": "test-sequence_correct_5.fasta",
            "content": ">P23G01_IgG1-1411:H:Q10C3:1/1:NID18\r\nCAGGTATTGAA\r\n",
            "content_type": "application/octet-stream",
        },
    }


def test_image_upload(test_client_factory: Callable[[Any], TestClient]) -> None:
    async def test_app(scope: "Scope", receive: "Receive", send: "Send") -> None:
        request = Request(scope, receive)
        data = await request.form()
        output: Dict[str, list] = {}  # type: ignore
        for key, value in data.multi_items():
            if key not in output:
                output[key] = []
            if isinstance(value, UploadFile):
                content = await value.read()
                output[key].append(
                    {
                        "filename": value.filename,
                        "content": content.decode("latin-1"),
                        "content_type": value.content_type,
                    }
                )
            else:
                output[key].append(value)
        await request.close()
        response = JSONResponse(output)
        await response(scope, receive, send)

    client = test_client_factory(test_app)

    with open(join(dirname(abspath(__file__)), "flower.jpeg"), "rb") as f:
        data = f.read()
        client.post("http://localhost:8000/", files={"flower": data})
