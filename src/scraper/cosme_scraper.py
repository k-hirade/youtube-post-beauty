"""
@file: cosme_scraper.py
@desc: アットコスメのPチャンネルランキングをスクレイピングするモジュール（詳細デバッグログ追加版）
"""

import time
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from scraper.config_categories import CATEGORY_MAP, CHANNEL_MAP

# ロガー設定
logger = logging.getLogger(__name__)

class CosmeNetScraper:
    """アットコスメのランキングページをスクレイピングするクラス"""
    
    BASE_URL = "https://www.cosme.net"
    RANKING_BASE_URL = "https://www.cosme.net/categories/pchannel/2/ranking/"
    
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
        
        # 設定ファイルからカテゴリーマッピングをロード
        self.CATEGORY_MAP = CATEGORY_MAP
        self.CHANNEL_MAP = CHANNEL_MAP
    
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
    
    def get_product_detail(self, product_id: str) -> Dict[str, Any]:
        """
        製品詳細ページから追加情報を取得
        
        Args:
            product_id: 製品ID
            
        Returns:
            追加情報の辞書
        """
        try:
            url = f"{self.BASE_URL}/products/{product_id}/"
            
            html = self.get_page(url)
            soup = BeautifulSoup(html, 'html.parser')
            
            # 製品画像のURLを取得
            main_image: Optional[str] = None

            carousel_box = soup.select_one(".carousel-box")
            if carousel_box:
                main_li = carousel_box.select_one("li.main_img a[href]")
                main_img_li = carousel_box.select_one("li.main_img")
                img_tag = main_img_li.select_one("img")
                main_image = img_tag['src']
                if main_li:
                    variation_url = urljoin(self.BASE_URL, main_li["href"].split("#")[0])
                    try:
                        variation_html = self.get_page(variation_url)
                        variation_soup = BeautifulSoup(variation_html, "html.parser")

                        md_img = variation_soup.select_one("p#mdImg img[src]")
                        if md_img:
                            main_image = md_img["src"]
                    except Exception as e:
                        logger.warning(f"バリエーションページ取得エラー: {variation_url} / {e}")

            if not main_image:
                first_img = soup.select_one(".carousel-box ul.pict-list li img[src]")
                main_image = first_img["src"] if first_img else None
                
            # ブランド情報を取得
            brand_info = {}
            brand_elem = soup.select_one("span.brd-name a.brand")
            if brand_elem:
                brand_name = brand_elem.text.strip()
                brand_url = urljoin(self.BASE_URL, brand_elem.get('href', ''))
                brand_info = {
                    "brand": brand_name,
                    "brand_url": brand_url
                }
            
            # 製品名を取得
            product_name = None
            product_name_elem = soup.select_one("strong.pdct-name")
            if product_name_elem:
                product_name = product_name_elem.text.strip()
            
            # 結果をマージ
            result = {
                "image_url": main_image,
                "product_url": url,
            }
            
            if brand_info:
                result.update(brand_info)
                
            if product_name:
                result["name"] = product_name
                
            return result
            
        except Exception as e:
            logger.error(f"製品詳細取得エラー: {str(e)}")
            return {}
    
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
                
                logger.debug(f"製品基本情報: ID={product_id}, 名前={product_name}, ランク={rank}")
                
                # ブランド情報
                brand_a = item.select_one("span.brand a")
                brand = brand_a.text.strip() if brand_a else "不明"
                brand_url = urljoin(self.BASE_URL, brand_a.get('href', '')) if brand_a else None
                
                # カテゴリ情報取得 (テキストベースに変更)
                category_links = item.select("span.category a")
                categories = []
                
                # デバッグ: カテゴリ要素の確認
                logger.debug(f"製品 ID={product_id} '{product_name}' のカテゴリ要素数: {len(category_links)}")
                
                for a in category_links:
                    cat_text = a.text.strip()
                    categories.append(cat_text)
                    logger.debug(f"製品 ID={product_id} のカテゴリ: {cat_text}")
                
                # 画像情報取得 (ランキングページの画像は小さいので、詳細ページを取得する)
                img_elem = item.select_one("dd.pic img")
                image_url = img_elem.get('src', '') if img_elem else ''
                
                # 価格情報
                price_elem = item.select_one("p.price")
                price_text = price_elem.text.strip() if price_elem else "不明"
                
                # 発売情報
                release_elem = item.select_one("p.onsale")
                release_text = release_elem.text.strip() if release_elem else ""
                
                # レビュー情報
                rating_elem = item.select_one("span.reviewer-average")
                rating = rating_elem.text.strip() if rating_elem else None
                
                votes_elem = item.select_one("p.votes span")
                votes = int(votes_elem.text.replace(',', '')) if votes_elem else 0
                
                # 製品情報をdict化
                product_data = {
                    "product_id": product_id,
                    "rank": rank,
                    "name": product_name,
                    "brand": brand,
                    "brand_url": brand_url,
                    "product_url": product_url,
                    "categories": categories,
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
    
    def is_product_in_genre(self, product: Dict[str, Any], genre: str) -> bool:
        """
        製品が指定されたジャンルに属するかを判定（テキストベース）
        
        Args:
            product: 製品情報の辞書
            genre: 対象ジャンル名
            
        Returns:
            True: 製品がジャンルに属する
            False: 製品がジャンルに属さない
        """
        # ジャンルが複数指定されている場合は分割
        genre_list = [g.strip() for g in genre.split(',')]
        
        # 製品カテゴリ
        product_categories = product.get("categories", [])
        
        logger.debug(f"製品: {product.get('name')} のカテゴリ: {product_categories}")
        logger.debug(f"対象ジャンル: {genre_list}")
        
        # 各ジャンルについて検証
        for g in genre_list:
            # CATEGORY_MAPから対象カテゴリのキーワードリストを取得
            target_categories = self.CATEGORY_MAP.get(g, [])
            logger.debug(f"対象カテゴリー キーワード: {target_categories}")
            
            # 製品カテゴリとターゲットカテゴリを比較
            for prod_cat in product_categories:
                for target_cat in target_categories:
                    if target_cat in prod_cat or prod_cat in target_cat:
                        logger.debug(f"カテゴリーマッチ: '{prod_cat}' と '{target_cat}'")
                        return True
                        
            # 直接ジャンル名とカテゴリ名のマッチング（バックアップ）
            for prod_cat in product_categories:
                if g in prod_cat or prod_cat in g:
                    logger.debug(f"直接マッチ: '{prod_cat}' と '{g}'")
                    return True
        
        logger.debug(f"製品: {product.get('name')} はジャンル {genre} に一致しませんでした")
        return False
    
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
        
        for product in products:
            product_id = product.get("product_id", "不明")
            product_name = product.get("name", "不明")
            
            # ジャンルに一致するか確認
            if self.is_product_in_genre(product, genre):
                # チャンネル情報追加
                product["channel"] = channel
                product["genre"] = genre
                
                # 製品詳細ページから追加情報を取得
                product_detail = self.get_product_detail(product_id)
                if product_detail:
                    # 高解像度の画像URLに更新
                    if "image_url" in product_detail and product_detail["image_url"]:
                        product["image_url"] = product_detail["image_url"]
                    
                    # 他の詳細情報も更新
                    for key, value in product_detail.items():
                        if key not in ["image_url"] and value:  # 画像URL以外の情報も更新
                            product[key] = value
                
                filtered_products.append(product)
                logger.info(f"該当製品: ID={product_id}, {product_name} ({product['brand']}), カテゴリ: {product['categories']}")
            else:
                logger.debug(f"ジャンル不一致のため除外: ID={product_id}, {product_name}")
        
        return filtered_products
    
    def download_product_images(self, products: List[Dict[str, Any]], output_dir: str) -> List[Dict[str, Any]]:
        """
        製品画像をダウンロードする
        
        Args:
            products: 製品情報のリスト
            output_dir: 画像の保存先ディレクトリ
            
        Returns:
            更新された製品情報のリスト
        """
        # 出力ディレクトリが存在することを確認
        os.makedirs(output_dir, exist_ok=True)
        
        updated_products = []
        
        for product in products:
            product_id = product.get("product_id")
            image_url = product.get("image_url")
            
            if not product_id or not image_url:
                logger.warning(f"製品IDまたは画像URLが不足しています: {product}")
                updated_products.append(product)
                continue
            
            # 画像の保存先パス
            img_path = os.path.join(output_dir, f"{product_id}.jpg")
            
            # 既に画像が存在する場合はスキップ
            if os.path.exists(img_path):
                logger.info(f"画像は既に存在します: {img_path}")
                # 保存先のパスを製品情報に追加
                product["local_image_path"] = img_path
                updated_products.append(product)
                continue
            
            # 画像のダウンロード
            try:
                logger.info(f"画像ダウンロード中: {image_url} -> {img_path}")
                self._respect_rate_limit()  # レート制限を遵守
                
                # リクエスト送信
                response = self.session.get(image_url, stream=True, timeout=30)
                response.raise_for_status()
                
                # 画像を保存
                with open(img_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                logger.info(f"画像ダウンロード成功: {img_path}")
                
                # 保存先のパスを製品情報に追加
                product["local_image_path"] = img_path
                
            except Exception as e:
                logger.error(f"画像ダウンロードエラー ({image_url}): {str(e)}")
                # エラーがあっても処理を続行
            
            updated_products.append(product)
        
        return updated_products
        
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
            if collected_products:
                logger.debug("最終収集製品リスト:")
                for i, p in enumerate(collected_products, 1):
                    logger.debug(f"{i}. ID={p['product_id']}, {p['brand']} {p['name']}")
                    logger.debug(f"  カテゴリ: {p.get('categories', [])}")
                    logger.debug(f"  画像URL: {p.get('image_url', 'なし')}")
                    logger.debug(f"  製品URL: {p.get('product_url', 'なし')}")
                    logger.debug(f"  ブランドURL: {p.get('brand_url', 'なし')}")
                
                product_names = [f"{p['brand']} {p['name']}" for p in collected_products]
                logger.info(f"収集された製品: {', '.join(product_names)}")
        
        return collected_products