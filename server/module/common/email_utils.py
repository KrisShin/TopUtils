# email_service.py
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from typing import List

# 从 settings.py 导入配置
from server.config import settings

# 创建一个 ConnectionConfig 对象
conf = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_FROM,  # 发件人邮箱地址
    MAIL_PASSWORD=settings.MAIL_SECRET,
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_FROM_NAME=settings.MAIL_FROMNAME,  # 发件人邮箱地址
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_STARTTLS=settings.MAIL_STARTTLS,
    MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True,
)


async def send_email(email: List[str], subject: str, body: str):
    """
    发送邮件的通用函数。

    Args:
        recipients (List[str]): 收件人邮箱列表。
        subject (str): 邮件主题。
        body (str): 邮件内容 (可以是HTML或纯文本)。
    """
    message = MessageSchema(subject=subject, recipients=[email], body=body, subtype="html")  # 收件人列表  # 或者 "plain"

    fm = FastMail(conf)
    try:
        await fm.send_message(message)
        print(f"邮件已成功发送至: {email}")
        return True
    except Exception as e:
        print(f"邮件发送失败: {e}")
        return False
