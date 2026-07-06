
import time
CACHE = {}

class Cache:
    @staticmethod
    def set(key: str, value, ttl: int = 300):
        CACHE[key] = {"value": value, "expire": time.time() + ttl}

    @staticmethod
    def get(key: str):
        item = CACHE.get(key)
        if not item:
            return None
        if time.time() > item["expire"]:
            del CACHE[key]
            return None
        return item["value"]
