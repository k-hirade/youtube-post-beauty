"""
@file: cosme_scraper.py
@desc: アットコスメのPチャンネルランキングをスクレイピングするモジュール（詳細デバッグログ追加版）
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
    RANKING_BASE_URL = "https://www.cosme.net/categories/pchannel/2/ranking/"
    
    # カテゴリーID対応表（例示、必要に応じて拡充）
    CATEGORY_MAP = {
        "化粧水": ["1003", "1071", "1072"],  # 化粧水、薬用化粧水、ミスト状化粧水
        "乳液": ["1004", "1005", "1006", "1067", "1073"],  # 乳液、美容液、クリーム等
        "パック": ["1007"]  # シートマスク・パック
    }
    
    CHANNEL_MAP = {
        "スーパー・ドラッグストア": "2",
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
            logger.info(f"URLを取得中: {url}")
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
        
        logger.info(f"ページから{len(items)}個の製品要素を検出")
        
        for item in items:
            try:
                # 順位取得 (既存コード維持)
                rank_elem = item.select_one("span.rank-num")
                if rank_elem:
                    if rank_elem.img:  # 1-3位はイメージタグ
                        rank = int(re.search(r'(\d+)位', rank_elem.img.get('alt', '')).group(1))
                    else:  # 4位以降はテキスト
                        rank = int(rank_elem.select_one("span.num").text.strip())
                else:
                    continue  # ランクがない場合はスキップ
                
                # 商品情報取得 (既存コード維持)
                product_a = item.select_one("h4.item a")
                if not product_a:
                    continue
                
                product_name = product_a.text.strip()
                product_url = urljoin(self.BASE_URL, product_a.get('href', ''))
                product_id = product_url.split('/')[-2] if '/products/' in product_url else None
                
                logger.debug(f"製品基本情報: ID={product_id}, 名前={product_name}, ランク={rank}")
                
                # ブランド情報 (既存コード維持)
                brand_a = item.select_one("span.brand a")
                brand = brand_a.text.strip() if brand_a else "不明"
                
                # カテゴリ情報取得 (修正: カテゴリの取得方法を強化)
                category_links = item.select("span.category a")
                categories = []
                category_ids = []
                
                # デバッグ: カテゴリ要素の確認
                logger.debug(f"製品 ID={product_id} '{product_name}' のカテゴリ要素数: {len(category_links)}")
                
                # カテゴリHTML全体のデバッグ出力
                category_span = item.select_one("span.category")
                if category_span:
                    logger.debug(f"カテゴリHTML: {category_span}")
                
                for a in category_links:
                    cat_text = a.text.strip()
                    categories.append(cat_text)
                    
                    # カテゴリIDを抽出 (URL: https://www.cosme.net/categories/item/1004/ から1004を取得)
                    cat_href = a.get('href', '')
                    logger.debug(f"製品 ID={product_id} のカテゴリリンク: {cat_href}")
                    
                    cat_id_match = re.search(r'/categories/item/(\d+)/', cat_href)
                    if cat_id_match:
                        cat_id = cat_id_match.group(1)
                        category_ids.append(cat_id)
                        logger.debug(f"製品 ID={product_id} のカテゴリID抽出: {cat_text} -> {cat_id}")
                    else:
                        logger.warning(f"製品 ID={product_id} のカテゴリIDが抽出できませんでした: {cat_href}")
                
                # デバッグ: 最終的なカテゴリリスト
                logger.debug(f"製品 ID={product_id} '{product_name}' のカテゴリ: {categories}")
                logger.debug(f"製品 ID={product_id} '{product_name}' のカテゴリID: {category_ids}")
                
                # 残りの情報取得 (既存コード維持)
                img_elem = item.select_one("dd.pic img")
                image_url = img_elem.get('src', '') if img_elem else ''
                
                price_elem = item.select_one("p.price")
                price_text = price_elem.text.strip() if price_elem else "不明"
                
                release_elem = item.select_one("p.onsale")
                release_text = release_elem.text.strip() if release_elem else ""
                
                rating_elem = item.select_one("span.reviewer-average")
                rating = rating_elem.text.strip() if rating_elem else None
                
                votes_elem = item.select_one("p.votes span")
                votes = int(votes_elem.text.replace(',', '')) if votes_elem else 0
                
                # 製品情報をdict化 (修正: category_idsを追加)
                product_data = {
                    "product_id": product_id,
                    "rank": rank,
                    "name": product_name,
                    "brand": brand,
                    "categories": categories,
                    "category_ids": category_ids,  # カテゴリIDを保存
                    "url": product_url,
                    "image_url": image_url,
                    "price": price_text,
                    "release_date": release_text,
                    "rating": rating,
                    "votes": votes
                }
                
                products.append(product_data)
                logger.debug(f"製品情報抽出完了: ID={product_id}, {product_name}")
                
            except Exception as e:
                logger.warning(f"製品情報抽出エラー: {str(e)}")
                continue
        
        return products
    
    def get_ranking_products(
        self, 
        channel: str,
        genre: str,
        week: int = 0,
        page: int = 1
    ) -> List[Dict[str, Any]]:
        """
        指定されたチャンネルとジャンルのランキング製品を取得
        
        Args:
            channel: チャンネル名
            genre: ジャンル名
            week: 何週前のランキングか（0=今週、1=先週、...）
            page: ページ番号
        
        Returns:
            製品情報の辞書リスト
        """
        # ランキングURL構築
        if week == 0:
            url = f"{self.RANKING_BASE_URL}?page={page}"
        else:
            url = f"{self.RANKING_BASE_URL}week{week}/?page={page}"
        
        # 対象ページを取得
        html = self.get_page(url)
        soup = BeautifulSoup(html, 'html.parser')
        
        # 製品リストを取得
        products = self._parse_product_items(soup)
        
        # 指定ジャンルの製品をフィルタリング
        filtered_products = []
        
        # カテゴリIDの取得(指定されたジャンルに対応するCATEGORY_MAPのID)
        genre_list = [g.strip() for g in genre.split(',')]
        target_category_ids = []
        
        for g in genre_list:
            if g in self.CATEGORY_MAP:
                target_category_ids.extend(self.CATEGORY_MAP[g])
        
        # デバッグ: ターゲットカテゴリID
        logger.debug(f"ターゲットジャンル: {genre_list}")
        logger.debug(f"ターゲットカテゴリID: {target_category_ids}")
        
        # フィルタリング実行
        for product in products:
            match = False
            product_id = product.get("product_id", "不明")
            product_name = product.get("name", "不明")
            
            # デバッグ: フィルタリング前の製品情報
            logger.debug(f"フィルタリング対象: ID={product_id}, {product_name}")
            logger.debug(f"  カテゴリ: {product.get('categories', [])}")
            logger.debug(f"  カテゴリID: {product.get('category_ids', [])}")
            
            # 1. カテゴリIDによるマッチング (優先)
            if "category_ids" in product and product["category_ids"]:
                for cat_id in product["category_ids"]:
                    logger.debug(f"  カテゴリID比較: {cat_id} in {target_category_ids}?")
                    if cat_id in target_category_ids:
                        match = True
                        logger.debug(f"  カテゴリIDマッチ: ID={product_id}, {cat_id} in {target_category_ids}")
                        break
                    else:
                        logger.debug(f"  カテゴリIDミスマッチ: ID={product_id}, {cat_id} not in {target_category_ids}")
            else:
                logger.debug(f"  カテゴリIDなし: ID={product_id}")
            
            # 2. テキストマッチングによるバックアップ
            if not match and product["categories"]:
                # カテゴリ名マッチング
                for cat in product["categories"]:
                    for g in genre_list:
                        if g in cat:
                            match = True
                            logger.debug(f"  カテゴリ名マッチ: ID={product_id}, '{g}' in '{cat}'")
                            break
                    if match:
                        break
            
            if match:
                # チャンネル情報追加
                product["channel"] = channel
                product["genre"] = genre
                filtered_products.append(product)
                logger.info(f"該当製品: ID={product_id}, {product_name} ({product['brand']}), カテゴリ: {product['categories']}")
            else:
                logger.debug(f"  ジャンル不一致のため除外: ID={product_id}, {product_name}")
        
        logger.info(f"{url} から {len(filtered_products)}/{len(products)} 個の製品を抽出")
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
        existing_ids = set()
        
        # デバッグ: 開始情報
        logger.debug(f"製品収集開始: チャンネル={channel}, ジャンル={genre}, 最小数={min_count}")
        
        # まず現在の週の複数ページをチェック
        for page in range(1, 6):  # page=1からpage=5まで
            if len(collected_products) >= min_count:
                break
                
            products = self.get_ranking_products(channel, genre, week=0, page=page)
            
            # 重複を避けるためにフィルタリング
            new_products = [p for p in products if p["product_id"] not in existing_ids]
            
            # 詳細なデバッグ: 新製品情報
            for p in new_products:
                logger.debug(f"新規追加製品: ID={p['product_id']}, {p['brand']} {p['name']}")
                logger.debug(f"  カテゴリ: {p.get('categories', [])}")
                logger.debug(f"  カテゴリID: {p.get('category_ids', [])}")
            
            # 既存IDセットを更新
            new_ids = [p["product_id"] for p in new_products]
            existing_ids.update(new_ids)
            logger.debug(f"新規追加ID: {new_ids}")
            
            collected_products.extend(new_products)
            logger.info(f"現在の週 ページ{page}: {len(new_products)}個追加、合計{len(collected_products)}個")
            
            # 次ページをチェックする前に少し待機
            time.sleep(self.rate_limit)
        
        # それでも足りない場合、過去の週のデータを取得
        for week in range(2, max_weeks_back + 1):  # week2, week3, ...
            if len(collected_products) >= min_count:
                break
                
            for page in range(1, 3):  # 各週は最初の2ページだけチェック
                products = self.get_ranking_products(channel, genre, week=week, page=page)
                
                # 重複を避けるためにフィルタリング
                new_products = [p for p in products if p["product_id"] not in existing_ids]
                
                # 詳細なデバッグ: 新製品情報（過去週）
                for p in new_products:
                    logger.debug(f"過去週{week}から追加製品: ID={p['product_id']}, {p['brand']} {p['name']}")
                    logger.debug(f"  カテゴリ: {p.get('categories', [])}")
                    logger.debug(f"  カテゴリID: {p.get('category_ids', [])}")
                
                # 既存IDセットを更新
                new_ids = [p["product_id"] for p in new_products]
                existing_ids.update(new_ids)
                logger.debug(f"過去週{week}から新規追加ID: {new_ids}")
                
                collected_products.extend(new_products)
                logger.info(f"週{week} ページ{page}: {len(new_products)}個追加、合計{len(collected_products)}個")
                
                if len(collected_products) >= min_count:
                    break
                
                # 次ページをチェックする前に少し待機
                time.sleep(self.rate_limit)
        
        # 最低要件を満たさない場合
        if len(collected_products) < min_count:
            logger.warning(
                f"必要な製品数（{min_count}個）を収集できませんでした。"
                f"現在: {len(collected_products)}個"
            )
            
            # 詳細なデバッグ情報を出力
            if collected_products:
                logger.debug("最終収集製品リスト:")
                for i, p in enumerate(collected_products, 1):
                    logger.debug(f"{i}. ID={p['product_id']}, {p['brand']} {p['name']}")
                    logger.debug(f"  カテゴリ: {p.get('categories', [])}")
                    logger.debug(f"  カテゴリID: {p.get('category_ids', [])}")
                
                product_names = [f"{p['brand']} {p['name']}" for p in collected_products]
                logger.info(f"収集された製品: {', '.join(product_names)}")
        
        return collected_products