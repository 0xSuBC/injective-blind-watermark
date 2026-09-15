"""
完整流程演示:
  1️⃣ 读取/生成测试图片
  2️⃣ 嵌入版权盲水印
  3️⃣ 链上存证 (local 模拟 CosmWasm)
  4️⃣ 链上查询存证记录
  5️⃣ 从图片提取版权 ID
  6️⃣ 完整版权归属验证
  7️⃣ 7 种攻击鲁棒性测试
"""
import os
import sys
import time
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.watermark_service import WatermarkService
from src.chain_service import ChainService
from blind_watermark import att


def make_test_image(path: str):
    import numpy as np
    import cv2
    img = np.zeros((640, 800, 3), dtype=np.uint8)
    for i in range(img.shape[0]):
        for j in range(img.shape[1]):
            img[i, j] = [
                (i * 180 // img.shape[0]) + 40,
                (j * 180 // img.shape[1]) + 40,
                ((i + j) * 180 // (img.shape[0] + img.shape[1])) + 40,
            ]
    cv2.putText(img, "INJ Watermark", (110, 190),
                cv2.FONT_HERSHEY_SIMPLEX, 2.2, (255, 255, 255), 6)
    cv2.putText(img, "Copyright (c) 2026", (140, 290),
                cv2.FONT_HERSHEY_SIMPLEX, 1.3, (240, 240, 240), 3)
    cv2.putText(img, "Blockchain Copyright Demo", (140, 360),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (220, 220, 220), 2)
    cv2.imwrite(path, img)


def section(title: str):
    print("\n" + "─" * 68)
    print(f"  {title}")
    print("─" * 68)


def run():
    print("\n" + "=" * 68)
    print("  🏛️   INJ Watermark - 版权盲水印 + 链上存证 完整演示")
    print("=" * 68)

    output_dir = os.path.join(ROOT, "examples", "output")
    os.makedirs(output_dir, exist_ok=True)

    original_path = os.path.join(output_dir, "_original.jpg")
    make_test_image(original_path)

    section("1️⃣  初始化服务")
    owner = "inj1qp8qy5rxl96fka6x7nvxwqt32smehafuhtny2c"
    print(f"   所有者地址    : {owner}")
    wm = WatermarkService(password_wm=20260908, password_img=77665544)
    chain = ChainService(mode="local")
    print(f"   水印服务密钥  : password_wm=20260908, password_img=77665544")
    print(f"   链服务模式    : local (模拟 CosmWasm 合约)")

    section("2️⃣  嵌入版权盲水印")
    watermarked_path = os.path.join(output_dir, "01_watermarked.jpg")
    metadata = {
        "title": "INJ 创世水印作品 #001",
        "creator": "Alice Chen",
        "license": "CC BY-NC-SA 4.0",
        "year": 2026,
        "tags": ["art", "injective", "nft-ready"],
    }
    record = wm.embed_copyright(
        original_img_path=original_path,
        output_img_path=watermarked_path,
        owner_address=owner,
        metadata=metadata,
    )
    print(f"   版权 ID        : {record['copyright_id']}")
    print(f"   原图 SHA256    : {record['original_hash'][:24]}...")
    print(f"   水印图 SHA256  : {record['watermarked_hash'][:24]}...")
    print(f"   水印 Bit 长度  : {record['wm_bit_length']} bits")
    print(f"   输出文件       : {watermarked_path}")

    section("3️⃣  链上存证 (CosmWasm 模拟)")
    tx = chain.store_record(record, owner)
    if tx["success"]:
        print(f"   ✅ 存证成功")
        print(f"   交易哈希 (TX) : {tx['tx_hash'][:24]}...")
        print(f"   记录完整性哈希: {tx['record_hash'][:24]}...")
        print(f"   区块高度       : {tx['block_height']}")
        t = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(tx['stored_at']))
        print(f"   存证时间       : {t}")
    else:
        print(f"   ❌ 存证失败: {tx.get('error')}")
        return

    section("4️⃣  从链上查询存证记录")
    queried = chain.query_record(record["copyright_id"])
    if queried:
        print(f"   ✅ 查询到记录")
        print(f"   版权 ID  : {queried['copyright_id']}")
        print(f"   所有者    : {queried['owner']}")
        print(f"   标题      : {queried['metadata'].get('title')}")
        print(f"   创作者    : {queried['metadata'].get('creator')}")
        print(f"   授权协议  : {queried['metadata'].get('license')}")
    else:
        print("   ❌ 未找到链上记录")
        return

    section("5️⃣  从水印图中提取版权 ID")
    extracted = wm.extract_copyright_id(watermarked_path, record["wm_bit_length"])
    match = "✅ 完全匹配" if extracted == record["copyright_id"] else "❌ 不匹配"
    print(f"   提取结果 : {extracted}")
    print(f"   原始 ID  : {record['copyright_id']}")
    print(f"   比对     : {match}")

    section("6️⃣  完整版权归属验证")
    ok, detail = wm.verify_ownership(watermarked_path, queried)
    print("   " + detail.replace("\n", "\n   "))

    section("7️⃣  鲁棒性测试：7 种攻击后提取水印")
    attacks = [
        ("亮度调高 (+10%)", lambda i, o: att.bright_att(i, o, ratio=1.1), None),
        ("亮度调低 (-15%)", lambda i, o: att.bright_att(i, o, ratio=0.85), None),
        ("横向裁剪 (80%)", lambda i, o: att.cut_att_width(i, o, ratio=0.8), (640, 800)),
        ("纵向裁剪 (80%)", lambda i, o: att.cut_att_height(i, o, ratio=0.8), (640, 800)),
        ("缩放攻击",        lambda i, o: att.resize_att(i, o, out_shape=(400, 500)), None),
        ("椒盐噪声 (3%)",   lambda i, o: att.salt_pepper_att(i, o, ratio=0.03), None),
        ("遮挡攻击 (3块)",  lambda i, o: att.shelter_att(i, o, ratio=0.08, n=3), None),
    ]
    print(f"   {'攻击方式':<18} | {'提取结果':<30} | 验证")
    print("   " + "-" * 70)
    recovered = 0
    for name, fn, recover_shape in attacks:
        attacked_path = os.path.join(output_dir, f"attack_{name[:4].replace(' ','_')}.jpg")
        try:
            fn(watermarked_path, attacked_path)
            ext_path = attacked_path
            if recover_shape:
                rec_path = os.path.join(output_dir, f"attack_{name[:4].replace(' ','_')}_rec.jpg")
                att.anti_cut_att(attacked_path, rec_path, origin_shape=recover_shape)
                ext_path = rec_path
            ex = wm.extract_copyright_id(ext_path, record["wm_bit_length"])
            if ex == record["copyright_id"]:
                status = "✅ 通过"
                recovered += 1
            else:
                status = f"⚠️  {ex[:18]}..."
            print(f"   {name:<18} | {ex[:30]:<30} | {status}")
        except Exception as e:
            print(f"   {name:<18} | {'(异常)':<30} | ❌ {str(e)[:28]}")

    print(f"\n   📊 鲁棒性汇总: {recovered}/{len(attacks)} 种攻击后水印仍可识别")

    section("📋 本地链上存证列表")
    records = chain.list_records()
    if not records:
        print("   (暂无存证)")
    for i, r in enumerate(records, 1):
        t = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(r["stored_at"]))
        print(f"   {i}. {r['copyright_id']}")
        print(f"      所有者: {r['owner']}  |  标题: {r['title']}")
        print(f"      区块: {r['block']}  |  时间: {t}")
        print(f"      TX: {r['tx_hash'][:20]}...")

    section("🔗 接入真实 Injective 链 (3 步)")
    print("""
   ① 部署 CosmWasm 版权合约:
        cd contracts/copyright
        rustup target add wasm32-unknown-unknown
        RUSTFLAGS='-C link-arg=-s' cargo build --release --target wasm32-unknown-unknown
        injectived tx wasm store target/wasm32-unknown-unknown/release/copyright_contract.wasm ...
        injectived tx wasm instantiate $CODE_ID '{\"admin\":\"你的地址\"}' ...

   ② 在 Python 中切换模式:
        chain = ChainService(
            mode=\"testnet\",
            contract_address=\"inj1...合约地址\"
        )

   ③ 存证 & 查询:
        store_record(...) → 返回 execute_msg，用私钥签名广播
        query_record_async(copyright_id) → 通过 LCD 从链上读取

   Testnet 水龙头: https://testnet.faucet.injective.network
   Testnet 浏览器: https://testnet.explorer.injective.network
""")

    print("\n" + "=" * 68)
    print(f"  🎉 演示完成！产物目录: {output_dir}")
    print("=" * 68 + "\n")


if __name__ == "__main__":
    run()
