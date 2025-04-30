#!/usr/bin/env python3
"""
@file: run_all_combinations.py
@desc: 複数の条件でmain.pyを実行するスクリプト
"""

import os
import subprocess
import sys
import time
import logging
from datetime import datetime

# ロガー設定
logger = logging.getLogger(__name__)

def setup_logging(log_file=None, log_level=logging.INFO):
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

# 購入場所チャンネルマッピング
CHANNELS = [
    "ドラッグストア",
    "コンビニ",
    "デパート"
]

# ランキングタイプマッピング
RANKING_TYPES = [
    "最新",
    "お好み"
]

# カテゴリーマッピング
CATEGORIES = [
    "乳液",
    "美容液",
    "リップ"
]

def run_main_with_params(channel, ranking_type, genre):
    """指定されたパラメータでmain.pyを実行"""
    command = [
        "python", "main.py",
        "--channel", channel,
        "--ranking-type", ranking_type,
        "--genre", genre
        # 他の引数はデフォルト値を使用
    ]
    
    logger.info(f"実行: {' '.join(command)}")
    
    try:
        # サブプロセスとして実行し、出力を取得
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # リアルタイムで出力を表示
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                logger.info(output.strip())
        
        # エラー出力がある場合は表示
        stderr = process.stderr.read()
        if stderr:
            logger.error(stderr)
        
        # 終了コードを確認
        return_code = process.poll()
        if return_code == 0:
            logger.info(f"成功: {channel} × {ranking_type} × {genre}")
            return True
        else:
            logger.error(f"失敗: {channel} × {ranking_type} × {genre}, 終了コード: {return_code}")
            return False
    
    except Exception as e:
        logger.exception(f"エラー: {channel} × {ranking_type} × {genre}, {str(e)}")
        return False

def main():
    """すべての組み合わせでmain.pyを実行"""
    # ロギング設定
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = f"data/logs/combinations_{timestamp}.log"
    setup_logging(log_file)
    
    logger.info("複数条件での実行開始")
    
    # 実行結果を記録
    results = []
    
    # 全ての組み合わせで実行
    total_combinations = len(CHANNELS) * len(RANKING_TYPES) * len(CATEGORIES)
    current = 0
    
    for channel in CHANNELS:
        for ranking_type in RANKING_TYPES:
            for genre in CATEGORIES:
                current += 1
                logger.info(f"処理: {current}/{total_combinations} - {channel} × {ranking_type} × {genre}")
                
                # 実行
                success = run_main_with_params(channel, ranking_type, genre)
                
                # 結果を記録
                results.append({
                    "channel": channel,
                    "ranking_type": ranking_type,
                    "genre": genre,
                    "success": success
                })
                
                # 各実行の間に少し待機（サーバー負荷軽減）
                time.sleep(10)
    
    # 実行結果のサマリー表示
    logger.info("\n--- 実行結果サマリー ---")
    success_count = sum(1 for r in results if r["success"])
    logger.info(f"成功: {success_count}/{len(results)}")
    
    if success_count < len(results):
        logger.info("\n--- 失敗した実行 ---")
        for r in results:
            if not r["success"]:
                logger.info(f"{r['channel']} × {r['ranking_type']} × {r['genre']}")
    
    logger.info("すべての実行が完了しました")

if __name__ == "__main__":
    main()