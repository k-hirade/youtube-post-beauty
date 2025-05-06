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
import json

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
        spreadsheet_id: Optional[str] = None
    ):
        """
        初期化
        
        Args:
            ffprobe_path: ffprobeのパス
            credentials_path: Google APIの認証情報JSONのパス
            spreadsheet_id: スプレッドシートID
        """
        # ffprobeのパス設定
        self.ffprobe_path = ffprobe_path or "ffprobe"
        
        # Google Sheets関連
        self.credentials_path = credentials_path or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        self.spreadsheet_id = spreadsheet_id or os.environ.get("SHEET_ID")
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
        max_duration: float = 120.0
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

    # ハッシュタグを生成する新しいヘルパー関数
    def _generate_hashtags(self, genre: str, channel: str, ranking_type: str) -> str:
        """
        動画の概要欄用のハッシュタグを生成
        
        Args:
            genre: 製品ジャンル
            channel: 購入場所チャンネル
            ranking_type: ランキングタイプ
            
        Returns:
            ハッシュタグ文字列
        """
        # 定型ハッシュタグ（7個）
        standard_tags = [
            "#コスメ",
            "#美容",
            "#スキンケア",
            "#ランキング",
            "#おすすめ",
            "#プチプラ",
            "#縦型動画"
        ]


        if ranking_type == "お好み":
            ranking_type = "人気"
        
        # 動的ハッシュタグ（3個）
        dynamic_tags = [
            f"#{genre}",
            f"#{ranking_type}ランキング",
            f"#{channel}"
        ]
        
        # 全てのハッシュタグを結合
        all_tags = standard_tags + dynamic_tags
        return " ".join(all_tags)

    # タイトルを新しいフォーマットに変換するヘルパー関数
    def _format_title(self, channel: str, genre: str) -> str:
        """
        動画タイトルを指定のフォーマットで生成
        
        Args:
            channel: 購入場所チャンネル
            genre: 製品ジャンル
            
        Returns:
            フォーマット済みタイトル
        """
        return f"一度はマジで使ってみて欲しい{channel}で買える神{genre}7選"

    def add_to_spreadsheet(
        self,
        metadata: Dict[str, Any],
        genre: str,
        channel: str,
        title: str,
        ranking_type: str,
        gcs_uri: Optional[str] = None,
        qa_status: str = "OK",
        notes: str = "",
        thumbnail_gcs_uri: Optional[str] = None,
        run_id: Optional[int] = None,
        social_media_results: Optional[Dict[str, Dict[str, str]]] = None
    ) -> bool:
        """
        スプレッドシートに動画情報を追加
        
        Args:
            metadata: 動画メタデータ
            genre: ジャンル
            channel: チャンネル
            title: タイトル
            ranking_type: ランキングタイプ
            gcs_uri: GCS URI（動画）
            qa_status: 検証ステータス
            notes: 備考
            thumbnail_gcs_uri: サムネイルのGCS URI
            run_id: 実行ID
            social_media_results: SNSアップロード結果
            
        Returns:
            成功したかどうか
        """
        if not self.sheets_client or not self.spreadsheet_id:
            logger.warning("Google Sheets連携が設定されていません")
            return False
        
        try:
            # スプレッドシートを開く
            spreadsheet = self.sheets_client.open_by_key(self.spreadsheet_id)
            
            # 「動画一覧」ワークシートを取得（なければ作成）
            try:
                worksheet = spreadsheet.worksheet("動画一覧")
            except gspread.exceptions.WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet(
                    title="動画一覧",
                    rows=1000,
                    cols=28
                )
                
                # ヘッダー設定
                header = [
                    "動画ID", "タイムスタンプ", "タイトル", "概要欄", "ジャンル", "チャンネル", "ランキングタイプ",
                    "GCS動画URI", "GCSサムネイルURI",
                    "YouTubeアップロード", "YouTube URL", "YouTube 動画ID",
                    "TikTokアップロード", "TikTok URL", 
                    "Instagramアップロード", "Instagram URL",
                    "Xアップロード", "X URL",
                    "QAステータス", "エラー詳細", "実行ID", "動画時間", 
                    "メタデータ", "備考", 
                ]
                worksheet.append_row(header)
            
            # タイムスタンプの作成
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            
            # YouTube情報の取得
            youtube_uploaded = "FALSE"
            youtube_url = ""
            youtube_id = ""
            
            # TikTok情報の取得
            tiktok_uploaded = "FALSE"
            tiktok_url = ""
            
            # Instagram情報の取得
            instagram_uploaded = "FALSE"
            instagram_url = ""
            
            # X情報の取得
            x_uploaded = "FALSE"
            x_url = ""
            
            # ソーシャルメディア結果の処理
            if social_media_results:
                # YouTube
                if social_media_results.get("youtube", {}).get("success", False):
                    youtube_uploaded = "TRUE"
                    youtube_id = social_media_results["youtube"].get("id", "")
                    youtube_url = social_media_results["youtube"].get("url", "")
                
                # TikTok
                if social_media_results.get("tiktok", {}).get("success", False):
                    tiktok_uploaded = "TRUE"
                    tiktok_url = social_media_results["tiktok"].get("url", "")
                
                # Instagram
                if social_media_results.get("instagram", {}).get("success", False):
                    instagram_uploaded = "TRUE"
                    instagram_url = social_media_results["instagram"].get("url", "")
                    
                # X
                if social_media_results.get("x", {}).get("success", False):
                    x_uploaded = "TRUE"
                    x_url = social_media_results["x"].get("url", "")
            
            # メタデータをJSON形式に変換
            metadata_json = json.dumps(metadata)
            
            # GCS URIのフォーマット変更
            formatted_gcs_uri = ""
            if gcs_uri and gcs_uri.startswith("gs://"):
                formatted_gcs_uri = gcs_uri.replace("gs://", "https://storage.cloud.google.com/")
            else:
                formatted_gcs_uri = gcs_uri or ''
                
            formatted_thumbnail_gcs_uri = ""
            if thumbnail_gcs_uri and thumbnail_gcs_uri.startswith("gs://"):
                formatted_thumbnail_gcs_uri = thumbnail_gcs_uri.replace("gs://", "https://storage.cloud.google.com/")
            else:
                formatted_thumbnail_gcs_uri = thumbnail_gcs_uri or ''
            
            # 前回の最大動画IDを取得
            try:
                all_rows = worksheet.get_all_values()
                if len(all_rows) > 1:  # ヘッダー行を除く
                    # 最後の行の動画ID（最初の列）を取得
                    last_video_id = all_rows[-1][0]
                    # 数値に変換
                    if last_video_id and last_video_id.isdigit():
                        video_id = int(last_video_id) + 1
                    else:
                        video_id = 1
                else:
                    video_id = 1
            except Exception as e:
                logger.error(f"動画ID取得エラー: {str(e)}")
                video_id = 1
            
            # 新しいタイトルフォーマットを適用
            formatted_title = self._format_title(channel, genre)
            
            # 概要欄のハッシュタグを生成
            description_hashtags = self._generate_hashtags(genre, channel, ranking_type)
            
            # データ行作成（概要欄カラムを追加）
            row = [
                str(video_id),  # 動画ID
                timestamp,
                formatted_title,
                description_hashtags,
                genre,
                channel,
                ranking_type,
                formatted_gcs_uri,
                formatted_thumbnail_gcs_uri,
                youtube_uploaded,
                youtube_url,
                youtube_id,
                tiktok_uploaded,
                tiktok_url,
                instagram_uploaded,
                instagram_url,
                x_uploaded,
                x_url,
                qa_status,
                notes,
                run_id or '',
                f"{metadata.get('duration', 0):.2f}",
                metadata_json,
                "",  # 備考
            ]

            try:
                # スプレッドシートに追加
                response = worksheet.append_row(row)
                logger.info(f"スプレッドシートに追加成功: {formatted_title}, 動画ID: {video_id}")

            except Exception as sheet_error:
                logger.error(f"スプレッドシート行追加エラー: {type(sheet_error).__name__}: {str(sheet_error)}")
                pass
            
            # 製品情報が含まれている場合は「使用製品」ワークシートにも追加
            if "products" in metadata and isinstance(metadata["products"], list):
                self._add_products_to_spreadsheet(spreadsheet, video_id, metadata["products"])
            
            return True
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"スプレッドシート追加エラー詳細:\n{error_details}")
            return False

    def _add_products_to_spreadsheet(
        self,
        spreadsheet: Any,
        video_id: int,
        products: List[Dict[str, Any]]
    ) -> bool:
        """
        「使用製品」ワークシートに製品情報を追加
        
        Args:
            spreadsheet: スプレッドシートオブジェクト
            video_id: 動画ID
            products: 製品情報のリスト
            
        Returns:
            成功したかどうか
        """
        try:
            # 「使用製品」ワークシートを取得（なければ作成）
            try:
                worksheet = spreadsheet.worksheet("使用製品")
            except gspread.exceptions.WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet(
                    title="使用製品",
                    rows=1000,
                    cols=6  # カラム数を7から6に変更（ランク列を削除）
                )
                
                # ヘッダー設定（ランク列を削除）
                header = [
                    "動画ID", "製品ID", "製品名", "ブランド", "画像URL", "製品URL"
                ]
                worksheet.append_row(header)
            
            # 各製品情報を追加
            for product in products:
                row = [
                    str(video_id),
                    product.get("product_id", ""),
                    # "ランク" 列を削除
                    product.get("name", ""),
                    product.get("brand", ""),
                    product.get("image_url", ""),
                    product.get("url", "")
                ]
                
                worksheet.append_row(row)
            
            logger.info(f"使用製品情報をスプレッドシートに追加成功: 動画ID {video_id}, 製品数 {len(products)}")
            return True
            
        except Exception as e:
            logger.error(f"製品情報追加エラー: {str(e)}")
            return False

    def add_performance_data(
        self,
        video_id: int,
        platform: str,
        view_count: int,
        like_count: int,
        comment_count: int,
        share_count: int,
        ctr: float = 0.0,
        avg_watch_time: float = 0.0
    ) -> bool:
        """
        「パフォーマンス分析」ワークシートにデータを追加
        
        Args:
            video_id: 動画ID
            platform: プラットフォーム名
            view_count: 再生回数
            like_count: いいね数
            comment_count: コメント数
            share_count: シェア数
            ctr: クリック率
            avg_watch_time: 平均視聴時間
            
        Returns:
            成功したかどうか
        """
        if not self.sheets_client or not self.spreadsheet_id:
            logger.warning("Google Sheets連携が設定されていません")
            return False
        
        try:
            # スプレッドシートを開く
            spreadsheet = self.sheets_client.open_by_key(self.spreadsheet_id)
            
            # 「パフォーマンス分析」ワークシートを取得（なければ作成）
            try:
                worksheet = spreadsheet.worksheet("パフォーマンス分析")
            except gspread.exceptions.WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet(
                    title="パフォーマンス分析",
                    rows=1000,
                    cols=8
                )
                
                # ヘッダー設定
                header = [
                    "動画ID", "プラットフォーム", "計測日", "再生回数", 
                    "いいね数", "コメント数", "シェア数", "CTR", "平均視聴時間"
                ]
                worksheet.append_row(header)
            
            # 現在日時
            today = datetime.now().strftime('%Y-%m-%d')
            
            # データ行作成
            row = [
                str(video_id),
                platform,
                today,
                str(view_count),
                str(like_count),
                str(comment_count),
                str(share_count),
                f"{ctr:.2f}",
                f"{avg_watch_time:.2f}"
            ]
            
            # スプレッドシートに追加
            worksheet.append_row(row)
            
            logger.info(f"パフォーマンスデータをスプレッドシートに追加成功: 動画ID {video_id}, プラットフォーム {platform}")
            return True
            
        except Exception as e:
            logger.error(f"パフォーマンスデータ追加エラー: {str(e)}")
            return False

    def add_publishing_schedule(
        self,
        video_id: int,
        publish_date: str,
        platform: str,
        status: str = "未公開",
        assignee: str = "",
        reminder: bool = False,
        notes: str = ""
    ) -> bool:
        """
        「公開スケジュール」ワークシートにデータを追加
        
        Args:
            video_id: 動画ID
            publish_date: 公開予定日 (YYYY-MM-DD形式)
            platform: 公開プラットフォーム
            status: 公開ステータス
            assignee: 担当者
            reminder: リマインダー設定
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
            
            # 「公開スケジュール」ワークシートを取得（なければ作成）
            try:
                worksheet = spreadsheet.worksheet("公開スケジュール")
            except gspread.exceptions.WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet(
                    title="公開スケジュール",
                    rows=1000,
                    cols=7
                )
                
                # ヘッダー設定
                header = [
                    "動画ID", "予定公開日", "公開プラットフォーム", 
                    "公開ステータス", "担当者", "リマインダー", "備考"
                ]
                worksheet.append_row(header)
            
            # データ行作成
            row = [
                str(video_id),
                publish_date,
                platform,
                status,
                assignee,
                "TRUE" if reminder else "FALSE",
                notes
            ]
            
            # スプレッドシートに追加
            worksheet.append_row(row)
            
            logger.info(f"公開スケジュールをスプレッドシートに追加成功: 動画ID {video_id}, 予定日 {publish_date}")
            return True
            
        except Exception as e:
            logger.error(f"公開スケジュール追加エラー: {str(e)}")
            return False