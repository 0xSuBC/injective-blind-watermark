#!/usr/bin/env python3
"""
INJ Watermark 一键 CLI
======================

嵌入水印 + 上链存证 + 提取验证（一条龙）

用法:
  # 1) 嵌入水印并上链存证
  python cli.py register \\
      --img /path/to/original.jpg \\
      --output /path/to/watermarked.jpg \\
      --owner inj1... \\
      --title "作品标题" --author "作者" --license "CC BY-NC-SA 4.0" \\
      [--mode local] [--contract inj1...] [--mnemonic "xxx xxx ..."]

  # 2) 从图片提取版权 ID
  python cli.py extract --img watermarked.jpg --bit-length 264

  # 3) 查询链上版权记录
  python cli.py query --copyright-id INJ-CPR-xxxxxxx [--contract inj1...]

  # 4) 完整验证 (水印提取 + 链上比对)
  python cli.py verify --img watermarked.jpg --copyright-id INJ-CPR-xxxxxxx [--mode local]

  # 5) 列出本地所有模拟链存证
  python cli.py list --mode local

  # 6) 使用真实 INJ Testnet (需要合约地址 + 助记词或私钥)
  python cli.py register --img a.jpg --output b.jpg \\
      --owner inj1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \\
      --mode testnet \\
      --contract <部署后的合约地址, 例如 inj1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx> \\
      --mnemonic "<你的 12 词 BIP-39 助记词>" \\
      --title "测试" --author "Me"
"""
import os
import sys
import json
import asyncio
import argparse

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from src.watermark_service import WatermarkService
from src.chain_service import ChainService, CopyrightRecord
from src.inj_broadcaster import InjectiveBroadcaster, build_register_msg


def banner():
    print("""
╔══════════════════════════════════════════════════════╗
║  🏛️   INJ WATERMARK CLI  —  盲水印 + 链上版权存证    ║
╚══════════════════════════════════════════════════════╝
""")


def cmd_register(args):
    if not os.path.exists(args.img):
        print(f"❌ 原图不存在: {args.img}")
        sys.exit(1)
    for d in os.path.split(args.output)[0]:
        pass
    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)

    wm = WatermarkService()
    metadata = {
        "title": args.title or "",
        "author": args.author or "",
        "license": args.license or "",
    }
    if args.extra_meta:
        try:
            metadata.update(json.loads(args.extra_meta))
        except Exception:
            print("⚠️  --extra-meta 解析失败，忽略")

    print(f"🔐 嵌入水印:")
    print(f"   原图     : {args.img}")
    print(f"   输出     : {args.output}")
    print(f"   所有者   : {args.owner}")
    print(f"   元数据   : {metadata}")
    record = wm.embed_copyright(args.img, args.output, args.owner, metadata)
    print(f"   版权 ID  : {record['copyright_id']}")
    print(f"   Bit 长度 : {record['wm_bit_length']}")
    print(f"   原图哈希 : {record['original_hash'][:32]}...")
    print(f"   水印哈希 : {record['watermarked_hash'][:32]}...")
    print(f"   记录哈希 : {CopyrightRecord.compute_record_hash(record)[:32]}...")

    # 上链
    mode = args.mode or "local"
    print(f"\n⛓️  上链存证 (mode={mode}):")

    if mode == "local":
        chain = ChainService(mode="local")
        tx = chain.store_record(record, args.owner)
        if tx["success"]:
            print(f"   ✅ 本地存证成功")
            print(f"   交易哈希 : {tx['tx_hash']}")
            print(f"   区块高度 : {tx['block_height']}")
            st = __import__('time').strftime("%Y-%m-%d %H:%M:%S",
                                             __import__('time').localtime(tx['stored_at']))
            print(f"   存证时间 : {st}")
        else:
            print(f"   ❌ 失败: {tx.get('error')}")

    else:  # testnet / mainnet
        if not args.contract:
            print("❌ 真实链需要 --contract <合约地址>")
            sys.exit(1)
        if not args.mnemonic and not args.privkey_hex:
            print("❌ 真实链需要 --mnemonic 或 --privkey-hex")
            sys.exit(1)

        brd = InjectiveBroadcaster(mode)
        if args.mnemonic:
            addr = brd.from_mnemonic(args.mnemonic.strip())
        else:
            addr = brd.from_private_key_hex(args.privkey_hex.strip())
        print(f"   发送者   : {addr}")
        if addr != args.owner:
            print(f"   ⚠️  发送者 ≠ 版权所有者 (允许，但合约会以 owner 字段为准)")

        execute_msg = build_register_msg(record)
        print(f"   合约     : {args.contract}")
        print(f"   Execute  : {list(execute_msg.keys())[0]}")

        async def go():
            try:
                await brd.fetch_account_info()
                print(f"   acc#={brd.account_number}, seq={brd.sequence}")
            except Exception as e:
                print(f"   ⚠️  账户查询失败: {e}")

            try:
                result = await brd.broadcast_wasm_execute(
                    args.contract,
                    execute_msg,
                    gas=args.gas,
                    memo=f"INJ Copyright {record['copyright_id']}",
                )
            except Exception as e:
                print(f"   ❌ 广播异常: {e}")
                return

            if result.get("success"):
                print(f"   ✅ 广播成功")
                print(f"   TXHASH   : {result['txhash']}")
                print(f"   RAWLOG   : {result.get('rawlog','')[:200]}")
                if "height" in result:
                    print(f"   HEIGHT   : {result['height']}")
                    print(f"   GAS_USED : {result.get('gas_used')} / {result.get('gas_wanted')}")
                else:
                    print(f"   (交易仍在 mempool，稍后在浏览器核对: {result['txhash']})")
                explorer_base = "https://testnet.explorer.injective.network" if mode == "testnet" \
                    else "https://explorer.injective.network"
                print(f"   浏览器   : {explorer_base}/transaction/{result['txhash']}")
            else:
                print(f"   ❌ 广播失败")
                print(json.dumps(result, indent=2, ensure_ascii=False))

        asyncio.run(go())

    # 保存存证记录 JSON 便于后续 verify / list
    output_json = args.output + ".record.json"
    with open(output_json, "w") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    print(f"\n💾 存证数据已保存: {output_json}")
    print(f"\n✅ 完成！你可以使用以下命令验证:")
    print(f"   python cli.py verify --img {args.output} "
          f"--copyright-id {record['copyright_id']} --mode {mode}")


