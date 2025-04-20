#!/usr/bin/env python3
"""
@file: project.py
@desc: プロジェクト管理ユーティリティスクリプト
"""

import os
import sys
import argparse
import subprocess
import logging
from pathlib import Path

# プロジェクトルートパスを取得
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ロガー設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def setup_env():
    """環境設定とディレクトリ構造の作成"""
    dirs = [
        'data/assets/images',
        'data/assets/bgm',
        'data/temp',
        'data/output',
        'data/logs',
    ]
    
    for d in dirs:
        path = PROJECT_ROOT / d
        path.mkdir(parents=True, exist_ok=True)
        logger.info(f"ディレクトリ作成: {path}")
    
    # .env ファイルの作成（存在しない場合）
    env_example = PROJECT_ROOT / 'config' / '.env.example'
    env_file = PROJECT_ROOT / 'config' / '.env'
    
    if not env_file.exists() and env_example.exists():
        with open(env_example, 'r', encoding='utf-8') as src:
            content = src.read()
        
        with open(env_file, 'w', encoding='utf-8') as dst:
            dst.write(content)
        
        logger.info(f".env ファイル作成: {env_file}")
        logger.info("環境変数を設定するには .env ファイルを編集してください。")

def init_db():
    """SQLiteデータベースの初期化"""
    try:
        # DBモジュールをインポート
        sys.path.insert(0, str(PROJECT_ROOT))
        from src.db.database import CosmeDatabase
        
        # データベース初期化
        db_path = PROJECT_ROOT / 'data' / 'cosme.db'
        db = CosmeDatabase(str(db_path))
        
        logger.info(f"データベース初期化完了: {db_path}")
        return True
    except Exception as e:
        logger.error(f"データベース初期化エラー: {str(e)}")
        return False

def install_dummy_bgm():
    """テスト用のBGMファイルを配置"""
    bgm_dir = PROJECT_ROOT / 'data' / 'assets' / 'bgm'
    dummy_bgm = bgm_dir / 'dummy_bgm.mp3'
    
    if not dummy_bgm.exists():
        # 超簡易的なMP3ファイル作成（実際には著作権フリーの音源を用意する）
        import wave
        import struct
        import array
        
        # WAVEファイルを作成
        wav_path = bgm_dir / 'dummy_bgm.wav'
        with wave.open(str(wav_path), 'w') as fp:
            fp.setnchannels(1)  # モノラル
            fp.setsampwidth(2)  # 16ビット
            fp.setframerate(44100)  # 44.1kHz
            
            # 1秒のサイレンス
            data = array.array('h', [0] * 44100)
            fp.writeframes(data.tobytes())
        
        # WAVをMP3に変換（ffmpegがインストールされている必要あり）
        try:
            subprocess.run(
                ['ffmpeg', '-i', str(wav_path), '-codec:a', 'libmp3lame', '-qscale:a', '2', str(dummy_bgm)],
                check=True, capture_output=True
            )
            logger.info(f"テスト用BGM作成: {dummy_bgm}")
            
            # WAVを削除
            wav_path.unlink()
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            logger.warning(f"MP3変換エラー（ffmpegのインストールが必要です）: {str(e)}")
            logger.info(f"代わりにWAVを使用します: {wav_path}")
    else:
        logger.info(f"テスト用BGMはすでに存在します: {dummy_bgm}")

def run_test():
    """テスト実行"""
    try:
        logger.info("テスト実行開始...")
        
        # テストコマンド実行
        result = subprocess.run(
            [sys.executable, '-m', 'pytest', '-xvs', 'tests'],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            logger.info("テスト成功！")
            print(result.stdout)
            return True
        else:
            logger.error("テスト失敗")
            print(result.stdout)
            print(result.stderr)
            return False
    except Exception as e:
        logger.error(f"テスト実行エラー: {str(e)}")
        return False

def run_dry():
    """ドライラン実行（実際には動画を作成しない）"""
    try:
        logger.info("ドライラン実行開始...")
        
        # メインスクリプト実行（ドライランモード）
        result = subprocess.run(
            [
                sys.executable, 
                str(PROJECT_ROOT / 'src' / 'main.py'),
                '--dry-run',
                '--verbose'
            ],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            logger.info("ドライラン成功！")
            print(result.stdout)
            return True
        else:
            logger.error("ドライラン失敗")
            print(result.stdout)
            print(result.stderr)
            return False
    except Exception as e:
        logger.error(f"ドライラン実行エラー: {str(e)}")
        return False

def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(description='Auto-Cosme Shorts プロジェクト管理')
    
    subparsers = parser.add_subparsers(dest='command', help='実行コマンド')
    
    # setup コマンド
    setup_parser = subparsers.add_parser('setup', help='環境設定')
    
    # run コマンド
    run_parser = subparsers.add_parser('run', help='実行')
    run_parser.add_argument('--genre', type=str, default='化粧水', 
                          choices=['化粧水', '乳液', '美容液', 'パック'],
                          help='対象ジャンル')
    run_parser.add_argument('--channel', type=str, default='スーパー',
                          choices=['スーパー'],
                          help='チャンネル（購入場所）')
    run_parser.add_argument('--dry-run', action='store_true',
                          help='ドライラン（動画作成なし）')
    
    # test コマンド
    test_parser = subparsers.add_parser('test', help='テスト実行')
    
    args = parser.parse_args()
    
    # コマンド実行
    if args.command == 'setup':
        setup_env()
        init_db()
        install_dummy_bgm()
        logger.info("セットアップ完了！")
    
    elif args.command == 'run':
        cmd = [sys.executable, str(PROJECT_ROOT / 'src' / 'main.py')]
        
        if args.genre:
            cmd.extend(['--genre', args.genre])
        
        if args.channel:
            cmd.extend(['--channel', args.channel])
        
        if args.dry_run:
            cmd.append('--dry-run')
        
        # 実行
        try:
            logger.info(f"実行コマンド: {' '.join(cmd)}")
            subprocess.run(cmd)
        except Exception as e:
            logger.error(f"実行エラー: {str(e)}")
    
    elif args.command == 'test':
        run_test()
    
    else:
        # コマンド未指定時はヘルプ表示
        parser.print_help()
        
        # プロジェクト情報表示
        print("\nプロジェクト情報:")
        print(f"  プロジェクトルート: {PROJECT_ROOT}")
        
        # .env ファイル状態確認
        env_file = PROJECT_ROOT / 'config' / '.env'
        if env_file.exists():
            print("  .env ファイル: 設定済み")
        else:
            print("  .env ファイル: 未設定（'setup' コマンドを実行してください）")
        
        # データベースファイル状態確認
        db_file = PROJECT_ROOT / 'data' / 'cosme.db'
        if db_file.exists():
            print(f"  データベース: 存在 ({db_file.stat().st_size / 1024:.1f} KB)")
        else:
            print("  データベース: 未作成（'setup' コマンドを実行してください）")

if __name__ == "__main__":
    main()