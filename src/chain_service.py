"""
INJ 链上交互服务 - 本地模拟 + 真实 Injective 链 LCD 支持
"""
import json
import hashlib
import base64
import time
from typing import Optional, Dict, Any, List


class CopyrightRecord:
    @staticmethod
    def canonical_json(record: dict) -> str:
        return json.dumps(record, sort_keys=True, separators=(',', ':'), ensure_ascii=False)

    @staticmethod
    def compute_record_hash(record: dict) -> str:
        return hashlib.sha256(CopyrightRecord.canonical_json(record).encode('utf-8')).hexdigest()


class LocalChainStore:
    def __init__(self):
        self._records: Dict[str, Dict[str, Any]] = {}
        self._tx_history: List[Dict[str, Any]] = []
        self._block = 1000

    def register(self, record: dict, sender: str) -> Dict[str, Any]:
        cid = record["copyright_id"]
        if cid in self._records:
            return {"success": False, "error": f"版权ID已存在: {cid}"}

        record_hash = CopyrightRecord.compute_record_hash(record)
        self._block += 1
        tx_hash = hashlib.sha256(f"{cid}{time.time()}{sender}".encode()).hexdigest()

        stored = {
            "record": record,
            "record_hash": record_hash,
            "sender": sender,
            "tx_hash": tx_hash,
            "block_height": self._block,
            "stored_at": int(time.time()),
        }
        self._records[cid] = stored
        self._tx_history.append(stored)
        return {"success": True, **stored}

    def query(self, copyright_id: str) -> Optional[dict]:
        s = self._records.get(copyright_id)
        return s["record"] if s else None

    def query_tx(self, copyright_id: str) -> Optional[dict]:
        return self._records.get(copyright_id)

    def list_all(self) -> List[Dict[str, Any]]:
        return [
            {
                "copyright_id": cid,
                "owner": s["record"]["owner"],
                "title": s["record"].get("metadata", {}).get("title", ""),
                "block": s["block_height"],
                "stored_at": s["stored_at"],
                "tx_hash": s["tx_hash"],
            }
            for cid, s in self._records.items()
        ]


class InjectiveChainService:
    TESTNET_CONFIG = {
        "chain_id": "injective-888",
        "lcd_endpoint": "https://testnet.lcd.injective.network",
        "explorer": "https://testnet.explorer.injective.network",
        "faucet": "https://testnet.faucet.injective.network",
        "gas_price_denom": "inj",
        "gas_price_amount": "500000000",
    }

    MAINNET_CONFIG = {
        "chain_id": "injective-1",
        "lcd_endpoint": "https://lcd.injective.network",
        "explorer": "https://explorer.injective.network",
        "gas_price_denom": "inj",
        "gas_price_amount": "500000000",
    }

    def __init__(self, network: str = "testnet", contract_address: Optional[str] = None):
        self.network = network
        self.config = self.MAINNET_CONFIG if network == "mainnet" else self.TESTNET_CONFIG
        self.contract_address = contract_address

    def build_register_msg(self, record: dict) -> Dict[str, Any]:
        record_hash = CopyrightRecord.compute_record_hash(record)
        meta_json = json.dumps(record.get("metadata", {}), sort_keys=True, ensure_ascii=False)
        metadata_b64 = base64.b64encode(meta_json.encode()).decode() if meta_json and meta_json != "{}" else None

        msg = {
            "register_copyright": {
                "copyright_id": record["copyright_id"],
                "owner": record["owner"],
                "original_hash": record["original_hash"],
                "watermarked_hash": record["watermarked_hash"],
                "wm_bit_length": record["wm_bit_length"],
                "record_hash": record_hash,
            }
        }
        if metadata_b64 is not None:
            msg["register_copyright"]["metadata"] = metadata_b64
        return msg

    def build_query_msg(self, copyright_id: str) -> Dict[str, Any]:
        return {"get_copyright": {"copyright_id": copyright_id}}

    def build_list_by_owner_msg(self, owner: str, limit: int = 30, start_after: Optional[str] = None) -> Dict[str, Any]:
        return {"list_by_owner": {"owner": owner, "limit": limit, "start_after": start_after}}

    def build_transfer_msg(self, copyright_id: str, new_owner: str) -> Dict[str, Any]:
        return {"transfer_copyright": {"copyright_id": copyright_id, "new_owner": new_owner}}

    async def query_via_lcd(self, query_msg: dict) -> Optional[dict]:
        if not self.contract_address:
            raise RuntimeError("请先设置 contract_address")

        import httpx

        query_b64 = base64.b64encode(
            json.dumps(query_msg, separators=(',', ':')).encode()
        ).decode()

        url = (f"{self.config['lcd_endpoint']}/cosmwasm/wasm/v1/contract/"
               f"{self.contract_address}/smart/{query_b64}")

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("data")
            return None

    def tx_explorer_url(self, tx_hash: str) -> str:
        return f"{self.config['explorer']}/transaction/{tx_hash}"

    def address_explorer_url(self, address: str) -> str:
        return f"{self.config['explorer']}/account/{address}"

    def contract_explorer_url(self) -> str:
        return f"{self.config['explorer']}/contract/{self.contract_address}" if self.contract_address else ""


class ChainService:
    def __init__(self, mode: str = "local", contract_address: Optional[str] = None):
        self.mode = mode
        self.local = LocalChainStore() if mode == "local" else None
        self.inj = InjectiveChainService(
            network=("mainnet" if mode == "mainnet" else "testnet"),
            contract_address=contract_address,
        ) if mode != "local" else None

    def store_record(self, record: dict, sender_address: str) -> Dict[str, Any]:
        if self.mode == "local":
            return self.local.register(record, sender_address)
        else:
            msg = self.inj.build_register_msg(record)
            return {
                "success": True,
                "note": "真实链模式：请使用私钥签名并广播以下 CosmWasm ExecuteMsg",
                "contract": self.inj.contract_address,
                "network": self.inj.network,
                "chain_id": self.inj.config["chain_id"],
                "execute_msg": msg,
                "record_hash": CopyrightRecord.compute_record_hash(record),
                "sender": sender_address,
            }

    def query_record(self, copyright_id: str) -> Optional[dict]:
        if self.mode == "local":
            return self.local.query(copyright_id)
        return None

    async def query_record_async(self, copyright_id: str) -> Optional[dict]:
        if self.mode == "local":
            return self.local.query(copyright_id)
        else:
            return await self.inj.query_via_lcd(self.inj.build_query_msg(copyright_id))

    async def list_by_owner_async(self, owner: str, limit: int = 30) -> Optional[list]:
        if self.mode == "local":
            return [r for r in self.local.list_all() if r["owner"] == owner]
        else:
            return await self.inj.query_via_lcd(self.inj.build_list_by_owner_msg(owner, limit))

    def query_tx_info(self, copyright_id: str) -> Optional[dict]:
        if self.mode == "local":
            return self.local.query_tx(copyright_id)
        return None

    def list_records(self) -> List[Dict[str, Any]]:
        if self.mode == "local":
            return self.local.list_all()
        return []
