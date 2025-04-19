"""
@file: asset_fetcher.py
@desc: 画像やBGMなどの素材を取得するモジュール
"""

import os
import logging
import aiohttp
import asyncio
import random
from typing import Dict, List, Optional, Any, Set, Tuple
from urllib.parse import urlparse, unquote
from pathlib import Path
import time

# ロガー設定
logger = logging.getLogger(__name__)

class AssetFetcher:
    """素材取得を行うクラス"""
    
    def __init__(
        self,
        image_dir: str = 'data/assets/images',
        bgm_dir: str = 'data/assets/bgm',
        temp_dir: str = 'data/temp',
        rate_limit: float = 1.0,
        max_retries: int = 3,
        timeout: int = 30
    ):
        """
        初期化
        
        Args:
            image_dir: 画像保存ディレクトリ
            bgm_dir: BGM保存ディレクトリ
            temp_dir: 一時ファイルディレクトリ
            rate_limit: リクエスト間隔（秒）
            max_retries: 最大リトライ回数
            timeout: タイムアウト（秒）
        """
        self.image_dir = image_dir
        self.bgm_dir = bgm_dir
        self.temp_dir = temp_dir
        self.rate_limit = rate_limit
        self.max_retries = max_retries
        self.timeout = timeout
        
        # ディレクトリ作成
        for directory in [image_dir, bgm_dir, temp_dir]:
            os.makedirs(directory, exist_ok=True)
        
        # リクエスト間隔制御用
        self.last_request_time = 0
    
    def _respect_rate_limit(self):
        """リクエスト間隔を制御"""
        now = time.time()
        elapsed = now - self.last_request_time
        
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        
        self.last_request_time = time.time()
    
    def _get_file_extension(self, url: str, headers: Dict = None) -> str:
        """
        URLやヘッダーから拡張子を取得
        
        Args:
            url: ファイルURL
            headers: レスポンスヘッダー
            
        Returns:
            拡張子（ドット付き）
        """
        # Content-Typeからの判定
        if headers and 'Content-Type' in headers:
            content_type = headers['Content-Type'].lower()
            
            if 'image/jpeg' in content_type:
                return '.jpg'
            elif 'image/png' in content_type:
                return '.png'
            elif 'image/gif' in content_type:
                return '.gif'
            elif 'image/webp' in content_type:
                return '.webp'
            elif 'audio/mpeg' in content_type:
                return '.mp3'
            elif 'audio/mp4' in content_type:
                return '.m4a'
            elif 'audio/wav' in content_type:
                return '.wav'
        
        # URLからの判定
        path = urlparse(url).path
        filename = os.path.basename(unquote(path))
        ext = os.path.splitext(filename)[1].lower()
        
        if ext:
            return ext
        
        # デフォルト
        return '.jpg'  # デフォルトは画像想定
    
    async def fetch_image(
        self,
        product_id: str,
        image_url: str,
        session: Optional[aiohttp.ClientSession] = None
    ) -> Optional[str]:
        """
        画像を取得
        
        Args:
            product_id: 製品ID
            image_url: 画像URL
            session: 既存のセッション
            
        Returns:
            保存したファイルパス、失敗時はNone
        """
        if not image_url:
            logger.warning(f"画像URLが空です: {product_id}")
            return None
        
        # 既に取得済みかチェック
        for ext in ['.jpg', '.png', '.gif', '.webp']:
            existing_path = os.path.join(self.image_dir, f"{product_id}{ext}")
            if os.path.exists(existing_path):
                logger.info(f"既存の画像を使用: {existing_path}")
                return existing_path
        
        # セッション管理
        close_session = False
        if session is None:
            session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout))
            close_session = True
        
        try:
            self._respect_rate_limit()
            
            for attempt in range(self.max_retries):
                try:
                    async with session.get(image_url) as response:
                        if response.status != 200:
                            logger.warning(
                                f"画像取得エラー: {image_url}, "
                                f"ステータス: {response.status} "
                                f"(試行 {attempt+1}/{self.max_retries})"
                            )
                            if attempt < self.max_retries - 1:
                                await asyncio.sleep(1 * (attempt + 1))  # バックオフ
                                continue
                            return None
                        
                        # 拡張子取得
                        ext = self._get_file_extension(
                            image_url, 
                            headers=response.headers
                        )
                        
                        # 保存パス
                        file_path = os.path.join(self.image_dir, f"{product_id}{ext}")
                        
                        # ファイル保存
                        content = await response.read()
                        with open(file_path, 'wb') as f:
                            f.write(content)
                        
                        logger.info(f"画像保存完了: {file_path}")
                        return file_path
                
                except aiohttp.ClientError as e:
                    logger.warning(
                        f"リクエストエラー: {image_url}, "
                        f"エラー: {str(e)} "
                        f"(試行 {attempt+1}/{self.max_retries})"
                    )
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(1 * (attempt + 1))  # バックオフ
                    else:
                        return None
        
        finally:
            if close_session:
                await session.close()
    
    async def fetch_images(
        self,
        products: List[Dict[str, Any]]
    ) -> Dict[str, str]:
        """
        複数の画像を並列取得
        
        Args:
            products: 製品情報リスト
            
        Returns:
            製品ID→画像パスのマッピング
        """
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
            tasks = []
            
            for product in products:
                product_id = product.get("product_id")
                image_url = product.get("image_url")
                
                if not product_id or not image_url:
                    continue
                
                task = self.fetch_image(product_id, image_url, session)
                tasks.append((product_id, task))
            
            # 並列実行（rate_limitは各リクエスト内で制御）
            results = {}
            for product_id, task in tasks:
                try:
                    file_path = await task
                    if file_path:
                        results[product_id] = file_path
                except Exception as e:
                    logger.error(f"画像取得タスクエラー: {product_id}, エラー: {str(e)}")
            
            return results
    
    def select_random_bgm(self) -> Optional[str]:
        """
        ランダムにBGMを選択
        
        Returns:
            選択したBGMのファイルパス、なければNone
        """
        if not os.path.exists(self.bgm_dir):
            logger.warning(f"BGMディレクトリが見つかりません: {self.bgm_dir}")
            return None
        
        bgm_files = [
            f for f in os.listdir(self.bgm_dir)
            if f.endswith(('.mp3', '.wav', '.m4a'))
        ]
        
        if not bgm_files:
            logger.warning(f"BGMファイルが見つかりません: {self.bgm_dir}")
            return None
        
        # ランダム選択
        bgm_file = random.choice(bgm_files)
        bgm_path = os.path.join(self.bgm_dir, bgm_file)
        
        logger.info(f"BGM選択: {bgm_path}")
        return bgm_path
    
    def fetch_assets(self, products: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        全素材を取得
        
        Args:
            products: 製品情報リスト
            
        Returns:
            素材情報辞書
        """
        # 画像取得
        image_paths = asyncio.run(self.fetch_images(products))
        
        # BGM選択
        bgm_path = self.select_random_bgm()
        
        # 製品情報を更新（画像パスを追加）
        updated_products = []
        for product in products:
            product_id = product.get("product_id")
            
            if product_id in image_paths:
                product_copy = product.copy()
                product_copy["local_image_path"] = image_paths[product_id]
                updated_products.append(product_copy)
            else:
                updated_products.append(product)
        
        return {
            "products": updated_products,
            "bgm_path": bgm_path
        }
