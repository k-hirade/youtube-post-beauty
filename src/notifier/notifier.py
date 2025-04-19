"""
@file: notifier.py
@desc: Slack・Emailで処理結果を通知するモジュール
"""

import os
import logging
import smtplib
import json
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Slackクライアント
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# ロガー設定
logger = logging.getLogger(__name__)

class Notifier:
    """処理結果を通知するクラス"""
    
    def __init__(
        self,
        slack_token: Optional[str] = None,
        slack_channel: Optional[str] = None,
        smtp_server: Optional[str] = None,
        smtp_port: int = 587,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        email_from: Optional[str] = None,
        email_to: Optional[List[str]] = None
    ):
        """
        初期化
        
        Args:
            slack_token: Slack APIトークン
            slack_channel: Slackチャンネル
            smtp_server: SMTPサーバー
            smtp_port: SMTPポート
            smtp_user: SMTPユーザー
            smtp_password: SMTPパスワード
            email_from: 送信元メールアドレス
            email_to: 送信先メールアドレスリスト
        """
        # Slack設定
        self.slack_token = slack_token or os.environ.get("SLACK_API_TOKEN")
        self.slack_channel = slack_channel or os.environ.get("SLACK_CHANNEL")
        self.slack_client = None
        
        if self.slack_token:
            try:
                self.slack_client = WebClient(token=self.slack_token)
                logger.info("Slack APIクライアント初期化成功")
            except Exception as e:
                logger.error(f"Slack APIクライアント初期化エラー: {str(e)}")
        
        # Email設定
        self.smtp_server = smtp_server or os.environ.get("SMTP_SERVER")
        self.smtp_port = smtp_port or int(os.environ.get("SMTP_PORT", "587"))
        self.smtp_user = smtp_user or os.environ.get("SMTP_USER")
        self.smtp_password = smtp_password or os.environ.get("SMTP_PASSWORD")
        self.email_from = email_from or os.environ.get("EMAIL_FROM")
        
        if email_to:
            self.email_to = email_to
        elif os.environ.get("EMAIL_TO"):
            self.email_to = os.environ.get("EMAIL_TO").split(",")
        else:
            self.email_to = []
    
    def send_slack_message(
        self,
        title: str,
        message: str,
        attachments: Optional[List[Dict[str, Any]]] = None,
        is_success: bool = True
    ) -> bool:
        """
        Slackメッセージ送信
        
        Args:
            title: タイトル
            message: メッセージ
            attachments: 添付情報
            is_success: 成功か失敗か
            
        Returns:
            成功したかどうか
        """
        if not self.slack_client or not self.slack_channel:
            logger.warning("Slack設定が不完全です")
            return False
        
        try:
            # カラー設定
            color = "#36a64f" if is_success else "#ff0000"
            
            # 現在時刻
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # ベースメッセージ
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{':white_check_mark:' if is_success else ':x:'} {title}"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": message
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"通知時刻: {now}"
                        }
                    ]
                }
            ]
            
            # 添付情報があれば追加
            if attachments:
                for attachment in attachments:
                    blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*{attachment.get('title', '')}*\n{attachment.get('text', '')}"
                        }
                    })
            
            # 送信
            response = self.slack_client.chat_postMessage(
                channel=self.slack_channel,
                text=title,  # フォールバック用
                blocks=blocks
            )
            
            logger.info(f"Slack通知送信成功: {title}")
            return True
            
        except SlackApiError as e:
            logger.error(f"Slack API エラー: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Slack通知送信エラー: {str(e)}")
            return False
    
    def send_email(
        self,
        subject: str,
        message: str,
        is_html: bool = False,
        is_success: bool = True
    ) -> bool:
        """
        メール送信
        
        Args:
            subject: 件名
            message: メッセージ
            is_html: HTMLメールかどうか
            is_success: 成功か失敗か
            
        Returns:
            成功したかどうか
        """
        if not all([self.smtp_server, self.smtp_user, self.smtp_password, self.email_from, self.email_to]):
            logger.warning("Email設定が不完全です")
            return False
        
        try:
            # メッセージ作成
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"{'[成功]' if is_success else '[失敗]'} {subject}"
            msg['From'] = self.email_from
            msg['To'] = ", ".join(self.email_to)
            
            # 本文設定
            content_type = 'html' if is_html else 'plain'
            msg.attach(MIMEText(message, content_type))
            
            # SMTP接続
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()  # TLS暗号化
            server.login(self.smtp_user, self.smtp_password)
            
            # 送信
            server.send_message(msg)
            server.quit()
            
            logger.info(f"メール送信成功: {subject} -> {', '.join(self.email_to)}")
            return True
            
        except Exception as e:
            logger.error(f"メール送信エラー: {str(e)}")
            return False
    
    def notify_video_created(
        self,
        title: str,
        video_path: str,
        gcs_uri: Optional[str] = None,
        products: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """
        動画作成完了通知
        
        Args:
            title: 動画タイトル
            video_path: 動画のローカルパス
            gcs_uri: GCSのURI（アップロード済みの場合）
            products: 製品情報リスト
            
        Returns:
            成功したかどうか
        """
        # 基本情報
        file_size_mb = os.path.getsize(video_path) / (1024 * 1024) if os.path.exists(video_path) else 0
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Slack用メッセージ
        slack_message = f"動画作成が完了しました！\n"
        slack_message += f"*タイトル:* {title}\n"
        slack_message += f"*ファイルサイズ:* {file_size_mb:.2f} MB\n"
        
        if gcs_uri:
            slack_message += f"*GCS URI:* `{gcs_uri}`\n"
        
        # 製品情報があれば追加
        attachments = []
        if products and len(products) > 0:
            product_text = "*ランキング製品:*\n"
            for product in products[:5]:  # 最初の5つだけ
                rank = product.get('new_rank', 0)
                product_text += f"{rank}位: {product.get('brand', '')} {product.get('name', '')}\n"
            
            if len(products) > 5:
                product_text += f"...他 {len(products) - 5} 製品"
            
            attachments.append({
                "title": "ランキング情報",
                "text": product_text
            })
        
        # Email用メッセージ
        email_subject = f"動画作成完了: {title}"
        email_message = f"""
        <h2>動画作成完了通知</h2>
        <p><strong>タイトル:</strong> {title}</p>
        <p><strong>ファイルサイズ:</strong> {file_size_mb:.2f} MB</p>
        <p><strong>作成日時:</strong> {timestamp}</p>
        """
        
        if gcs_uri:
            email_message += f"<p><strong>GCS URI:</strong> {gcs_uri}</p>"
        
        if products and len(products) > 0:
            email_message += "<h3>ランキング製品:</h3><ul>"
            for product in products:
                rank = product.get('new_rank', 0)
                email_message += f"<li>{rank}位: {product.get('brand', '')} {product.get('name', '')}</li>"
            email_message += "</ul>"
        
        # 通知送信
        slack_success = self.send_slack_message(
            title=f"動画作成完了: {title}",
            message=slack_message,
            attachments=attachments,
            is_success=True
        )
        
        email_success = self.send_email(
            subject=email_subject,
            message=email_message,
            is_html=True,
            is_success=True
        )
        
        return slack_success or email_success
    
    def notify_error(
        self,
        title: str,
        error_message: str,
        details: Optional[str] = None
    ) -> bool:
        """
        エラー通知
        
        Args:
            title: タイトル
            error_message: エラーメッセージ
            details: 詳細情報
            
        Returns:
            成功したかどうか
        """
        # Slack用メッセージ
        slack_message = f"エラーが発生しました！\n"
        slack_message += f"*エラー:* {error_message}\n"
        
        if details:
            slack_message += f"*詳細:*\n```{details}```"
        
        # Email用メッセージ
        email_subject = f"エラー発生: {title}"
        email_message = f"""
        <h2>エラー通知</h2>
        <p><strong>タイトル:</strong> {title}</p>
        <p><strong>エラー:</strong> {error_message}</p>
        """
        
        if details:
            email_message += f"<h3>詳細:</h3><pre>{details}</pre>"
        
        # 通知送信
        slack_success = self.send_slack_message(
            title=f"エラー発生: {title}",
            message=slack_message,
            is_success=False
        )
        
        email_success = self.send_email(
            subject=email_subject,
            message=email_message,
            is_html=True,
            is_success=False
        )
        
        return slack_success or email_success
