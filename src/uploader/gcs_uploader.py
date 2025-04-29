"""
@file: gcs_uploader.py
@desc: Google Cloud Storageに動画とサムネイルをアップロードするモジュール
"""

import os
import logging
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
from google.cloud import storage
from google.cloud.exceptions import NotFound

# ロガー設定
logger = logging.getLogger(__name__)

class GCSUploader:
    """Google Cloud Storageにファイルをアップロードするクラス"""
    
    def __init__(
        self,
        bucket_name: str,
        credentials_path: Optional[str] = None,
        project_id: Optional[str] = None
    ):
        """
        初期化
        
        Args:
            bucket_name: GCSバケット名
            credentials_path: サービスアカウントJSONのパス
            project_id: GCPプロジェクトID
        """
        self.bucket_name = bucket_name
        
        # 認証情報設定
        if credentials_path:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
        
        self.project_id = project_id or os.environ.get("GCP_PROJECT_ID")
        
        try:
            # ストレージクライアント初期化
            self.client = storage.Client(project=self.project_id)
            
            # バケット存在確認
            try:
                self.bucket = self.client.get_bucket(bucket_name)
                logger.info(f"GCSバケット接続成功: {bucket_name}")
            except NotFound:
                logger.error(f"GCSバケットが見つかりません: {bucket_name}")
                raise
                
        except Exception as e:
            logger.error(f"GCS初期化エラー: {str(e)}")
            raise
    
    def upload_file(
        self,
        local_path: str,
        gcs_path: str,
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None
    ) -> str:
        """
        ファイルをアップロード
        
        Args:
            local_path: ローカルファイルパス
            gcs_path: GCS上のパス
            content_type: コンテンツタイプ
            metadata: メタデータ
            
        Returns:
            アップロードされたGCSのURI
        """
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"ファイルが見つかりません: {local_path}")
        
        try:
            # BLOBの作成
            blob = self.bucket.blob(gcs_path)
            
            # メタデータの設定
            if metadata:
                blob.metadata = metadata
            
            # コンテンツタイプの設定
            if content_type:
                blob.content_type = content_type
            elif gcs_path.endswith('.mp4'):
                blob.content_type = 'video/mp4'
            elif gcs_path.endswith('.jpg') or gcs_path.endswith('.jpeg'):
                blob.content_type = 'image/jpeg'
            elif gcs_path.endswith('.png'):
                blob.content_type = 'image/png'
            
            # アップロード
            blob.upload_from_filename(local_path)
            
            # 公開URLの取得
            gcs_uri = f"gs://{self.bucket_name}/{gcs_path}"
            
            logger.info(f"ファイルアップロード成功: {gcs_uri}")
            
            return gcs_uri
            
        except Exception as e:
            logger.error(f"アップロードエラー: {str(e)}")
            raise
    
    def upload_video_and_thumbnail(
        self,
        video_path: str,
        thumbnail_path: str,
        title: str,
        genre: str,
        channel: str
    ) -> Tuple[str, str]:
        """
        動画とサムネイルをアップロード
        
        Args:
            video_path: 動画のローカルパス
            thumbnail_path: サムネイルのローカルパス
            title: 動画タイトル
            genre: ジャンル
            channel: チャンネル
            
        Returns:
            Tuple[str, str]: アップロードされた動画とサムネイルのGCS URI
        """
        # タイムスタンプを生成（両方のファイルで共通して使用）
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # ファイル名の生成
        video_filename = f"video_{timestamp}.mp4"
        thumbnail_filename = f"thumbnail_{timestamp}.png"
        
        # メタデータの設定
        metadata = {
            "title": title,
            "genre": genre,
            "channel": channel,
            "created_at": datetime.now().isoformat(),
            "content_type": "cosme_shorts_video",
            "timestamp": timestamp
        }
        
        # 動画アップロード
        video_gcs_path = f"videos/{video_filename}"
        video_uri = self.upload_file(
            local_path=video_path,
            gcs_path=video_gcs_path,
            content_type="video/mp4",
            metadata=metadata
        )
        
        # サムネイルアップロード
        thumbnail_gcs_path = f"thumbnails/{thumbnail_filename}"
        thumbnail_uri = self.upload_file(
            local_path=thumbnail_path,
            gcs_path=thumbnail_gcs_path,
            content_type="image/png",
            metadata=metadata
        )
        
        return video_uri, thumbnail_uri
    
    def upload_video(
        self,
        video_path: str,
        title: str,
        genre: str,
        channel: str,
        thumbnail_path: Optional[str] = None
    ) -> str:
        """
        動画をアップロード（後方互換性のために維持）
        
        Args:
            video_path: 動画のローカルパス
            title: 動画タイトル
            genre: ジャンル
            channel: チャンネル
            thumbnail_path: サムネイルのローカルパス（オプション）
            
        Returns:
            str: アップロードされた動画のGCS URI
        """
        # サムネイルが指定されている場合は新しいメソッドを使用
        if thumbnail_path:
            video_uri, _ = self.upload_video_and_thumbnail(
                video_path=video_path,
                thumbnail_path=thumbnail_path,
                title=title,
                genre=genre,
                channel=channel
            )
            return video_uri
        
        # サムネイルが指定されていない場合（従来の動作）
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        video_filename = f"video_{timestamp}.mp4"
        
        # メタデータの設定
        metadata = {
            "title": title,
            "genre": genre,
            "channel": channel,
            "created_at": datetime.now().isoformat(),
            "content_type": "cosme_shorts_video",
            "timestamp": timestamp
        }
        
        # 動画アップロード
        video_gcs_path = f"videos/{video_filename}"
        return self.upload_file(
            local_path=video_path,
            gcs_path=video_gcs_path,
            content_type="video/mp4",
            metadata=metadata
        )