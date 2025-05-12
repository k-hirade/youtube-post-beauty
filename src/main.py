#!/usr/bin/env python3
"""
@file: main.py
@desc: ショート動画を自動生成するメインスクリプト
"""

import os
import random
import sys
import logging
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import subprocess

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 内部モジュールのインポート
from src.scraper.cosme_scraper import CosmeNetScraper
from src.selector.product_selector import ProductSelector
from src.db.database import CosmeDatabase
from src.review.review_generator import ReviewGenerator
from src.video.video_maker import VideoMaker
from src.video.video_maker_chinese import ChineseVideoMaker
from src.uploader.gcs_uploader import GCSUploader
from src.qa.video_qa import VideoQA
# from src.notifier.notifier import Notifier 
# from src.uploader.social_media_poster import SocialMediaPoster
from src.scraper.config_categories import CATEGORY_MAP
from src.scraper.config_categories import CHANNEL_MAP
from src.scraper.config_categories import RANKING_TYPE_MAP

# 環境変数読み込み
from dotenv import load_dotenv
load_dotenv()

# ロガー設定
logger = logging.getLogger(__name__)

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
    parser = argparse.ArgumentParser(description='アットコスメランキングからショート動画を自動生成')
    
    parser.add_argument('--channel', type=str, default='ドラッグストア',
                        choices=list(CHANNEL_MAP.keys()),
                        help='購入場所チャンネル')
    
    parser.add_argument('--genre', type=str, default='美容液',
                        choices=list(CATEGORY_MAP.keys()),
                        help='対象ジャンル')
    
    parser.add_argument('--ranking-type', type=str, default='最新',
                        choices=list(RANKING_TYPE_MAP.keys()),
                        help='最初に試すランキングの種類')
    
    parser.add_argument('--min-products', type=int, default=10,
                        help='最小必要製品数')
    
    parser.add_argument('--max-products', type=int, default=10,
                        help='最大製品数')
    
    parser.add_argument('--db-path', type=str, default='data/cosme.db',
                        help='SQLiteデータベースパス')
    
    parser.add_argument('--log-file', type=str, 
                        default='data/logs/cosme-shorts.log',
                        help='ログファイルパス')
    
    parser.add_argument('--dry-run', action='store_true',
                        help='実際の動画を作成せずテスト実行')
    
    parser.add_argument('--use-alternative-ranking', action='store_true',
                        help='十分な製品数が集まらない場合、代替ランキングタイプも試す')
    
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='詳細なログを出力')
    
    return parser.parse_args()

