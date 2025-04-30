"""
@file: tiktok_poster.py
@desc: TikTokに動画を投稿するためのモジュール
"""

import os
import logging
import json
import time
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime

# ロガー設定
logger = logging.getLogger(__name__)

class TikTokPoster:
    """TikTokに動画を投稿するクラス"""
    
    def __init__(
        self,
        client_key: Optional[str] = None,
        client_secret: Optional[str] = None,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None
    ):
        """
        初期化
        
        Args:
            client_key: TikTok APIのClient Key（環境変数から読み込み可能）
            client_secret: TikTok APIのClient Secret（環境変数から読み込み可能）
            access_token: TikTok APIのアクセストークン（環境変数から読み込み可能）
            refresh_token: TikTok APIのリフレッシュトークン（環境変数から読み込み可能）
        """
        # API認証情報
        self.client_key = client_key or os.environ.get("TIKTOK_CLIENT_KEY")
        self.client_secret = client_secret or os.environ.get("TIKTOK_CLIENT_SECRET")
        self.access_token = access_token or os.environ.get("TIKTOK_ACCESS_TOKEN")
        self.refresh_token = refresh_token or os.environ.get("TIKTOK_REFRESH_TOKEN")
        
        # APIエンドポイント
        self.api_base_url = "https://open.tiktokapis.com/v2"
        
        # トークンの有効期限確認
        self.check_and_refresh_token()
        
        logger.info("TikTok投稿モジュール初期化完了")
    
    def check_and_refresh_token(self) -> bool:
        """
        アクセストークンの有効期限を確認し、必要に応じて更新
        
        Returns:
            更新成功かどうか
        """
        try:
            # トークン情報がない場合は更新不要
            if not self.access_token or not self.refresh_token:
                logger.warning("TikTok APIトークンが設定されていません")
                return False
            
            # トークン情報取得エンドポイント
            url = f"{self.api_base_url}/oauth/token/info/"
            
            # リクエスト
            headers = {
                "Authorization": f"Bearer {self.access_token}"
            }
            
            response = requests.get(url, headers=headers)
            
            # レスポンスの確認
            if response.status_code == 200:
                data = response.json().get("data", {})
                
                # 残り有効期間（秒）を確認
                expires_in = data.get("expires_in", 0)
                
                # 有効期限が24時間未満の場合は更新
                if expires_in < 24 * 60 * 60:
                    logger.info(f"TikTokアクセストークンの有効期限が近いため更新します（残り{expires_in}秒）")
                    return self.refresh_access_token()
                else:
                    logger.info(f"TikTokアクセストークンは有効です（残り{expires_in}秒）")
                    return True
            
            # 401エラーの場合はトークン無効なので更新
            elif response.status_code == 401:
                logger.warning("TikTokアクセストークンが無効です。更新を試みます。")
                return self.refresh_access_token()
            
            else:
                logger.error(f"TikTokトークン情報取得エラー: {response.status_code} {response.text}")
                return False
            
        except Exception as e:
            logger.error(f"TikTokトークン確認エラー: {str(e)}")
            return False
    
    def refresh_access_token(self) -> bool:
        """
        リフレッシュトークンを使用してアクセストークンを更新
        
        Returns:
            更新成功かどうか
        """
        try:
            # トークン更新エンドポイント
            url = f"{self.api_base_url}/oauth/token/"
            
            # リクエストデータ
            data = {
                "client_key": self.client_key,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token
            }
            
            # リクエスト
            response = requests.post(url, data=data)
            
            # レスポンスの確認
            if response.status_code == 200:
                result = response.json()
                
                # 新しいトークンを保存
                self.access_token = result.get("access_token")
                self.refresh_token = result.get("refresh_token")
                
                # 環境変数にも設定（次回起動時のために）
                os.environ["TIKTOK_ACCESS_TOKEN"] = self.access_token
                os.environ["TIKTOK_REFRESH_TOKEN"] = self.refresh_token
                
                logger.info("TikTokアクセストークンの更新に成功しました")
                return True
            else:
                logger.error(f"TikTokトークン更新エラー: {response.status_code} {response.text}")
                return False
            
        except Exception as e:
            logger.error(f"TikTokトークン更新処理エラー: {str(e)}")
            return False
    
    def post_video(
        self,
        video_path: str,
        title: str,
        tags: Optional[List[str]] = None,
        privacy_level: str = "PUBLIC"
    ) -> Dict[str, Any]:
        """
        TikTokに動画を投稿
        
        Args:
            video_path: 動画ファイルパス
            title: キャプション
            tags: ハッシュタグリスト
            privacy_level: 公開設定（'PUBLIC', 'SELF_ONLY', 'FOLLOWINGS_ONLY'）
            
        Returns:
            投稿結果
        """
        try:
            logger.info(f"TikTok動画投稿開始: {video_path}")
            
            # 1. 動画アップロード準備（インテント作成）
            # APIエンドポイント: POST /v2/post/publish/video/init/
            init_url = f"{self.api_base_url}/post/publish/video/init/"
            
            # ファイルサイズを取得
            file_size = os.path.getsize(video_path)
            
            # リクエストヘッダー
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            
            # リクエストボディ
            init_data = {
                "post_info": {
                    "title": title,
                    "privacy_level": privacy_level,
                    "disable_duet": False,
                    "disable_comment": False,
                    "disable_stitch": False,
                }
            }
            
            # タグが指定されている場合は追加
            if tags and isinstance(tags, list):
                title_with_tags = title
                for tag in tags:
                    title_with_tags += f" #{tag}"
                init_data["post_info"]["title"] = title_with_tags
            
            # リクエスト送信
            init_response = requests.post(init_url, headers=headers, json=init_data)
            
            if init_response.status_code != 200:
                logger.error(f"TikTok動画投稿初期化エラー: {init_response.status_code} {init_response.text}")
                return {
                    "success": False,
                    "error": f"投稿初期化エラー: {init_response.text}"
                }
            
            init_result = init_response.json()
            
            # アップロードパラメータを取得
            publish_id = init_result.get("data", {}).get("publish_id")
            upload_url = init_result.get("data", {}).get("upload_url")
            
            if not publish_id or not upload_url:
                logger.error(f"TikTok投稿パラメータ取得エラー: {init_result}")
                return {
                    "success": False,
                    "error": "投稿パラメータ取得エラー"
                }
            
            # 2. 動画ファイルをアップロード
            # 動画ファイルを読み込み
            with open(video_path, "rb") as f:
                video_data = f.read()
            
            # アップロードリクエスト
            upload_headers = {
                "Content-Type": "video/mp4",  # 適切なMIMEタイプに変更
                "Content-Length": str(file_size)
            }
            
            upload_response = requests.put(upload_url, headers=upload_headers, data=video_data)
            
            if upload_response.status_code not in [200, 201, 204]:
                logger.error(f"TikTok動画アップロードエラー: {upload_response.status_code} {upload_response.text}")
                return {
                    "success": False,
                    "error": f"動画アップロードエラー: {upload_response.text}"
                }
            
            # 3. 投稿完了確認
            # APIエンドポイント: POST /v2/post/publish/status/fetch/
            status_url = f"{self.api_base_url}/post/publish/status/fetch/"
            
            # リクエストボディ
            status_data = {
                "publish_id": publish_id
            }
            
            # 投稿状態を確認（最大10回、30秒間隔）
            for attempt in range(10):
                # 少し待機
                time.sleep(30)
                
                # リクエスト送信
                status_response = requests.post(status_url, headers=headers, json=status_data)
                
                if status_response.status_code != 200:
                    logger.warning(f"TikTok投稿状態確認エラー: {status_response.status_code} {status_response.text}")
                    continue
                
                status_result = status_response.json()
                status = status_result.get("data", {}).get("status")
                
                # 投稿成功の場合
                if status == "PUBLISH_COMPLETE":
                    post_id = status_result.get("data", {}).get("post_id")
                    url = f"https://www.tiktok.com/@{self.get_user_info().get('username', 'user')}/video/{post_id}"
                    
                    logger.info(f"TikTok投稿成功: {post_id}")
                    return {
                        "success": True,
                        "post_id": post_id,
                        "url": url
                    }
                
                # 投稿失敗の場合
                elif status in ["PUBLISH_FAILED", "REVIEW_REJECTED"]:
                    error_message = status_result.get("data", {}).get("error", {}).get("message", "不明なエラー")
                    logger.error(f"TikTok投稿失敗: {error_message}")
                    return {
                        "success": False,
                        "error": f"投稿失敗: {error_message}"
                    }
                
                # まだ処理中の場合
                else:
                    logger.info(f"TikTok投稿処理中... ステータス: {status} (試行: {attempt+1}/10)")
            
            # タイムアウト
            logger.error("TikTok投稿タイムアウト: 処理完了を確認できませんでした")
            return {
                "success": False,
                "error": "投稿タイムアウト"
            }
            
        except Exception as e:
            logger.error(f"TikTok投稿処理エラー: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_user_info(self) -> Dict[str, Any]:
        """
        ユーザー情報を取得
        
        Returns:
            ユーザー情報
        """
        try:
            url = f"{self.api_base_url}/user/info/"
            
            headers = {
                "Authorization": f"Bearer {self.access_token}"
            }
            
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                return response.json().get("data", {})
            else:
                logger.error(f"TikTokユーザー情報取得エラー: {response.status_code} {response.text}")
                return {}
                
        except Exception as e:
            logger.error(f"TikTokユーザー情報取得処理エラー: {str(e)}")
            return {}