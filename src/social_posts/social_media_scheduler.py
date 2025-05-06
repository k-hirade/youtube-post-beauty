"""
@file: social_media_scheduler.py
@desc: 指定したスケジュールに従ってソーシャルメディアに動画を投稿するスクリプト
"""

import os
import sys
import logging
import time
import schedule
import json
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

# Google Sheets連携用
import gspread
from google.oauth2.service_account import Credentials
from google.cloud import storage

from tiktok_poster import TikTokPoster
from instagram_poster import InstagramPoster
from twitter_poster import TwitterPoster
from youtube_poster import YouTubePoster

# 環境変数読み込み
from dotenv import load_dotenv
load_dotenv()

# ロガー設定
logger = logging.getLogger(__name__)

class SocialMediaScheduler:
    """ソーシャルメディア投稿をスケジュールするクラス"""
    
    def __init__(
        self,
        sheet_id: str,
        credentials_path: str,
        videos_folder: str,
        thumbnails_folder: str,
        youtube_client_secrets: Optional[str] = None,
        youtube_token_path: Optional[str] = None,
        target_channel_id: Optional[str] = None,
        log_file: Optional[str] = None,
        log_level: int = logging.INFO,
        platforms: List[str] = ["tiktok", "instagram", "twitter", "youtube"]
    ):
        """
        初期化
        
        Args:
            sheet_id: スプレッドシートID
            credentials_path: Google APIの認証情報JSONのパス
            videos_folder: 動画ファイル保存フォルダ
            thumbnails_folder: サムネイル画像保存フォルダ
            youtube_client_secrets: YouTubeクライアントシークレットファイルのパス
            youtube_token_path: YouTube認証トークンのパス
            target_channel_id: 投稿先YouTubeチャンネルID
            log_file: ログファイルパス
            log_level: ログレベル
            platforms: 有効な投稿プラットフォームのリスト
        """
        # 設定
        self.sheet_id = sheet_id
        self.credentials_path = credentials_path
        self.videos_folder = videos_folder
        self.thumbnails_folder = thumbnails_folder
        self.platforms = platforms
        
        # YouTubeのAPI認証情報
        self.youtube_client_secrets = youtube_client_secrets or os.environ.get("YOUTUBE_CLIENT_SECRETS")
        self.youtube_token_path = youtube_token_path or os.environ.get("YOUTUBE_TOKEN")
        self.target_channel_id = target_channel_id or os.environ.get("TARGET_CHANNEL_ID")
        
        # ロギング設定
        self.setup_logging(log_file, log_level)
        
        # Google Sheets連携初期化
        self.sheets_client = None
        self._init_google_sheets()
        
        # 各プラットフォームの投稿クラスを初期化
        if "tiktok" in self.platforms:
            self.tiktok_poster = TikTokPoster()
        
        if "instagram" in self.platforms:
            self.instagram_poster = InstagramPoster()
        
        if "twitter" in self.platforms:
            self.twitter_poster = TwitterPoster()
        
        if "youtube" in self.platforms:
            self.youtube_poster = YouTubePoster(
                client_secrets_path=self.youtube_client_secrets,
                token_path=self.youtube_token_path,
                target_channel_id=self.target_channel_id
            )
        
        # 投稿キューと履歴
        self.post_queue = []
        self.post_history = {}
        
        # スケジューラーの設定
        self.configure_schedule()
    
    def setup_logging(self, log_file: Optional[str] = None, log_level: int = logging.INFO):
        """ロギングの設定"""
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        
        # ルートロガー設定
        logging.basicConfig(
            level=log_level,
            format=log_format
        )
        
        # ファイルハンドラの追加（指定がある場合）
        if log_file:
            # ディレクトリ作成
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(log_level)
            file_handler.setFormatter(logging.Formatter(log_format))
            logging.getLogger().addHandler(file_handler)
            
        logger.info("ロギング設定完了")
    
    def _init_google_sheets(self):
        """Google Sheets APIクライアントの初期化"""
        try:
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            
            creds = Credentials.from_service_account_file(
                self.credentials_path, scopes=scopes
            )
            
            self.sheets_client = gspread.authorize(creds)
            logger.info("Google Sheets連携初期化成功")
        except Exception as e:
            logger.error(f"Google Sheets初期化エラー: {str(e)}")
            raise
    
    def load_pending_videos(self, limit: int = 1) -> List[Dict[str, Any]]:
        """
        投稿されていない動画をスプレッドシートから読み込む
        動画IDの若い順から、いずれかのプラットフォームが未投稿の動画を取得
        
        Args:
            limit: 読み込む最大動画数
                
        Returns:
            投稿対象動画のリスト
        """
        try:
            # スプレッドシートを開く
            spreadsheet = self.sheets_client.open_by_key(self.sheet_id)
            
            # 「動画一覧」ワークシートを取得
            worksheet = spreadsheet.worksheet("動画一覧")
            
            # 全てのデータを取得
            all_data = worksheet.get_all_records()
            
            # 必要なカラムのインデックスを取得
            required_columns = [
                "動画ID", "タイトル", "概要欄", "GCS動画URI", "GCSサムネイルURI"
            ]
            
            # プラットフォームごとのカラムを追加
            for platform in self.platforms:
                if platform == "youtube":
                    platform_col = "YouTubeアップロード"
                elif platform == "tiktok":
                    platform_col = "TikTokアップロード"
                elif platform == "instagram":
                    platform_col = "Instagramアップロード"
                elif platform == "twitter":
                    platform_col = "Xアップロード"
                
                required_columns.append(platform_col)
            
            # 結果リスト
            pending_videos = []
            
            # 動画IDの昇順にソート
            sorted_data = sorted(all_data, key=lambda x: int(x.get("動画ID", 0)))
            
            # 未投稿の動画を探す
            for row in sorted_data:
                # いずれかのプラットフォームに未投稿のものを探す
                any_pending = False
                
                for platform in self.platforms:
                    if platform == "youtube":
                        platform_col = "YouTubeアップロード"
                    elif platform == "tiktok":
                        platform_col = "TikTokアップロード"
                    elif platform == "instagram":
                        platform_col = "Instagramアップロード"
                    elif platform == "twitter":
                        platform_col = "Xアップロード"
                    
                    if row.get(platform_col, "").upper() == "FALSE":
                        any_pending = True
                        break
                
                if not any_pending:
                    continue
                
                # GCS URIが存在するものだけ処理
                if row.get("GCS動画URI"):
                    video_info = {
                        "video_id": int(row.get("動画ID", 0)),
                        "title": row.get("タイトル", ""),
                        "description": row.get("概要欄", ""),
                        "video_uri": row.get("GCS動画URI", ""),
                        "thumbnail_uri": row.get("GCSサムネイルURI", ""),
                        "row_index": all_data.index(row) + 2  # 1-based indexing + header row
                    }
                    
                    # 各プラットフォームの投稿状況を追加
                    for platform in self.platforms:
                        if platform == "youtube":
                            video_info["youtube_uploaded"] = row.get("YouTubeアップロード", "").upper() == "TRUE"
                            video_info["youtube_url"] = row.get("YouTube URL", "")
                        elif platform == "tiktok":
                            video_info["tiktok_uploaded"] = row.get("TikTokアップロード", "").upper() == "TRUE"
                            video_info["tiktok_url"] = row.get("TikTok URL", "")
                        elif platform == "instagram":
                            video_info["instagram_uploaded"] = row.get("Instagramアップロード", "").upper() == "TRUE"
                            video_info["instagram_url"] = row.get("Instagram URL", "")
                        elif platform == "twitter":
                            video_info["twitter_uploaded"] = row.get("Xアップロード", "").upper() == "TRUE"
                            video_info["twitter_url"] = row.get("X URL", "")
                    
                    pending_videos.append(video_info)
                    
                    if len(pending_videos) >= limit:
                        break
            
            logger.info(f"{len(pending_videos)}件の投稿待ち動画を読み込みました")
            return pending_videos
            
        except Exception as e:
            logger.error(f"動画読み込みエラー: {str(e)}")
            return []
    
    def download_video_from_gcs(self, video_uri: str, video_id: int) -> Optional[str]:
        """
        GCSから動画をダウンロード
        
        Args:
            video_uri: GCS URI
            video_id: 動画ID
            
        Returns:
            ダウンロードされた動画のローカルパス
        """
        try:
            # URIからバケット名とオブジェクト名を抽出
            if video_uri.startswith("gs://"):
                # gs://bucket-name/path/to/object 形式
                parts = video_uri[5:].split("/", 1)
                bucket_name = parts[0]
                object_name = parts[1]
            elif video_uri.startswith("https://storage.cloud.google.com/"):
                # https://storage.cloud.google.com/bucket-name/path/to/object 形式
                parts = video_uri[len("https://storage.cloud.google.com/"):].split("/", 1)
                bucket_name = parts[0]
                object_name = parts[1]
            else:
                logger.error(f"サポートされていないURI形式: {video_uri}")
                return None
            
            # 保存先パス
            local_filename = f"video_{video_id}.mp4"
            local_path = os.path.join(self.videos_folder, local_filename)
            
            # ディレクトリ作成
            os.makedirs(self.videos_folder, exist_ok=True)
            
            # クライアント初期化
            storage_client = storage.Client()
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(object_name)
            
            # ダウンロード
            blob.download_to_filename(local_path)
            logger.info(f"動画ダウンロード完了: {local_path}")
            
            return local_path
            
        except Exception as e:
            logger.error(f"動画ダウンロードエラー: {str(e)}")
            return None
    
    def download_thumbnail_from_gcs(self, thumbnail_uri: str, video_id: int) -> Optional[str]:
        """
        GCSからサムネイルをダウンロード
        
        Args:
            thumbnail_uri: GCS URI
            video_id: 動画ID
            
        Returns:
            ダウンロードされたサムネイルのローカルパス
        """
        try:
            # URIがない場合はスキップ
            if not thumbnail_uri:
                return None
                
            # URIからバケット名とオブジェクト名を抽出
            if thumbnail_uri.startswith("gs://"):
                # gs://bucket-name/path/to/object 形式
                parts = thumbnail_uri[5:].split("/", 1)
                bucket_name = parts[0]
                object_name = parts[1]
            elif thumbnail_uri.startswith("https://storage.cloud.google.com/"):
                # https://storage.cloud.google.com/bucket-name/path/to/object 形式
                parts = thumbnail_uri[len("https://storage.cloud.google.com/"):].split("/", 1)
                bucket_name = parts[0]
                object_name = parts[1]
            else:
                logger.error(f"サポートされていないURI形式: {thumbnail_uri}")
                return None
            
            # 保存先パス
            local_filename = f"thumbnail_{video_id}.png"
            local_path = os.path.join(self.thumbnails_folder, local_filename)
            
            # ディレクトリ作成
            os.makedirs(self.thumbnails_folder, exist_ok=True)
            
            # クライアント初期化
            storage_client = storage.Client()
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(object_name)
            
            # ダウンロード
            blob.download_to_filename(local_path)
            logger.info(f"サムネイルダウンロード完了: {local_path}")
            
            return local_path
            
        except Exception as e:
            logger.error(f"サムネイルダウンロードエラー: {str(e)}")
            return None
    
    def update_spreadsheet_status(
        self,
        video_id: int,
        row_index: int,
        platform: str,
        status: bool,
        url: Optional[str] = None
    ) -> bool:
        """
        スプレッドシートの投稿ステータスを更新
        
        Args:
            video_id: 動画ID
            row_index: 行インデックス
            platform: プラットフォーム名
            status: 投稿ステータス
            url: 投稿URL
            
        Returns:
            更新成功かどうか
        """
        try:
            # スプレッドシートを開く
            spreadsheet = self.sheets_client.open_by_key(self.sheet_id)
            
            # 「動画一覧」ワークシートを取得
            worksheet = spreadsheet.worksheet("動画一覧")
            
            # ヘッダーの取得
            headers = worksheet.row_values(1)
            
            # 更新対象のカラムを特定
            status_col = None
            url_col = None
            
            if platform == "youtube":
                status_col = headers.index("YouTubeアップロード") + 1
                url_col = headers.index("YouTube URL") + 1
            elif platform == "tiktok":
                status_col = headers.index("TikTokアップロード") + 1
                url_col = headers.index("TikTok URL") + 1
            elif platform == "instagram":
                status_col = headers.index("Instagramアップロード") + 1
                url_col = headers.index("Instagram URL") + 1
            elif platform == "twitter":
                status_col = headers.index("Xアップロード") + 1
                url_col = headers.index("X URL") + 1
            else:
                logger.error(f"不明なプラットフォーム: {platform}")
                return False
            
            # ステータス更新
            worksheet.update_cell(row_index, status_col, "TRUE" if status else "FALSE")
            
            # URL更新（ある場合）
            if url and status:
                worksheet.update_cell(row_index, url_col, url)
            
            logger.info(f"スプレッドシート更新完了: 動画ID {video_id}, プラットフォーム {platform}, ステータス {status}")
            return True
            
        except Exception as e:
            logger.error(f"スプレッドシート更新エラー: {str(e)}")
            return False
    
    def post_to_youtube(self, video: Dict[str, Any]) -> Dict[str, Any]:
        """
        YouTubeに動画を投稿
        
        Args:
            video: 動画情報
            
        Returns:
            投稿結果
        """
        try:
            if "youtube" not in self.platforms:
                logger.info("YouTube投稿は無効化されています")
                return {"success": False, "error": "YouTube投稿無効"}
            
            video_id = video["video_id"]
            
            # 既に投稿済みの場合はスキップ
            if video["youtube_uploaded"]:
                logger.info(f"動画ID {video_id} は既にYouTubeに投稿済みです")
                return {"success": True, "already_posted": True}
            
            # 動画をダウンロード
            local_video_path = self.download_video_from_gcs(video["video_uri"], video_id)
            if not local_video_path:
                logger.error(f"動画ID {video_id} のダウンロードに失敗しました")
                return {"success": False, "error": "動画ダウンロード失敗"}
            
            # サムネイルをダウンロード（あれば）
            thumbnail_path = None
            if video.get("thumbnail_uri"):
                thumbnail_path = self.download_thumbnail_from_gcs(video["thumbnail_uri"], video_id)
            
            # YouTubeに投稿
            logger.info(f"YouTubeに投稿開始: 動画ID {video_id}")
            
            # タイトルと説明文を設定
            title = video["title"] 
            description = video["description"]
            
            result = self.youtube_poster.post_video(
                video_path=local_video_path,
                title=title,
                description=description,
                tags=["コスメ", "ランキング", "ショート"],
                thumbnail_path=thumbnail_path,
                privacy_status="public"  # 公開設定
            )
            
            # 投稿成功した場合はスプレッドシートを更新
            if result["success"]:
                self.update_spreadsheet_status(
                    video_id=video_id,
                    row_index=video["row_index"],
                    platform="youtube",
                    status=True,
                    url=result.get("url")
                )
                logger.info(f"YouTube投稿成功: 動画ID {video_id}")
            else:
                logger.error(f"YouTube投稿失敗: 動画ID {video_id}, エラー: {result.get('error')}")
            
            # 一時ファイルの削除
            try:
                os.remove(local_video_path)
                if thumbnail_path:
                    os.remove(thumbnail_path)
            except Exception as e:
                logger.warning(f"一時ファイル削除エラー: {str(e)}")
            
            return result
            
        except Exception as e:
            logger.error(f"YouTube投稿エラー: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def post_to_tiktok(self, video: Dict[str, Any]) -> Dict[str, Any]:
        """
        TikTokに動画を投稿
        
        Args:
            video: 動画情報
            
        Returns:
            投稿結果
        """
        try:
            if "tiktok" not in self.platforms:
                logger.info("TikTok投稿は無効化されています")
                return {"success": False, "error": "TikTok投稿無効"}
            
            video_id = video["video_id"]
            
            # 既に投稿済みの場合はスキップ
            if video["tiktok_uploaded"]:
                logger.info(f"動画ID {video_id} は既にTikTokに投稿済みです")
                return {"success": True, "already_posted": True}
            
            # 動画をダウンロード
            local_video_path = self.download_video_from_gcs(video["video_uri"], video_id)
            if not local_video_path:
                logger.error(f"動画ID {video_id} のダウンロードに失敗しました")
                return {"success": False, "error": "動画ダウンロード失敗"}
            
            # TikTokに投稿
            logger.info(f"TikTokに投稿開始: 動画ID {video_id}")
            result = self.tiktok_poster.post_video(
                video_path=local_video_path,
                title=video["title"],
                tags=["コスメ", "ランキング"]
            )
            
            # 投稿成功した場合はスプレッドシートを更新
            if result["success"]:
                self.update_spreadsheet_status(
                    video_id=video_id,
                    row_index=video["row_index"],
                    platform="tiktok",
                    status=True,
                    url=result.get("url")
                )
                logger.info(f"TikTok投稿成功: 動画ID {video_id}")
            else:
                logger.error(f"TikTok投稿失敗: 動画ID {video_id}, エラー: {result.get('error')}")
            
            # 一時ファイルの削除
            try:
                os.remove(local_video_path)
            except:
                pass
            
            return result
            
        except Exception as e:
            logger.error(f"TikTok投稿エラー: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def post_to_instagram(self, video: Dict[str, Any]) -> Dict[str, Any]:
        """
        Instagramに動画を投稿
        
        Args:
            video: 動画情報
            
        Returns:
            投稿結果
        """
        try:
            if "instagram" not in self.platforms:
                logger.info("Instagram投稿は無効化されています")
                return {"success": False, "error": "Instagram投稿無効"}
            
            video_id = video["video_id"]
            
            # 既に投稿済みの場合はスキップ
            if video["instagram_uploaded"]:
                logger.info(f"動画ID {video_id} は既にInstagramに投稿済みです")
                return {"success": True, "already_posted": True}
            
            # 動画をダウンロード
            local_video_path = self.download_video_from_gcs(video["video_uri"], video_id)
            if not local_video_path:
                logger.error(f"動画ID {video_id} のダウンロードに失敗しました")
                return {"success": False, "error": "動画ダウンロード失敗"}
            
            # サムネイルをダウンロード（あれば）
            thumbnail_path = None
            if video.get("thumbnail_uri"):
                thumbnail_path = self.download_thumbnail_from_gcs(video["thumbnail_uri"], video_id)

            title = video['title']
            description = video["description"]
            
            # Instagramに投稿
            logger.info(f"Instagramに投稿開始: 動画ID {video_id}")
            result = self.instagram_poster.post_video(
                video_path=video["video_uri"],
                caption=f"{title} {description}",
                thumbnail_path=thumbnail_path
            )
            
            # 投稿成功した場合はスプレッドシートを更新
            if result["success"]:
                self.update_spreadsheet_status(
                    video_id=video_id,
                    row_index=video["row_index"],
                    platform="instagram",
                    status=True,
                    url=result.get("url")
                )
                logger.info(f"Instagram投稿成功: 動画ID {video_id}")
            else:
                logger.error(f"Instagram投稿失敗: 動画ID {video_id}, エラー: {result.get('error')}")
            
            # 一時ファイルの削除
            try:
                os.remove(local_video_path)
                if thumbnail_path:
                    os.remove(thumbnail_path)
            except:
                pass
            
            return result
            
        except Exception as e:
            logger.error(f"Instagram投稿エラー: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def post_to_twitter(self, video: Dict[str, Any]) -> Dict[str, Any]:
        """
        Twitter(X)に動画を投稿
        
        Args:
            video: 動画情報
            
        Returns:
            投稿結果
        """
        try:
            if "twitter" not in self.platforms:
                logger.info("Twitter投稿は無効化されています")
                return {"success": False, "error": "Twitter投稿無効"}
            
            video_id = video["video_id"]
            
            # 既に投稿済みの場合はスキップ
            if video["twitter_uploaded"]:
                logger.info(f"動画ID {video_id} は既にTwitterに投稿済みです")
                return {"success": True, "already_posted": True}
            
            # 動画をダウンロード
            local_video_path = self.download_video_from_gcs(video["video_uri"], video_id)
            if not local_video_path:
                logger.error(f"動画ID {video_id} のダウンロードに失敗しました")
                return {"success": False, "error": "動画ダウンロード失敗"}

            title = video["title"] 
            description = video["description"]
            
            # Twitterに投稿
            logger.info(f"Twitterに投稿開始: 動画ID {video_id}")
            result = self.twitter_poster.post_video(
                video_path=local_video_path,
                text=f"{title} {description}"
            )
            
            # 投稿成功した場合はスプレッドシートを更新
            if result["success"]:
                self.update_spreadsheet_status(
                    video_id=video_id,
                    row_index=video["row_index"],
                    platform="twitter",
                    status=True,
                    url=result.get("url")
                )
                logger.info(f"Twitter投稿成功: 動画ID {video_id}")
            else:
                logger.error(f"Twitter投稿失敗: 動画ID {video_id}, エラー: {result.get('error')}")
            
            # 一時ファイルの削除
            try:
                os.remove(local_video_path)
            except:
                pass
            
            return result
            
        except Exception as e:
            logger.error(f"Twitter投稿エラー: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def post_to_all_platforms(self, video: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """
        全プラットフォームに投稿
        
        Args:
            video: 動画情報
            
        Returns:
            プラットフォーム別投稿結果
        """
        results = {}
        
        # YouTubeに投稿（環境変数がtrueの場合のみ）
        if "youtube" in self.platforms and os.environ.get("ENABLE_YOUTUBE_SHORTS", "false").lower() == "true":
            results["youtube"] = self.post_to_youtube(video)
        else:
            logging.info("Youtube投稿をスキップ")
        
        # TikTokに投稿（環境変数がtrueの場合のみ）
        if "tiktok" in self.platforms and os.environ.get("ENABLE_TIKTOK_SHORTS", "false").lower() == "true":
            results["tiktok"] = self.post_to_tiktok(video)
        else:
            logging.info("Tiktok投稿をスキップ")
        
        # Instagramに投稿（環境変数がtrueの場合のみ）
        if "instagram" in self.platforms and os.environ.get("ENABLE_INSTAGRAM_SHORTS", "false").lower() == "true":
            results["instagram"] = self.post_to_instagram(video)
        else:
            logging.info("Instagram投稿をスキップ")
        
        # Twitterに投稿（環境変数がtrueの場合のみ）
        if "twitter" in self.platforms and os.environ.get("ENABLE_TWITTER_SHORTS", "false").lower() == "true":
            results["twitter"] = self.post_to_twitter(video)
        else:
            logging.info("Twitter投稿をスキップ")
        
        return results
    
    def process_posting_job(self, time_slot: str):
        """
        指定された時間枠の投稿を実行
        
        Args:
            time_slot: 時間枠（'morning', 'noon', 'afternoon', 'evening'）
        """
        logger.info(f"投稿ジョブ開始: {time_slot}")
        
        # 投稿対象動画の取得 - 1本だけ投稿する
        videos = self.load_pending_videos(limit=1)
        
        if not videos:
            logger.info(f"投稿対象の動画がありません: {time_slot}")
            return
        
        # 1本の動画を処理
        video = videos[0]
        try:
            logger.info(f"[{time_slot}] 投稿処理: 動画ID {video['video_id']}")
            
            # 全プラットフォームに投稿
            results = self.post_to_all_platforms(video)
            
            # 結果をログに記録
            logger.info(f"投稿結果: {json.dumps(results)}")
            
            # 投稿履歴に追加
            self.post_history[video["video_id"]] = {
                "time": datetime.now().isoformat(),
                "time_slot": time_slot,
                "results": results
            }
            
        except Exception as e:
            logger.error(f"動画ID {video['video_id']} の投稿処理中にエラーが発生: {str(e)}")
        
        logger.info(f"投稿ジョブ完了: {time_slot}")
    
    def configure_schedule(self):
        """スケジュール設定"""
        # 朝: 6:00から7:00まで15分ごとに1本
        schedule.every().day.at("06:00").do(self.process_posting_job, time_slot="morning")
        schedule.every().day.at("06:15").do(self.process_posting_job, time_slot="morning")
        schedule.every().day.at("06:30").do(self.process_posting_job, time_slot="morning")
        schedule.every().day.at("06:45").do(self.process_posting_job, time_slot="morning")
        schedule.every().day.at("07:00").do(self.process_posting_job, time_slot="morning")
        
        # 昼: 11:00から12:00まで15分ごとに1本
        schedule.every().day.at("11:00").do(self.process_posting_job, time_slot="noon")
        schedule.every().day.at("11:15").do(self.process_posting_job, time_slot="noon")
        schedule.every().day.at("11:30").do(self.process_posting_job, time_slot="noon")
        schedule.every().day.at("11:45").do(self.process_posting_job, time_slot="noon")
        schedule.every().day.at("12:00").do(self.process_posting_job, time_slot="noon")
        
        # 夕方: 16:00から17:00まで15分ごとに1本
        schedule.every().day.at("16:00").do(self.process_posting_job, time_slot="afternoon")
        schedule.every().day.at("16:15").do(self.process_posting_job, time_slot="afternoon")
        schedule.every().day.at("16:30").do(self.process_posting_job, time_slot="afternoon")
        schedule.every().day.at("16:45").do(self.process_posting_job, time_slot="afternoon")
        schedule.every().day.at("17:00").do(self.process_posting_job, time_slot="afternoon")
        
        # 夜: 19:00から20:00まで15分ごとに1本
        schedule.every().day.at("19:00").do(self.process_posting_job, time_slot="evening")
        schedule.every().day.at("19:15").do(self.process_posting_job, time_slot="evening")
        schedule.every().day.at("19:30").do(self.process_posting_job, time_slot="evening")
        schedule.every().day.at("19:45").do(self.process_posting_job, time_slot="evening")
        schedule.every().day.at("20:00").do(self.process_posting_job, time_slot="evening")
        
        logger.info("スケジュール設定完了")
    
    def run(self):
        """スケジューラーを実行"""
        logger.info("スケジューラー開始")
        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("ユーザーによる中断")
        except Exception as e:
            logger.error(f"スケジューラーエラー: {str(e)}")
        finally:
            logger.info("スケジューラー終了")


def parse_args():
    """コマンドライン引数のパース"""
    parser = argparse.ArgumentParser(description='ソーシャルメディア自動投稿スケジューラー')
    
    parser.add_argument('--sheet-id', type=str, 
                        default=os.environ.get('SHEET_ID'),
                        help='スプレッドシートID')
    
    parser.add_argument('--credentials', type=str, 
                        default=os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'),
                        help='Google API認証情報JSONパス')
    
    parser.add_argument('--videos-folder', type=str, 
                        default='data/videos',
                        help='動画一時保存フォルダ')
    
    parser.add_argument('--thumbnails-folder', type=str, 
                        default='data/thumbnails',
                        help='サムネイル一時保存フォルダ')
    
    parser.add_argument('--youtube-client-secrets', type=str,
                        default=os.environ.get('YOUTUBE_CLIENT_SECRETS'),
                        help='YouTubeクライアントシークレットファイルパス')
    
    parser.add_argument('--youtube-token', type=str,
                        default=os.environ.get('YOUTUBE_TOKEN'),
                        help='YouTube認証トークンファイルパス')
    
    parser.add_argument('--target-channel-id', type=str,
                        default=os.environ.get('TARGET_CHANNEL_ID'),
                        help='投稿先YouTubeチャンネルID')
    
    parser.add_argument('--log-file', type=str, 
                        default='data/logs/social_media_scheduler.log',
                        help='ログファイルパス')
    
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='詳細なログを出力')
    
    parser.add_argument('--test-post', action='store_true',
                        help='テスト投稿モード（スケジュール無視して即時投稿）')
    
    parser.add_argument('--platforms', type=str, 
                        default='youtube,tiktok,instagram,twitter',
                        help='投稿対象プラットフォーム（カンマ区切り）')
    
    return parser.parse_args()


def main():
    """メイン関数"""
    # 引数のパース
    args = parse_args()
    
    # 必須パラメータの確認
    if not args.sheet_id:
        print("エラー: スプレッドシートIDが指定されていません")
        sys.exit(1)
    
    if not args.credentials:
        print("エラー: Google API認証情報パスが指定されていません")
        sys.exit(1)
    
    # YouTube投稿有効時の必須パラメータ確認
    platforms = args.platforms.split(",")
    if "youtube" in platforms and not args.youtube_client_secrets:
        print("エラー: YouTube投稿が有効ですが、クライアントシークレットファイルが指定されていません")
        sys.exit(1)
    
    # ロギングレベル
    log_level = logging.DEBUG if args.verbose else logging.INFO
    
    # スケジューラー初期化
    scheduler = SocialMediaScheduler(
        sheet_id=args.sheet_id,
        credentials_path=args.credentials,
        videos_folder=args.videos_folder,
        thumbnails_folder=args.thumbnails_folder,
        youtube_client_secrets=args.youtube_client_secrets,
        youtube_token_path=args.youtube_token,
        target_channel_id=args.target_channel_id,
        log_file=args.log_file,
        log_level=log_level,
        platforms=platforms
    )
    
    # テスト投稿モードの場合
    if args.test_post:
        print("テスト投稿モードで実行します")
        scheduler.process_posting_job(time_slot="test")
        return
    
    # 通常モードの場合
    print("スケジューラーを起動します")
    scheduler.run()


if __name__ == "__main__":
    main()