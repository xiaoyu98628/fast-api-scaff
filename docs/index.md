# 使用手册

这套文档面向两类读者：第一次运行脚手架的使用者，以及准备在其上新增限界上下文、数据库连接、缓存实现或宿主入口的维护者。

建议先按顺序阅读“开始使用”，遇到具体问题时再进入专题章节。文档只描述当前代码中已经实现并可验证的能力；常驻调度服务尚未实现，因此不作为现有功能说明。

## 开始使用

- [快速开始](getting-started.md)：三种启动路径、迁移顺序和首次验证。
- [配置参考](configuration.md)：环境变量、默认值、校验时机和生效方式。
- [HTTP 接口](http.md)：路由、统一响应、错误处理、中间件和扩展方法。
- [Console 命令](console.md)：命令、输出协议、退出码和新增命令方式。

## 基础设施

- [数据库](database.md)：多连接、SQLAlchemy、Repository、Unit of Work 和 Alembic。
- [缓存](cache.md)：Redis、Memcached、Memory、key、TTL、编码与边界。
- [HTTP 出站请求](outbound-http.md)：公共契约、普通/流式请求、连接池、超时和错误语义。
- [日志](logging.md)：结构化日志、访问日志、字段、输出流和扩展驱动。

## 设计与维护

- [架构说明](architecture.md)：模块化单体、DDD 分层、依赖方向和上下文扩展。
- [开发与质量](development.md)：测试、Lint、类型检查、迁移和提交前检查。
- [故障排查](troubleshooting.md)：按症状定位配置、数据库、缓存、HTTP 和 Console 问题。

## 当前能力边界

已经实现：

- FastAPI HTTP 宿主与 Typer Console 宿主；
- 用户限界上下文的增、查、改、删示例；
- MySQL、PostgreSQL、SQLite 异步数据库连接；
- Redis、Memcached、进程内 Memory 字节级 KV 缓存；
- 普通与流式 HTTP 出站客户端、独立连接池和统一传输错误；
- JSON/Text 结构化日志、请求 ID、访问日志和统一 HTTP 响应；
- Alembic 数据库迁移与架构依赖测试。

尚未实现：

- 常驻 Scheduler/Worker 宿主；
- 登录认证、授权、密码修改和令牌；
- 领域事件、Outbox、Saga 或跨数据库原子事务；
- Redis Hash/List/Set/ZSet 等数据结构；
- 缓存故障时的自动降级或透明回退。
- 通用 HTTP 自动重试、熔断和具体上游服务注册。

“尚未实现”并不表示不能扩展，而是提醒使用者不要把规划能力当成现有契约。扩展前先阅读[架构说明](architecture.md)中的边界与取舍。
