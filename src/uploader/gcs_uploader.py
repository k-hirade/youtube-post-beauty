"""
@file: gcs_uploader.py
@desc: Google Cloud Storageに動画をアップロードするモジュール
"""

import os
import logging
from typing import Optional, Dict, Any
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
    
    def get_storage_path(
        self,
        file_name: str,
        prefix: Optional[str] = None,
        use_date_folder: bool = True
    ) -> str:
        """
        GCS上のストレージパスを生成
        
        Args:
            file_name: ファイル名
            prefix: プレフィックス（フォルダパス）
            use_date_folder: 日付フォルダを使用するか
            
        Returns:
            GCSパス
        """
        # ベースパス
        base_path = prefix or ""
        
        # 日付フォルダ
        if use_date_folder:
            date_path = datetime.now().strftime('%Y/%m/%d')
            if base_path:
                base_path = f"{base_path}/{date_path}"
            else:
                base_path = date_path
        
        # 最終パス
        if base_path:
            return f"{base_path}/{file_name}"
        else:
            return file_name
    
    def upload_file(
        self,
        local_path: str,
        gcs_path: Optional[str] = None,
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None
    ) -> str:
        """
        ファイルをアップロード
        
        Args:
            local_path: ローカルファイルパス
            gcs_path: GCS上のパス（Noneの場合はファイル名を使用）
            content_type: コンテンツタイプ
            metadata: メタデータ
            
        Returns:
            アップロードされたGCSのURI
        """
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"ファイルが見つかりません: {local_path}")
        
        # GCSパス未指定の場合はファイル名を使用
        if not gcs_path:
            file_name = os.path.basename(local_path)
            gcs_path = self.get_storage_path(file_name)
        
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
    
    def upload_video(
        self,
        video_path: str,
        title: str,
        genre: str,
        channel: str
    ) -> str:
        """
        動画をアップロード
        
        Args:
            video_path: 動画のローカルパス
            title: 動画タイトル
            genre: ジャンル
            channel: チャンネル
            
        Returns:
            アップロードされたGCSのURI
        """
        # ファイル名の生成
        file_name = os.path.basename(video_path)
        
        # メタデータの設定
        metadata = {
            "title": title,
            "genre": genre,
            "channel": channel,
            "created_at": datetime.now().isoformat(),
            "content_type": "cosme_shorts_video"
        }
        
        # GCSパスの生成
        gcs_path = self.get_storage_path(
            file_name,
            prefix=f"videos/{genre}/{channel}",
            use_date_folder=True
        )
        
        # アップロード
        return self.upload_file(
            local_path=video_path,
            gcs_path=gcs_path,
            content_type="video/mp4",
            metadata=metadata
        )
