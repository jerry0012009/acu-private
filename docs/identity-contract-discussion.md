# acu-private 身份边界讨论

## 已确定

`acu-private` 是第三个仓库，不是 `new-api` 的替代 fork，也不是 `acu-router` 的复制品。

职责保持最小：

```text
已登录 Console 请求
  -> acu-private 验证/接收账户身份
  -> 调用 acu-router 受保护的内部 Advisor API
  -> 返回当前账户自己的 Advisor
```

以下内容继续留在 `acu-router`：

- 每 10 次 Agent LLM call 的 Observer 触发；
- Advisor 两轮 Mimo 调用；
- 每条人工 user message 的 Learning Judge；
- Acontext adapter；
- Advisor 结果持久化；
- Router 内部 token 保护。

以下内容继续留在 `acu-frontend`：

- `/dashboard/acu-advisor`；
- Advisor 展示；
- helpful / inaccurate / ignored 反馈操作。

## 需要确认的一件事

`acu-private` 如何获得已登录用户的可信 `newapiUserId`？

候选只有两个：

### A. 可信内部请求头

由已经完成登录认证的 Console 入口或反向代理设置，例如：

```text
X-ACU-Authenticated-User: <verified-newapi-user-id>
```

`acu-private` 只接受来自可信内网/代理的请求，并拒绝浏览器直接提供的同名 header。

### B. 签名内部身份令牌

登录入口向 `acu-private` 发送短时效、带 audience 的内部签名令牌。`acu-private` 验证签名、过期时间和用户 id。

第一版不在 `acu-private` 新建账号系统，也不复制 New API 的 Cookie/JWT 认证逻辑。身份来源确定后，再实现两个最小 API endpoint。
