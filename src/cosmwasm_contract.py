"""
CosmWasm 版权存证合约 - 接口说明文档
对应 contracts/copyright/ 下的 Rust 实现
"""


def print_contract_guide():
    print(r"""
╔══════════════════════════════════════════════════════════════════╗
║          📜 INJ 版权存证 CosmWasm 合约 部署指南                  ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  ⚙️  编译环境设置 (首次执行)                                     ║
║  ───────────────────────────────────────────────────────        ║
║  # 1. 安装 Rust (如果没装)                                      ║
║  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh ║
║  rustup default stable                                          ║
║                                                                  ║
║  # 2. 添加 wasm32 编译目标                                      ║
║  rustup target add wasm32-unknown-unknown                       ║
║                                                                  ║
║  # 3. 安装 wasm-opt (优化 wasm 体积, 推荐)                      ║
║  brew install binaryen              # macOS                    ║
║  # 或从 https://github.com/WebAssembly/binaryen/releases 下载   ║
║                                                                  ║
║  📦 编译合约                                                    ║
║  ───────────────────────────────────────────────────────        ║
║  cd contracts/copyright                                         ║
║                                                                  ║
║  # 开发编译 (快, 未优化)                                        ║
║  cargo build --target wasm32-unknown-unknown                    ║
║                                                                  ║
║  # 发布编译 (小体积, 用于上链)  ⭐                               ║
║  RUSTFLAGS='-C link-arg=-s'                                   ║
║    cargo build --release --target wasm32-unknown-unknown        ║
║                                                                  ║
║  # 产物位置:                                                     ║
║  # target/wasm32-unknown-unknown/release/copyright_contract.wasm║
║                                                                  ║
║  # 用 wasm-opt 进一步优化 (推荐, 可节省 30-50% 体积)            ║
║  wasm-opt -Os -o copyright_opt.wasm                           ║
║    target/wasm32-unknown-unknown/release/copyright_contract.wasm║
║                                                                  ║
║  🚀 部署到 Injective Testnet                                    ║
║  ───────────────────────────────────────────────────────        ║
║  # 前置: 安装 injectived CLI 并导入钱包                         ║
║  # 申请测试网 INJ: https://testnet.faucet.injective.network     ║
║                                                                  ║
║  WALLET=my_testnet_key   # 替换为你的钱包 key 名称              ║
║  CHAIN=injective-888                                            ║
║  NODE=https://testnet.sentry.tm.injective.network:443           ║
║  WASM=copyright_opt.wasm                                        ║
║                                                                  ║
║  # Step 1: 上传合约代码 (store)                                 ║
║  injectived tx wasm store $WASM                               ║
║    --from=$WALLET --chain-id=$CHAIN --node=$NODE              ║
║    --gas=auto --gas-adjustment=1.5                            ║
║    --gas-prices=500000000inj -y                                 ║
║  # 👉 记录返回的 CODE_ID (例如 12345)                           ║
║                                                                  ║
║  CODE_ID=<这里填返回的code_id>                                   ║
║                                                                  ║
║  # Step 2: 实例化合约 (instantiate)                             ║
║  INIT_MSG='{"admin":"'$(injectived keys show $WALLET -a)'"}'    ║
║  injectived tx wasm instantiate $CODE_ID "$INIT_MSG"          ║
║    --from=$WALLET --chain-id=$CHAIN --node=$NODE              ║
║    --label="INJ Copyright Registrar"                          ║
║    --no-admin -y                                                 ║
║  # 👉 记录合约地址 inj1...                                      ║
║                                                                  ║
║  🧪 测试合约 (存证一条版权)                                     ║
║  ───────────────────────────────────────────────────────        ║
║  CONTRACT=inj1xxxx...                                            ║
║  REGISTER='{"register_copyright":{                              ║
║    "copyright_id":"INJ-CPR-test0001-abcdef0123456789",          ║
║    "owner":"'$(injectived keys show $WALLET -a)'",              ║
║    "original_hash":"0" repeat 64 chars,                         ║
║    "watermarked_hash":"1" repeat 64 chars,                      ║
║    "wm_bit_length":320,                                         ║
║    "record_hash":"2" repeat 64 chars                            ║
║  }}'                                                             ║
║  injectived tx wasm execute $CONTRACT "$REGISTER"             ║
║    --from=$WALLET --chain-id=$CHAIN --node=$NODE              ║
║    --gas=auto --gas-adjustment=1.3 -y                           ║
║                                                                  ║
║  # 查询刚才存证的版权                                           ║
║  QUERY='{"get_copyright":{"copyright_id":"INJ-CPR-test0001-..."}}'║
║  injectived query wasm contract-state smart $CONTRACT "$QUERY"  ║
║                                                                  ║
║  🌐 浏览器中查看:                                               ║
║  https://testnet.explorer.injective.network/contract/$CONTRACT ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
""")