def cmd_extract(args):
    wm = WatermarkService()
    if not os.path.exists(args.img):
        print(f"❌ 图片不存在: {args.img}")
        sys.exit(1)
    if args.bit_length <= 0:
        print("❌ --bit-length 必须 > 0 (即 register 时输出的 wm_bit_length)")
        sys.exit(1)
    cid = wm.extract_copyright_id(args.img, args.bit_length)
    print(f"🖼️  图片 : {args.img}")
    print(f"🔍 提取 : {cid}")


def cmd_query(args):
    mode = args.mode or "local"
    print(f"🔎 查询版权 ID: {args.copyright_id} (mode={mode})")
    if mode == "local":
        chain = ChainService(mode="local")
        rec = chain.query_record(args.copyright_id)
        if rec:
            print(json.dumps(rec, indent=2, ensure_ascii=False))
        else:
            print("❌ 本地模拟链未找到该版权 ID (请用 register 先注册)")
    else:
        if not args.contract:
            print("❌ 真实链查询需要 --contract <合约地址>")
            sys.exit(1)
        brd = InjectiveBroadcaster(mode)

        async def go():
            msg = {"get_copyright": {"copyright_id": args.copyright_id}}
            data = await brd.query_wasm_smart(args.contract, msg)
            if data is None:
                print("   ❌ 查询为空 (未注册 / 合约不存在 / 网络问题)")
            else:
                print(json.dumps(data, indent=2, ensure_ascii=False))
        asyncio.run(go())


