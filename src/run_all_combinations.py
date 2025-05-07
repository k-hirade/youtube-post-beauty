#!/usr/bin/env python3
"""
@file: run_all_combinations.py
@desc: 各種組み合わせでmain.pyを実行するスクリプト
run: python run_all_combinations.py --use-alternative-ranking
"""

import os
import sys
import argparse
import subprocess
import itertools
from datetime import datetime

# チャンネル設定
CHANNEL_MAP = {
    "ドラッグストア": "ドラッグストア",
    # "コンビニ": "コンビニ",
    # "デパート": "デパート"
}

# ランキングタイプ設定
RANKING_TYPE_MAP = {
    # "最新": "最新",
    "お好み": "お好み"
}

# カテゴリー設定
CATEGORY_MAP = {
    # "洗顔": "洗顔",
    # "化粧水": "化粧水",
    # "導入化粧水": "導入化粧水",
    # "乳液": "乳液",
    # "美容液": "美容液",
    # "まつげ美容液": "まつげ美容液",
    # "フェイスクリーム": "フェイスクリーム",
    # "クレンジング": "クレンジング",
    # "フェイスパック": "フェイスパック",
    # "ファンデーション": "ファンデーション",
    # "アイケア": "アイケア",
    # "リップ": "リップ",
    # "顔用日焼け止め": "顔用日焼け止め",
    # "ボディ日焼け止め": "ボディ日焼け止め",
    # "アイブロウペンシル": "アイブロウペンシル",
    # "パウダーアイブロウ": "パウダーアイブロウ",
    # "マスカラ": "マスカラ",
    "眉マスカラ": "眉マスカラ",
    "マスカラ下地": "マスカラ下地",
    "口紅": "口紅",
    "リップグロス": "リップグロス",
    "リップライナー": "リップライナー",
    "アイライナー": "アイライナー",
    "アイシャドウ": "アイシャドウ",
    "チーク": "チーク",
    "化粧下地": "化粧下地",
    "コンシーラー": "コンシーラー",
    "フェイスパウダー": "フェイスパウダー",
    "香水": "香水",
    "シャンプー": "シャンプー",
    "トリートメント": "トリートメント",
    "ヘアオイル": "ヘアオイル",
    "頭皮ケア": "頭皮ケア",
    "ヘアスタイリング": "ヘアスタイリング",
    "ボディローション": "ボディローション",
    "ボディクリーム": "ボディクリーム",
    "ボディソープ": "ボディソープ",
    "歯磨き粉": "歯磨き粉",
    "歯ブラシ": "歯ブラシ",
    "マウスウォッシュ": "マウスウォッシュ",
    "デコルテケア": "デコルテケア",
    "バスト・ヒップケア": "バスト・ヒップケア",
    "ハンドクリーム": "ハンドクリーム",
    "入浴剤": "入浴剤",
    "ムダ毛ケア": "ムダ毛ケア",
    "デオドラント": "デオドラント",
    "コットン": "コットン",
    "あぶらとり紙": "あぶらとり紙",
    "美容家電": "美容家電",
    "ピューラー": "ピューラー",
    "パフ・スポンジ": "パフ・スポンジ",
    "つけまつげ": "つけまつげ",
    "二重グッズ": "二重グッズ",
    "ヘアケア": "ヘアケア",
    "美肌サプリ": "美肌サプリ",
    "ダイエットサプリ": "ダイエットサプリ",
    "健康サプリ": "健康サプリ"
}

def parse_args():
    """コマンドライン引数のパース"""
    parser = argparse.ArgumentParser(description='各種組み合わせでmain.pyを実行するスクリプト')
    
    parser.add_argument('--dry-run', action='store_true',
                        help='実際のコマンドを実行せずに表示のみ')
    
    parser.add_argument('--use-alternative-ranking', action='store_true',
                        help='十分な製品数が集まらない場合、代替ランキングタイプも試す')
    
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='詳細なログを出力')
    
    parser.add_argument('--log-dir', type=str, default='data/logs/run_all',
                        help='ログ出力ディレクトリ')
    
    parser.add_argument('--main-script', type=str, default='src/main.py',
                        help='実行するメインスクリプトのパス')
    
    return parser.parse_args()

def setup_log_directory(log_dir):
    """ログディレクトリの作成"""
    os.makedirs(log_dir, exist_ok=True)
    return log_dir

def main():
    """メイン関数"""
    args = parse_args()
    
    # ログディレクトリ設定
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_dir = setup_log_directory(args.log_dir)
    main_log_file = os.path.join(log_dir, f"run_all_{timestamp}.log")
    
    # 実行回数のカウント
    total_combinations = len(CHANNEL_MAP) * len(RANKING_TYPE_MAP) * len(CATEGORY_MAP)
    print(f"実行する組み合わせ数: {total_combinations}")
    
    # ログファイルへの書き込み開始
    with open(main_log_file, 'w') as log:
        log.write(f"実行開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        log.write(f"全組み合わせ数: {total_combinations}\n")
        log.write("-" * 80 + "\n")
        
        # 全ての組み合わせを生成
        combinations = list(itertools.product(
            CHANNEL_MAP.keys(),
            RANKING_TYPE_MAP.keys(),
            CATEGORY_MAP.keys()
        ))
        
        # 各組み合わせで実行
        for i, (channel, ranking_type, genre) in enumerate(combinations, 1):
            # 進捗表示
            progress = f"[{i}/{total_combinations}]"
            combination_str = f"{channel} × {ranking_type} × {genre}"
            print(f"{progress} 実行: {combination_str}")
            log.write(f"{progress} 実行: {combination_str}\n")
            
            # コマンド生成
            cmd = [
                "python", args.main_script,
                "--channel", channel,
                "--genre", genre,
                "--ranking-type", ranking_type
            ]
            
            # オプション引数の追加
            if args.dry_run:
                cmd.append("--dry-run")
            
            if args.use_alternative_ranking:
                cmd.append("--use-alternative-ranking")
                
            if args.verbose:
                cmd.append("--verbose")
            
            # 個別のログファイル名
            individual_log_file = os.path.join(
                log_dir, 
                f"{timestamp}_{channel}_{ranking_type}_{genre}.log"
            )
            cmd.extend(["--log-file", individual_log_file])
            
            # コマンドのログ記録
            cmd_str = " ".join(cmd)
            log.write(f"コマンド: {cmd_str}\n")
            
            # コマンド実行（ドライランモードの場合は表示のみ）
            if args.dry_run:
                print(f"  ドライランモード: {cmd_str}")
                log.write("  ドライランモード: 実行せず\n")
            else:
                print(f"  実行中: {cmd_str}")
                try:
                    start_time = datetime.now()
                    result = subprocess.run(
                        cmd, 
                        check=False,  # エラーがあっても続行
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True
                    )
                    end_time = datetime.now()
                    duration = (end_time - start_time).total_seconds()
                    
                    # 結果をログに記録
                    status = "成功" if result.returncode == 0 else "失敗"
                    log.write(f"  結果: {status} (終了コード: {result.returncode})\n")
                    log.write(f"  所要時間: {duration:.2f}秒\n")
                    
                    # エラーがあれば記録
                    if result.returncode != 0:
                        log.write(f"  標準出力:\n{result.stdout}\n")
                        log.write(f"  エラー出力:\n{result.stderr}\n")
                except Exception as e:
                    log.write(f"  実行エラー: {str(e)}\n")
            
            log.write("-" * 80 + "\n")
            log.flush()  # バッファをフラッシュして即座に書き込む
        
        # 完了ログ
        log.write(f"全実行完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    print(f"全ての組み合わせの実行が完了しました。ログ: {main_log_file}")

if __name__ == "__main__":
    main()