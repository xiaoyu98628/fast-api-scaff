-- 判断与删除必须在同一次执行中完成；达到阈值时不改变计数或 TTL。
local threshold = ARGV[1]
if not string.match(threshold, '^[1-9][0-9]*$') then
    return redis.error_reply('invalid counter threshold')
end
local raw = redis.call('GET', KEYS[1])
if not raw then
    return 0
end
-- INCR 的正计数是规范十进制有符号 64 位整数；异常状态不得被清理掩盖。
local maximum = '9223372036854775807'
if not string.match(raw, '^[1-9][0-9]*$') or #raw > #maximum or (#raw == #maximum and raw > maximum) then
    return redis.error_reply('invalid counter state')
end
-- 按长度和字典序比较，避免 Lua 浮点数在大整数边界上丢失精度。
if #raw < #threshold or (#raw == #threshold and raw < threshold) then
    return redis.call('DEL', KEYS[1])
end
return 0
