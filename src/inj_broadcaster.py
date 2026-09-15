"""
Injective 链上真实广播服务
使用 cosmospy + httpx 完成:
  - 构建 MsgExecuteContract
  - 签名 (secp256k1, amino-json 兼容 Cosmos SDK)
  - 通过 LCD REST (sync/async) 广播
  - 查询交易回执 & 合约状态

注：injective-py SDK 接口版本众多，这里直接用底层通用方式，兼容性最强。
"""
import hashlib
import json
import base64
import time
import os
from typing import Optional, Dict, Any, Tuple, List

from bech32 import bech32_encode, convertbits
import ecdsa
import httpx


# ========== 加密工具 ==========

def mnemonic_to_private_key(mnemonic: str) -> bytes:
    """BIP-39/44 简化：直接从 mnemonic seed 派生出 secp256k1 私钥
    (使用 hdwallets + mnemonic 库，它们在 injective-py 依赖链中)
    """
    import mnemonic as mnemo
    from hdwallets import BIP32
    if not mnemo.Mnemonic('english').check(mnemonic):
        raise ValueError("助记词校验失败")
    seed = mnemo.Mnemonic.to_seed(mnemonic, passphrase='')
    bip32 = BIP32.from_seed(seed)
    # Cosmos 标准路径: m/44'/118'/0'/0/0 (Injective 兼容)
    child = bip32.get_child_for_path("m/44'/118'/0'/0/0")
    return child.private_key


def privkey_to_inj_address(privkey_bytes: bytes) -> str:
    """secp256k1 私钥 -> inj1... bech32 地址"""
    from ecdsa import SigningKey, SECP256k1
    sk = SigningKey.from_string(privkey_bytes, curve=SECP256k1)
    vk = sk.get_verifying_key()
    pub_bytes = vk.to_string()  # 64 bytes (uncompressed, no prefix)
    # Cosmos 取 sha256 → ripemd160 的前 20 bytes 当地址
    sha = hashlib.sha256(pub_bytes).digest()
    # ripemd160 via hashlib.new
    rip = hashlib.new('ripemd160')
    rip.update(sha)
    raw20 = rip.digest()
    # bech32 编码: 5 bits per char
    bits = convertbits(list(raw20), 8, 5, True)
    return bech32_encode('inj', bits)


# ========== LCD 配置 ==========

