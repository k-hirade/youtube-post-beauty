#!/usr/bin/env python
"""
@file: post_specific_video.py
@desc: 特定の動画IDを指定して各ソーシャルメディアに投稿するスクリプト
"""

import os
import sys
import logging
import argparse
from typing import Dict, List, Optional, Any

from social_posts.social_media_scheduler import SocialMediaScheduler

def setup_logging(log_file: Optional[str] = None, log_level: int = logging.INFO):
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

def parse_args():
    """コマンドライン引数のパース"""
    parser = argparse.ArgumentParser(description='特定の動画IDを各ソーシャルメディアに投稿する')
    
    parser.add_argument('--video-id', type=int, required=True,
                        help='投稿する動画のID（必須）')
    
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
                        default='data/logs/post_specific_video.log',
                        help='ログファイルパス')
    
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='詳細なログを出力')
    
    parser.add_argument('--platforms', type=str, 
                        default='youtube,tiktok,instagram,twitter',
                        help='投稿対象プラットフォーム（カンマ区切り）')
    
    parser.add_argument('--force', '-f', action='store_true',
                        help='既に投稿済みでも強制的に再投稿する')
    
    parser.add_argument('--dry-run', action='store_true',
                        help='実際に投稿せずに動作確認のみ行う')
    
    return parser.parse_args()

