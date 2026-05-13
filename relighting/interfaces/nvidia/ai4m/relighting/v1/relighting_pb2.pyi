from google.protobuf import empty_pb2 as _empty_pb2
from nvidia.ai4m.video.v1 import video_pb2 as _video_pb2
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class BackgroundSource(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    BACKGROUND_SOURCE_UNSPECIFIED: _ClassVar[BackgroundSource]
    BACKGROUND_SOURCE_FROM_IMAGE: _ClassVar[BackgroundSource]
    BACKGROUND_SOURCE_FROM_HDR: _ClassVar[BackgroundSource]

class ImageType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    IMAGE_TYPE_UNSPECIFIED: _ClassVar[ImageType]
    IMAGE_TYPE_HDRI: _ClassVar[ImageType]
    IMAGE_TYPE_BACKGROUND: _ClassVar[ImageType]
BACKGROUND_SOURCE_UNSPECIFIED: BackgroundSource
BACKGROUND_SOURCE_FROM_IMAGE: BackgroundSource
BACKGROUND_SOURCE_FROM_HDR: BackgroundSource
IMAGE_TYPE_UNSPECIFIED: ImageType
IMAGE_TYPE_HDRI: ImageType
IMAGE_TYPE_BACKGROUND: ImageType

class RelightConfig(_message.Message):
    __slots__ = ("hdri_preset_id", "hdri_image_provided", "angle_pan_radians", "angle_v_fov_radians", "output_video_encoding", "background_source", "background_image_type", "background_color", "foreground_gain", "background_gain", "blur_strength", "specular", "autorotate", "rotation_rate")
    HDRI_PRESET_ID_FIELD_NUMBER: _ClassVar[int]
    HDRI_IMAGE_PROVIDED_FIELD_NUMBER: _ClassVar[int]
    ANGLE_PAN_RADIANS_FIELD_NUMBER: _ClassVar[int]
    ANGLE_V_FOV_RADIANS_FIELD_NUMBER: _ClassVar[int]
    OUTPUT_VIDEO_ENCODING_FIELD_NUMBER: _ClassVar[int]
    BACKGROUND_SOURCE_FIELD_NUMBER: _ClassVar[int]
    BACKGROUND_IMAGE_TYPE_FIELD_NUMBER: _ClassVar[int]
    BACKGROUND_COLOR_FIELD_NUMBER: _ClassVar[int]
    FOREGROUND_GAIN_FIELD_NUMBER: _ClassVar[int]
    BACKGROUND_GAIN_FIELD_NUMBER: _ClassVar[int]
    BLUR_STRENGTH_FIELD_NUMBER: _ClassVar[int]
    SPECULAR_FIELD_NUMBER: _ClassVar[int]
    AUTOROTATE_FIELD_NUMBER: _ClassVar[int]
    ROTATION_RATE_FIELD_NUMBER: _ClassVar[int]
    hdri_preset_id: int
    hdri_image_provided: bool
    angle_pan_radians: float
    angle_v_fov_radians: float
    output_video_encoding: _video_pb2.VideoEncoding
    background_source: BackgroundSource
    background_image_type: ImageType
    background_color: int
    foreground_gain: float
    background_gain: float
    blur_strength: float
    specular: float
    autorotate: bool
    rotation_rate: float
    def __init__(self, hdri_preset_id: _Optional[int] = ..., hdri_image_provided: bool = ..., angle_pan_radians: _Optional[float] = ..., angle_v_fov_radians: _Optional[float] = ..., output_video_encoding: _Optional[_Union[_video_pb2.VideoEncoding, _Mapping]] = ..., background_source: _Optional[_Union[BackgroundSource, str]] = ..., background_image_type: _Optional[_Union[ImageType, str]] = ..., background_color: _Optional[int] = ..., foreground_gain: _Optional[float] = ..., background_gain: _Optional[float] = ..., blur_strength: _Optional[float] = ..., specular: _Optional[float] = ..., autorotate: bool = ..., rotation_rate: _Optional[float] = ...) -> None: ...

class ImageData(_message.Message):
    __slots__ = ("image_type", "data")
    IMAGE_TYPE_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    image_type: ImageType
    data: bytes
    def __init__(self, image_type: _Optional[_Union[ImageType, str]] = ..., data: _Optional[bytes] = ...) -> None: ...

class RelightRequest(_message.Message):
    __slots__ = ("config", "video_data", "image_data")
    CONFIG_FIELD_NUMBER: _ClassVar[int]
    VIDEO_DATA_FIELD_NUMBER: _ClassVar[int]
    IMAGE_DATA_FIELD_NUMBER: _ClassVar[int]
    config: RelightConfig
    video_data: bytes
    image_data: ImageData
    def __init__(self, config: _Optional[_Union[RelightConfig, _Mapping]] = ..., video_data: _Optional[bytes] = ..., image_data: _Optional[_Union[ImageData, _Mapping]] = ...) -> None: ...

class ImageUploadAck(_message.Message):
    __slots__ = ("image_type", "size_bytes")
    IMAGE_TYPE_FIELD_NUMBER: _ClassVar[int]
    SIZE_BYTES_FIELD_NUMBER: _ClassVar[int]
    image_type: ImageType
    size_bytes: int
    def __init__(self, image_type: _Optional[_Union[ImageType, str]] = ..., size_bytes: _Optional[int] = ...) -> None: ...

class ProcessingProgress(_message.Message):
    __slots__ = ("frames_processed", "total_frames")
    FRAMES_PROCESSED_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FRAMES_FIELD_NUMBER: _ClassVar[int]
    frames_processed: int
    total_frames: int
    def __init__(self, frames_processed: _Optional[int] = ..., total_frames: _Optional[int] = ...) -> None: ...

class RelightResponse(_message.Message):
    __slots__ = ("video_data", "keep_alive", "progress", "image_upload_ack")
    VIDEO_DATA_FIELD_NUMBER: _ClassVar[int]
    KEEP_ALIVE_FIELD_NUMBER: _ClassVar[int]
    PROGRESS_FIELD_NUMBER: _ClassVar[int]
    IMAGE_UPLOAD_ACK_FIELD_NUMBER: _ClassVar[int]
    video_data: bytes
    keep_alive: _empty_pb2.Empty
    progress: ProcessingProgress
    image_upload_ack: ImageUploadAck
    def __init__(self, video_data: _Optional[bytes] = ..., keep_alive: _Optional[_Union[_empty_pb2.Empty, _Mapping]] = ..., progress: _Optional[_Union[ProcessingProgress, _Mapping]] = ..., image_upload_ack: _Optional[_Union[ImageUploadAck, _Mapping]] = ...) -> None: ...
