"""
@file: product_selector.py
@desc: スクレイピングした製品から条件に合う商品を選定するモジュール
"""

import random
import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta

# ロガー設定
logger = logging.getLogger(__name__)

class ProductSelector:
    """製品選定を行うクラス"""
    
    def __init__(self, min_products: int = 7, max_products: int = 10):
        """
        初期化
        
        Args:
            min_products: 最小必要製品数
            max_products: 最大製品数
        """
        self.min_products = min_products
        self.max_products = max_products
    
    def filter_by_genre(
        self, 
        products: List[Dict[str, Any]], 
        genre: str
    ) -> List[Dict[str, Any]]:
        """
        指定ジャンルでフィルタリング
        
        Args:
            products: 製品リスト
            genre: ジャンル名
        
        Returns:
            フィルタリングされた製品リスト
        """
        return [p for p in products if p.get("genre") == genre]
    
    def filter_by_channel(
        self, 
        products: List[Dict[str, Any]], 
        channel: str
    ) -> List[Dict[str, Any]]:
        """
        指定チャンネル（購入場所）でフィルタリング
        
        Args:
            products: 製品リスト
            channel: チャンネル名
        
        Returns:
            フィルタリングされた製品リスト
        """
        return [p for p in products if p.get("channel") == channel]
    
    def remove_duplicates(
        self, 
        products: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        重複を除去（product_idで判断）
        
        Args:
            products: 製品リスト
        
        Returns:
            重複を除いた製品リスト
        """
        seen_ids = set()
        unique_products = []
        
        for product in products:
            product_id = product.get("product_id")
            if product_id and product_id not in seen_ids:
                seen_ids.add(product_id)
                unique_products.append(product)
        
        return unique_products
    
    def shuffle_ranks(
        self, 
        products: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        製品のランキングをシャッフル
        
        Args:
            products: 製品リスト
        
        Returns:
            ランクをシャッフルした製品リスト
        """
        # 元のリストをコピーしてシャッフル
        shuffled_products = products.copy()
        random.shuffle(shuffled_products)
        
        # 新しいランクを割り当て (7位から1位)
        for i, product in enumerate(shuffled_products):
            # 昇順にするため、リストの最後が1位、最初が7位となるように
            new_rank = len(shuffled_products) - i
            product["new_rank"] = new_rank
            # 元のランクは保持
            product["original_rank"] = product.get("rank", 0)
        
        return shuffled_products
    
    def select_products(
        self,
        products: List[Dict[str, Any]],
        channel: str,
        genre: str
    ) -> List[Dict[str, Any]]:
        """
        条件に合う製品を選定
        
        Args:
            products: 製品リスト
            channel: チャンネル名
            genre: ジャンル名
        
        Returns:
            選定された製品リスト（7-10個）
        """
        logger.info(f"製品選定開始: {channel} × {genre}")
        
        # チャンネルとジャンルでフィルタリング
        filtered_products = self.filter_by_channel(products, channel)
        filtered_products = self.filter_by_genre(filtered_products, genre)
        
        # 重複除去
        filtered_products = self.remove_duplicates(filtered_products)
        
        # 十分な製品があるか確認
        if len(filtered_products) < self.min_products:
            logger.warning(
                f"十分な製品({self.min_products}個)が見つかりませんでした: {len(filtered_products)}個"
            )
            return []
        
        # 最大数を制限
        if len(filtered_products) > self.max_products:
            # 上位のものを優先して選ぶ（元のランキングに基づく）
            filtered_products = sorted(filtered_products, key=lambda x: x.get("rank", 999))
            filtered_products = filtered_products[:self.max_products]
        
        # ランクをシャッフル
        selected_products = self.shuffle_ranks(filtered_products)
        
        logger.info(f"製品選定完了: {len(selected_products)}個")
        return selected_products


# モジュールのメイン動作（実行時のテスト用）
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # テスト用データ
    test_products = [
        {"product_id": "1", "name": "化粧水A", "brand": "ブランドX", "channel": "ドラッグストア", "genre": "化粧水", "rank": 1},
        {"product_id": "2", "name": "化粧水B", "brand": "ブランドY", "channel": "ドラッグストア", "genre": "化粧水", "rank": 2},
        {"product_id": "3", "name": "美容液C", "brand": "ブランドZ", "channel": "ドラッグストア", "genre": "美容液", "rank": 3},
        {"product_id": "4", "name": "乳液D", "brand": "ブランドX", "channel": "スーパー", "genre": "乳液", "rank": 4},
        {"product_id": "5", "name": "化粧水E", "brand": "ブランドY", "channel": "ドラッグストア", "genre": "化粧水", "rank": 5},
        {"product_id": "6", "name": "化粧水F", "brand": "ブランドZ", "channel": "ドラッグストア", "genre": "化粧水", "rank": 6},
        {"product_id": "7", "name": "化粧水G", "brand": "ブランドX", "channel": "ドラッグストア", "genre": "化粧水", "rank": 7},
        {"product_id": "8", "name": "化粧水H", "brand": "ブランドY", "channel": "ドラッグストア", "genre": "化粧水", "rank": 8},
        {"product_id": "9", "name": "化粧水I", "brand": "ブランドZ", "channel": "ドラッグストア", "genre": "化粧水", "rank": 9},
        {"product_id": "10", "name": "化粧水J", "brand": "ブランドX", "channel": "ドラッグストア", "genre": "化粧水", "rank": 10},
    ]
    
    selector = ProductSelector(min_products=7, max_products=10)
    
    # ドラッグストアの化粧水選定
    selected = selector.select_products(test_products, "ドラッグストア", "化粧水")
    
    # 選定結果表示
    print(f"選定製品数: {len(selected)}")
    for product in selected:
        print(f"{product['new_rank']}位 (元: {product['original_rank']}位): {product['name']} ({product['brand']})")