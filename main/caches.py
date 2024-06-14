import hashlib

from django.core.cache import caches

local_cache = caches["local-memory"]


class CacheKey:
    # Redis Cache
    URL_CACHED_FILE_FIELD_KEY_FORMAT = "url-cached-file-key-{0}"

    # Local (RAM) Cache
    TEMP_CLIENT_ID_KEY_FORMAT = "client-id-mixin-{request_hash}-{instance_type}-{instance_id}"

    EXPORT_TASK_ID_CACHE_KEY = "export-task-async-id-%s"

    @staticmethod
    def generate_hash(string: str):
        hash_md5 = hashlib.md5()
        hash_md5.update(string.encode())
        return hash_md5.hexdigest()
