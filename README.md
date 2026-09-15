# INJ Watermark — 图片盲水印 + Injective 链上版权存证

> 在图片中嵌入不可见的版权水印，并将存证记录锚定到 Injective 区块链。支持本地模式（零门槛体验）和测试网模式（真实链上存证）。

---

## ✨ 功能特性

| 功能 | 说明 |
|---|---|
| 🖼️ **盲水印嵌入** | 基于 DWT+SVD 频域算法，肉眼不可见，抗裁剪/缩放/噪声 |
| ⛓️ **链上存证** | 版权哈希 + 签名写入 Injective CosmWasm 合约，不可篡改 |
| 🔍 **一键验证** | 从任意图提取水印 ID，自动与链上记录比对并验签 |
| 🧪 **本地模拟** | `--mode local` 无需链和钱包，直接跑通全流程 |
| 🧾 **版权元数据** | 标题 / 作者 / 许可证 / 联系方式 自定义 |

---

## 📦 环境准备

### 1. Python 依赖

```bash
cd INJ_Watermark
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置环境变量（仅测试网模式需要）

```bash
cp .env.example .env
# 然后编辑 .env，填入你的助记词或私钥 + 地址
```

> ⚠️ **安全提醒**：`.env` 已加入 `.gitignore`，**绝对不要**把助记词或私钥提交到 GitHub！

---

## 🚀 快速上手（本地模式，5 分钟跑通）

无需链、无需钱包，先在本地跑通一遍全流程。

### Step 1 — 嵌入水印 + 本地存证

```bash
python cli.py register \
  --img examples/output/original_demo.jpg \
  --output examples/output/wm_local_demo.jpg \
  --owner <你的 inj 地址, 例如 inj1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx> \
  --title "我的第一张测试图" \
  --author "张三" \
  --license "CC BY-NC-SA 4.0" \
  --mode local
```

运行成功后你会看到：

```
✅ 水印嵌入完成 → examples/output/wm_local_demo.jpg
✅ 本地存证完成 → copyright-id: INJ-CPR-xxxxxxxx
💡 验证命令:
  python cli.py verify --img examples/output/wm_local_demo.jpg --copyright-id INJ-CPR-xxxxxxxx --mode local
```

### Step 2 — 验证水印

复制上面的验证命令直接跑：

```bash
python cli.py verify \
  --img examples/output/wm_local_demo.jpg \
  --copyright-id INJ-CPR-xxxxxxxx \
  --mode local
```

预期输出：

```
✅ 水印提取成功
✅ 版权记录存在
✅ 签名校验通过 → 验证成功 🎉
```

---

## 🌐 测试网模式（真实链上存证）

### 前置条件

1. **领测试网 INJ**：访问 https://testnet.faucet.injective.network ，输入你的 inj 地址领水
2. **配置 `.env`**：填入助记词或私钥 + 地址
3. **合约地址**（如使用已部署示例）：`<你部署的合约地址, 例如 inj1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx>`

### Step 1 — 注册版权上链

```bash
python cli.py register \
  --img examples/output/original_demo.jpg \
  --output examples/output/wm_on_chain_demo.jpg \
  --owner $(grep OWNER_ADDRESS .env | cut -d'"' -f2) \
  --title "我的第一幅链上存证作品" \
  --author "张三" \
  --license "CC BY-NC-SA 4.0" \
  --mode testnet \
  --contract $(grep CONTRACT_ADDRESS .env | cut -d'"' -f2) \
  --privkey-hex "$(grep PRIVATE_KEY_HEX .env | cut -d'"' -f2)"
```

### Step 2 — 从链上查询记录

```bash
python cli.py query \
  --copyright-id INJ-CPR-xxxxxxxx \
  --contract $(grep CONTRACT_ADDRESS .env | cut -d'"' -f2)
```

### Step 3 — 完整验证（水印提取 + 链上比对）

```bash
python cli.py verify \
  --img examples/output/wm_on_chain_demo.jpg \
  --copyright-id INJ-CPR-xxxxxxxx \
  --mode testnet \
  --contract $(grep CONTRACT_ADDRESS .env | cut -d'"' -f2)