def cmd_verify(args):
    if not os.path.exists(args.img):
        print(f"❌ 图片不存在: {args.img}")
        sys.exit(1)
    mode = args.mode or "local"
    print(f"✅ 版权验证 (mode={mode})")
    print(f"   图片     : {args.img}")
    print(f"   版权 ID  : {args.copyright_id}")

    # 1. 取链上记录
    record = None
    if mode == "local":
        chain = ChainService(mode="local")
        record = chain.query_record(args.copyright_id)
    else:
        if not args.contract:
            print("❌ 真实链需要 --contract")
            sys.exit(1)
        brd = InjectiveBroadcaster(mode)

        async def q():
            msg = {"get_copyright": {"copyright_id": args.copyright_id}}
            return await brd.query_wasm_smart(args.contract, msg)
        record = asyncio.run(q())

    if not record:
        print("   ❌ 链上找不到该版权 ID 记录")
        sys.exit(1)

    # 2. 水印验证
    wm = WatermarkService()
    ok, detail = wm.verify_ownership(args.img, record)
    print("   " + detail.replace("\n", "\n   "))
    sys.exit(0 if ok else 2)


def cmd_list(args):
    mode = args.mode or "local"
    if mode != "local":
        print("ℹ️  list 仅支持 mode=local，真实链请使用 query + list_by_owner 合约接口")
        return
    chain = ChainService(mode="local")
    rows = chain.list_records()
    if not rows:
        print("(空)")
        return
    print(f"共 {len(rows)} 条存证:\n")
    for i, r in enumerate(rows, 1):
        t = __import__('time').strftime("%Y-%m-%d %H:%M:%S",
                                         __import__('time').localtime(r['stored_at']))
        print(f"[{i}] {r['copyright_id']}")
        print(f"    所有者  : {r['owner']}")
        print(f"    标题    : {r['title']}")
        print(f"    区块    : {r['block']}    时间: {t}")
        print(f"    TXHASH  : {r['tx_hash']}")
        print()


def build_parser():
    p = argparse.ArgumentParser(prog="cli.py", description="INJ 盲水印 + 链上版权存证 CLI")
    sub = p.add_subparsers(dest="command", required=True)

    # register
    pr = sub.add_parser("register", help="嵌入水印并上链存证")
    pr.add_argument("--img", required=True, help="原图路径")
    pr.add_argument("--output", required=True, help="带水印图片输出路径")
    pr.add_argument("--owner", required=True, help="版权所有者 inj1... 地址")
    pr.add_argument("--mode", default="local", choices=["local", "testnet", "mainnet"],
                    help="local=模拟, testnet/mainnet=真实链 (默认 local)")
    pr.add_argument("--contract", default=None, help="真实链模式下的 CosmWasm 合约地址")
    pr.add_argument("--mnemonic", default=None, help="真实链签名用助记词 (空格分隔)")
    pr.add_argument("--privkey-hex", default=None, help="真实链签名用 HEX 私钥 (与 mnemonic 二选一)")
    pr.add_argument("--title", default=None, help="作品标题 (元数据)")
    pr.add_argument("--author", default=None, help="作者 (元数据)")
    pr.add_argument("--license", default=None, help="授权协议 (元数据)")
    pr.add_argument("--extra-meta", default=None, help='额外元数据 (JSON 字符串)，例如 \'{"tags":["a","b"]}\'')
    pr.add_argument("--gas", type=int, default=400_000, help="真实链广播 gas 上限 (默认 400000)")
    pr.set_defaults(func=cmd_register)

    # extract
    pe = sub.add_parser("extract", help="从水印图提取版权 ID")
    pe.add_argument("--img", required=True, help="水印图路径")
    pe.add_argument("--bit-length", type=int, required=True,
                    help="水印 bit 长度 (register 时输出的 wm_bit_length)")
    pe.set_defaults(func=cmd_extract)

    # query
    pq = sub.add_parser("query", help="查询链上版权记录")
    pq.add_argument("--copyright-id", required=True)
    pq.add_argument("--mode", default="local", choices=["local", "testnet", "mainnet"])
    pq.add_argument("--contract", default=None)
    pq.set_defaults(func=cmd_query)

    # verify
    pv = sub.add_parser("verify", help="提取水印并与链上记录比对")
    pv.add_argument("--img", required=True)
    pv.add_argument("--copyright-id", required=True)
    pv.add_argument("--mode", default="local", choices=["local", "testnet", "mainnet"])
    pv.add_argument("--contract", default=None)
    pv.set_defaults(func=cmd_verify)

    # list
    pl = sub.add_parser("list", help="列出本地模拟链所有存证")
    pl.add_argument("--mode", default="local", choices=["local"])
    pl.set_defaults(func=cmd_list)

    return p


def main():
    banner()
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
