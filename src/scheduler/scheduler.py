"""
@file: scheduler.py
@desc: 定期実行スケジューラーモジュール
"""

import os
import sys
import time
import logging
import random
import signal
import itertools
from typing import Dict, List, Optional, Any, Callable, Tuple
from datetime import datetime, timedelta
import threading
import subprocess

# ロガー設定
logger = logging.getLogger(__name__)

class JobScheduler:
    """定期実行ジョブスケジューラー"""
    
    def __init__(
        self,
        config_file: Optional[str] = None,
        base_interval: int = 86400  # 1日（秒）
    ):
        """
        初期化
        
        Args:
            config_file: 設定ファイルパス
            base_interval: 基本実行間隔（秒）
        """
        self.config_file = config_file
        self.base_interval = base_interval
        self.jobs = []
        self.running = False
        self.current_job = None
        
        # ジョブパターン（ジャンル×チャンネル）
        self.job_patterns = list(itertools.product(
            ["化粧水", "乳液", "美容液", "パック"],  # ジャンル
            ["スーパー"]           # チャンネル
        ))
        
        # シグナルハンドラ設定
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, sig, frame):
        """シグナル処理"""
        logger.info(f"シグナル {sig} を受信しました。終了します。")
        self.stop()
        sys.exit(0)
    
    def _load_config(self) -> Dict[str, Any]:
        """設定ファイル読み込み"""
        if not self.config_file or not os.path.exists(self.config_file):
            logger.warning("設定ファイルが見つかりません。デフォルト設定を使用します。")
            return {}
        
        try:
            import json
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            logger.info(f"設定ファイル読み込み成功: {self.config_file}")
            return config
            
        except Exception as e:
            logger.error(f"設定ファイル読み込みエラー: {str(e)}")
            return {}
    
    def _get_next_job(self) -> Tuple[str, str]:
        """
        次の実行ジョブを選択
        
        Returns:
            (ジャンル, チャンネル)
        """
        # ランダム選択
        genre, channel = random.choice(self.job_patterns)
        return genre, channel
    
    def add_job(
        self,
        job_func: Callable,
        args: Optional[List] = None,
        kwargs: Optional[Dict] = None,
        interval: Optional[int] = None,
        start_delay: int = 0
    ):
        """
        ジョブ追加
        
        Args:
            job_func: 実行する関数
            args: 位置引数
            kwargs: キーワード引数
            interval: 実行間隔（秒）
            start_delay: 初回実行までの遅延（秒）
        """
        job = {
            "func": job_func,
            "args": args or [],
            "kwargs": kwargs or {},
            "interval": interval or self.base_interval,
            "last_run": datetime.now() - timedelta(seconds=interval or self.base_interval) + timedelta(seconds=start_delay),
            "running": False
        }
        
        self.jobs.append(job)
        logger.info(f"ジョブ追加: {job_func.__name__}, 間隔: {job['interval']}秒")
    
    def _run_job(self, job):
        """
        ジョブ実行
        
        Args:
            job: ジョブ辞書
        """
        if job["running"]:
            logger.warning(f"ジョブ {job['func'].__name__} は既に実行中です。スキップします。")
            return
        
        job["running"] = True
        self.current_job = job
        
        try:
            logger.info(f"ジョブ開始: {job['func'].__name__}")
            start_time = time.time()
            
            # ジャンルとチャンネルを選択
            genre, channel = self._get_next_job()
            
            # 引数にジャンルとチャンネルを追加
            kwargs = job["kwargs"].copy()
            kwargs["genre"] = genre
            kwargs["channel"] = channel
            
            # 関数実行
            result = job["func"](*job["args"], **kwargs)
            
            elapsed = time.time() - start_time
            logger.info(f"ジョブ完了: {job['func'].__name__}, 実行時間: {elapsed:.2f}秒, 結果: {result}")
            
        except Exception as e:
            logger.error(f"ジョブ実行エラー: {job['func'].__name__}, エラー: {str(e)}")
        
        finally:
            job["last_run"] = datetime.now()
            job["running"] = False
            self.current_job = None
    
    def _run_job_in_thread(self, job):
        """
        スレッドでジョブ実行
        
        Args:
            job: ジョブ辞書
        """
        thread = threading.Thread(target=self._run_job, args=(job,))
        thread.daemon = True
        thread.start()
    
    def _run_job_in_process(self, job):
        """
        別プロセスでジョブ実行
        
        Args:
            job: ジョブ辞書
        """
        # 本コードではPythonスクリプトとして実行
        # 実際のコマンド生成（例: python src/main.py --genre 化粧水 --channel ドラッグストア）
        genre, channel = self._get_next_job()
        
        cmd = [
            sys.executable,
            "src/main.py",
            "--genre", genre,
            "--channel", channel
        ]
        
        # 追加引数があれば
        for key, value in job["kwargs"].items():
            if key not in ["genre", "channel"] and value is not None:
                cmd.extend([f"--{key}", str(value)])
        
        # 実行
        try:
            logger.info(f"プロセス実行: {' '.join(cmd)}")
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # 非同期待機
            def monitor_process():
                stdout, stderr = process.communicate()
                exit_code = process.wait()
                
                if exit_code == 0:
                    logger.info(f"プロセス正常終了: {' '.join(cmd)}")
                else:
                    logger.error(f"プロセス異常終了: {' '.join(cmd)}, 終了コード: {exit_code}")
                    if stderr:
                        logger.error(f"エラー出力: {stderr}")
                
                job["last_run"] = datetime.now()
                job["running"] = False
            
            thread = threading.Thread(target=monitor_process)
            thread.daemon = True
            thread.start()
            
            job["running"] = True
            
        except Exception as e:
            logger.error(f"プロセス実行エラー: {str(e)}")
            job["running"] = False
    
    def run(self):
        """スケジューラー実行"""
        self.running = True
        logger.info("スケジューラー開始")
        
        while self.running:
            now = datetime.now()
            
            # 各ジョブをチェック
            for job in self.jobs:
                if job["running"]:
                    continue
                
                time_since_last_run = (now - job["last_run"]).total_seconds()
                
                # 実行間隔を過ぎていれば実行
                if time_since_last_run >= job["interval"]:
                    self._run_job_in_process(job)
            
            # 1分ごとにチェック
            time.sleep(60)
        
        logger.info("スケジューラー停止")
    
    def run_once(self, job_index: int = 0):
        """
        指定ジョブを1回実行
        
        Args:
            job_index: ジョブインデックス
        """
        if job_index >= len(self.jobs):
            logger.error(f"ジョブインデックス {job_index} は範囲外です")
            return
        
        job = self.jobs[job_index]
        self._run_job(job)
    
    def stop(self):
        """スケジューラー停止"""
        logger.info("スケジューラー停止リクエスト受信")
        self.running = False
        
        # 実行中ジョブの完了を待機
        if self.current_job:
            logger.info(f"実行中ジョブ {self.current_job['func'].__name__} の完了を待機中...")
