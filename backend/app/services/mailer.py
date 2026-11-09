"""发送邮件（SMTP）。

未配置 SMTP_HOST 时：开发环境只把邮件内容打印到日志（方便本地测试验证码），
正式环境直接报错，避免用户收不到验证码却以为已发送。
"""

import logging
from email.message import EmailMessage

import aiosmtplib

from app.core.config import get_settings
from app.core.errors import AppError

logger = logging.getLogger("underleaf.mail")


async def send_mail(to: str, subject: str, text: str) -> None:
    settings = get_settings()
    if not settings.smtp_host:
        if settings.app_env == "prod":
            raise AppError(503, "mail_unavailable", "邮件服务未配置，暂时无法发送验证码")
        logger.warning("【未配置 SMTP，邮件未真正发送】收件人：%s，主题：%s\n%s", to, subject, text)
        return

    message = EmailMessage()
    message["From"] = settings.smtp_from or settings.smtp_username
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text)
    try:
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username or None,
            password=settings.smtp_password or None,
            use_tls=settings.smtp_ssl,
            start_tls=not settings.smtp_ssl,
            timeout=15,
        )
    except aiosmtplib.SMTPException as e:
        logger.exception("发送邮件失败：%s", to)
        raise AppError(502, "mail_failed", "验证码发送失败，请稍后重试") from e
