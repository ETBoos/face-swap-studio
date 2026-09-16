# USDT 收费与壳内埋点

仅支持 USDT（TRC20 优先，ERC20 可选）。法币不接。

## 档位

| 档位 | 年费 USDT | 席位 | 简易 | 顶级 dfm |
|------|-----------|------|------|----------|
| Starter | 199 | 1 | ✓ | ✗ |
| Pro | 599 | 3 | ✓ | ✓ |
| Studio | 1499 | 10 | ✓ | ✓ |

加购：额外席位 79 USDT/年。

## 壳内模块

- `licensing/plans.py` — 档位目录
- `licensing/store.py` — 本地 `license.json` + `apply_usdt_payment_callback()`
- 回调：链上到账服务验证 tx 后调用回调 → `active=true` 开授权

## 未做（下一迭代）

- 真实链上扫块 / 地址分配
- 授权加密狗 / 机器指纹
- 支付二维码 UI

## 虚拟摄像头与档位

虚拟摄像头输出（OBS → MF → WhatsApp/微信实验）仅 **Pro / Studio**；Starter 仅预览窗。详见 PRODUCT_SPEC「桌面通话兼容」。

## Studio 可选硬件

L3 微信保底：`HDMI 环出 + HDMI→USB UVC 采集卡（1080p60）` 为 Studio 可选件，不进软件标配价。
