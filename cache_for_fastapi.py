import datetime
import json
import pickle
from decimal import Decimal
from typing import Any, Callable, ClassVar, Dict, Optional, TypeVar, Union, overload, List
from venv import logger
import pendulum
from fastapi.encoders import jsonable_encoder
from starlette.responses import JSONResponse
from starlette.templating import (
    _TemplateResponse as TemplateResponse,
)

from core.config import redis, EXPIRED_CACHE



class ModelField:
    pass


_T = TypeVar("_T", bound=type)

CONVERTERS: Dict[str, Callable[[str], Any]] = {"date": lambda x: pendulum.parse(x, exact=True),
                                               "datetime": lambda x: pendulum.parse(x, exact=True),
                                               "decimal": Decimal}


class JsonEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, datetime.datetime):
            return {"val": str(o), "_spec_type": "datetime"}
        elif isinstance(o, datetime.date):
            return {"val": str(o), "_spec_type": "date"}
        elif isinstance(o, Decimal):
            return {"val": str(o), "_spec_type": "decimal"}
        else:
            return jsonable_encoder(o)


def object_hook(obj: Any) -> Any:
    _spec_type = obj.get("_spec_type")
    if not _spec_type:
        return obj

    if _spec_type in CONVERTERS:
        return CONVERTERS[_spec_type](obj["val"])
    else:
        raise TypeError(f"Unknown {_spec_type}")


class Coder:
    @classmethod
    def encode(cls, value: Any) -> bytes:
        raise NotImplementedError

    @classmethod
    def decode(cls, value: bytes) -> Any:
        raise NotImplementedError

    _type_field_cache: ClassVar[Dict[Any, ModelField]] = {}

    @overload
    @classmethod
    def decode_as_type(cls, value: bytes, *, type_: _T) -> _T:
        ...

    @overload
    @classmethod
    def decode_as_type(cls, value: bytes, *, type_: None) -> Any:
        ...

    @classmethod
    def decode_as_type(cls, value: bytes, *, type_: Optional[_T]) -> Union[_T, Any]:
        result = cls.decode(value)
        return result


class JsonCoder(Coder):
    @classmethod
    def encode(cls, value: Any) -> bytes:
        if isinstance(value, JSONResponse):
            return value.body
        return json.dumps(value, cls=JsonEncoder).encode()

    @classmethod
    def decode(cls, value: bytes) -> Any:
        return json.loads(value.decode(), object_hook=object_hook)


class PickleCoder(Coder):
    @classmethod
    def encode(cls, value: Any) -> bytes:
        if isinstance(value, TemplateResponse):
            value = value.body
        return pickle.dumps(value)

    @classmethod
    def decode(cls, value: bytes) -> Any:
        return pickle.loads(value)  # noqa: S301

    @classmethod
    def decode_as_type(cls, value: bytes, *, type_: Optional[_T]) -> Any:
        return cls.decode(value)


json_coder = JsonCoder()
pickle_coder = PickleCoder()


class CacheCalendar:

    def __init__(self, prefix: str = '', postfix: str = ''):
        """При каждом вызове manual_cache передавать room_name и username"""
        self.prefix = prefix
        self.postfix = postfix

    async def cached_router(self, cached_value: List | Dict = None) -> bool:
        if check_room(self.prefix):
            encode_cache = pickle_coder.encode(value=cached_value)
            await redis.setex(f'{self.prefix}_{self.postfix}', EXPIRED_CACHE, encode_cache)
            return True
        encode_cache = pickle_coder.encode(value=cached_value)
        await redis.setex(f'{self.prefix}_{self.postfix}', EXPIRED_CACHE, encode_cache)
        return True

    async def get_cached_router(self) -> bool:
        if check_room(self.prefix):
            if cache := await redis.get(f'{self.prefix}_{self.postfix}'):
                decode_cache = pickle_coder.decode(value=cache)
                return decode_cache
            return False
        if cache := await redis.get(f'{self.prefix}_{self.postfix}'):
            decode_cache = pickle_coder.decode(value=cache)
            return decode_cache
        return False

    async def delete_cache(self) -> None:
        try:
            pattern = (f'*{self.prefix}_{self.postfix}*' if self.prefix else f'*{self.postfix}*')
            async for key in redis.scan_iter(pattern):
                await redis.delete(key)
        except Exception as error:
            logger.error(error)

    @classmethod
    async def delete_all_cache_calendar(cls) -> None:
        list_postfix = ('all_events', 'free_rooms', 'all_calendar', 'get_time_block')
        for postfix in list_postfix:
            await CacheCalendar(postfix=postfix).delete_cache()
