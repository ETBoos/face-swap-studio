# 试用激活码

试用码和 USDT 年费同时存在，互不替代。

| 种类 | 形式 | 作用 |
|------|------|------|
| 试用 | `FS-1D-…` 1 天，`FS-30D-…` 30 天 | 开通预览。到期回到未激活 |
| 正式 | USDT 年费（Starter / Pro / Studio） | `apply_usdt_payment_callback()` 后 `active=true` |

试用到期**不会**自动升级 Pro，也不会打开专模 `.dfm`。专模仍要 Pro/Studio 且 USDT 已开通。

未激活或试用已到期：「开始预览」和「导出参考帧」不可用，主窗口留「激活」。已使用的码不能再用。

本机记录在 `~/FaceSwapStudio/license.json`（`activated_at`、`expires_at`、`used_codes`）。码表没有签名，也没有机器指纹。改这个本地文件可以绕过，这是有意接受的。

## 怎么增加激活码

编辑 `src/face_swap_studio/licensing/codes.py` 的 `CODE_TABLE`，加一行：

```python
"FS-1D-XXXX-XXXX-XXXX": 1,    # 1 天
"FS-30D-XXXX-XXXX-XXXX": 30,  # 30 天
```

天数只写 `1` 或 `30`。不要把「已使用」写回这张表；用过的码在用户机器的 `license.json` → `used_codes`。