def run_pipeline(args):
    """メインパイプラインの実行"""
    logger.info(f"処理開始: {args.channel} × {args.genre} × {args.ranking_type}")
    
    # 1. データベース初期化
    db = CosmeDatabase(args.db_path)
    
    # 2. 新しい実行レコードの作成
    run_id = db.create_run(args.genre, args.channel, args.ranking_type)
    if not run_id:
        logger.error("実行レコードの作成に失敗しました。")
        return False
    
    try:
        # 3. スクレイパーの初期化と実行
        scraper = CosmeNetScraper()
        logger.info("ランキング取得開始")
        
        if args.use_alternative_ranking:
            logger.info("代替ランキングタイプの使用が有効です")
            products = scraper.get_products_by_criteria(
                channel=args.channel,
                genre=args.genre,
                ranking_type=args.ranking_type,
                min_count=args.min_products
            )
        else:
            logger.info("単一ランキングタイプからの収集のみを行います")
            # 単一ランキングタイプからのみ収集する場合は古い方法を使用
            products = []
            for page in range(1, 6):
                if len(products) >= args.min_products:
                    break
                
                page_products = scraper.get_ranking_products(
                    channel=args.channel,
                    genre=args.genre,
                    ranking_type=args.ranking_type,
                    week=0,
                    page=page
                )
                
                products.extend(page_products)
                logger.info(f"ページ{page}: {len(page_products)}個取得、合計{len(products)}個")
        
        # 4. 製品情報をデータベースに保存
        success_count = db.save_products(products)
        logger.info(f"製品保存完了: {success_count}/{len(products)}個")

        if len(products) < args.min_products:
            logger.error(f"収集された製品数が最小閾値未満です: {len(products)}/{args.min_products}")
            logger.info("処理を中断し、次の組み合わせに進みます")
            db.update_run_status(run_id, "insufficient_products")
            return False
                
        # 5. セレクターによる製品選定
        selector = ProductSelector(
            min_products=args.min_products,
            max_products=args.max_products
        )
        selected_products = selector.select_products(products, args.channel, args.genre)
        
        if not selected_products:
            logger.error("製品選定に失敗しました。")
            db.update_run_status(run_id, "error")
            return False
        
        # 6. 製品画像をダウンロード（ここで追加）
        temp_image_dir = os.path.join('data', 'temp')
        logger.info(f"製品画像のダウンロード開始: {len(selected_products)}個")
        selected_products = scraper.download_product_images(selected_products, temp_image_dir)
        logger.info("製品画像のダウンロード完了")
        
        # 7. レビュー生成（OpenAI使用）
        review_generator = ReviewGenerator()
        selected_with_reviews = []

        for product in selected_products:
            logger.info(f"レビュー生成: {product['name']}")
            reviews = review_generator.generate_reviews(product)
            
            product["reviews"] = reviews
            
            # レビューをキャッシュに保存
            db.save_reviews(product["product_id"], reviews)
            
            selected_with_reviews.append(product)
                
        # 8. 使用した製品をマーク
        product_ids = [p["product_id"] for p in selected_with_reviews]
        db.mark_products_as_used(product_ids)
        
        # ドライランモードの場合はここまで
        if args.dry_run:
            logger.info("ドライラン実行完了")
            for i, product in enumerate(selected_with_reviews, 1):
                print(f"\n--- 製品 {i} ({product['new_rank']}位) ---")
                print(f"ID: {product['product_id']}")
                print(f"名前: {product['name']}")
                print(f"ブランド: {product['brand']}")
                print(f"画像パス: {product.get('local_image_path', 'なし')}")
                print(f"レビュー:")
                for j, review in enumerate(product['reviews'], 1):
                    print(f"  {j}. {review}")
            
            db.update_run_status(run_id, "success")
            return True

        shuffled_products = random.sample(products, len(products))
        shuffled_products = shuffled_products[:7]
        
        # 9. 動画作成
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        video_filename = f"video_{timestamp}.mp4"
        video_maker = VideoMaker(temp_dir=temp_image_dir)  # temp_dirを明示的に設定
        output_video = video_maker.create_video(
            products=shuffled_products,
            title=f"{args.channel}で買える{args.genre}ランキング",
            channel=args.channel,
            output_filename=video_filename,
        )

        # サムネイルの作成
        thumbnail_filename = f"thumbnail_{timestamp}.png"
        thumbnail_path = os.path.join('data/temp', thumbnail_filename)
        video_maker.save_thumbnail(
            channel=args.channel,
            genre=args.genre,
            output_path=thumbnail_path
        )

        # 10. 中国語翻訳付き動画の作成（追加）
        # chinese_video_path = ""
        # chinese_gcs_uri = ""
        # chinese_output_filename = f"video_chinese_{timestamp}.mp4"
        
        # enable_chinese = os.environ.get("ENABLE_CHINESE_TRANSLATION", "").lower() == "true"
        
        # if enable_chinese:
        #     try:
        #         logger.info("中国語翻訳付き動画の作成を開始します")
                
        #         # 中国語動画メーカーのインスタンス化
        #         chinese_video_maker = ChineseVideoMaker(temp_dir=temp_image_dir)
                
        #         # 日本語と中国語の動画を作成
        #         _, chinese_video_path = chinese_video_maker.create_video_with_chinese(
        #             products=shuffled_products,
        #             title=f"{args.channel}で買える{args.genre}ランキング",
        #             channel=args.channel,
        #             output_filename=video_filename,
        #             chinese_output_filename=chinese_output_filename
        #         )
                
        #         logger.info(f"中国語翻訳付き動画の作成完了: {chinese_video_path}")
        #     except Exception as e:
        #         logger.error(f"中国語翻訳付き動画の作成中にエラーが発生しました: {str(e)}")
        #         import traceback
        #         logger.error(traceback.format_exc())
        # else:
        #     logger.info("中国語翻訳付き動画の作成はスキップされました (ENABLE_CHINESE_TRANSLATION=false)")

        gcs_upload = os.environ.get("GCS_UPLOAD")

        # 11. GCS へアップロード
        jp_gcs_uri = ""  # 日本語版動画のGCS URI
        cn_gcs_uri = ""  # 中国語版動画のGCS URI
        thumbnail_gcs_uri = ""  # サムネイルのGCS URI

        if gcs_upload:
            # GCS認証ファイルパスの確認
            credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
            if not credentials_path or not os.path.exists(credentials_path):
                logger.warning(f"GCS認証ファイルが見つかりません: {credentials_path}")
                logger.warning("GCSアップロードをスキップします")
            else:
                try:
                    logging.info("credentials_pathが存在します。")
                    uploader = GCSUploader(
                        bucket_name=os.environ["GCS_BUCKET"],
                        credentials_path=credentials_path,
                        project_id=os.environ.get("GCP_PROJECT_ID")
                    )
                    
                    # 動画とサムネイルを一緒にアップロード
                    video_uri, thumbnail_uri = uploader.upload_video_and_thumbnail(
                        video_path=output_video,
                        thumbnail_path=thumbnail_path,
                        title=f"{args.channel}で買える{args.genre}ランキング",
                        genre=args.genre,
                        channel=args.channel
                    )
                    jp_gcs_uri = video_uri
                    thumbnail_gcs_uri = thumbnail_uri
                    logger.info(f"GCSアップロード完了: 動画={jp_gcs_uri}, サムネイル={thumbnail_gcs_uri}")
                    
                    # 中国語翻訳付き動画のアップロード
                    # if enable_chinese and chinese_video_path and os.path.exists(chinese_video_path):
                    #     try:
                    #         cn_gcs_uri = uploader.upload_video_chinese(
                    #             video_path=chinese_video_path,
                    #             title=f"{args.channel}で買える{args.genre}ランキング【中文字幕版】",
                    #             genre=args.genre,
                    #             channel=args.channel,
                    #             thumbnail_path=thumbnail_path  # 同じサムネイルを使用
                    #         )
                    #         logger.info(f"中国語動画GCSアップロード完了: {cn_gcs_uri}")
                    #     except Exception as e:
                    #         logger.error(f"中国語動画GCSアップロードエラー: {str(e)}")
                except Exception as e:
                    logger.error(f"GCSアップロード中にエラーが発生しました: {str(e)}")
        else:
            logger.info("GCP upload skipped")

        # 11. Social Media Posting
        social_media_results = None
        # if os.environ.get("ENABLE_SOCIAL_MEDIA").lower() == "true":
        #     try:
        #         social_media_poster = SocialMediaPoster(
        #             enable_youtube=os.environ.get("ENABLE_YOUTUBE_SHORTS", "").lower() == "true",
        #             youtube_client_secrets=os.environ.get("YOUTUBE_CLIENT_SECRETS"),
        #             youtube_token_path=os.environ.get("YOUTUBE_TOKEN"),
        #             target_channel_id=os.environ.get("TARGET_CHANNEL_ID")
        #         )
                
        #         social_media_results = social_media_poster.post_video(
        #             video_path=output_video,
        #             title=f"{args.channel}で買える{args.genre}ランキング",
        #             description=f"{args.channel}で買える人気{args.genre}のランキングをご紹介します！",
        #             thumbnail_path=thumbnail_path,
        #             tags=[args.genre, "ランキング", "コスメ", args.channel]
        #         )
        #         logger.info(f"SNS投稿結果: {social_media_results}")
        #     except Exception as e:
        #         logger.error(f"SNS投稿エラー: {str(e)}")
        #         social_media_results = None
        # else:
        #     logger.info("Social media posting skipped")

        # 12. QA ＋ スプレッドシート登録 (日本語版)
        qa = VideoQA()
        is_ok, metadata, err = qa.validate_video(output_video)
        metadata["products"] = shuffled_products
        qa.add_to_spreadsheet(
            metadata=metadata,
            genre=args.genre,
            channel=args.channel,
            title=f"{args.channel}で買える{args.genre}ランキング",
            ranking_type=args.ranking_type,
            gcs_uri=jp_gcs_uri,  # 日本語版のURIを使用
            thumbnail_gcs_uri=thumbnail_gcs_uri,
            qa_status="OK" if is_ok else "NG",
            notes=err,
            run_id=run_id,
            social_media_results=social_media_results
        )

        # 中国語版のスプレッドシート登録
        # if enable_chinese and chinese_video_path and os.path.exists(chinese_video_path):
        #     try:
        #         chinese_qa = VideoQA()  # 新しいインスタンスを作成
        #         is_ok_cn, metadata_cn, err_cn = chinese_qa.validate_video(chinese_video_path)
        #         # メタデータに製品情報を追加
        #         metadata_cn["products"] = selected_with_reviews
                
        #         # 中国語翻訳付き動画をスプレッドシートに追加
        #         chinese_qa.add_to_chinese_spreadsheet(
        #             metadata=metadata_cn,
        #             genre=args.genre,
        #             channel=args.channel,
        #             title=f"{args.channel}で買える{args.genre}ランキング",
        #             ranking_type=args.ranking_type,
        #             gcs_uri=cn_gcs_uri,  # 中国語版のURIを使用
        #             thumbnail_gcs_uri=thumbnail_gcs_uri,
        #             qa_status="OK" if is_ok_cn else "NG",
        #             notes=err_cn,
        #             run_id=run_id,
        #             social_media_results=None
        #         )
        #         logger.info("中国語翻訳付き動画をスプレッドシートに追加しました")
        #     except Exception as e:
        #         logger.error(f"中国語翻訳付き動画のスプレッドシート追加エラー: {str(e)}")

        # 最終的なステータス更新には日本語版のURIを使用
        db.update_run_status(
            run_id=run_id, 
            status="success", 
            video_gs_uri=jp_gcs_uri,  # 日本語版のURIを使用
            thumbnail_gs_uri=thumbnail_gcs_uri
        )

        return True
        
    except Exception as e:
        logger.exception(f"処理エラー: {str(e)}")
        db.update_run_status(run_id, "error")
        return False

def main():
    """メイン関数"""
    # 引数のパース
    args = parse_args()
    
    # ロギング設定
    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging(args.log_file, log_level)
    
    # 代替ランキングタイプ使用の情報をログに残す
    if args.use_alternative_ranking:
        alternative_ranking = "お好み" if args.ranking_type == "最新" else "最新"
        logger.info(f"代替ランキングタイプ使用モードが有効です。必要に応じて「{alternative_ranking}」ランキングタイプの製品も収集します。")
    else:
        logger.info(f"単一ランキングタイプモード: {args.ranking_type}")
    
    # パイプライン実行
    success = run_pipeline(args)
    
    # 終了コード設定
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    print("Script starting...")
    try:
        main()
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()