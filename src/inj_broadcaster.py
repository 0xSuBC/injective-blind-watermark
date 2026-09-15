"""
Injective 链上真实广播服务
完全对齐 pyinjective 官方 SDK 行为：
  - 地址派生：keccak256(uncompressed_pubkey[64B, no 04 prefix])[-20:] → bech32 inj
  - 公钥类型：injective.crypto.v1beta1.ethsecp256k1.PubKey (key 字段 = 0x04||X||Y 完整 65B)
  - 签名流程：SignDoc Protobuf(SerializeToString) → keccak_256 → ECDSA secp256k1 deterministic
  - 广播: tx_raw_bytes = TxRaw.SerializeToString(), POST /cosmos/tx/v1beta1/txs
"""
import hashlib
import json
import base64
import time
import os
from typing import Optional, Dict, Any, List

from bech32 import bech32_encode, convertbits
from Crypto.Hash import keccak as _keccak_mod
import httpx

# ========== 直接复用 pyinjective 官方生成的 pb2 类（保证 100% 与链兼容） ==========
from google.protobuf import any_pb2
from pyinjective.proto.cosmos.base.v1beta1.coin_pb2 import Coin
from pyinjective.proto.cosmos.tx.signing.v1beta1 import signing_pb2 as _tx_sign
from pyinjective.proto.cosmos.tx.v1beta1 import tx_pb2 as _cosmos_tx
from pyinjective.proto.injective.crypto.v1beta1.ethsecp256k1.keys_pb2 import PubKey as EthSecp256k1PubKey

SIGN_MODE_DIRECT = _tx_sign.SIGN_MODE_DIRECT


def _keccak256(data: bytes) -> bytes:
    kh = _keccak_mod.new(digest_bits=256)
    kh.update(data)
    return kh.digest()


# ========== 加密工具（与 pyinjective.wallet 逐行对齐） ==========

def mnemonic_to_private_key(mnemonic: str) -> bytes:
    """BIP-39/44: 从 mnemonic 派生出 secp256k1 私钥，使用 pyinjective 官方实现"""
    from pyinjective.wallet import PrivateKey as _Priv
    official_pk = _Priv.from_mnemonic(mnemonic)
    # PrivateKey 没有直接暴露 bytes，但能从 hex 还原
    return bytes.fromhex(official_pk.to_hex())


def privkey_to_inj_address(privkey_bytes: bytes) -> str:
    """secp256k1 私钥 → inj1... bech32 地址
    与 pyinjective PublicKey.to_address 完全一致：
      pubkey = vk.to_string("uncompressed")  # 65 bytes (04||X||Y)
      raw20 = keccak256(pubkey[1:])[12:]  # 去掉 04 前缀的 64B → keccak256 → 末 20B
    """
    from ecdsa import SigningKey, SECP256k1
    sk = SigningKey.from_string(privkey_bytes, curve=SECP256k1, hashfunc=hashlib.sha256)
    vk = sk.get_verifying_key()
    pubkey_65B = vk.to_string("uncompressed")  # 04 || X || Y
    raw20 = _keccak256(pubkey_65B[1:])[12:]
    bits = convertbits(list(raw20), 8, 5, True)
    return bech32_encode('inj', bits)


def _pubkey_to_ethsecp_proto_bytes(privkey_bytes: bytes) -> bytes:
    """私钥 → EthSecp256k1PubKey.SerializeToString()
    key 字段 = 完整 uncompressed 65-byte pubkey (0x04 prefix)
    """
    from ecdsa import SigningKey, SECP256k1
    sk = SigningKey.from_string(privkey_bytes, curve=SECP256k1, hashfunc=hashlib.sha256)
    vk = sk.get_verifying_key()
    pubkey_65B = vk.to_string("uncompressed")
    return EthSecp256k1PubKey(key=pubkey_65B).SerializeToString()


def _sign_with_private_key(privkey_bytes: bytes, msg: bytes) -> bytes:
    """对齐 pyinjective PrivateKey.sign(): 使用官方 SDK 的签名流程，100% 兼容"""
    from pyinjective.wallet import PrivateKey as _OfficialPriv
    hex_key = privkey_bytes.hex()
    official_pk = _OfficialPriv.from_hex(hex_key)
    return official_pk.sign(msg)


# ========== LCD 配置 ==========

NETWORKS = {
    "testnet": {
        "chain_id": "injective-888",
        "lcd": "https://k8s.testnet.lcd.injective.network",
        "denom": "inj",
        "gas_price": "500000000",
        "faucet": "https://testnet.faucet.injective.network",
    },
    "mainnet": {
        "chain_id": "injective-1",
        "lcd": "https://lcd.injective.network",
        "denom": "inj",
        "gas_price": "500000000",
    },
}


