"""
@file: video_qa.py
@desc: 作成した動画の品質を検証するモジュール
"""

import os
import logging
import json
import subprocess
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

# Google Sheets連携
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# ロガー設定
logger = logging.getLogger(__name__)

class VideoQA:
    """動画品質検証を行うクラス"""
    
    def __init__(
        self,
        ffprobe_path: Optional[str] = None,
        credentials_path: Optional[str] = None,
        spreadsheet_id: Optional[str] = None,
        worksheet_name: Optional[str] = "VideoQA"
    ):
        """
        初期化
        
        Args:
            ffprobe_path: ffprobeのパス
            credentials_path: Google APIの認証情報JSONのパス
            spreadsheet_id: スプレッドシートID
            worksheet_name: ワークシート名
        """
        # ffprobeのパス設定
        self.ffprobe_path = ffprobe_path or "ffprobe"
        
        # Google Sheets関連
        self.credentials_path = credentials_path or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        self.spreadsheet_id = spreadsheet_id or os.environ.get("SHEET_ID")
        self.worksheet_name = worksheet_name
        self.sheets_client = None
        
        # Google Sheets初期化
        if self.credentials_path and self.spreadsheet_id:
            try:
                self._init_google_sheets()
                logger.info("Google Sheets連携初期化成功")
            except Exception as e:
                logger.error(f"Google Sheets初期化エラー: {str(e)}")
    
    def _init_google_sheets(self):
        """Google Sheets APIクライアントの初期化"""
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        
        creds = Credentials.from_service_account_file(
            self.credentials_path, scopes=scopes
        )
        
        self.sheets_client = gspread.authorize(creds)
    
    def _get_video_metadata(self, video_path: str) -> Dict[str, Any]:
        """
        ffprobeを使って動画メタデータを取得
        
        Args:
            video_path: 動画ファイルパス
            
        Returns:
            動画メタデータ辞書
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"動画ファイルが見つかりません: {video_path}")
        
        try:
            # ffprobeコマンド実行
            cmd = [
                self.ffprobe_path,
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                video_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            
            # 必要なメタデータを抽出
            metadata = {
                "path": video_path,
                "filename": os.path.basename(video_path),
                "format": data.get("format", {}).get("format_name", "unknown"),
                "duration": float(data.get("format", {}).get("duration", 0)),
                "size_bytes": int(data.get("format", {}).get("size", 0)),
                "bitrate": int(data.get("format", {}).get("bit_rate", 0)),
                "streams": []
            }
            
            # 映像・音声ストリーム情報
            for stream in data.get("streams", []):
                stream_type = stream.get("codec_type")
                
                if stream_type == "video":
                    metadata["video_codec"] = stream.get("codec_name")
                    metadata["width"] = stream.get("width")
                    metadata["height"] = stream.get("height")
                    metadata["fps"] = eval(stream.get("r_frame_rate", "0/1"))  # "30/1" → 30.0
                    metadata["streams"].append({
                        "type": "video",
                        "codec": stream.get("codec_name"),
                        "width": stream.get("width"),
                        "height": stream.get("height"),
                        "fps": eval(stream.get("r_frame_rate", "0/1"))
                    })
                
                elif stream_type == "audio":
                    metadata["audio_codec"] = stream.get("codec_name")
                    metadata["audio_channels"] = stream.get("channels")
                    metadata["audio_sample_rate"] = stream.get("sample_rate")
                    metadata["streams"].append({
                        "type": "audio",
                        "codec": stream.get("codec_name"),
                        "channels": stream.get("channels"),
                        "sample_rate": stream.get("sample_rate")
                    })
            
            return metadata
            
        except subprocess.CalledProcessError as e:
            logger.error(f"ffprobe実行エラー: {str(e)}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"ffprobe結果解析エラー: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"メタデータ取得エラー: {str(e)}")
            raise
    
    def validate_video(
        self,
        video_path: str,
        expected_width: int = 1080,
        expected_height: int = 1920,
        min_duration: float = 10.0,
        max_duration: float = 60.0
    ) -> Tuple[bool, Dict[str, Any], str]:
        """
        動画が期待する仕様を満たしているか検証
        
        Args:
            video_path: 動画ファイルパス
            expected_width: 期待する幅
            expected_height: 期待する高さ
            min_duration: 最小長さ（秒）
            max_duration: 最大長さ（秒）
            
        Returns:
            (検証結果, メタデータ, エラーメッセージ)
        """
        try:
            # メタデータ取得
            metadata = self._get_video_metadata(video_path)
            
            # 検証結果
            is_valid = True
            error_messages = []
            
            # 解像度チェック
            if metadata.get("width") != expected_width or metadata.get("height") != expected_height:
                is_valid = False
                error_messages.append(
                    f"解像度不一致: 期待={expected_width}x{expected_height}, "
                    f"実際={metadata.get('width')}x{metadata.get('height')}"
                )
            
            # 長さチェック
            duration = metadata.get("duration", 0)
            if duration < min_duration:
                is_valid = False
                error_messages.append(
                    f"動画が短すぎます: {duration:.2f}秒 < {min_duration}秒"
                )
            
            if duration > max_duration:
                is_valid = False
                error_messages.append(
                    f"動画が長すぎます: {duration:.2f}秒 > {max_duration}秒"
                )
            
            # 映像・音声ストリームの存在チェック
            if "video_codec" not in metadata:
                is_valid = False
                error_messages.append("映像ストリームがありません")
            
            if "audio_codec" not in metadata:
                is_valid = False
                error_messages.append("音声ストリームがありません")
            
            # 結果を返す
            return is_valid, metadata, "\n".join(error_messages)
            
        except Exception as e:
            logger.error(f"動画検証エラー: {str(e)}")
            return False, {}, f"検証処理エラー: {str(e)}"
    
    def add_to_spreadsheet(
        self,
        metadata: Dict[str, Any],
        genre: str,
        channel: str,
        title: str,
        gcs_uri: Optional[str] = None,
        qa_status: str = "OK",
        notes: str = ""
    ) -> bool:
        """
        スプレッドシートに動画情報を追加
        
        Args:
            metadata: 動画メタデータ
            genre: ジャンル
            channel: チャンネル
            title: タイトル
            gcs_uri: GCS URI
            qa_status: 検証ステータス
            notes: 備考
            
        Returns:
            成功したかどうか
        """
        if not self.sheets_client or not self.spreadsheet_id:
            logger.warning("Google Sheets連携が設定されていません")
            return False
        
        try:
            # スプレッドシートを開く
            spreadsheet = self.sheets_client.open_by_key(self.spreadsheet_id)
            
            # ワークシートを取得（なければ作成）
            try:
                worksheet = spreadsheet.worksheet(self.worksheet_name)
            except gspread.exceptions.WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet(
                    title=self.worksheet_name,
                    rows=1000,
                    cols=10
                )
                
                # ヘッダー設定
                header = [
                    "タイムスタンプ", "タイトル", "ジャンル", "チャンネル", 
                    "ファイル名", "長さ(秒)", "解像度", "サイズ(MB)",
                    "GCS URI", "QAステータス", "備考"
                ]
                worksheet.append_row(header)
            
            # データ行作成
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            resolution = f"{metadata.get('width', 0)}x{metadata.get('height', 0)}"
            size_mb = metadata.get('size_bytes', 0) / (1024 * 1024)
            
            row = [
                now,
                title,
                genre,
                channel,
                metadata.get('filename', ''),
                f"{metadata.get('duration', 0):.2f}",
                resolution,
                f"{size_mb:.2f}",
                gcs_uri or '',
                qa_status,
                notes
            ]
            
            # スプレッドシートに追加
            worksheet.append_row(row)
            
            logger.info(f"スプレッドシートに追加成功: {title}")
            return True
            
        except Exception as e:
            logger.error(f"スプレッドシート追加エラー: {str(e)}")
            return False
