import httpx
import logging
from typing import Optional
from config import settings

logger = logging.getLogger("wa_service")

class WhatsAppService:
    @staticmethod
    def format_target(to_phone: str) -> str:
        """
        Format target tujuan:
        - Jika target berupa WhatsApp LID (@lid, misal: 170020676092120@lid), pertahankan format asli JID (@lid).
        - Jika target berakhiran @s.whatsapp.net, bersihkan dan normalkan ke nomor 628xxx.
        - Jika nomor handphone (08xxx atau 628xxx), normalkan diawali 62.
        - JANGAN PERNAH mengalihkan (reroute) nomor/LID tamu ke nomor admin!
        """
        target = str(to_phone or "").strip()
        if not target:
            return ""

        # 1. Format WhatsApp LID (misal: 170020676092120@lid, 7511964934235@lid)
        if "@lid" in target:
            return target

        # 2. Format @s.whatsapp.net
        if "@s.whatsapp.net" in target:
            base_phone = target.split(":")[0].replace("@s.whatsapp.net", "").strip()
            clean_digits = "".join(ch for ch in base_phone if ch.isdigit())
            if clean_digits.startswith("08"):
                clean_digits = "62" + clean_digits[1:]
            return clean_digits or target

        # 3. Nomor telepon standar
        clean_digits = "".join(ch for ch in target if ch.isdigit())
        if clean_digits.startswith("08"):
            clean_digits = "62" + clean_digits[1:]
        elif clean_digits.startswith("8") and 9 <= len(clean_digits) <= 13:
            clean_digits = "62" + clean_digits

        if not clean_digits:
            return target

        # 4. Jika panjang digit >= 14 dan bukan nomor HP reguler (awalan 628), anggap sebagai ID LID
        if len(clean_digits) >= 14 and not clean_digits.startswith(("08", "628")):
            return f"{clean_digits}@lid"

        return clean_digits

    @classmethod
    async def send_message(cls, to_phone: str, message: str, instance_id: Optional[str] = None) -> bool:
        """
        Mengirim pesan teks balasan ke nomor tamu via endpoint WhatsApp Gateway Wuller/wa.
        Mendukung nomor telepon standar (628xxx) maupun WhatsApp LID (xxx@lid).
        """
        target_instance = instance_id or settings.WA_INSTANCE_ID
        endpoint = f"{settings.WA_GATEWAY_URL}/api/instances/{target_instance}/send"
        clean_target = cls.format_target(to_phone)
        from garda_service import GardaService
        clean_message = GardaService.sanitize_wa_text(message)

        payload = {
            "to": clean_target,
            "message": clean_message
        }

        headers = {
            "Authorization": f"Bearer {settings.WA_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(endpoint, json=payload, headers=headers)
                if res.status_code in [200, 201]:
                    logger.info(f"Pesan WA berhasil dikirim ke {clean_target} (via instance {target_instance}): {res.text}")
                    try:
                        from activity_logger import ActivityLogger
                        ActivityLogger.log_wa_outbound(to_phone=clean_target, message=clean_message, sender_type=f"Gateway {target_instance}", status="TERKIRIM")
                    except Exception:
                        pass
                    return True
                else:
                    logger.error(f"Gagal kirim pesan WA ke {clean_target} via {target_instance}, HTTP {res.status_code}: {res.text}")
                    try:
                        from activity_logger import ActivityLogger
                        ActivityLogger.log_wa_outbound(to_phone=clean_target, message=clean_message, sender_type=f"Gateway {target_instance}", status=f"GAGAL_{res.status_code}")
                    except Exception:
                        pass
                    return False
        except Exception as e:
            logger.error(f"Exception saat kirim pesan WA ke {clean_target}: {e}")
            try:
                from activity_logger import ActivityLogger
                ActivityLogger.log_wa_outbound(to_phone=clean_target, message=clean_message, sender_type=f"Gateway {target_instance}", status="EXCEPTION")
            except Exception:
                pass
            return False

    @classmethod
    async def send_media(
        cls,
        to_phone: str,
        base64_data: str,
        caption: str = "",
        filename: str = "gambar.jpg",
        mimetype: str = "image/jpeg",
        instance_id: Optional[str] = None
    ) -> bool:
        """
        Mengirim media gambar/dokumen berformat Base64 langsung ke tamu via WhatsApp Gateway.
        Menggunakan endpoint resmi /send dengan payload { to, message, media: { mimetype, filename, data } }.
        """
        target_instance = instance_id or settings.WA_INSTANCE_ID
        endpoint = f"{settings.WA_GATEWAY_URL}/api/instances/{target_instance}/send"
        clean_target = cls.format_target(to_phone)
        from garda_service import GardaService
        clean_caption = GardaService.sanitize_wa_text(caption) if caption else ""

        payload = {
            "to": clean_target,
            "message": clean_caption,
            "media": {
                "mimetype": mimetype,
                "data": base64_data,
                "filename": filename
            }
        }
        headers = {
            "Authorization": f"Bearer {settings.WA_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(endpoint, json=payload, headers=headers)
                if res.status_code in [200, 201]:
                    logger.info(f"Media gambar ({filename}, {mimetype}) berhasil dikirim ke {clean_target}")
                    try:
                        from activity_logger import ActivityLogger
                        ActivityLogger.log_wa_outbound(to_phone=clean_target, message=clean_caption or f"[Media: {filename}]", sender_type=f"Gateway {target_instance}", status="TERKIRIM")
                    except Exception:
                        pass
                    return True
                else:
                    logger.warning(f"Kirim media gagal (HTTP {res.status_code}): {res.text}")
                    try:
                        from activity_logger import ActivityLogger
                        ActivityLogger.log_wa_outbound(to_phone=clean_target, message=clean_caption or f"[Media: {filename}]", sender_type=f"Gateway {target_instance}", status=f"GAGAL_{res.status_code}")
                    except Exception:
                        pass
                    return False
        except Exception as e:
            logger.error(f"Exception saat kirim media WA ke {clean_target}: {e}")
            try:
                from activity_logger import ActivityLogger
                ActivityLogger.log_wa_outbound(to_phone=clean_target, message=clean_caption or f"[Media: {filename}]", sender_type=f"Gateway {target_instance}", status="EXCEPTION")
            except Exception:
                pass
            return False

    @classmethod
    async def send_image_url(
        cls,
        to_phone: str,
        image_url: str,
        caption: str = "",
        instance_id: Optional[str] = None,
        qr_string: Optional[str] = None,
        fallback_url: Optional[str] = None
    ) -> bool:
        """
        Mengirim tautan gambar QR Code beserta seluruh rincian pesan ke tamu via WhatsApp.
        Mengirimkan satu pesan terpadu yang 100% stabil dan langsung terkirim tanpa crash di gateway worker.
        """
        clean_caption = caption or ""
        target_link = image_url or fallback_url or ""

        if clean_caption and target_link:
            if target_link in clean_caption:
                full_msg = clean_caption
            else:
                full_msg = f"{clean_caption}\n\n🖼️ *Link Gambar QR Code:*\n{target_link}"
        elif clean_caption:
            full_msg = clean_caption
        else:
            full_msg = f"🖼️ *Link Gambar QR Code:*\n{target_link}"

        return await cls.send_message(to_phone, full_msg, instance_id=instance_id)

    @classmethod
    async def send_qris_media(
        cls,
        to_phone: str,
        qr_url: Optional[str] = None,
        qr_string: Optional[str] = None,
        checkout_url: Optional[str] = None,
        caption: str = "",
        instance_id: Optional[str] = None
    ) -> bool:
        """
        Metode khusus untuk mengirim QR Code pembayaran QRIS TriPay ke WhatsApp tamu.
        Mengirimkan gambar QR Code secara langsung via Base64 payload, dengan fallback ke tautan teks.
        """
        try:
            from qr_service import QRService
            b64_data, _, mime = await QRService.resolve_qr_media(
                qr_url=qr_url,
                qr_string=qr_string,
                fallback_url=checkout_url
            )
            if b64_data:
                media_ok = await cls.send_media(
                    to_phone=to_phone,
                    base64_data=b64_data,
                    caption=caption,
                    filename="qris.png",
                    mimetype=mime or "image/png",
                    instance_id=instance_id
                )
                if media_ok:
                    return True
        except Exception as e:
            logger.warning(f"Gagal kirim via send_media di send_qris_media: {e}")

        return await cls.send_image_url(
            to_phone=to_phone,
            image_url=qr_url or "",
            caption=caption,
            instance_id=instance_id,
            qr_string=qr_string,
            fallback_url=checkout_url
        )

    @classmethod
    async def disable_gateway_internal_bot(cls, instance_id: Optional[str] = None) -> bool:
        """
        Memastikan fitur 'gardaAutoReplyDm' bawaan gateway wa.inovasiuitjbt.uk nonaktif,
        sehingga bot internal gateway tidak mendahului / membalas pesan tamu secara terpisah
        dengan prompt generic yang menanyakan nama hotel.
        """
        target_instance = instance_id or settings.WA_INSTANCE_ID
        endpoint = f"{settings.WA_GATEWAY_URL}/api/instances/{target_instance}"
        headers = {
            "Authorization": f"Bearer {settings.WA_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {"gardaAutoReplyDm": False}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.patch(endpoint, json=payload, headers=headers)
                if res.status_code == 200:
                    logger.info(f"Berhasil menonaktifkan gardaAutoReplyDm pada instance {target_instance}")
                    return True
                else:
                    logger.warning(f"Gagal patch gardaAutoReplyDm (HTTP {res.status_code}): {res.text}")
        except Exception as e:
            logger.warning(f"Exception saat menonaktifkan gardaAutoReplyDm gateway: {e}")
        return False

