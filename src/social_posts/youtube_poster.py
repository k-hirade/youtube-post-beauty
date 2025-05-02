"""
@file: youtube_poster.py
@desc: YouTubeに動画を投稿するためのモジュール
"""

import os
import logging
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# ロガー設定
logger = logging.getLogger(__name__)

# 必要なスコープ
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.readonly",
]

class YouTubePoster:
    """YouTubeに動画を投稿するクラス"""
    
    def __init__(
        self,
        client_secrets_path: Optional[str] = None,
        token_path: Optional[str] = None,
        target_channel_id: Optional[str] = None
    ):
        """
        初期化
        
        Args:
            client_secrets_path: YouTubeのクライアントシークレットファイルパス（環境変数から読み込み可能）
            token_path: 認証トークンのパス（環境変数から読み込み可能）
            target_channel_id: 投稿先チャンネルID（環境変数から読み込み可能）
        """
        # 認証情報
        self.client_secrets_path = client_secrets_path or os.environ.get("YOUTUBE_CLIENT_SECRETS")
        self.token_path = token_path or os.environ.get("YOUTUBE_TOKEN")
        self.target_channel_id = target_channel_id or os.environ.get("TARGET_CHANNEL_ID", "")
        
        # ファイルパスをPathオブジェクトに変換
        if self.client_secrets_path:
            self.client_secrets_path = Path(self.client_secrets_path).expanduser()
        
        if self.token_path:
            self.token_path = Path(self.token_path).expanduser()
        
        # ディレクトリの作成
        if self.client_secrets_path:
            self.client_secrets_path.parent.mkdir(parents=True, exist_ok=True)
        
        if self.token_path:
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
        
        # YouTube APIサービス
        self.service = None
        
        logger.info("YouTube投稿モジュール初期化完了")
    
    def _get_authenticated_service(self):
        """
        YouTube APIの認証済みサービスを取得
        
        Returns:
            認証済みのYouTube APIサービス
        """
        if not self.client_secrets_path or not os.path.exists(self.client_secrets_path):
            logger.error(f"クライアントシークレットファイルが見つかりません: {self.client_secrets_path}")
            return None
        
        creds = None
        
        # トークンファイルがある場合は読み込み
        if self.token_path and os.path.exists(self.token_path):
            try:
                creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
            except Exception as e:
                logger.error(f"トークンファイル読み込みエラー: {str(e)}")
                # トークンファイルが壊れている場合は再認証
                creds = None
        
        # アクセストークンが無効な場合、リフレッシュトークンがあればリフレッシュ
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                # 更新したトークンを保存
                with open(str(self.token_path), 'w') as token_file:
                    token_file.write(creds.to_json())
                logger.info("認証トークンを更新しました")
            except Exception as e:
                logger.error(f"トークン更新エラー: {str(e)}")
                # リフレッシュに失敗した場合は再認証
                creds = None
        
        # 認証情報がない、または無効な場合は再認証
        if not creds or not creds.valid:
            try:
                flow = InstalledAppFlow.from_client_secrets_file(str(self.client_secrets_path), SCOPES)
                # ローカルサーバーで認証
                creds = flow.run_local_server(port=0)
                # トークンを保存
                if self.token_path:
                    with open(str(self.token_path), 'w') as token_file:
                        token_file.write(creds.to_json())
                    logger.info("新しい認証トークンを保存しました")
            except Exception as e:
                logger.error(f"認証フローエラー: {str(e)}")
                return None
        
        # 認証済みサービスの構築
        try:
            service = build('youtube', 'v3', credentials=creds)
            logger.info("YouTube API認証成功")
            return service
        except Exception as e:
            logger.error(f"YouTube APIサービス構築エラー: {str(e)}")
            return None
    
    def post_video(
        self,
        video_path: str,
        title: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        category_id: str = "22",  # 22=People & Blogs
        privacy_status: str = "unlisted", # to modify
        made_for_kids: bool = False,
        thumbnail_path: Optional[str] = None,
        notify_subscribers: bool = True
    ) -> Dict[str, Any]:
        """
        YouTubeに動画を投稿
        
        Args:
            video_path: 動画ファイルパス
            title: 動画タイトル
            description: 動画説明
            tags: タグリスト
            category_id: カテゴリID
            privacy_status: 公開設定（'public', 'private', 'unlisted'）
            made_for_kids: 子供向けコンテンツかどうか
            thumbnail_path: サムネイル画像パス（省略可）
            notify_subscribers: 登録者に通知するかどうか
            
        Returns:
            投稿結果
        """
        try:
            # 動画ファイルの存在確認
            if not os.path.exists(video_path):
                logger.error(f"動画ファイルが見つかりません: {video_path}")
                return {
                    "success": False,
                    "error": "動画ファイルが見つかりません"
                }
            
            # APIサービスの取得
            if not self.service:
                self.service = self._get_authenticated_service()
            
            if not self.service:
                logger.error("YouTube API認証に失敗しました")
                return {
                    "success": False,
                    "error": "API認証失敗"
                }
            
            # リクエストボディの作成
            body = {
                "snippet": {
                    "title": title,
                    "description": description,
                    "tags": tags or [],
                    "categoryId": category_id,
                },
                "status": {
                    "privacyStatus": privacy_status,
                    "selfDeclaredMadeForKids": made_for_kids,
                },
                "notifySubscribers": notify_subscribers
            }
            
            # チャンネルIDが指定されている場合は追加
            if self.target_channel_id:
                body["snippet"]["channelId"] = self.target_channel_id
            
            # メディアファイルの準備
            media = MediaFileUpload(
                video_path,
                mimetype="video/mp4",
                resumable=True,
                chunksize=1024*1024  # 1MB単位でアップロード
            )
            
            # 動画アップロードリクエスト
            logger.info(f"YouTube動画アップロード開始: {title}")
            upload_request = self.service.videos().insert(
                part=",".join(body.keys()),
                body=body,
                media_body=media
            )
            
            # アップロード実行（チャンクごとに進捗を報告）
            response = None
            retries = 0
            max_retries = 10
            retry_interval = 5  # 再試行間隔（秒）
            
            while response is None:
                try:
                    status, response = upload_request.next_chunk()
                    if status:
                        progress = int(status.progress() * 100)
                        logger.info(f"アップロード進捗: {progress}%")
                except HttpError as e:
                    # 一時的なエラーの場合は再試行
                    if e.resp.status in [500, 502, 503, 504] and retries < max_retries:
                        retries += 1
                        logger.warning(f"一時的なエラー発生、再試行 ({retries}/{max_retries}): {str(e)}")
                        time.sleep(retry_interval * retries)  # 徐々に間隔を長くする
                    else:
                        logger.error(f"YouTube APIエラー: {str(e)}")
                        return {
                            "success": False,
                            "error": f"APIエラー: {str(e)}"
                        }
                except Exception as e:
                    logger.error(f"アップロード中のエラー: {str(e)}")
                    return {
                        "success": False,
                        "error": f"アップロードエラー: {str(e)}"
                    }
            
            video_id = response["id"]
            logger.info(f"YouTube動画アップロード完了: {video_id}")
            
            # サムネイルの設定（指定がある場合）
            if thumbnail_path and os.path.exists(thumbnail_path):
                try:
                    logger.info(f"サムネイル設定開始: {thumbnail_path}")
                    self.service.thumbnails().set(
                        videoId=video_id,
                        media_body=MediaFileUpload(thumbnail_path)
                    ).execute()
                    logger.info("サムネイル設定完了")
                except Exception as e:
                    # サムネイル設定のエラーは致命的ではないので、ログを残すだけ
                    logger.error(f"サムネイル設定エラー: {str(e)}")
            
            # ショート動画のURLを作成
            video_url = f"https://youtube.com/shorts/{video_id}"
            
            logger.info(f"YouTube投稿成功: {video_url}")
            return {
                "success": True,
                "video_id": video_id,
                "url": video_url
            }
            
        except Exception as e:
            logger.exception(f"YouTube投稿エラー: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_video_info(self, video_id: str) -> Dict[str, Any]:
        """
        動画情報を取得
        
        Args:
            video_id: 動画ID
            
        Returns:
            動画情報
        """
        try:
            # APIサービスの取得
            if not self.service:
                self.service = self._get_authenticated_service()
            
            if not self.service:
                logger.error("YouTube API認証に失敗しました")
                return {}
            
            # 動画情報を取得
            response = self.service.videos().list(
                part="snippet,statistics,status",
                id=video_id
            ).execute()
            
            if not response.get("items"):
                logger.error(f"動画が見つかりません: {video_id}")
                return {}
            
            video = response["items"][0]
            
            # 必要な情報を抽出
            result = {
                "id": video["id"],
                "title": video["snippet"]["title"],
                "description": video["snippet"]["description"],
                "published_at": video["snippet"]["publishedAt"],
                "thumbnail_url": video["snippet"]["thumbnails"]["high"]["url"],
                "view_count": int(video["statistics"].get("viewCount", 0)),
                "like_count": int(video["statistics"].get("likeCount", 0)),
                "comment_count": int(video["statistics"].get("commentCount", 0)),
                "privacy_status": video["status"]["privacyStatus"],
                "embedable": video["status"].get("embeddable", False)
            }
            
            return result
            
        except Exception as e:
            logger.error(f"動画情報取得エラー: {str(e)}")
            return {}
    
    def delete_video(self, video_id: str) -> bool:
        """
        動画を削除
        
        Args:
            video_id: 動画ID
            
        Returns:
            削除成功かどうか
        """
        try:
            # APIサービスの取得
            if not self.service:
                self.service = self._get_authenticated_service()
            
            if not self.service:
                logger.error("YouTube API認証に失敗しました")
                return False
            
            # 動画を削除
            self.service.videos().delete(id=video_id).execute()
            logger.info(f"YouTube動画削除成功: {video_id}")
            return True
            
        except Exception as e:
            logger.error(f"YouTube動画削除エラー: {str(e)}")
            return False
    
    def update_video_metadata(
        self,
        video_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        category_id: Optional[str] = None,
        privacy_status: Optional[str] = None,
        made_for_kids: Optional[bool] = None,
        thumbnail_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        動画メタデータを更新
        
        Args:
            video_id: 動画ID
            title: 動画タイトル
            description: 動画説明
            tags: タグリスト
            category_id: カテゴリID
            privacy_status: 公開設定（'public', 'private', 'unlisted'）
            made_for_kids: 子供向けコンテンツかどうか
            thumbnail_path: サムネイル画像パス
            
        Returns:
            更新結果
        """
        try:
            # APIサービスの取得
            if not self.service:
                self.service = self._get_authenticated_service()
            
            if not self.service:
                logger.error("YouTube API認証に失敗しました")
                return {
                    "success": False,
                    "error": "API認証失敗"
                }
            
            # 現在の動画情報を取得
            response = self.service.videos().list(
                part="snippet,status",
                id=video_id
            ).execute()
            
            if not response.get("items"):
                logger.error(f"動画が見つかりません: {video_id}")
                return {
                    "success": False,
                    "error": "動画が見つかりません"
                }
            
            video = response["items"][0]
            snippet = video["snippet"]
            status = video["status"]
            
            # 更新リクエストの準備
            update_parts = []
            
            # スニペット更新の準備
            if any([x is not None for x in [title, description, tags, category_id]]):
                update_parts.append("snippet")
                
                if title is not None:
                    snippet["title"] = title
                
                if description is not None:
                    snippet["description"] = description
                
                if tags is not None:
                    snippet["tags"] = tags
                
                if category_id is not None:
                    snippet["categoryId"] = category_id
            
            # ステータス更新の準備
            if any([x is not None for x in [privacy_status, made_for_kids]]):
                update_parts.append("status")
                
                if privacy_status is not None:
                    status["privacyStatus"] = privacy_status
                
                if made_for_kids is not None:
                    status["selfDeclaredMadeForKids"] = made_for_kids
            
            # 更新すべき項目がなければ成功扱い
            if not update_parts:
                return {
                    "success": True,
                    "message": "更新する項目はありません"
                }
            
            # 更新リクエスト実行
            update_response = self.service.videos().update(
                part=",".join(update_parts),
                body={
                    "id": video_id,
                    "snippet": snippet,
                    "status": status
                }
            ).execute()
            
            # サムネイルの更新（指定がある場合）
            if thumbnail_path and os.path.exists(thumbnail_path):
                try:
                    logger.info(f"サムネイル更新開始: {thumbnail_path}")
                    self.service.thumbnails().set(
                        videoId=video_id,
                        media_body=MediaFileUpload(thumbnail_path)
                    ).execute()
                    logger.info("サムネイル更新完了")
                except Exception as e:
                    # サムネイル設定のエラーは致命的ではないので、ログを残すだけ
                    logger.error(f"サムネイル更新エラー: {str(e)}")
            
            logger.info(f"YouTube動画情報更新成功: {video_id}")
            return {
                "success": True,
                "video_id": video_id,
                "url": f"https://youtube.com/shorts/{video_id}" if self._is_short_video(video_id) else f"https://youtube.com/watch?v={video_id}"
            }
            
        except Exception as e:
            logger.error(f"YouTube動画更新エラー: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_analytics(self, video_id: str) -> Dict[str, Any]:
        """
        動画の分析データを取得
        
        Args:
            video_id: 動画ID
            
        Returns:
            分析データ
        """
        try:
            # APIサービスの取得
            if not self.service:
                self.service = self._get_authenticated_service()
            
            if not self.service:
                logger.error("YouTube API認証に失敗しました")
                return {}
            
            # YouTube Analytics APIの準備（権限が必要）
            analytics = build('youtubeAnalytics', 'v2', credentials=self.service._credentials)
            
            # アナリティクスデータの取得（過去28日間）
            now = time.strftime('%Y-%m-%d')
            start_date = (datetime.strptime(now, '%Y-%m-%d') - timedelta(days=28)).strftime('%Y-%m-%d')
            
            # メトリクスリクエスト
            analytics_response = analytics.reports().query(
                ids=f"channel=={self.target_channel_id or 'mine'}",
                startDate=start_date,
                endDate=now,
                metrics="views,likes,dislikes,comments,shares,averageViewDuration,averageViewPercentage",
                dimensions="day",
                filters=f"video=={video_id}"
            ).execute()
            
            # レスポンスの処理
            results = {}
            if analytics_response.get("rows"):
                # 時系列データの処理
                time_series = []
                for row in analytics_response["rows"]:
                    date = row[0]  # 日付
                    metrics = {
                        "views": row[1],
                        "likes": row[2],
                        "dislikes": row[3],
                        "comments": row[4],
                        "shares": row[5],
                        "avg_view_duration": row[6],
                        "avg_view_percentage": row[7]
                    }
                    time_series.append({"date": date, "metrics": metrics})
                
                # 累計データの集計
                total_views = sum(row[1] for row in analytics_response["rows"])
                total_likes = sum(row[2] for row in analytics_response["rows"])
                total_comments = sum(row[4] for row in analytics_response["rows"])
                total_shares = sum(row[5] for row in analytics_response["rows"])
                
                # 平均値の計算
                if analytics_response["rows"]:
                    avg_view_duration = sum(row[6] for row in analytics_response["rows"]) / len(analytics_response["rows"])
                    avg_view_percentage = sum(row[7] for row in analytics_response["rows"]) / len(analytics_response["rows"])
                else:
                    avg_view_duration = 0
                    avg_view_percentage = 0
                
                results = {
                    "total": {
                        "views": total_views,
                        "likes": total_likes,
                        "comments": total_comments,
                        "shares": total_shares,
                        "avg_view_duration": avg_view_duration,
                        "avg_view_percentage": avg_view_percentage
                    },
                    "time_series": time_series
                }
            
            return results
            
        except Exception as e:
            logger.error(f"YouTube分析データ取得エラー: {str(e)}")
            return {}
    
    def _is_short_video(self, video_id: str) -> bool:
        """
        動画がショート動画かどうかを判定
        
        Args:
            video_id: 動画ID
            
        Returns:
            ショート動画かどうか
        """
        try:
            # APIサービスの取得
            if not self.service:
                self.service = self._get_authenticated_service()
            
            if not self.service:
                logger.error("YouTube API認証に失敗しました")
                return False
            
            # 動画情報を取得
            response = self.service.videos().list(
                part="contentDetails",
                id=video_id
            ).execute()
            
            if not response.get("items"):
                return False
            
            # 動画の長さを確認
            duration = response["items"][0]["contentDetails"]["duration"]
            
            # ISO 8601形式の時間をパース
            # PT1M30S形式（1分30秒）
            minutes = 0
            seconds = 0
            
            if "M" in duration:
                minutes_part = duration.split("M")[0].split("PT")[1]
                minutes = int(minutes_part)
            
            if "S" in duration:
                if "M" in duration:
                    seconds_part = duration.split("M")[1].split("S")[0]
                else:
                    seconds_part = duration.split("PT")[1].split("S")[0]
                seconds = int(seconds_part)
            
            total_seconds = minutes * 60 + seconds
            
            # 60秒以内ならショート動画
            return total_seconds <= 60
            
        except Exception as e:
            logger.error(f"ショート動画判定エラー: {str(e)}")
            return False