-- 递增和首次设置过期时间必须原子执行，避免计数 key 缺少 TTL。
local value = redis.call('INCR', KEYS[1])
if value == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return value
