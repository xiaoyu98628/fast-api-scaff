-- 判断、计数与 TTL 读取必须原子执行，避免并发超额或跨窗口读取。
local limit = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local raw = redis.call('GET', KEYS[1])
if not raw then
    redis.call('SET', KEYS[1], 1, 'PX', window_ms)
    return {1, 0}
end
local count = tonumber(raw)
local ttl = redis.call('PTTL', KEYS[1])
if not count or count < 1 or count ~= math.floor(count) or ttl < 0 then
    return redis.error_reply('invalid rate limit state')
end
if count >= limit then
    return {0, ttl}
end
redis.call('INCR', KEYS[1])
return {1, 0}
