"""
@file: review_generator.py
@desc: 製品の口コミページから要点を抽出し、短いレビュー要約を生成するモジュール
"""

import os
import time
import logging
import random
import requests
from typing import Dict, List, Optional, Any
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# OpenAI APIクライアント
from openai import OpenAI

# ロガー設定
logger = logging.getLogger(__name__)

class ReviewGenerator:
    """製品レビューを抽出・要約するクラス"""
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        model: str = "gpt-4o",
        max_retries: int = 3,
        retry_delay: float = 3.0
    ):
        """
        初期化
        
        Args:
            api_key: OpenAI APIキー（Noneの場合は環境変数から取得）
            model: 使用するモデル名
            max_retries: 最大リトライ回数
            retry_delay: リトライ間隔（秒）
        """
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI APIキーが設定されていません")
        
        self.model = model
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.base_url = "https://www.cosme.net"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Auto-Cosme-Shorts/0.1 (https://example.com/bot; bot@example.com)"
        })
        
        # APIクライアント設定
        self.client = OpenAI(api_key=self.api_key)
    
    def _get_product_reviews(self, product_id: str) -> List[str]:
        """
        製品の口コミページから実際のレビューテキストを取得
        
        Args:
            product_id: 製品ID
            
        Returns:
            レビューテキストのリスト
        """
        try:
            # 製品の口コミページのURL
            url = f"{self.base_url}/products/{product_id}"
            logger.info(f"口コミページ取得中: {url}")
            
            # ページを取得
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            # HTMLをパース
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 口コミテキストを抽出
            reviews = []
            review_elements = soup.select("p.review-text.description")
            
            logger.info(f"口コミ要素数: {len(review_elements)}")
            
            for elem in review_elements[:5]:  # 最大で5つの口コミを取得
                review_text = elem.text.strip()
                if review_text:
                    reviews.append(review_text)
            
            return reviews
            
        except Exception as e:
            logger.error(f"口コミ取得エラー: {str(e)}")
            return []
    

    def _get_summary_prompt(self, product: Dict[str, Any], reviews: List[str]) -> str:
        """口コミ要約のためのプロンプトを生成"""
        reviews_text = "\n\n".join([f"口コミ{i+1}: {review}" for i, review in enumerate(reviews)])
        
        return f"""
        「{product['brand']}」の「{product['name']}」についての実際の口コミから、女性が書いたような重要な要点を3つに絞って要約し、それらをコメントとして出力してください。

        以下の口コミを分析し、最も印象的な3つのポイントを抽出してください:
        
        {reviews_text}
        
        各要点は女性が書いたように表現してください。以下のような特徴を取り入れてください：
        1. 女性特有の表現
        2. 感情表現が豊か
        3. 肌の変化や使用感などの具体的な表現
        4. 記号や絵文字は使用しないでください。

        ＊重要 出力は3行でそれぞれのコメントだけを30文字以内でシンプルに書いてください。出力の際に記号等は絶対に使用しないでください。
        """
    
    def _get_fallback_prompt(self, product: Dict[str, Any]) -> str:
        """口コミが取得できなかった場合のフォールバックプロンプト"""
        return f"""
        「{product['brand']}」の「{product['name']}」についての女性ユーザーが書いたような感想を3つ作成してください。
        ジャンル: {product['genre']}
        
        各要点は女性が書いたように表現してください。以下のような特徴を取り入れてください：
        1. 女性特有の表現
        2. 感情表現が豊か
        3. 肌の変化や使用感などの具体的な表現
        4. 記号や絵文字は使用しないでください。

        ＊重要 出力は3行でそれぞれのコメントだけを30文字以内でシンプルに書いてください。出力の際に記号等は絶対に使用しないでください。
        """
    
    def _parse_response(self, response_text: str) -> List[str]:
        """APIレスポンスから要点を抽出"""
        lines = [line.strip() for line in response_text.strip().split('\n')]
        # 空行を除外
        summaries = [line for line in lines if line]
        
        # 最大3つまで取得
        return summaries[:3]
    
    def generate_reviews(self, product: Dict[str, Any]) -> List[str]:
        """
        製品の口コミから要点を抽出して短い要約を生成
        
        Args:
            product: 製品情報辞書
        
        Returns:
            生成された要約のリスト（最大3つ）
        """
        logger.info(f"レビュー生成開始: {product['name']}")
        
        # 実際の口コミを取得
        reviews = self._get_product_reviews(product["product_id"])
        
        for attempt in range(self.max_retries):
            try:
                # 口コミが取得できた場合は要約プロンプト、取得できなかった場合はフォールバックプロンプトを使用
                if reviews:
                    logger.info(f"口コミ{len(reviews)}件を取得、要約開始")
                    user_prompt = self._get_summary_prompt(product, reviews)
                else:
                    logger.warning(f"口コミが取得できなかったため、フォールバックを使用")
                    user_prompt = self._get_fallback_prompt(product)
                
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "user", "content": user_prompt}
                    ],
                )
                
                response_text = response.choices[0].message.content
                summaries = self._parse_response(response_text)
                
                # バリデーション：30文字以内か確認
                valid_summaries = []
                for summary in summaries:
                    if len(summary) <= 40:
                        valid_summaries.append(summary)
                    else:
                        # 長すぎる場合は切り詰め
                        valid_summaries.append(summary[:40])
                
                logger.info(f"レビュー生成成功: {valid_summaries}")
                return valid_summaries[:3]  # 必ず3つだけ返す
                
            except Exception as e:
                logger.error(f"レビュー生成エラー (試行 {attempt+1}/{self.max_retries}): {str(e)}")
                
                if attempt < self.max_retries - 1:
                    # 次のリトライまで待機（エクスポネンシャルバックオフ）
                    sleep_time = self.retry_delay * (2 ** attempt)
                    time.sleep(sleep_time)