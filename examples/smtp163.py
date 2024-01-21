import asyncio
import os
from email.mime.text import MIMEText
from email.header import Header
import aiosmtplib
from aiosmtplib.email import formataddr

from metagpt.logs import logger


class AsyncMailer:
    def __init__(self, smtp_server="smtp.163.com", smtp_port=25):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.password = os.environ["MAIL_PASSWORD"]

    async def send(self, sender, receiver, title, content) -> None:
        message = MIMEText(content, 'plain', 'utf-8')
        message['From'] = formataddr((sender.split('@')[0], sender))  # 设置发件人昵称
        message['To'] = formataddr((receiver.split('@')[0], receiver))  # 设置收件人昵称
        # message['Message-ID'] = Header('123456789', 'utf-8')  # 设置邮件id
        message['Content-Type'] = Header('text/plain', 'utf-8')  # 设置邮件内容类型
        message['Content-Transfer-Encoding'] = Header('base64', 'utf-8')  # 设置邮件内容编码
        message['X-Priority'] = Header('3', 'utf-8')  # 设置邮件优先级
        message['X-Mailer'] = Header('Aiosmtplib', 'utf-8')  # 设置邮件客户端
        message['MIME-Version'] = Header('1.0', 'utf-8')  # 设置邮件版本
        message['X-AntiAbuse'] = Header('1', 'utf-8')  # 设置邮件防垃圾邮件
        message['Subject'] = Header(title, 'utf-8')  # 设置邮件主题

        # 异步连接邮件服务器并登录
        smtp_connection = aiosmtplib.SMTP(hostname=self.smtp_server, port=self.smtp_port, local_hostname='localhost')
        await smtp_connection.connect()
        await smtp_connection.login(sender, self.password)

        # 异步发送邮件
        await smtp_connection.sendmail(sender, receiver, message.as_string())

        # 关闭连接
        await smtp_connection.quit()
        logger.info("邮件发送成功！")




async def main():
    async_mailer = AsyncMailer()
    await async_mailer.send(os.environ["MAIL_SENDER"], os.environ["MAIL_RECEIVER"], 'Mail Test', 'Hello World!')

if __name__ == '__main__':
    # 运行示例
    asyncio.run(main())
