"""
水印服务模块 - 封装 blind_watermark，面向版权存证场景
"""
import hashlib
import json
import os
import tempfile
import time
from typing import Tuple, Optional, Dict, Any

import numpy as np
import cv2

from blind_watermark import WaterMark


class WatermarkService:
    """水印服务：嵌入/提取版权水印，生成存证数据"""

    MIN_IMAGE_SIZE = (1000, 1000)

    def __init__(self, password_wm: int = 20240908, password_img: int = 99887766):
        self.password_wm = password_wm
        self.password_img = password_img

    @staticmethod
    def compute_file_hash(file_path: str) -> str:
        h = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def compute_text_hash(text: str) -> str:
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    @staticmethod
    def generate_copyright_id(owner_address: str, original_hash: str) -> str:
        short_owner = owner_address[4:12] if len(owner_address) > 12 else owner_address[:8]
        short_hash = original_hash[:16]
        return f"INJ-CPR-{short_owner}-{short_hash}"

    def _ensure_large_image(self, img_path: str) -> Tuple[str, bool]:
        """
        如果图片小于最小尺寸，则放大。返回 (处理后路径, 是否被放大)
        original_hash 仍用原图计算，仅嵌入时使用放大版本
        """
        img = cv2.imread(img_path)
        if img is None:
            raise IOError(f"无法读取图片: {img_path}")
        h, w = img.shape[:2]
        min_h, min_w = self.MIN_IMAGE_SIZE
        if h >= min_h and w >= min_w:
            return img_path, False
        scale = max(min_h / h, min_w / w, 1.0)
        new_h, new_w = int(h * scale), int(w * scale)
        resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
        tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        tmp.close()
        cv2.imwrite(tmp.name, resized)
        return tmp.name, True

    def embed_copyright(
        self,
        original_img_path: str,
        output_img_path: str,
        owner_address: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not os.path.exists(original_img_path):
            raise FileNotFoundError(f"原图不存在: {original_img_path}")

        original_hash = self.compute_file_hash(original_img_path)
        copyright_id = self.generate_copyright_id(owner_address, original_hash)

        embed_src, was_resized = self._ensure_large_image(original_img_path)

        bwm = WaterMark(password_wm=self.password_wm, password_img=self.password_img)
        bwm.bwm_core.d1, bwm.bwm_core.d2 = 50, 30
        bwm.read_img(embed_src)
        bwm.read_wm(copyright_id, mode='str')
        bwm.embed(output_img_path)
        wm_bit_length = len(bwm.wm_bit)

        if was_resized and embed_src != original_img_path:
            try:
                os.unlink(embed_src)
            except Exception:
                pass

        watermarked_hash = self.compute_file_hash(output_img_path)

        return {
            "copyright_id": copyright_id,
            "owner": owner_address,
            "original_hash": original_hash,
            "watermarked_hash": watermarked_hash,
            "wm_bit_length": wm_bit_length,
            "metadata": metadata or {},
            "embed_timestamp": int(time.time()),
            "embed_resized": was_resized,
        }

    def extract_copyright_id(
        self,
        watermarked_img_path: str,
        wm_bit_length: int,
    ) -> str:
        if not os.path.exists(watermarked_img_path):
            raise FileNotFoundError(f"图片不存在: {watermarked_img_path}")

        extract_src, was_resized = self._ensure_large_image(watermarked_img_path)

        bwm = WaterMark(password_wm=self.password_wm, password_img=self.password_img)
        bwm.bwm_core.d1, bwm.bwm_core.d2 = 50, 30
        try:
            result = bwm.extract(
                filename=extract_src,
                wm_shape=wm_bit_length,
                mode='str',
            )
            cleaned = result.strip('\x00').strip()
        except Exception as e:
            cleaned = f"[提取失败: {e}]"
        finally:
            if was_resized and extract_src != watermarked_img_path:
                try:
                    os.unlink(extract_src)
                except Exception:
                    pass

        return cleaned

    @staticmethod
    def _hamming_like(a: str, b: str) -> int:
        """字符级差异计数（容错匹配用）"""
        if len(a) == 0 or len(b) == 0:
            return max(len(a), len(b))
        if len(a) != len(b):
            shorter, longer = sorted([a, b], key=len)
            best = len(longer)
            for i in range(len(longer) - len(shorter) + 1):
                d = sum(1 for x, y in zip(shorter, longer[i:i + len(shorter)]) if x != y)
                best = min(best, d + (len(longer) - len(shorter)))
            return best
        return sum(1 for x, y in zip(a, b) if x != y)

    def verify_ownership(
        self,
        watermarked_img_path: str,
        chain_record: Dict[str, Any],
    ) -> Tuple[bool, str]:
        try:
            extracted = self.extract_copyright_id(
                watermarked_img_path,
                chain_record["wm_bit_length"],
            )
        except Exception as e:
            return False, f"水印提取异常: {e}"

        expected = chain_record["copyright_id"]
        exact_match = (extracted == expected)
        diff = self._hamming_like(extracted, expected)
        fuzzy_ok = (not exact_match) and (diff <= max(3, len(expected) // 8))

        if not exact_match and not fuzzy_ok:
            return False, (
                f"❌ 版权ID不匹配\n"
                f"   图片提取: {extracted}\n"
                f"   链上记录: {expected}\n"
                f"   字符差异: {diff}"
            )

        file_hash = self.compute_file_hash(watermarked_img_path)
        hash_match = file_hash == chain_record.get("watermarked_hash", "")

        if exact_match:
            wm_status = "✅ 精确匹配"
        else:
            wm_status = f"🟡 容错匹配 (差异字符: {diff}/{len(expected)})"

        status_icon = "✅" if (hash_match or fuzzy_ok) else "⚠️"
        hash_note = "" if hash_match else "（图片文件哈希与存证不一致，图片可能被编辑过）"

        # 兼容链上和本地两种字段名: 链上返回 registered_at (Timestamp, 纳秒)
        # 本地 record 里是 embed_timestamp (秒)
        ts_raw = chain_record.get("embed_timestamp") \
            or chain_record.get("registered_at") \
            or chain_record.get("created_ts") \
            or chain_record.get("timestamp") \
            or 0
        try:
            # 如果是 CosmWasm Timestamp 对象 (字典含 nanos)
            if isinstance(ts_raw, dict):
                secs = int(ts_raw.get("seconds", 0)) + int(ts_raw.get("nanos", 0)) // 1_000_000_000
            elif isinstance(ts_raw, (int, float)):
                # 大于 1e12 视为纳秒，否则秒
                secs = int(ts_raw) // 1_000_000_000 if ts_raw > 1e12 else int(ts_raw)
            else:
                secs = int(ts_raw)
        except Exception:
            secs = 0

        t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(secs)) if secs else "(未知)"

        meta = chain_record.get("metadata", {})
        # 链上 metadata 可能是 base64 字符串，这里尝试解码
        if isinstance(meta, str):
            try:
                import base64 as _b64
                meta = json.loads(_b64.b64decode(meta).decode('utf-8'))
            except Exception:
                meta = {}
        title = meta.get("title", "(未命名作品)") if isinstance(meta, dict) else "(未命名作品)"

        owner_val = chain_record.get("owner")
        if isinstance(owner_val, dict):
            owner_val = owner_val.get("addr", str(owner_val))

        return True, (
            f"{status_icon} 验证通过{hash_note}\n"
            f"   作品标题:   {title}\n"
            f"   版权 ID:    {expected}\n"
            f"   提取结果:   {extracted}\n"
            f"   水印状态:   {wm_status}\n"
            f"   所有者:      {owner_val}\n"
            f"   存证时间:    {t}\n"
            f"   元数据:      {json.dumps(meta, ensure_ascii=False)}"
        )
