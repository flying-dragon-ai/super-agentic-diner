"""共享 Redis/fakeredis 客户端工厂。

当 USE_FAKEREDIS=true(启用模拟Redis) 时，返回 fakeredis(进程内模拟Redis) 客户端，
所有模块共享同一个 FakeServer(模拟服务端)，保证写入的数据能被其他模块读到。
否则返回真实 redis-py 客户端，连接 settings.redis_url。
"""
from __future__ import annotations

import logging

import redis
from redis.exceptions import RedisError

from app.config import settings

logger = logging.getLogger(__name__)

# fakeredis(模拟Redis) 共享服务端：全局单例，保证进程内所有模块看到同一份数据。
_fake_server = None


def get_redis_client(decode_responses: bool = True) -> redis.Redis:
    """获取 Redis 客户端：fakeredis（本地）或 redis-py（远程）。

    fakeredis 模式下所有调用共享同一个 FakeServer，保证 chat_history(对话历史)
    和 experience_agent(经验继承) 等模块读写的数据一致。
    """
    global _fake_server
    if settings.use_fakeredis:
        import fakeredis

        if _fake_server is None:
            _fake_server = fakeredis.FakeServer()
            logger.info("fakeredis(模拟Redis) 已启用，使用进程内共享 FakeServer(模拟服务端)")
        return fakeredis.FakeRedis(server=_fake_server, decode_responses=decode_responses)
    return redis.Redis.from_url(
        settings.redis_url,
        decode_responses=decode_responses,
        socket_connect_timeout=settings.redis_socket_connect_timeout,
        socket_timeout=settings.redis_socket_timeout,
    )
