from google.protobuf import any_pb2 as _any_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class VideoCodec(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    VIDEO_CODEC_UNSPECIFIED: _ClassVar[VideoCodec]
    VIDEO_CODEC_H264: _ClassVar[VideoCodec]
VIDEO_CODEC_UNSPECIFIED: VideoCodec
VIDEO_CODEC_H264: VideoCodec

class LossyEncoding(_message.Message):
    __slots__ = ("bitrate_mbps", "idr_interval")
    BITRATE_MBPS_FIELD_NUMBER: _ClassVar[int]
    IDR_INTERVAL_FIELD_NUMBER: _ClassVar[int]
    bitrate_mbps: int
    idr_interval: int
    def __init__(self, bitrate_mbps: _Optional[int] = ..., idr_interval: _Optional[int] = ...) -> None: ...

class CustomEncodingParams(_message.Message):
    __slots__ = ("custom",)
    class CustomEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: _any_pb2.Any
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[_any_pb2.Any, _Mapping]] = ...) -> None: ...
    CUSTOM_FIELD_NUMBER: _ClassVar[int]
    custom: _containers.MessageMap[str, _any_pb2.Any]
    def __init__(self, custom: _Optional[_Mapping[str, _any_pb2.Any]] = ...) -> None: ...

class VideoEncoding(_message.Message):
    __slots__ = ("lossless", "lossy", "custom_encoding")
    LOSSLESS_FIELD_NUMBER: _ClassVar[int]
    LOSSY_FIELD_NUMBER: _ClassVar[int]
    CUSTOM_ENCODING_FIELD_NUMBER: _ClassVar[int]
    lossless: bool
    lossy: LossyEncoding
    custom_encoding: CustomEncodingParams
    def __init__(self, lossless: bool = ..., lossy: _Optional[_Union[LossyEncoding, _Mapping]] = ..., custom_encoding: _Optional[_Union[CustomEncodingParams, _Mapping]] = ...) -> None: ...
