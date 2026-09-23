# 密钥激活与 Railway 后台

FaceSwap Studio 使用 Ed25519 数字签名授权。桌面端只内置公钥，签名私钥仅存在授权后台；修改本地 JSON、套餐名或功能列表不会得到有效授权。

## 用户端行为

- 未激活：可以检查带 `FaceSwap Studio · Preview` 标记的本机预览，不能启动虚拟摄像头输出，也不能导入专业人物模型。
- Starter：照片预览、带标记输出、1 台设备。
- Pro / Studio：按签名凭证开放专业人物模型、去除标记和对应设备数。
- 在线激活后会保存一份设备绑定的签名凭证。默认可离线使用 7 天，联网刷新后续期；产品总有效期仍由密钥控制。
- 离线授权文件也是设备绑定的签名凭证，不能复制到另一台电脑使用。

## 生成签名密钥

在安全的管理电脑上执行，私钥目录已被 Git 忽略：

```sh
mkdir -p .secrets
uv run face-swap-studio-license init-keys --private-key .secrets/license-signing-key.pem
```

命令会输出 `FSS_LICENSE_PUBLIC_KEY`。私钥不能提交到 GitHub，也不能放进 Windows 安装包。请单独加密备份；丢失私钥后，已发行客户端无法验证新后台签发的凭证。

## Railway 部署

仓库根目录的 `Dockerfile` 和 `railway.json` 已配置容器入口、`/health` 健康检查和失败重启。

1. 在 Railway 新建项目，从 GitHub 选择本仓库与正式分支。
2. 为服务挂载 Volume，挂载路径填写 `/data`。SQLite 授权库会保存在 `/data/licenses.sqlite3`，没有 Volume 时重新部署会丢失已发行密钥和设备绑定记录。
3. 在服务 Variables 中设置：
   - `FSS_LICENSE_PRIVATE_KEY`：完整 PEM 私钥，或 PEM 文件的 base64 内容。
   - `FSS_ADMIN_TOKEN`：至少 32 字节的随机管理员令牌。
   - `FSS_OFFLINE_DAYS=7`。
   - `FSS_LICENSE_DATABASE=/data/licenses.sqlite3`。
4. 在 Settings → Networking 生成 Railway HTTPS 域名。确认 `https://你的域名/health` 返回 `{"ok": true}`。
5. 将域名和公钥写入 GitHub 仓库 Variables：`FSS_ACTIVATION_URL`、`FSS_LICENSE_PUBLIC_KEY`。下一次 Windows 构建会把二者写入安装包的 `activation.json`，不会包含私钥或管理员令牌。

Railway 会给服务注入 `PORT`，后台自动监听该端口。部署变量只在运行时读取，不会进入容器镜像。

## 云端发卡

发卡接口只接受 Railway 中的管理员令牌。下面示例创建一个 365 天、1 台设备的 Starter 密钥：

```sh
curl -X POST "$FSS_ACTIVATION_URL/v1/admin/licenses" \
  -H "Authorization: Bearer $FSS_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"plan":"starter","days":365,"max_devices":1,"note":"订单号或客户备注"}'
```

返回的 `product_key` 只在创建时出现，应立即交付给客户。查看授权列表：

```sh
curl "$FSS_ACTIVATION_URL/v1/admin/licenses" \
  -H "Authorization: Bearer $FSS_ADMIN_TOKEN"
```

停用授权使用 `POST /v1/admin/disable`，请求体为 `{"license_id":"lic_...","disabled":true}`。释放一台旧设备使用 `POST /v1/admin/release-device`，请求体包含 `license_id` 和桌面激活窗口显示的 `device_id`。

## 本地验证

```sh
FSS_LICENSE_PRIVATE_KEY="$(cat .secrets/license-signing-key.pem)" \
FSS_ADMIN_TOKEN="本地测试令牌" \
FSS_LICENSE_DATABASE="./licenses.sqlite3" \
uv run face-swap-studio-license-server --host 127.0.0.1 --port 8787
```

开发版可在仓库根目录创建被 Git 忽略的 `activation.local.json`：

```json
{
  "activation_url": "http://127.0.0.1:8787",
  "license_public_key": "init-keys 输出的公钥"
}
```

非本机地址必须使用 HTTPS。正式安装包不接受远程明文 HTTP 激活。
