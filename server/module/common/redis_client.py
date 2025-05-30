import json
from datetime import timedelta

from redis import asyncio

from server.config.settings import CACHE_HEADER, REDIS_URL
from server.module.common.pydantics import UserOperation


class RedisCache:
    client = None

    def __init__(self) -> None:
        self.client = None

    async def get_redis(self):
        if self.client:
            pong = await self.client.ping()
            if pong:
                return self.client
        self.client = await asyncio.from_url(REDIS_URL, decode_responses=True, encoding="utf8")
        return self.client

    async def set_cache(self, key: str, value, ex: timedelta = None) -> bool:
        await self.get_redis()
        if not all((key, value)):
            return False

        params = {'name': f'{CACHE_HEADER}{key}', 'value': value}
        if ex:
            try:
                if isinstance(ex, timedelta | int):
                    params['ex'] = ex
                else:
                    params['ex'] = int(ex)
            except:
                pass

        if isinstance(value, int | float | str):
            return await self.client.set(**params)
        else:
            try:
                params['value'] = json.dumps(value)
                return await self.client.set(**params)
            except json.JSONDecodeError:
                return False

    async def get_cache(self, key: str) -> str:
        await self.get_redis()
        return await self.client.get(f'{CACHE_HEADER}{key}')

    async def del_cache(self, key: str) -> str:
        await self.get_redis()
        return await self.client.delete(f'{CACHE_HEADER}{key}')

    async def limit_opt_cache(self, user_id: str, operation_type: UserOperation) -> str:
        """
        increase operation times, return whether over time or not.
        """
        await self.get_redis()
        key = self.generate_user_operation_key(user_id, operation_type)
        times = await self.client.incr(f'{CACHE_HEADER}{key}')
        await self.expire_cache(key, operation_type.value.expire)
        return times > operation_type.value.limit

    async def clear_cache(self) -> str:
        await self.get_redis()
        return await self.client.flushall()

    async def expire_cache(self, key: str, ex: timedelta) -> str:
        await self.get_redis()
        return await self.client.expire(f'{CACHE_HEADER}{key}', ex)

    def generate_user_operation_key(self, user_id: str, operation_type: UserOperation):
        return f"{user_id}.{operation_type.value.code}"


cache_client = RedisCache()
