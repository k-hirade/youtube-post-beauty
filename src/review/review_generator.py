"""
@file: review_generator.py
@desc: OpenAI APIを活用して製品レビューの短い要約を生成するモジュール
"""

import os
import time
import logging
import random
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

# OpenAI APIクライアント
import openai

# ロガー設定
logger = logging.getLogger(__name__)

class ReviewGenerator:
    """製品レビューを生成するクラス"""
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        model: str = "gpt-3.5-turbo",
        temperature: float = 0.8,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        """
        初期化
        
        Args:
            api_key: OpenAI APIキー（Noneの場合は環境変数から取得）
            model: 使用するモデル名
            temperature: 生成の多様性（0.0-1.0）
            max_retries: 最大リトライ回数
            retry_delay: リトライ間隔（秒）
        """
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI APIキーが設定されていません")
        
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # APIクライアント設定
        openai.api_key = self.api_key
    
    def _get_system_prompt(self) -> str:
        """システムプロンプトを生成"""
        return """
あなたは美容製品に関する短い感想を生成する専門家です。
以下のフォーマットとルールに従って感想を作成してください：

- 20文字以内の短い感想を3つ作成してください
- 表現はバラエティに富んだものにしてください
- 若い女性が使用した感想として書いてください
- 肌への効果や使用感を具体的に表現してください
- 自然な表現を使ってください（SNSで友達に伝えるような感じで）
- 絵文字は使わないでください
"""
    
    def _get_user_prompt(self, product: Dict[str, Any]) -> str:
        """ユーザープロンプトを生成"""
        return f"""
「{product['brand']}」の「{product['name']}」についての感想を3つ作成してください。
ジャンル: {product['genre']}

各感想は必ず20文字以内にしてください。
出力は3行でそれぞれの感想だけをシンプルに書いてください。
"""
    
    def _parse_response(self, response_text: str) -> List[str]:
        """APIレスポンスから感想を抽出"""
        lines = [line.strip() for line in response_text.strip().split('\n')]
        # 空行を除外
        summaries = [line for line in lines if line]
        
        # 最大3つまで取得
        return summaries[:3]
    
    def generate_reviews(self, product: Dict[str, Any]) -> List[str]:
        """
        製品の短いレビューを生成
        
        Args:
            product: 製品情報辞書
        
        Returns:
            生成された要約のリスト（最大3つ）
        """
        logger.info(f"レビュー生成開始: {product['name']}")
        
        for attempt in range(self.max_retries):
            try:
                system_prompt = self._get_system_prompt()
                user_prompt = self._get_user_prompt(product)
                
                response = openai.ChatCompletion.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=self.temperature,
                    max_tokens=150,
                    n=1
                )
                
                response_text = response.choices[0].message.content
                summaries = self._parse_response(response_text)
                
                # バリデーション：20文字以内か確認
                valid_summaries = []
                for summary in summaries:
                    if len(summary) <= 20:
                        valid_summaries.append(summary)
                    else:
                        # 長すぎる場合は切り詰め
                        valid_summaries.append(summary[:20])
                
                logger.info(f"レビュー生成成功: {len(valid_summaries)}件")
                return valid_summaries
                
            except Exception as e:
                logger.error(f"レビュー生成エラー (試行 {attempt+1}/{self.max_retries}): {str(e)}")
                
                if attempt < self.max_retries - 1:
                    # 次のリトライまで待機（エクスポネンシャルバックオフ）
                    sleep_time = self.retry_delay * (2 ** attempt)
                    time.sleep(sleep_time)
                else:
                    logger.error("リトライ上限に達しました。フォールバックレビューを使用します。")
                    # フォールバックとして汎用的なレビューを返す
                    return self._get_fallback_reviews(product['genre'])
        
        # すべてのリトライが失敗した場合
        return self._get_fallback_reviews(product['genre'])
    
    def _get_fallback_reviews(self, genre: str) -> List[str]:
        """
        APIが失敗した時のフォールバックレビュー
        
        Args:
            genre: 製品ジャンル
        
        Returns:
            フォールバックレビューのリスト
        """
        # ジャンル別のフォールバックレビュー
        fallbacks = {
            "化粧水": [
                "肌がもっちり潤う",
                "つけ心地さっぱり",
                "乾燥知らずになった"
            ],
            "乳液": [
                "しっとり肌守る",
                "伸びがいいのに軽い",
                "ベタつかず保湿◎"
            ],
            "美容液": [
                "ハリ実感できた！",
                "毛穴目立たなくなる",
                "透明感がアップ"
            ],
            "パック": [
                "翌朝肌が違う",
                "集中保湿できる",
                "手軽に贅沢ケア"
            ]
        }
        
        # 該当ジャンルがなければ汎用レビュー
        if genre not in fallbacks:
            return [
                "コスパ最高でリピ確定",
                "使い心地がイイ",
                "効果実感できた"
            ]
        
        return fallbacks[genre]
