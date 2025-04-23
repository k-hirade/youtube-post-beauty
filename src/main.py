#!/usr/bin/env python3
"""
@file: main.py
@desc: ショート動画を自動生成するメインスクリプト
"""

import os
import sys
import logging
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 内部モジュールのインポート
from src.scraper.cosme_scraper import CosmeNetScraper
from src.selector.product_selector import ProductSelector
from src.db.database import CosmeDatabase
from src.review.review_generator import ReviewGenerator
from src.video.video_maker import VideoMaker
from src.uploader.gcs_uploader import GCSUploader
from src.qa.video_qa import VideoQA
from src.notifier.notifier import Notifier

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
    
    parser.add_argument('--channel', type=str, default='スーパー',
                        choices=['スーパー'],
                        help='購入場所チャンネル')
    
    parser.add_argument('--genre', type=str, default='乳液',
                        choices=['化粧水', '乳液', 'パック'],
                        help='対象ジャンル')
    
    parser.add_argument('--min-products', type=int, default=7,
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
    
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='詳細なログを出力')
    
    return parser.parse_args()

def run_pipeline(args):
    """メインパイプラインの実行"""
    logger.info(f"処理開始: {args.channel} × {args.genre}")
    
    # 1. データベース初期化
    db = CosmeDatabase(args.db_path)
    
    # 2. 新しい実行レコードの作成
    run_id = db.create_run(args.genre, args.channel)
    if not run_id:
        logger.error("実行レコードの作成に失敗しました。")
        return False
    
    try:
        # 3. スクレイパーの初期化と実行
        scraper = CosmeNetScraper()
        logger.info("ランキング取得開始")
        products = scraper.get_products_by_criteria(
            channel=args.channel,
            genre=args.genre,
            min_count=args.min_products
        )
        
        if not products or len(products) < args.min_products:
            logger.error(f"十分な製品({args.min_products}個)が見つかりませんでした: {len(products)}個")
            db.update_run_status(run_id, "error")
            return False
        
        logger.info(f"製品取得完了: {len(products)}個")
        
        # 4. 製品情報をデータベースに保存
        success_count = db.save_products(products)
        logger.info(f"製品保存完了: {success_count}/{len(products)}個")
        
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
        
        # 9. 動画作成
        video_maker = VideoMaker(temp_dir=temp_image_dir)  # temp_dirを明示的に設定
        output_video = video_maker.create_video(
            products=selected_with_reviews,
            title=f"{args.channel}で買える{args.genre}ランキング",
        )

        # 10. GCS へアップロード
        uploader = GCSUploader(
            bucket_name=os.environ["GCS_BUCKET"],
            credentials_path=os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"),
            project_id=os.environ.get("GCP_PROJECT_ID")
        )
        gcs_uri = uploader.upload_video(
            video_path=output_video,
            title=os.path.basename(output_video),
            genre=args.genre,
            channel=args.channel
        )

        # 11. QA ＋ スプレッドシート登録
        qa = VideoQA()
        is_ok, meta, err = qa.validate_video(output_video)
        qa.add_to_spreadsheet(
            metadata=meta,
            genre=args.genre,
            channel=args.channel,
            title=os.path.basename(output_video),
            gcs_uri=gcs_uri,
            qa_status="OK" if is_ok else "NG",
            notes=err
        )

        # 12. 通知
        notifier = Notifier()
        if is_ok:
            notifier.notify_video_created(
                title=os.path.basename(output_video),
                video_path=output_video,
                gcs_uri=gcs_uri,
                products=selected_with_reviews
            )
        else:
            notifier.notify_error(
                title="動画QA失敗",
                error_message=err
            )

        db.update_run_status(run_id, "success", video_gs_uri=gcs_uri)
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