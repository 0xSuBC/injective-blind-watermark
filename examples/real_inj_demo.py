"""
真实 Injective 链演示 (LCD 只读查询 + 构造上链消息)
运行：python examples/real_inj_demo.py
"""
import os
import sys
import asyncio
import json
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.watermark_service import WatermarkService
from src.chain_service import ChainService
from src.cosmwasm_contract import print_contract_guide


def make_test_image(path: str):
    import numpy as np
    import cv2
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    for i in range(img.shape[0]):
        for j in range(img.shape[1]):
            img[i, j] = [
                (i * 200 // img.shape[0]) + 30,
                (j * 200 // img.shape[1]) + 30,
                80,
            ]
    cv2.putText(img, "Real INJ Chain", (100, 200),
                cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 5)
    cv2.putText(img, "Copyright 2026", (140, 280),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (240, 240, 240), 3)
    cv2.imwrite(path, img)


async def query_demo():
    print("╔════════════════════════════════════════════════════════╗")
    print("║   🔗 Injective 测试网 - 版权 LCD 查询 演示            ║")
    print("╚════════════════════════════════════════════════════════╝\n")

    CONTRACT_ADDR = "inj1_replace_with_your_contract_address"

    if "replace" in CONTRACT_ADDR:
        print("ℹ️  未设置真实合约地址，展示合约部署指南：\n")
        print_contract_guide()
        return

    chain = ChainService(mode="testnet", contract_address=CONTRACT_ADDR)
    demo_cid = "INJ-CPR-demo0001-0000000000000000"

    print(f"网络: Injective Testnet (injective-888)")
    print(f"合约: {CONTRACT_ADDR}")
    print(f"LCD : {chain.inj.config['lcd_endpoint']}")
    print(f"\n查询版权 ID: {demo_cid} ...\n")

    try:
        result = await chain.query_record_async(demo_cid)
        if result:
            print("✅ 查询成功:\n")
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("ℹ️  该版权 ID 尚未在链上注册（示例行为，属正常）")
    except Exception as e:
        print(f"❌ 查询异常: {type(e).__name__}: {e}")
        print("   (可能是合约未部署、网络问题、或查询语法问题)")


def local_embed_for_real_chain():
    print("\n╔════════════════════════════════════════════════════════╗")
    print("║   🖼️  本地嵌入水印 + 生成上链 ExecuteMsg               ║")
    print("╚════════════════════════════════════════════════════════╝\n")

    output_dir = os.path.join(ROOT, "examples", "output")
    os.makedirs(output_dir, exist_ok=True)
    original_path = os.path.join(output_dir, "_original_real.jpg")

    make_test_image(original_path)

    watermarked_path = os.path.join(output_dir, "02_real_chain_ready.jpg")

    wm = WatermarkService(password_wm=20260908, password_img=77665544)
    owner = "inj1qp8qy5rxl96fka6x7nvxwqt32smehafuhtny2c"

    record = wm.embed_copyright(
        original_img_path=original_path,
        output_img_path=watermarked_path,
        owner_address=owner,
        metadata={"title": "Real INJ Chain Demo #1", "year": 2026, "author": "Alice"},
    )

    chain_local = ChainService(mode="local")
    tx = chain_local.store_record(record, owner)

    print(f"✅ 水印嵌入完成")
    print(f"   版权 ID        : {record['copyright_id']}")
    print(f"   水印图文件     : {watermarked_path}")
    print(f"   水印 Bit 长度  : {record['wm_bit_length']}")
    print(f"   记录完整性哈希: {tx['record_hash']}\n")

    CONTRACT = "inj1_replace_with_your_contract_address"
    chain_testnet = ChainService(mode="testnet", contract_address=CONTRACT)
    broadcast = chain_testnet.store_record(record, owner)

    print("📤 上链广播数据 (CosmWasm ExecuteMsg):")
    print("─" * 60)
    print(json.dumps(broadcast["execute_msg"], indent=2, ensure_ascii=False))
    print("─" * 60)

    print("\n📟 等效 injectived CLI 广播命令:")
    print("=" * 60)
    msg_str = json.dumps(broadcast["execute_msg"]).replace('"', '\\"')
    print(f"""
# 替换 WALLET 为你的钱包别名，CHAIN / NODE 按需修改
WALLET=my_testnet_key
CHAIN=injective-888
NODE=https://testnet.sentry.tm.injective.network:443
CONTRACT={CONTRACT}

injectived tx wasm execute $CONTRACT "{msg_str}" \\
  --from=$WALLET \\
  --chain-id=$CHAIN --node=$NODE \\
  --gas=auto --gas-adjustment=1.5 \\
  --gas-prices=500000000inj \\
  -y
""")
    print("=" * 60)

    print("\n📖 验证流程:")
    print("   1) 执行上面的 CLI 命令 → 拿到交易哈希")
    print("   2) 打开 https://testnet.explorer.injective.network/transaction/<TX_HASH> 确认上链")
    print("   3) 重新运行本脚本并填入合约地址，通过 LCD 查询刚写入的版权")
    print("   4) 用 demo_flow.py 的 verify_ownership() 做链上+水印联合验证\n")


async def main():
    await query_demo()
    local_embed_for_real_chain()


if __name__ == "__main__":
    asyncio.run(main())
