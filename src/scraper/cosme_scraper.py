"""
@file: cosme_scraper.py
@desc: アットコスメのPチャンネルランキングをスクレイピングするモジュール
"""

import time
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# ロガー設定
logger = logging.getLogger(__name__)

class CosmeNetScraper:
    """アットコスメのランキングページをスクレイピングするクラス"""
    
    BASE_URL = "https://www.cosme.net"
    RANKING_URL = "https://www.cosme.net/categories/pchannel/2/ranking/"
    
    # カテゴリーID対応表（例示、必要に応じて拡充）
    CATEGORY_MAP = {
        "化粧水": ["1002", "1003", "1071"],  # 化粧水、薬用化粧水、ミスト状化粧水
        "乳液": ["1004"],                    # 乳液
        "美容液": ["1006"],                   # 美容液
        "パック": ["1007"]                    # シートマスク・パック
    }
    
    # 購入場所チャンネル (仮定: スーパー=1, ドラッグストア=2)
    CHANNEL_MAP = {
        "スーパー": "1",
        "ドラッグストア": "2"
    }
    
    def __init__(self, rate_limit: float = 1.0):
        """
        初期化
        
        Args:
            rate_limit: リクエスト間隔（秒）
        """
        self.rate_limit = rate_limit
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Auto-Cosme-Shorts/0.1 (https://example.com/bot; bot@example.com)"
        })
        self.last_request_time = 0
    
    def _respect_rate_limit(self):
        """レート制限を遵守するために必要に応じて待機"""
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self.last_request_time = time.time()
    
    def get_page(self, url: str) -> str:
        """
        指定URLのページを取得
        
        Args:
            url: 取得するURL
        
        Returns:
            HTML内容
        """
        self._respect_rate_limit()
        try:
            response = self.session.get(url)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logger.error(f"ページ取得エラー: {url}, {str(e)}")
            raise
    
    def _parse_product_items(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """
        ランキングページからアイテム情報を抽出
        
        Args:
            soup: BeautifulSoupオブジェクト
        
        Returns:
            製品情報の辞書リスト
        """
        products = []
        items = soup.select("div.keyword-ranking-item")
        
        for item in items:
            try:
                # 順位取得
                rank_elem = item.select_one("span.rank-num")
                if rank_elem:
                    if rank_elem.img:  # 1-3位はイメージタグ
                        rank = int(re.search(r'(\d+)位', rank_elem.img.get('alt', '')).group(1))
                    else:  # 4位以降はテキスト
                        rank = int(rank_elem.select_one("span.num").text.strip())
                else:
                    continue  # ランクがない場合はスキップ
                
                # 商品情報取得
                product_a = item.select_one("h4.item a")
                if not product_a:
                    continue
                
                product_name = product_a.text.strip()
                product_url = urljoin(self.BASE_URL, product_a.get('href', ''))
                product_id = product_url.split('/')[-2] if '/products/' in product_url else None
                
                # ブランド情報
                brand_a = item.select_one("span.brand a")
                brand = brand_a.text.strip() if brand_a else "不明"
                
                # カテゴリ情報
                category_links = item.select("span.category a")
                categories = [a.text.strip() for a in category_links]
                
                # 画像URL
                img_elem = item.select_one("dd.pic img")
                image_url = img_elem.get('src', '') if img_elem else ''
                
                # 価格情報
                price_elem = item.select_one("p.price")
                price_text = price_elem.text.strip() if price_elem else "不明"
                
                # 発売日情報
                release_elem = item.select_one("p.onsale")
                release_text = release_elem.text.strip() if release_elem else ""
                
                # 評価情報
                rating_elem = item.select_one("span.reviewer-average")
                rating = rating_elem.text.strip() if rating_elem else None
                
                # クチコミ数
                votes_elem = item.select_one("p.votes span")
                votes = int(votes_elem.text.replace(',', '')) if votes_elem else 0
                
                # 製品情報をdict化
                product_data = {
                    "product_id": product_id,
                    "rank": rank,
                    "name": product_name,
                    "brand": brand,
                    "categories": categories,
                    "url": product_url,
                    "image_url": image_url,
                    "price": price_text,
                    "release_date": release_text,
                    "rating": rating,
                    "votes": votes
                }
                
                products.append(product_data)
                
            except Exception as e:
                logger.warning(f"製品情報抽出エラー: {str(e)}")
                continue
        
        return products
    
    def get_ranking_products(
        self, 
        channel: str = "ドラッグストア", 
        genre: str = "化粧水",
        weeks_back: int = 0
    ) -> List[Dict[str, Any]]:
        """
        指定されたチャンネルとジャンルのランキング製品を取得
        
        Args:
            channel: 購入場所チャンネル名
            genre: ジャンル名
            weeks_back: 何週前のランキングか（0=今週）
        
        Returns:
            製品情報の辞書リスト
        """
        # TODO: 週を遡るロジックを実装する（現在は簡略化し今週のみ）
        url = self.RANKING_URL
        
        # 対象ページを取得
        html = self.get_page(url)
        soup = BeautifulSoup(html, 'html.parser')
        
        # 製品リストを取得
        products = self._parse_product_items(soup)
        
        # 指定ジャンルの製品をフィルタリング
        category_ids = self.CATEGORY_MAP.get(genre, [])
        filtered_products = []
        
        for product in products:
            # カテゴリチェック (今はカテゴリ名でマッチング、将来的にはIDでの照合に変更予定)
            category_match = False
            for cat in product["categories"]:
                if genre in cat:
                    category_match = True
                    break
            
            if category_match:
                # チャンネル情報はここではまだ取得できないため、別途取得か付与する必要あり
                # 現状では仮の値をセット
                product["channel"] = channel
                product["genre"] = genre
                filtered_products.append(product)
        
        return filtered_products
    
    def get_products_by_criteria(
        self, 
        channel: str,
        genre: str, 
        min_count: int = 7,
        max_weeks_back: int = 3
    ) -> List[Dict[str, Any]]:
        """
        基準を満たす製品リストを取得
        
        Args:
            channel: チャンネル名
            genre: ジャンル名 
            min_count: 必要な最小製品数
            max_weeks_back: 最大遡る週数
        
        Returns:
            製品情報リスト
        """
        collected_products = []
        
        # 週ごとに製品を収集
        for week in range(max_weeks_back + 1):
            products = self.get_ranking_products(channel, genre, week)
            
            # 重複を避けるために製品IDでフィルタリング
            existing_ids = {p["product_id"] for p in collected_products}
            new_products = [p for p in products if p["product_id"] not in existing_ids]
            
            collected_products.extend(new_products)
            
            # 十分な製品が集まったらループを終了
            if len(collected_products) >= min_count:
                break
        
        # 最低要件を満たさない場合
        if len(collected_products) < min_count:
            logger.warning(
                f"必要な製品数（{min_count}個）を収集できませんでした。"
                f"現在: {len(collected_products)}個"
            )
        
        return collected_products[:min_count] if len(collected_products) >= min_count else collected_products
