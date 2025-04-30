"""
@file: twitter_poster.py
@desc: Twitter(X)に動画を投稿するためのモジュール
"""

import os
import logging
import json
import time
import requests
import base64
import hmac
import hashlib
import urllib.parse
from typing import Dict, List, Optional, Any
from datetime import datetime

# Twitter APIクライアント
import tweepy

# ロガー設定
logger = logging.getLogger(__name__)

class TwitterPoster:
    """Twitter(X)に動画を投稿するクラス"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        access_token: Optional[str] = None,
        access_token_secret: Optional[str] = None,
        bearer_token: Optional[str] = None
    ):
        """
        初期化
        
        Args:
            api_key: Twitter API Key（環境変数から読み込み可能）
            api_secret: Twitter API Secret（環境変数から読み込み可能）
            access_token: Twitter Access Token（環境変数から読み込み可能）
            access_token_secret: Twitter Access Token Secret（環境変数から読み込み可能）
            bearer_token: Twitter Bearer Token（環境変数から読み込み可能）
        """
        # API認証情報
        self.api_key = api_key or os.environ.get("TWITTER_API_KEY")
        self.api_secret = api_secret or os.environ.get("TWITTER_API_SECRET")
        self.access_token = access_token or os.environ.get("TWITTER_ACCESS_TOKEN")
        self.access_token_secret = access_token_secret or os.environ.get("TWITTER_ACCESS_TOKEN_SECRET")
        self.bearer_token = bearer_token or os.environ.get("TWITTER_BEARER_TOKEN")
        
        # Tweepy APIクライアント初期化
        self.api = None
        self.client = None
        self._init_api()
        
        logger.info("Twitter投稿モジュール初期化完了")
    
    def _init_api(self):
        """Tweepy APIクライアントの初期化"""
        try:
            # 認証情報チェック
            if not all([self.api_key, self.api_secret, self.access_token, self.access_token_secret]):
                logger.warning("Twitter API認証情報が不足しています")
                return
            
            # APIクライアント初期化
            auth = tweepy.OAuth1UserHandler(
                self.api_key,
                self.api_secret,
                self.access_token,
                self.access_token_secret
            )
            
            self.api = tweepy.API(auth)
            
            # API v2クライアント初期化
            self.client = tweepy.Client(
                bearer_token=self.bearer_token,
                consumer_key=self.api_key,
                consumer_secret=self.api_secret,
                access_token=self.access_token,
                access_token_secret=self.access_token_secret
            )
            
            logger.info("Twitter APIクライアント初期化成功")
            
        except Exception as e:
            logger.error(f"Twitter APIクライアント初期化エラー: {str(e)}")
    
    def post_text(self, text: str) -> Dict[str, Any]:
        """
        テキストツイートを投稿
        
        Args:
            text: ツイート本文
            
        Returns:
            投稿結果
        """
        try:
            # APIクライアントが初期化されていない場合はエラー
            if not self.client:
                logger.error("Twitter APIクライアントが初期化されていません")
                return {
                    "success": False,
                    "error": "APIクライアント未初期化"
                }
            
            # ツイート投稿
            response = self.client.create_tweet(text=text)
            
            # 投稿結果確認
            if response and hasattr(response, "data") and "id" in response.data:
                tweet_id = response.data["id"]
                logger.info(f"ツイート投稿成功: {tweet_id}")
                
                # ユーザー情報を取得してURLを作成
                user_info = self.get_user_info()
                username = user_info.get("username", "")
                
                return {
                    "success": True,
                    "tweet_id": tweet_id,
                    "url": f"https://twitter.com/{username}/status/{tweet_id}"
                }
            else:
                logger.error(f"ツイート投稿エラー: 不明なレスポンス形式")
                return {
                    "success": False,
                    "error": "不明なレスポンス形式"
                }
            
        except Exception as e:
            logger.error(f"ツイート投稿エラー: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def post_video(
        self, 
        video_path: str, 
        text: str = "", 
        media_category: str = "tweet_video"
    ) -> Dict[str, Any]:
        """
        動画ツイートを投稿
        
        Args:
            video_path: 動画ファイルパス
            text: ツイート本文
            media_category: メディアカテゴリ
            
        Returns:
            投稿結果
        """
        try:
            # APIクライアントが初期化されていない場合はエラー
            if not self.api:
                logger.error("Twitter APIクライアントが初期化されていません")
                return {
                    "success": False,
                    "error": "APIクライアント未初期化"
                }
            
            logger.info(f"動画アップロード開始: {video_path}")
            
            # メディアアップロード
            media = self.api.media_upload(
                filename=video_path,
                media_category=media_category,
                chunked=True  # 大きなファイル用
            )
            
            # メディアIDを取得
            media_id = media.media_id_string
            logger.info(f"メディアアップロード完了: {media_id}")
            
            # メディア処理が完了するまで待機
            self._wait_for_media_processing(media_id)
            
            # ツイート投稿
            status = self.api.update_status(status=text, media_ids=[media_id])
            
            # 投稿結果確認
            if status and hasattr(status, "id"):
                tweet_id = status.id
                logger.info(f"動画ツイート投稿成功: {tweet_id}")
                
                # ユーザー名を取得してURLを作成
                username = status.user.screen_name
                
                return {
                    "success": True,
                    "tweet_id": tweet_id,
                    "url": f"https://twitter.com/{username}/status/{tweet_id}"
                }
            else:
                logger.error(f"動画ツイート投稿エラー: 不明なレスポンス形式")
                return {
                    "success": False,
                    "error": "不明なレスポンス形式"
                }
            
        except Exception as e:
            logger.error(f"動画ツイート投稿エラー: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _wait_for_media_processing(self, media_id: str, timeout: int = 60) -> bool:
        """
        メディア処理の完了を待機
        
        Args:
            media_id: メディアID
            timeout: タイムアウト時間（秒）
            
        Returns:
            処理成功かどうか
        """
        start_time = time.time()
        
        while True:
            try:
                # 処理状態を確認
                status = self.api.get_media_upload_status(media_id=media_id)
                
                # 処理状態の確認
                if hasattr(status, "processing_info"):
                    processing_info = status.processing_info
                    
                    # 処理完了の場合
                    if processing_info is None:
                        logger.info(f"メディア処理完了: {media_id}")
                        return True
                    
                    # 処理中の場合
                    state = processing_info.get("state", "")
                    
                    if state == "succeeded":
                        logger.info(f"メディア処理完了: {media_id}")
                        return True
                    
                    elif state == "failed":
                        error = processing_info.get("error", {})
                        logger.error(f"メディア処理失敗: {media_id} - {error}")
                        return False
                    
                    elif state == "in_progress":
                        # 待機時間が指定されている場合
                        check_after_secs = processing_info.get("check_after_secs", 5)
                        logger.info(f"メディア処理中: {media_id} - {check_after_secs}秒後に再確認")
                        time.sleep(check_after_secs)
                else:
                    # 処理情報がない場合は完了とみなす
                    logger.info(f"メディア処理情報なし（完了とみなします）: {media_id}")
                    return True
                
                # タイムアウトチェック
                if time.time() - start_time > timeout:
                    logger.error(f"メディア処理タイムアウト: {media_id}")
                    return False
                
            except Exception as e:
                logger.error(f"メディア処理確認エラー: {str(e)}")
                # エラーが発生しても続行（一時的なものかもしれないため）
                time.sleep(5)
                
                # タイムアウトチェック
                if time.time() - start_time > timeout:
                    logger.error(f"メディア処理確認タイムアウト: {media_id}")
                    return False
    
    def get_user_info(self) -> Dict[str, Any]:
        """
        ユーザー情報を取得
        
        Returns:
            ユーザー情報
        """
        try:
            # APIクライアントが初期化されていない場合はエラー
            if not self.client:
                logger.error("Twitter APIクライアントが初期化されていません")
                return {}
            
            # 自分のユーザー情報を取得
            response = self.client.get_me(user_fields=["id", "name", "username", "description", "public_metrics"])
            
            if response and hasattr(response, "data"):
                user_data = response.data
                
                # 辞書形式に変換
                user_info = {
                    "id": user_data.id,
                    "name": user_data.name,
                    "username": user_data.username
                }
                
                # その他の情報があれば追加
                if hasattr(user_data, "description"):
                    user_info["description"] = user_data.description
                
                if hasattr(user_data, "public_metrics"):
                    user_info.update(user_data.public_metrics)
                
                return user_info
            else:
                logger.error(f"ユーザー情報取得エラー: 不明なレスポンス形式")
                return {}
            
        except Exception as e:
            logger.error(f"ユーザー情報取得エラー: {str(e)}")
            return {}