```

### Step 4 — 查看某地址所有版权

```bash
python cli.py list-by-owner \
  --owner <要查询的 inj 地址, 例如 inj1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx> \
  --contract $(grep CONTRACT_ADDRESS .env | cut -d'"' -f2)
```

---

## 🛠️ CLI 完整命令清单

| 命令 | 说明 |
|---|---|
| `register` | 嵌入水印并（本地或链上）注册版权 |
| `extract` | 仅从图片提取水印 bit 串（不上链） |
| `query` | 按 copyright-id 查询（本地或链上）存证记录 |
| `verify` | 水印提取 + 记录存在性 + 签名校验，一条龙验证 |
| `list-by-owner` | 列出某地址名下的所有版权 |
| `list` | 列出本地模拟链全部记录（`--mode local`） |

查看每个命令的参数：

```bash
python cli.py register --help
python cli.py verify --help
```

---

## 📁 项目结构

```
INJ_Watermark/
├── cli.py                    # 命令行入口
├── requirements.txt          # Python 依赖
├── .env.example              # 环境变量模板（复制为 .env 用）
├── .gitignore                # 敏感文件忽略规则
├── blind_watermark/          # 盲水印核心算法库（DWT+SVD）
│   ├── blind_watermark.py
│   ├── bwm_core.py
│   └── ...
├── src/                      # 业务封装
│   ├── watermark_service.py  # 水印嵌入/提取 + 哈希
│   ├── chain_service.py      # 本地模拟链 + 记录结构
│   ├── inj_broadcaster.py    # Injective 链交易广播
│   └── cosmwasm_contract.py  # CosmWasm 合约交互封装
├── contracts/copyright/      # CosmWasm 版权存证合约（Rust）
│   ├── Cargo.toml
│   └── src/
│       ├── contract.rs       # instantiate/execute/query
│       ├── msg.rs            # 消息定义
│       ├── state.rs          # 存储结构
│       └── error.rs
└── examples/
    ├── demo_flow.py          # 本地演示脚本
    ├── real_inj_demo.py      # 链上演示脚本
    └── output/               # 测试图片 & 输出
```

---

## 🔐 安全须知

1. **私钥/助记词**：永远放在 `.env` 或环境变量里，不要写进代码、日志、聊天记录
2. **上传 GitHub 前自查**：提交前跑一遍 `git status`，确认 `.env`、`*.key`、`*.pem` 没被 staged
3. **测试网优先**：所有操作先用 testnet 验证，确认无误再考虑主网
4. **地址格式**：签名用 Bech32（inj1…），不要和 EVM（0x…）混用

---

## 📚 Injective 资源链接

| 资源 | 地址 |
|---|---|
| 官方文档 | https://docs.injective.network/ |
| 浏览器（主网） | https://explorer.injective.network/ |
| 浏览器（测试网） | https://testnet.explorer.injective.network/ |
| 测试网水龙头 | https://injhub.com/faucet |
| 公共端点 | https://docs.injective.network/infra/public-endpoints |
| sdk-ts | https://github.com/InjectiveLabs/sdk-ts |
| injective-py | https://github.com/InjectiveLabs/sdk-python |

---

## 🐛 常见问题

**Q: 提取水印时位长不对，报长度错误？**  
A: 提取时必须加 `--bit-length 264`，这是本项目约定的固定长度。

**Q: `KeyError: 'embed_timestamp'`？**  
A: 已修复（链上返回 `registered_at`，单位是纳秒，代码里会自动转成秒）。请拉取最新代码。

**Q: `list-by-owner` 报 `invalid choice`？**  
A: 已修复 argparse 注册问题。请拉取最新代码。

**Q: CLI 跑 verify 时说找不到 `--contract` 参数？**  
A: 新版 `register` 输出的提示命令已自动带 `--contract` 参数，直接复制即可。

---

## 📄 License

Copyright © 2026. Code released under MIT.
