import hmac
import hashlib
import json
import logging
import httpx
from typing import Dict, Any, Optional, List
from config import settings

logger = logging.getLogger("tripay_service")

class TriPayService:
    @staticmethod
    def generate_signature(merchant_ref: str, amount: int) -> str:
        """
        Menghasilkan signature HMAC-SHA256 untuk closed payment:
        Formula: HMAC-SHA256(merchant_code + merchant_ref + amount, private_key)
        """
        message = f"{settings.TRIPAY_MERCHANT_CODE}{merchant_ref}{int(amount)}"
        return hmac.new(
            bytes(settings.TRIPAY_PRIVATE_KEY, "latin-1"),
            bytes(message, "latin-1"),
            hashlib.sha256
        ).hexdigest()

    @staticmethod
    def verify_callback_signature(raw_body: bytes, incoming_signature: str) -> bool:
        """
        Memvalidasi keaslian signature webhook callback dari TriPay:
        Formula: HMAC-SHA256(raw_body, private_key)
        """
        if not incoming_signature:
            return False
        calculated = hmac.new(
            bytes(settings.TRIPAY_PRIVATE_KEY, "latin-1"),
            raw_body,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(calculated, incoming_signature)

    @classmethod
    async def get_payment_channels(cls) -> Dict[str, Any]:
        """Mengambil daftar saluran pembayaran aktif dari TriPay."""
        endpoint = f"{settings.TRIPAY_BASE_URL}/merchant/payment-channel"
        headers = {
            "Authorization": f"Bearer {settings.TRIPAY_API_KEY}"
        }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                res = await client.get(endpoint, headers=headers)
                return res.json()
        except Exception as e:
            logger.error(f"Gagal mengambil payment channels TriPay: {e}")
            return {"success": False, "message": str(e), "data": []}

    @classmethod
    async def create_closed_transaction(
        cls,
        method: str,
        merchant_ref: str,
        amount: int,
        customer_name: str,
        customer_email: str,
        customer_phone: str,
        order_items: List[Dict[str, Any]],
        callback_url: Optional[str] = None,
        return_url: Optional[str] = None,
        expired_time: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Membuat transaksi closed payment baru di TriPay.
        """
        signature = cls.generate_signature(merchant_ref, amount)
        cb_url = callback_url or settings.tripay_callback_url

        clean_tripay_phone = "".join(ch for ch in str(customer_phone or "") if ch.isdigit())
        if clean_tripay_phone.startswith("08"):
            clean_tripay_phone = "62" + clean_tripay_phone[1:]
        elif not clean_tripay_phone.startswith("62") and clean_tripay_phone:
            clean_tripay_phone = "62" + clean_tripay_phone
        if not clean_tripay_phone:
            clean_tripay_phone = "628123456789"

        payload = {
            "method": method,
            "merchant_ref": merchant_ref,
            "amount": int(amount),
            "customer_name": customer_name,
            "customer_email": customer_email,
            "customer_phone": clean_tripay_phone,
            "order_items": order_items,
            "callback_url": cb_url,
            "signature": signature
        }

        if return_url:
            payload["return_url"] = return_url
        if expired_time:
            payload["expired_time"] = int(expired_time)

        endpoint = f"{settings.TRIPAY_BASE_URL}/transaction/create"
        headers = {
            "Authorization": f"Bearer {settings.TRIPAY_API_KEY}",
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                res = await client.post(endpoint, json=payload, headers=headers)
                data = res.json()
                logger.info(f"TriPay create transaction status {res.status_code}: {data.get('message', '')}")
                return data
        except Exception as e:
            logger.error(f"Exception saat create transaction TriPay: {e}")
            return {"success": False, "message": str(e)}

    @classmethod
    async def get_transaction_detail(cls, reference: str) -> Dict[str, Any]:
        """Mengambil detail dan status transaksi dari TriPay."""
        endpoint = f"{settings.TRIPAY_BASE_URL}/transaction/detail"
        headers = {
            "Authorization": f"Bearer {settings.TRIPAY_API_KEY}"
        }
        params = {"reference": reference}
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                res = await client.get(endpoint, params=params, headers=headers)
                return res.json()
        except Exception as e:
            logger.error(f"Gagal mengambil detail transaksi TriPay: {e}")
            return {"success": False, "message": str(e)}

    @classmethod
    async def get_payment_instruction(cls, code: str, pay_code: Optional[str] = None, amount: Optional[int] = None) -> Dict[str, Any]:
        """Mengambil tata cara pembayaran untuk channel tertentu."""
        endpoint = f"{settings.TRIPAY_BASE_URL}/payment/instruction"
        headers = {
            "Authorization": f"Bearer {settings.TRIPAY_API_KEY}"
        }
        params = {"code": code, "allow_html": 1}
        if pay_code:
            params["pay_code"] = pay_code
        if amount:
            params["amount"] = str(amount)

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                res = await client.get(endpoint, params=params, headers=headers)
                return res.json()
        except Exception as e:
            logger.error(f"Gagal mengambil instruksi bayar TriPay: {e}")
            return {"success": False, "message": str(e)}