NETWORKS = {
    "testnet": {
        "chain_id": "injective-888",
        "lcd": "https://testnet.lcd.injective.network",
        "denom": "inj",
        "gas_price": "500000000",  # 0.5 inj per gas-unit equivalent
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
    Injective 链通用广播器
    用法:
        brd = InjectiveBroadcaster("testnet")
        brd.from_mnemonic("dove topple ... tomato")
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

    # -------- 签名 --------
    def _sign_bytes(self, tx_bytes: bytes) -> bytes:
        from ecdsa import SigningKey, SECP256k1
        from ecdsa.util import sigencode_string_canonize
        sk = SigningKey.from_string(self.privkey, curve=SECP256k1, hashfunc=hashlib.sha256)
        # Cosmos 要求 SHA256 + DER/Compact 签名。用 compact (73 bytes 兼容):
        sig = sk.sign_digest_deterministic(
            hashlib.sha256(tx_bytes).digest(),
            sigencode=sigencode_string_canonize,
            hashfunc=hashlib.sha256,
        )
        return sig

    # -------- 构建 + 广播交易 --------
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
        :returns: {"txhash": ..., "rawlog": ..., "height": ...(if confirmed)}
        """
        if self.privkey is None:
            raise RuntimeError("请先调用 from_mnemonic 或 from_private_key_hex 初始化钱包")
        if self.account_number is None:
            await self.fetch_account_info()

        sender = self.address
        msg_bytes = json.dumps(execute_msg, separators=(',', ':'), sort_keys=True).encode()
        msg_b64 = base64.b64encode(msg_bytes).decode()

        msgs = [{
            "@type": "/cosmwasm.wasm.v1.MsgExecuteContract",
            "sender": sender,
            "contract": contract_addr,
            "msg": msg_b64,
            "funds": funds or [],
        }]

        fee = {
            "amount": [{"denom": self.cfg["denom"],
                        "amount": str(int(self.cfg["gas_price"]) * gas)}],
            "gas_limit": str(gas),
            "payer": "",
            "granter": "",
        }

        # 构造签名用 SignDoc (protobuf 等价 JSON)
        sign_doc = {
            "chain_id": self.cfg["chain_id"],
            "account_number": str(self.account_number),
            "sequence": str(self.sequence),
            "auth_info_bytes": base64.b64encode(json.dumps({
                "signer_infos": [{
                    "public_key": {
                        "@type": "/cosmos.crypto.secp256k1.PubKey",
                        # pubkey will be serialized below
                        "key": base64.b64encode(self._pubkey_bytes()).decode(),
                    },
                    "mode_info": {"single": {"mode": "SIGN_MODE_DIRECT"}},
                    "sequence": str(self.sequence),
                }],
                "fee": {
                    **fee,
                    "granter": "",
                    "payer": "",
                },
                "tip": None,
            }, separators=(',', ':')).encode()).decode(),
            "tx_body_bytes": base64.b64encode(json.dumps({
                "messages": msgs,
                "memo": memo,
                "timeout_height": "0",
                "extension_options": [],
                "non_critical_extension_options": [],
            }, separators=(',', ':')).encode()).decode(),
        }

        # SIGN_MODE_DIRECT 签名: sign sha256( auth_info || tx_body )
        auth_info_raw = base64.b64decode(sign_doc["auth_info_bytes"])
        tx_body_raw = base64.b64decode(sign_doc["tx_body_bytes"])
        sign_bytes = hashlib.sha256(auth_info_raw + tx_body_raw).digest()

        from ecdsa import SigningKey, SECP256k1
        from ecdsa.util import sigencode_string_canonize
        sk = SigningKey.from_string(self.privkey, curve=SECP256k1, hashfunc=hashlib.sha256)
        signature = sk.sign_digest_deterministic(
            sign_bytes,
            sigencode=sigencode_string_canonize,
            hashfunc=hashlib.sha256,
        )
        sig_b64 = base64.b64encode(signature).decode()

        tx_raw = {
            "tx_bytes": base64.b64encode(json.dumps({
                "body": {
                    "messages": msgs,
                    "memo": memo,
                    "timeout_height": "0",
                    "extension_options": [],
                    "non_critical_extension_options": [],
                },
                "auth_info": {
                    "signer_infos": [{
                        "public_key": {
                            "@type": "/cosmos.crypto.secp256k1.PubKey",
                            "key": base64.b64encode(self._pubkey_bytes()).decode(),
                        },
                        "mode_info": {"single": {"mode": "SIGN_MODE_DIRECT"}},
                        "sequence": str(self.sequence),
                    }],
                    "fee": fee,
                    "tip": None,
                },
                "signatures": [sig_b64],
            }, separators=(',', ':')).encode()).decode(),
            "mode": "BROADCAST_MODE_SYNC",
        }

        url = f"{self.cfg['lcd']}/cosmos/tx/v1beta1/txs"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=tx_raw)
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
            self.sequence += 1
            if wait_confirm:
                confirmed = await self.query_tx(txhash)
                if confirmed:
                    result["height"] = confirmed.get("height")
                    result["gas_wanted"] = confirmed.get("gas_wanted")
                    result["gas_used"] = confirmed.get("gas_used")
                    result["code"] = confirmed.get("code")
            return result
        return {"success": False, "error": body}

    def _pubkey_bytes(self) -> bytes:
        from ecdsa import SigningKey, SECP256k1
        sk = SigningKey.from_string(self.privkey, curve=SECP256k1)
        return sk.get_verifying_key().to_string("compressed")


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