class VideoPostExecutor:
    """特定の動画を投稿する実行クラス"""
    
    def __init__(
        self,
        video_id: int,
        sheet_id: str,
        credentials_path: str,
        videos_folder: str,
        thumbnails_folder: str,
        youtube_client_secrets: Optional[str] = None,
        youtube_token_path: Optional[str] = None,
        target_channel_id: Optional[str] = None,
        log_file: Optional[str] = None,
        log_level: int = logging.INFO,
        platforms: List[str] = ["tiktok", "instagram", "twitter", "youtube"],
        force_post: bool = False,
        dry_run: bool = False
    ):
        """
        初期化
        
        Args:
            video_id: 投稿対象の動画ID
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
            force_post: 既に投稿済みでも強制的に再投稿するか
            dry_run: 実際に投稿せずに動作確認のみ行うか
        """
        # 設定
        self.video_id = video_id
        self.force_post = force_post
        self.dry_run = dry_run
        
        # ロギング設定
        setup_logging(log_file, log_level)
        self.logger = logging.getLogger(__name__)
        
        # スケジューラーのインスタンス化
        self.scheduler = SocialMediaScheduler(
            sheet_id=sheet_id,
            credentials_path=credentials_path,
            videos_folder=videos_folder,
            thumbnails_folder=thumbnails_folder,
            youtube_client_secrets=youtube_client_secrets,
            youtube_token_path=youtube_token_path,
            target_channel_id=target_channel_id,
            log_file=log_file,
            log_level=log_level,
            platforms=platforms
        )
    
    def find_video_by_id(self) -> Optional[Dict[str, Any]]:
        """
        指定されたIDの動画情報をスプレッドシートから検索する
        
        Returns:
            動画情報 または None
        """
        try:
            # スプレッドシートを開く
            spreadsheet = self.scheduler.sheets_client.open_by_key(self.scheduler.sheet_id)
            
            # 「テストシート」ワークシートを取得
            worksheet = spreadsheet.worksheet("テストシート")
            
            # 全てのデータを取得
            all_data = worksheet.get_all_records()
            
            # 動画IDで検索
            for i, row in enumerate(all_data):
                if int(row.get("動画ID", 0)) == self.video_id:
                    video_info = {
                        "video_id": self.video_id,
                        "title": row.get("タイトル", ""),
                        "video_uri": row.get("GCS動画URI", ""),
                        "thumbnail_uri": row.get("GCSサムネイルURI", ""),
                        "row_index": i + 2  # 1-based indexing + header row
                    }
                    
                    # 各プラットフォームの投稿状況を追加
                    for platform in self.scheduler.platforms:
                        if platform == "youtube":
                            video_info["youtube_uploaded"] = row.get("YouTubeアップロード", "").upper() == "TRUE"
                            video_info["youtube_url"] = row.get("YouTubeURL", "")
                        elif platform == "tiktok":
                            video_info["tiktok_uploaded"] = row.get("TikTokアップロード", "").upper() == "TRUE"
                            video_info["tiktok_url"] = row.get("TikTok URL", "")
                        elif platform == "instagram":
                            video_info["instagram_uploaded"] = row.get("Instagramアップロード", "").upper() == "TRUE"
                            video_info["instagram_url"] = row.get("Instagram URL", "")
                        elif platform == "twitter":
                            video_info["twitter_uploaded"] = row.get("Xアップロード", "").upper() == "TRUE"
                            video_info["twitter_url"] = row.get("X URL", "")
                    
                    return video_info
            
            self.logger.error(f"動画ID {self.video_id} が見つかりませんでした")
            return None
            
        except Exception as e:
            self.logger.error(f"動画検索エラー: {str(e)}")
            return None
    
    def execute(self) -> bool:
        """
        指定された動画IDの投稿を実行
        
        Returns:
            成功したかどうか
        """
        self.logger.info(f"動画ID {self.video_id} の投稿処理を開始します")
        
        # 動画情報を取得
        video = self.find_video_by_id()
        if not video:
            self.logger.error(f"動画ID {self.video_id} の情報が取得できませんでした")
            return False
        
        self.logger.info(f"動画情報: タイトル={video['title']}, URI={video['video_uri']}")
        
        # 既に投稿済みかどうかチェック
        already_posted = {}
        for platform in self.scheduler.platforms:
            if platform == "youtube":
                already_posted[platform] = video["youtube_uploaded"]
            elif platform == "tiktok":
                already_posted[platform] = video["tiktok_uploaded"]
            elif platform == "instagram":
                already_posted[platform] = video["instagram_uploaded"]
            elif platform == "twitter":
                already_posted[platform] = video["twitter_uploaded"]
        
        # 投稿状況のログ
        for platform, posted in already_posted.items():
            self.logger.info(f"{platform}への投稿状況: {'投稿済み' if posted else '未投稿'}")
        
        # ドライランモードの場合
        if self.dry_run:
            self.logger.info("ドライランモードのため、実際の投稿は行いません")
            for platform in self.scheduler.platforms:
                if already_posted[platform] and not self.force_post:
                    self.logger.info(f"{platform}は既に投稿済みのためスキップします")
                else:
                    self.logger.info(f"{platform}への投稿をシミュレートします")
            return True
        
        # 強制投稿モードの処理
        if self.force_post:
            for platform in self.scheduler.platforms:
                if platform == "youtube":
                    video["youtube_uploaded"] = False
                elif platform == "tiktok":
                    video["tiktok_uploaded"] = False
                elif platform == "instagram":
                    video["instagram_uploaded"] = False
                elif platform == "twitter":
                    video["twitter_uploaded"] = False
            
            self.logger.info("強制投稿モードが有効: 全プラットフォームに再投稿します")
        
        # 全プラットフォームに投稿
        results = self.scheduler.post_to_all_platforms(video)
        
        # 結果を確認
        success = True
        for platform, result in results.items():
            if result.get("success", False):
                if result.get("already_posted", False):
                    self.logger.info(f"{platform}は既に投稿済みでした")
                else:
                    self.logger.info(f"{platform}への投稿が成功しました: URL={result.get('url', 'N/A')}")
            else:
                self.logger.error(f"{platform}への投稿が失敗しました: エラー={result.get('error', 'N/A')}")
                success = False
        
        return success

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
    
    # 投稿実行クラスのインスタンス化と実行
    executor = VideoPostExecutor(
        video_id=args.video_id,
        sheet_id=args.sheet_id,
        credentials_path=args.credentials,
        videos_folder=args.videos_folder,
        thumbnails_folder=args.thumbnails_folder,
        youtube_client_secrets=args.youtube_client_secrets,
        youtube_token_path=args.youtube_token,
        target_channel_id=args.target_channel_id,
        log_file=args.log_file,
        log_level=log_level,
        platforms=platforms,
        force_post=args.force,
        dry_run=args.dry_run
    )
    
    # 実行
    success = executor.execute()
    
    # 終了ステータス
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()