class InjectiveBroadcaster:
    """
    Injective 链通用广播器（完全对齐 pyinjective 官方 SDK 的 Protobuf + 签名语义）
    用法:
        brd = InjectiveBroadcaster("testnet")
        brd.from_mnemonic("<你的 12 词 BIP-39 助记词>")
        txhash = brd.broadcast_wasm_execute(contract_addr, {"register_copyright": {...}})
    """

    def __init__(self, network: str = "testnet"):
        self.network = network
        self.cfg = NETWORKS[network]
        self.privkey: Optional[bytes] = None
        self.address: Optional[str] = None
        self.account_number: Optional[int] = None
        self.sequence: Optional[int] = None

    # -------- 初始化钱包 --------
    def from_mnemonic(self, mnemonic: str) -> str:
        self.privkey = mnemonic_to_private_key(mnemonic)
        self.address = privkey_to_inj_address(self.privkey)
        return self.address

    def from_private_key_hex(self, privkey_hex: str) -> str:
        self.privkey = bytes.fromhex(privkey_hex)
        self.address = privkey_to_inj_address(self.privkey)
        return self.address

    # -------- 链上查询 --------
    async def fetch_account_info(self):
        """从链上获取 account_number / sequence"""
        url = f"{self.cfg['lcd']}/cosmos/auth/v1beta1/accounts/{self.address}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
            data = resp.json()
        info = data.get("account", data)
        if "base_account" in info:
            info = info["base_account"]
        self.account_number = int(info.get("account_number", 0))
        self.sequence = int(info.get("sequence", 0))
        return self.account_number, self.sequence

    async def query_balance(self, address: Optional[str] = None) -> List[Dict[str, Any]]:
        addr = address or self.address
        url = f"{self.cfg['lcd']}/cosmos/bank/v1beta1/balances/{addr}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
            data = resp.json()
        return data.get("balances", [])

    async def query_wasm_smart(self, contract_addr: str, query_msg: Dict[str, Any]) -> Optional[Any]:
        query_b64 = base64.b64encode(
            json.dumps(query_msg, separators=(',', ':'), sort_keys=True).encode()
        ).decode()
        url = f"{self.cfg['lcd']}/cosmwasm/wasm/v1/contract/{contract_addr}/smart/{query_b64}"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    return resp.json().get("data")
            return None
        except Exception:
            return None

    async def query_tx(self, txhash: str, timeout_sec: int = 30) -> Optional[Dict[str, Any]]:
        """轮询查询交易，直到被打包或超时"""
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            url = f"{self.cfg['lcd']}/cosmos/tx/v1beta1/txs/{txhash.upper()}"
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url)
            if resp.status_code == 200:
                tx = resp.json().get("tx_response")
                if tx and tx.get("height") and int(tx["height"]) > 0:
                    return tx
            await __import__('asyncio').sleep(1.5)
        return None

    # -------- 构建 + 广播交易（完全对齐 pyinjective Transaction + broadcaster） --------
    async def broadcast_wasm_execute(
        self,
        contract_addr: str,
        execute_msg: Dict[str, Any],
        funds: Optional[List[Dict[str, str]]] = None,
        gas: int = 300_000,
        memo: str = "",
        wait_confirm: bool = True,
    ) -> Dict[str, Any]:
        """
        广播 MsgExecuteContract
        :returns: {"success": True/False, "txhash": ..., ...}
        """
        if self.privkey is None:
            raise RuntimeError("请先调用 from_mnemonic 或 from_private_key_hex 初始化钱包")
        if self.account_number is None:
            await self.fetch_account_info()

        sender = self.address

        # 1) 构建 MsgExecuteContract CosmWasm msg（bytes）
        msg_json_bytes = json.dumps(
            execute_msg, separators=(',', ':'), sort_keys=True, ensure_ascii=False
        ).encode('utf-8')

        # 使用 google.protobuf.message.Message + Pack 机制，但因为 pyinjective 未必包含 cosmwasm pb2，
        # 我们直接按 protobuf 语义手动构造 Any: type_url + SerializeToString()
        # cosmwasm.wasm.v1.MsgExecuteContract 的字段定义:
        #   string sender = 1; string contract = 2; bytes msg = 3; repeated Coin funds = 5;
        from pyinjective.proto.cosmwasm.wasm.v1 import tx_pb2 as _cw_tx
        exec_pb = _cw_tx.MsgExecuteContract(
            sender=sender,
            contract=contract_addr,
            msg=msg_json_bytes,
            funds=[Coin(denom=f["denom"], amount=f["amount"]) for f in (funds or [])],
        )

        # 2) 把 msg 包成 google.protobuf.Any（与 official Transaction.__convert_msgs 一致）
        msg_any = any_pb2.Any()
        msg_any.Pack(exec_pb, type_url_prefix="")

        # 3) 构建 Coin list (fee)
        fee_denom = self.cfg["denom"]
        fee_amount = int(self.cfg["gas_price"]) * gas
        fee_coins = [Coin(denom=fee_denom, amount=str(fee_amount))]

        # 4) 构建 EthSecp256k1 PubKey Any
        pubkey_proto_bytes = _pubkey_to_ethsecp_proto_bytes(self.privkey)
        pubkey_any = any_pb2.Any()
        # type_url 必须与 Pack 时的行为一致: full_name 无斜杠前缀 → Pack("", full) → "/{full_name}"
        pubkey_any.type_url = "/" + EthSecp256k1PubKey.DESCRIPTOR.full_name
        pubkey_any.value = pubkey_proto_bytes

        # 5) 构建 ModeInfo/SignerInfo/AuthInfo + Fee + TxBody (同 official transaction.py __generate_info)
        tx_body = _cosmos_tx.TxBody(
            messages=[msg_any],
            memo=memo,
            timeout_height=0,
        )
        body_bytes = tx_body.SerializeToString()

        mode_info = _cosmos_tx.ModeInfo(
            single=_cosmos_tx.ModeInfo.Single(mode=SIGN_MODE_DIRECT)
        )
        signer_info = _cosmos_tx.SignerInfo(
            public_key=pubkey_any,
            mode_info=mode_info,
            sequence=int(self.sequence or 0),
        )
        fee_pb = _cosmos_tx.Fee(amount=fee_coins, gas_limit=gas)
        auth_info = _cosmos_tx.AuthInfo(signer_infos=[signer_info], fee=fee_pb)
        auth_info_bytes = auth_info.SerializeToString()

        # 6) SignDoc = {body_bytes, auth_info_bytes, chain_id, account_number}
        #    同 official Transaction.get_sign_doc
        sign_doc = _cosmos_tx.SignDoc(
            body_bytes=body_bytes,
            auth_info_bytes=auth_info_bytes,
            chain_id=self.cfg["chain_id"],
            account_number=int(self.account_number or 0),
        )
        sign_doc_bytes = sign_doc.SerializeToString()

        # 7) 对齐 pyinjective.broadcaster L386:
        #    sig = private_key.sign(sign_doc.SerializeToString())
        signature = _sign_with_private_key(self.privkey, sign_doc_bytes)

        # 8) TxRaw = {body_bytes, auth_info_bytes, [signature]}
        #    同 official Transaction.get_tx_data
        tx_raw = _cosmos_tx.TxRaw(
            body_bytes=body_bytes,
            auth_info_bytes=auth_info_bytes,
            signatures=[signature],
        )
        tx_raw_bytes = tx_raw.SerializeToString()
        tx_b64 = base64.b64encode(tx_raw_bytes).decode()

        # 9) POST 到 LCD txs 端点（sync mode）
        url = f"{self.cfg['lcd']}/cosmos/tx/v1beta1/txs"
        req_body = {"tx_bytes": tx_b64, "mode": "BROADCAST_MODE_SYNC"}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=req_body)
            body = resp.json()

        if "tx_response" in body:
            txresp = body["tx_response"]
            txhash = txresp["txhash"]
            code = int(txresp.get("code", 0))
            if code != 0:
                return {"success": False, "code": code, "rawlog": txresp.get("raw_log", ""),
                        "txhash": txhash}
            result = {"success": True, "txhash": txhash, "rawlog": txresp.get("raw_log", "")}
            # 自增 sequence，连续广播不回查
            self.sequence = (self.sequence or 0) + 1
            if wait_confirm:
                confirmed = await self.query_tx(txhash)
                if confirmed:
                    result["height"] = confirmed.get("height")
                    result["gas_wanted"] = confirmed.get("gas_wanted")
                    result["gas_used"] = confirmed.get("gas_used")
                    result["code"] = confirmed.get("code")
            return result
        return {"success": False, "error": body}


# 便捷函数: 导出合约接口给上层用
def build_register_msg(record: dict) -> dict:
    from src.chain_service import CopyrightRecord
    meta = record.get("metadata", {})
    meta_json = json.dumps(meta, sort_keys=True, ensure_ascii=False)
    metadata_b64 = base64.b64encode(meta_json.encode()).decode() if meta_json and meta_json != "{}" else None
    msg = {
        "register_copyright": {
            "copyright_id": record["copyright_id"],
            "owner": record["owner"],
            "original_hash": record["original_hash"],
            "watermarked_hash": record["watermarked_hash"],
            "wm_bit_length": record["wm_bit_length"],
            "record_hash": CopyrightRecord.compute_record_hash(record),
        }
    }
    if metadata_b64:
        msg["register_copyright"]["metadata"] = metadata_b64
    return msg
