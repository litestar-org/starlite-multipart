from dataclasses import dataclass
from typing import Dict


@dataclass
class MultipartMessageEvent:
    __slots__ = ()


@dataclass
class PreambleEvent(MultipartMessageEvent):
    __slots__ = ("data",)

    data: bytes


@dataclass
class FieldEvent(MultipartMessageEvent):
    __slots__ = (
        "name",
        "headers",
    )

    name: str
    headers: Dict[str, str]


@dataclass
class FileEvent(MultipartMessageEvent):
    __slots__ = (
        "name",
        "headers",
        "filename",
    )

    name: str
    filename: str
    headers: Dict[str, str]


@dataclass
class DataEvent(MultipartMessageEvent):
    __slots__ = (
        "data",
        "more_data",
    )

    data: bytes
    more_data: bool


@dataclass
class EpilogueEvent(MultipartMessageEvent):
    __slots__ = ("data",)
    data: bytes
