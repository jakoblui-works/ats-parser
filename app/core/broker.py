from taskiq_redis import RedisAsyncResultBackend, RedisStreamBroker

from app.core.config import settings

broker = RedisStreamBroker(
    url=settings.redis.url,
    queue_name="ats",
).with_result_backend(RedisAsyncResultBackend(settings.redis.url, result_ex_time=3600, prefix_str="ats"))
