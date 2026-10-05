import os
import io
import base64
import logging
from typing import Optional, Tuple
import httpx
import qrcode
from qrcode.image.pil import PilImage

logger = logging.getLogger("qr_service")

STATIC_QR_DIR = os.path.join(os.path.dirname(__file__), "static", "qr")
os.makedirs(STATIC_QR_DIR, exist_ok=True)

class QRService:
    """
    Layanan pembuatan dan konversi QR Code lokal untuk WhatsApp & Web.
    Mendukung pembuatan gambar PNG dari EMVCo qr_string TriPay atau URL.
    """

    @classmethod
    def save_qr_locally(cls, filename: str, png_bytes: bytes) -> str:
        """Menyimpan file gambar QR code ke disk lokal server."""
        try:
            os.makedirs(STATIC_QR_DIR, exist_ok=True)
            file_path = os.path.join(STATIC_QR_DIR, filename)
            with open(file_path, "wb") as f:
                f.write(png_bytes)
            logger.info(f"QR Code berhasil disimpan di lokal: {file_path}")
            return file_path
        except Exception as e:
            logger.error(f"Gagal menyimpan QR ke lokal: {e}")
            return ""

    @staticmethod
    def generate_qr_bytes(data: str, box_size: int = 10, border: int = 2) -> bytes:
        """
        Menghasilkan byte array gambar PNG dari teks/data QRIS.
        """
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=box_size,
            border=border,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img: PilImage = qr.make_image(fill_color="black", back_color="white")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    @staticmethod
    def generate_qr_jpeg_bytes(data: str, box_size: int = 10, border: int = 2) -> bytes:
        """
        Menghasilkan byte array gambar JPEG dari teks/data QRIS (format resmi WhatsApp Media).
        """
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=box_size,
            border=border,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=95)
        return buf.getvalue()

    @classmethod
    def generate_qr_base64(cls, data: str, box_size: int = 10, border: int = 2) -> str:
        """
        Menghasilkan base64 encoded string dari gambar QR Code JPEG (siap dikirim ke WA Gateway).
        """
        jpeg_bytes = cls.generate_qr_jpeg_bytes(data, box_size=box_size, border=border)
        return base64.b64encode(jpeg_bytes).decode("utf-8")

    @classmethod
    async def resolve_qr_media(
        cls,
        qr_url: Optional[str] = None,
        qr_string: Optional[str] = None,
        fallback_url: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[bytes], str]:
        """
        Mengambil atau men-generate gambar QR berformat JPEG:
        1. Coba download dari qr_url jika tersedia, lalu konversi ke JPEG.
        2. Jika qr_url gagal / tidak ada, buat JPEG secara lokal dari qr_string.
        3. Jika qr_string adalah 'SANDBOX MODE' atau kosong, gunakan fallback_url (checkout_url).

        Return: (base64_data, jpeg_bytes, "image/jpeg")
        """
        # 1. Coba download dari URL resmi TriPay
        if qr_url and qr_url.startswith("http"):
            try:
                async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                    res = await client.get(qr_url)
                    if res.status_code == 200 and len(res.content) > 100:
                        from PIL import Image
                        im = Image.open(io.BytesIO(res.content))
                        buf = io.BytesIO()
                        im.convert("RGB").save(buf, format="JPEG", quality=95)
                        jpeg_bytes = buf.getvalue()
                        b64_data = base64.b64encode(jpeg_bytes).decode("utf-8")
                        logger.info(f"QR berhasil diunduh dan dikonversi ke JPEG ({len(jpeg_bytes)} bytes)")
                        return b64_data, jpeg_bytes, "image/jpeg"
            except Exception as e:
                logger.warning(f"Gagal download qr_url ({qr_url}): {e}. Beralih ke generator lokal.")

        # 2. Coba generate lokal dari qr_string (format resmi QRIS EMVCo)
        source_data = None
        if qr_string and qr_string.strip() and qr_string.strip() != "SANDBOX MODE":
            source_data = qr_string.strip()
        elif fallback_url and fallback_url.strip():
            source_data = fallback_url.strip()
        elif qr_url and qr_url.strip():
            source_data = qr_url.strip()

        if source_data:
            try:
                jpeg_bytes = cls.generate_qr_jpeg_bytes(source_data)
                b64_data = base64.b64encode(jpeg_bytes).decode("utf-8")
                logger.info(f"QR Code JPEG berhasil digenerate lokal dari data ({len(jpeg_bytes)} bytes)")
                return b64_data, jpeg_bytes, "image/jpeg"
            except Exception as e:
                logger.error(f"Gagal generate QR lokal: {e}")

        return None, None, "image/jpeg"
