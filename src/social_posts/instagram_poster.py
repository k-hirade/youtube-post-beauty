"""
@file: instagram_poster.py
@desc: Instagramに動画を投稿するためのモジュール
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

class InstagramPoster:
    """Instagramに動画を投稿するクラス"""
    
    def __init__(
        self,
        access_token: Optional[str] = None,
        user_id: Optional[str] = None,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None
    ):
        """
        初期化
        
        Args:
            access_token: Facebookのアクセストークン（環境変数から読み込み可能）
            user_id: InstagramビジネスアカウントのID（環境変数から読み込み可能）
            app_id: FacebookアプリのID（環境変数から読み込み可能）
            app_secret: FacebookアプリのSecret（環境変数から読み込み可能）
        """
        # API認証情報
        self.access_token = access_token or os.environ.get("INSTAGRAM_ACCESS_TOKEN")
        self.user_id = user_id or os.environ.get("INSTAGRAM_USER_ID")
        self.app_id = app_id or os.environ.get("FACEBOOK_APP_ID")
        self.app_secret = app_secret or os.environ.get("FACEBOOK_APP_SECRET")
        
        # APIエンドポイント
        self.api_base_url = "https://graph.facebook.com/v22.0"
        
        # トークンの有効期限確認
        self.check_and_refresh_token()
        
        logger.info("Instagram投稿モジュール初期化完了")
    
    def check_and_refresh_token(self) -> bool:
        """
        アクセストークンの有効期限を確認し、必要に応じて更新
        
        Returns:
            更新成功かどうか
        """
        try:
            # トークン情報がない場合は更新不要
            if not self.access_token:
                logger.warning("Instagram APIトークンが設定されていません")
                return False
            
            # トークン情報取得エンドポイント
            url = f"{self.api_base_url}/debug_token"
            
            # リクエストパラメータ
            params = {
                "input_token": self.access_token,
                "access_token": f"{self.app_id}|{self.app_secret}"
            }
            
            # リクエスト
            response = requests.get(url, params=params)
            
            # レスポンスの確認
            if response.status_code == 200:
                data = response.json().get("data", {})
                
                # 有効期限を確認
                expires_at = data.get("expires_at", 0)
                is_valid = data.get("is_valid", False)
                
                if not is_valid:
                    logger.warning("Instagramアクセストークンが無効です。更新を試みます。")
                    return self.refresh_access_token()
                
                # 現在のタイムスタンプ
                current_time = int(time.time())
                
                # 有効期限が7日未満の場合は更新
                if expires_at > 0 and (expires_at - current_time) < 7 * 24 * 60 * 60:
                    logger.info(f"Instagramアクセストークンの有効期限が近いため更新します")
                    return self.refresh_access_token()
                else:
                    logger.info(f"Instagramアクセストークンは有効です")
                    return True
                
            else:
                logger.error(f"Instagramトークン情報取得エラー: {response.status_code} {response.text}")
                return False
            
        except Exception as e:
            logger.error(f"Instagramトークン確認エラー: {str(e)}")
            return False
    
    def refresh_access_token(self) -> bool:
        """
        アクセストークンを長期トークンに更新
        
        Returns:
            更新成功かどうか
        """
        try:
            # トークン更新エンドポイント
            url = f"{self.api_base_url}/oauth/access_token"
            
            # リクエストパラメータ
            params = {
                "grant_type": "fb_exchange_token",
                "client_id": self.app_id,
                "client_secret": self.app_secret,
                "fb_exchange_token": self.access_token
            }
            
            # リクエスト
            response = requests.get(url, params=params)
            
            # レスポンスの確認
            if response.status_code == 200:
                result = response.json()
                
                # 新しいトークンを保存
                self.access_token = result.get("access_token")
                
                # 環境変数にも設定（次回起動時のために）
                os.environ["INSTAGRAM_ACCESS_TOKEN"] = self.access_token
                
                logger.info("Instagramアクセストークンの更新に成功しました")
                return True
            else:
                logger.error(f"Instagramトークン更新エラー: {response.status_code} {response.text}")
                return False
            
        except Exception as e:
            logger.error(f"Instagramトークン更新処理エラー: {str(e)}")
            return False
    
    def post_video(
        self,
        video_path: str,
        caption: str,
        thumbnail_path: Optional[str] = None,
        location_id: Optional[str] = None,
        user_tags: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Instagramに動画を投稿
        
        Args:
            video_path: 動画ファイルパス
            caption: キャプション
            thumbnail_path: サムネイル画像パス（省略可）
            location_id: 位置情報ID（省略可）
            user_tags: ユーザータグ情報（省略可）
            
        Returns:
            投稿結果
        """
        try:
            logger.info(f"Instagram動画投稿開始: {video_path}")
            
            # ユーザーIDが設定されていない場合はエラー
            if not self.user_id:
                logger.error("InstagramユーザーIDが設定されていません")
                return {
                    "success": False,
                    "error": "ユーザーID未設定"
                }
            
            # 1. コンテナの作成
            container_url = f"{self.api_base_url}/{self.user_id}/media"
            
            # リクエストパラメータ
            container_params = {
                "media_type": "REELS",  # REELSとして投稿
                "video_url": f"file://{os.path.abspath(video_path)}",  # ファイルパスをURLに変換
                "caption": caption,
                "access_token": self.access_token
            }
            
            # サムネイルがある場合
            if thumbnail_path and os.path.exists(thumbnail_path):
                container_params["thumb_source"] = f"file://{os.path.abspath(thumbnail_path)}"
            
            # 位置情報がある場合
            if location_id:
                container_params["location_id"] = location_id
            
            # ユーザータグがある場合
            if user_tags:
                container_params["user_tags"] = json.dumps(user_tags)
            
            # アップロードリクエスト
            # 注意: 実際の実装ではマルチパートフォームデータとしてファイルをアップロードする必要があります
            # この例では簡略化のためにURLを指定していますが、実際にはファイルをアップロードする実装が必要です
            
            # 以下、実際のアップロード処理
            files = {}
            
            # 動画ファイルをマルチパートフォームでアップロード
            with open(video_path, "rb") as video_file:
                files["video_file"] = video_file
                
                # サムネイルがある場合
                if thumbnail_path and os.path.exists(thumbnail_path):
                    with open(thumbnail_path, "rb") as thumb_file:
                        files["thumb_file"] = thumb_file
                        
                        # リクエスト送信
                        container_response = requests.post(
                            container_url, 
                            params=container_params,
                            files=files
                        )
                else:
                    # サムネイルなしでリクエスト送信
                    container_response = requests.post(
                        container_url, 
                        params=container_params,
                        files=files
                    )
            
            if container_response.status_code != 200:
                logger.error(f"Instagramコンテナ作成エラー: {container_response.status_code} {container_response.text}")
                return {
                    "success": False,
                    "error": f"コンテナ作成エラー: {container_response.text}"
                }
            
            container_result = container_response.json()
            
            # コンテナIDを取得
            container_id = container_result.get("id")
            
            if not container_id:
                logger.error(f"Instagramコンテナ識別子取得エラー: {container_result}")
                return {
                    "success": False,
                    "error": "コンテナ識別子取得エラー"
                }
            
            # 2. 公開処理
            # 最大10回、30秒間隔で処理状態を確認
            for attempt in range(10):
                # 公開エンドポイント
                publish_url = f"{self.api_base_url}/{self.user_id}/media_publish"
                
                # リクエストパラメータ
                publish_params = {
                    "creation_id": container_id,
                    "access_token": self.access_token
                }
                
                # リクエスト送信
                publish_response = requests.post(publish_url, params=publish_params)
                
                # 成功の場合
                if publish_response.status_code == 200:
                    publish_result = publish_response.json()
                    post_id = publish_result.get("id")
                    
                    logger.info(f"Instagram投稿成功: {post_id}")
                    return {
                        "success": True,
                        "post_id": post_id,
                        "url": f"https://www.instagram.com/p/{post_id}/"
                    }
                
                # 処理中の場合は待機
                elif "PENDING" in publish_response.text or "IN_PROGRESS" in publish_response.text:
                    logger.info(f"Instagram投稿処理中... (試行: {attempt+1}/10)")
                    time.sleep(30)
                    continue
                
                # それ以外のエラー
                else:
                    logger.error(f"Instagram公開エラー: {publish_response.status_code} {publish_response.text}")
                    
                    # エラーが一時的なものの場合は再試行
                    if "try again later" in publish_response.text.lower():
                        logger.info("一時的なエラーのため30秒後に再試行します")
                        time.sleep(30)
                        continue
                    
                    return {
                        "success": False,
                        "error": f"公開エラー: {publish_response.text}"
                    }
            
            # タイムアウト
            logger.error("Instagram投稿タイムアウト: 処理完了を確認できませんでした")
            return {
                "success": False,
                "error": "投稿タイムアウト"
            }
            
        except Exception as e:
            logger.error(f"Instagram投稿処理エラー: {str(e)}")
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
            url = f"{self.api_base_url}/{self.user_id}"
            
            params = {
                "fields": "id,username,name,biography,followers_count,follows_count,media_count",
                "access_token": self.access_token
            }
            
            response = requests.get(url, params=params)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Instagramユーザー情報取得エラー: {response.status_code} {response.text}")
                return {}
                
        except Exception as e:
            logger.error(f"Instagramユーザー情報取得処理エラー: {str(e)}")
            return {}
    
    def get_media_insights(self, media_id: str) -> Dict[str, Any]:
        """
        投稿のインサイト情報を取得
        
        Args:
            media_id: 投稿ID
            
        Returns:
            インサイト情報
        """
        try:
            url = f"{self.api_base_url}/{media_id}/insights"
            
            params = {
                "metric": "engagement,impressions,reach,saved",
                "access_token": self.access_token
            }
            
            response = requests.get(url, params=params)
            
            if response.status_code == 200:
                return response.json().get("data", {})
            else:
                logger.error(f"Instagramインサイト取得エラー: {response.status_code} {response.text}")
                return {}
                
        except Exception as e:
            logger.error(f"Instagramインサイト取得処理エラー: {str(e)}")
            return {}
    
    def delete_media(self, media_id: str) -> bool:
        """
        投稿を削除
        
        Args:
            media_id: 投稿ID
            
        Returns:
            削除成功かどうか
        """
        try:
            url = f"{self.api_base_url}/{media_id}"
            
            params = {
                "access_token": self.access_token
            }
            
            response = requests.delete(url, params=params)
            
            if response.status_code == 200:
                result = response.json()
                success = result.get("success", False)
                
                if success:
                    logger.info(f"Instagram投稿削除成功: {media_id}")
                    return True
                else:
                    logger.error(f"Instagram投稿削除失敗: {result}")
                    return False
            else:
                logger.error(f"Instagram投稿削除エラー: {response.status_code} {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Instagram投稿削除処理エラー: {str(e)}")
            return False
    
    def post_story(
        self, 
        image_path: str, 
        caption: Optional[str] = None,
        stickers: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Instagramストーリーに画像を投稿
        
        Args:
            image_path: 画像ファイルパス
            caption: キャプション（省略可）
            stickers: ステッカー情報（省略可）
            
        Returns:
            投稿結果
        """
        try:
            logger.info(f"Instagramストーリー投稿開始: {image_path}")
            
            # ユーザーIDが設定されていない場合はエラー
            if not self.user_id:
                logger.error("InstagramユーザーIDが設定されていません")
                return {
                    "success": False,
                    "error": "ユーザーID未設定"
                }
            
            # 1. コンテナの作成
            container_url = f"{self.api_base_url}/{self.user_id}/media"
            
            # リクエストパラメータ
            container_params = {
                "media_type": "STORIES",  # STORIESとして投稿
                "image_url": f"file://{os.path.abspath(image_path)}",  # ファイルパスをURLに変換
                "access_token": self.access_token
            }
            
            # キャプションがある場合
            if caption:
                container_params["caption"] = caption
            
            # ステッカーがある場合
            if stickers:
                container_params["story_stickers"] = json.dumps(stickers)
            
            # 画像ファイルをマルチパートフォームでアップロード
            with open(image_path, "rb") as image_file:
                files = {"image_file": image_file}
                
                # リクエスト送信
                container_response = requests.post(
                    container_url, 
                    params=container_params,
                    files=files
                )
            
            if container_response.status_code != 200:
                logger.error(f"Instagramストーリーコンテナ作成エラー: {container_response.status_code} {container_response.text}")
                return {
                    "success": False,
                    "error": f"ストーリーコンテナ作成エラー: {container_response.text}"
                }
            
            container_result = container_response.json()
            
            # コンテナIDを取得
            container_id = container_result.get("id")
            
            if not container_id:
                logger.error(f"Instagramストーリーコンテナ識別子取得エラー: {container_result}")
                return {
                    "success": False,
                    "error": "ストーリーコンテナ識別子取得エラー"
                }
            
            # 2. 公開処理
            publish_url = f"{self.api_base_url}/{self.user_id}/media_publish"
            
            # リクエストパラメータ
            publish_params = {
                "creation_id": container_id,
                "access_token": self.access_token
            }
            
            # リクエスト送信
            publish_response = requests.post(publish_url, params=publish_params)
            
            # 成功の場合
            if publish_response.status_code == 200:
                publish_result = publish_response.json()
                story_id = publish_result.get("id")
                
                logger.info(f"Instagramストーリー投稿成功: {story_id}")
                return {
                    "success": True,
                    "story_id": story_id
                }
            else:
                logger.error(f"Instagramストーリー公開エラー: {publish_response.status_code} {publish_response.text}")
                return {
                    "success": False,
                    "error": f"ストーリー公開エラー: {publish_response.text}"
                }
                
        except Exception as e:
            logger.error(f"Instagramストーリー投稿処理エラー: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def upload_from_url(
        self,
        media_url: str,
        caption: str,
        media_type: str = "REELS"
    ) -> Dict[str, Any]:
        """
        URLからメディアをインポートして投稿
        
        Args:
            media_url: メディアのURL
            caption: キャプション
            media_type: メディアタイプ（'FEED', 'REELS', 'STORIES'）
            
        Returns:
            投稿結果
        """
        try:
            logger.info(f"InstagramへのURL投稿開始: {media_url}")
            
            # ユーザーIDが設定されていない場合はエラー
            if not self.user_id:
                logger.error("InstagramユーザーIDが設定されていません")
                return {
                    "success": False,
                    "error": "ユーザーID未設定"
                }
            
            # 1. コンテナの作成
            container_url = f"{self.api_base_url}/{self.user_id}/media"
            
            # リクエストパラメータ
            container_params = {
                "media_type": media_type,
                "caption": caption,
                "access_token": self.access_token
            }
            
            # メディアタイプに応じてURLパラメータを設定
            if media_type == "REELS" or media_type == "FEED" and media_url.endswith(('.mp4', '.mov')):
                container_params["video_url"] = media_url
            else:
                container_params["image_url"] = media_url
            
            # リクエスト送信
            container_response = requests.post(container_url, params=container_params)
            
            if container_response.status_code != 200:
                logger.error(f"InstagramコンテナURL作成エラー: {container_response.status_code} {container_response.text}")
                return {
                    "success": False,
                    "error": f"コンテナURL作成エラー: {container_response.text}"
                }
            
            container_result = container_response.json()
            
            # コンテナIDを取得
            container_id = container_result.get("id")
            
            if not container_id:
                logger.error(f"InstagramコンテナURL識別子取得エラー: {container_result}")
                return {
                    "success": False,
                    "error": "コンテナURL識別子取得エラー"
                }
            
            # 2. 公開処理
            # 最大10回、30秒間隔で処理状態を確認
            for attempt in range(10):
                # 公開エンドポイント
                publish_url = f"{self.api_base_url}/{self.user_id}/media_publish"
                
                # リクエストパラメータ
                publish_params = {
                    "creation_id": container_id,
                    "access_token": self.access_token
                }
                
                # リクエスト送信
                publish_response = requests.post(publish_url, params=publish_params)
                
                # 成功の場合
                if publish_response.status_code == 200:
                    publish_result = publish_response.json()
                    post_id = publish_result.get("id")
                    
                    logger.info(f"InstagramURL投稿成功: {post_id}")
                    return {
                        "success": True,
                        "post_id": post_id,
                        "url": f"https://www.instagram.com/p/{post_id}/"
                    }
                
                # 処理中の場合は待機
                elif "PENDING" in publish_response.text or "IN_PROGRESS" in publish_response.text:
                    logger.info(f"InstagramURL投稿処理中... (試行: {attempt+1}/10)")
                    time.sleep(30)
                    continue
                
                # それ以外のエラー
                else:
                    logger.error(f"InstagramURL公開エラー: {publish_response.status_code} {publish_response.text}")
                    
                    # エラーが一時的なものの場合は再試行
                    if "try again later" in publish_response.text.lower():
                        logger.info("一時的なエラーのため30秒後に再試行します")
                        time.sleep(30)
                        continue
                    
                    return {
                        "success": False,
                        "error": f"URL公開エラー: {publish_response.text}"
                    }
            
            # タイムアウト
            logger.error("InstagramURL投稿タイムアウト: 処理完了を確認できませんでした")
            return {
                "success": False,
                "error": "URL投稿タイムアウト"
            }
            
        except Exception as e:
            logger.error(f"InstagramURL投稿処理エラー: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }