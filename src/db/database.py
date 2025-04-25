"""
@file: database.py
@desc: SQLiteデータベースとの連携モジュール
"""

import os
import sqlite3
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any, Union

# ロガー設定
logger = logging.getLogger(__name__)

class CosmeDatabase:
    """アットコスメ動画生成システムのデータベース操作クラス"""
    
    def __init__(self, db_path: str = 'data/cosme.db'):
        """
        初期化
        
        Args:
            db_path: SQLiteデータベースファイルのパス
        """
        self.db_path = db_path
        self._ensure_db_dir()
        self._init_db()
    
    def _ensure_db_dir(self):
        """データベースディレクトリが存在することを確認"""
        db_dir = os.path.dirname(self.db_path)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)
    
    def _get_connection(self) -> sqlite3.Connection:
        """データベース接続を取得"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # 辞書形式で結果を取得
        return conn
    
    def _init_db(self):
        """データベースの初期化（テーブル作成）"""
        try:
            # スキーマファイルがあれば読み込む
            schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
            if os.path.exists(schema_path):
                with open(schema_path, 'r', encoding='utf-8') as f:
                    schema_sql = f.read()
            else:
                # なければハードコードされたスキーマを使用
                schema_sql = """
                CREATE TABLE IF NOT EXISTS products (
                product_id   TEXT PRIMARY KEY,
                genre        TEXT,
                channel      TEXT,
                name         TEXT,
                brand        TEXT,
                image_url    TEXT,
                product_url  TEXT,
                brand_url    TEXT,
                scraped_rank INTEGER,
                first_seen   DATETIME,
                last_used    DATETIME
                );
                CREATE TABLE IF NOT EXISTS runs (
                run_id       INTEGER PRIMARY KEY AUTOINCREMENT,
                genre        TEXT,
                channel      TEXT,
                ranking_type TEXT DEFAULT '最新',
                created_at   DATETIME,
                status       TEXT,
                video_gs_uri TEXT,
                error_details TEXT
                );
                CREATE TABLE IF NOT EXISTS review_cache (
                product_id   TEXT PRIMARY KEY,
                summary1     TEXT,
                summary2     TEXT,
                summary3     TEXT,
                updated_at   DATETIME
                );
                """
                
            conn = self._get_connection()
            
            # ランキングタイプカラムが存在するか確認
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(runs)")
            columns = cursor.fetchall()
            column_names = [column['name'] for column in columns]
            
            # テーブル作成
            conn.executescript(schema_sql)
            
            # ランキングタイプカラムが存在しない場合は追加
            if 'ranking_type' not in column_names:
                try:
                    conn.execute("ALTER TABLE runs ADD COLUMN ranking_type TEXT DEFAULT '最新'")
                    logger.info("runs テーブルに ranking_type カラムを追加しました")
                except sqlite3.OperationalError:
                    # カラムが既に存在する場合は無視
                    pass
            
            conn.commit()
            conn.close()
            logger.info("データベース初期化完了")
        except Exception as e:
            logger.error(f"データベース初期化エラー: {str(e)}")
            raise
    
    def save_product(self, product: Dict[str, Any]) -> bool:
        """
        製品情報をデータベースに保存
        
        Args:
            product: 製品情報辞書
        
        Returns:
            成功したかどうか
        """
        try:
            now = datetime.now().isoformat()
            conn = self._get_connection()
            
            # 製品が既に存在するか確認
            cursor = conn.cursor()
            cursor.execute(
                "SELECT product_id FROM products WHERE product_id = ?",
                (product["product_id"],)
            )
            exists = cursor.fetchone()
            
            if exists:
                # 既存の場合は更新
                cursor.execute(
                    """
                    UPDATE products
                    SET genre = ?, channel = ?, name = ?, brand = ?,
                        image_url = ?, product_url = ?, brand_url = ?, scraped_rank = ?
                    WHERE product_id = ?
                    """,
                    (
                        product["genre"],
                        product["channel"],
                        product["name"],
                        product["brand"],
                        product["image_url"],
                        product.get("product_url", ""),  # 新しく追加されたフィールド
                        product.get("brand_url", ""),    # 新しく追加されたフィールド
                        product["rank"],
                        product["product_id"]
                    )
                )
            else:
                # 新規の場合は挿入
                cursor.execute(
                    """
                    INSERT INTO products (
                        product_id, genre, channel, name, brand,
                        image_url, product_url, brand_url, scraped_rank, first_seen
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        product["product_id"],
                        product["genre"],
                        product["channel"],
                        product["name"],
                        product["brand"],
                        product["image_url"],
                        product.get("product_url", ""),  # 新しく追加されたフィールド
                        product.get("brand_url", ""),    # 新しく追加されたフィールド
                        product["rank"],
                        now
                    )
                )
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"製品保存エラー: {str(e)}")
            return False
    
    def save_products(self, products: List[Dict[str, Any]]) -> int:
        """
        複数の製品情報を一括保存
        
        Args:
            products: 製品情報辞書のリスト
        
        Returns:
            保存に成功した製品数
        """
        success_count = 0
        for product in products:
            if self.save_product(product):
                success_count += 1
        
        return success_count
    
    def get_products_by_criteria(
        self,
        genre: str,
        channel: str,
        limit: int = 10,
        exclude_used: bool = True,
        days_threshold: int = 30
    ) -> List[Dict[str, Any]]:
        """
        条件に合致する製品を取得
        
        Args:
            genre: ジャンル
            channel: チャンネル
            limit: 取得する最大数
            exclude_used: 最近使われた製品を除外するか
            days_threshold: 除外する日数のしきい値
            
        Returns:
            製品情報辞書のリスト
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            query = """
            SELECT * FROM products
            WHERE genre = ? AND channel = ?
            """
            
            params = [genre, channel]
            
            if exclude_used:
                # 最近使われた製品を除外
                query += """
                AND (last_used IS NULL OR 
                    julianday('now') - julianday(last_used) > ?)
                """
                params.append(days_threshold)
            
            query += " ORDER BY scraped_rank ASC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            
            products = []
            for row in cursor.fetchall():
                product = dict(row)
                products.append(product)
            
            conn.close()
            return products
        except Exception as e:
            logger.error(f"製品検索エラー: {str(e)}")
            return []
    
    def mark_products_as_used(self, product_ids: List[str]) -> bool:
        """
        製品を使用済みとしてマーク
        
        Args:
            product_ids: 製品IDのリスト
            
        Returns:
            成功したかどうか
        """
        try:
            now = datetime.now().isoformat()
            conn = self._get_connection()
            cursor = conn.cursor()
            
            for product_id in product_ids:
                cursor.execute(
                    "UPDATE products SET last_used = ? WHERE product_id = ?",
                    (now, product_id)
                )
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"製品使用マークエラー: {str(e)}")
            return False
    
    def create_run(self, genre: str, channel: str, ranking_type: str = "最新") -> Optional[int]:
        """
        新しい実行記録を作成
        
        Args:
            genre: ジャンル
            channel: チャンネル
            ranking_type: ランキングタイプ（最新、お好みなど）
            
        Returns:
            作成されたrun_id、失敗時はNone
        """
        try:
            now = datetime.now().isoformat()
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                """
                INSERT INTO runs (genre, channel, created_at, status, ranking_type)
                VALUES (?, ?, ?, 'started', ?)
                """,
                (genre, channel, now, ranking_type)
            )
            
            run_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return run_id
        except Exception as e:
            logger.error(f"実行記録作成エラー: {str(e)}")
            return None
    
    def update_run_status(
        self,
        run_id: int,
        status: str,
        video_gs_uri: Optional[str] = None,
        ranking_type: Optional[str] = None,
        notes: Optional[str] = None
    ) -> bool:
        """
        実行記録のステータスを更新
        
        Args:
            run_id: 実行ID
            status: 新しいステータス
            video_gs_uri: 動画のCloud StorageのURI（成功時）
            ranking_type: ランキングタイプ
            notes: 追加の備考
            
        Returns:
            成功したかどうか
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            query = "UPDATE runs SET status = ?"
            params = [status]
            
            if video_gs_uri:
                query += ", video_gs_uri = ?"
                params.append(video_gs_uri)
            
            if ranking_type:
                query += ", ranking_type = ?"
                params.append(ranking_type)
                
            if notes:
                query += ", error_details = ?"
                params.append(notes)
                
            query += " WHERE run_id = ?"
            params.append(run_id)
            
            cursor.execute(query, params)
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"実行記録更新エラー: {str(e)}")
            return False

    def save_reviews(
        self,
        product_id: str,
        summaries: List[str]
    ) -> bool:
        """
        製品レビュー要約を保存
        
        Args:
            product_id: 製品ID
            summaries: 要約リスト（最大3つ）
            
        Returns:
            成功したかどうか
        """
        try:
            now = datetime.now().isoformat()
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 既存のレビューがあるか確認
            cursor.execute(
                "SELECT product_id FROM review_cache WHERE product_id = ?",
                (product_id,)
            )
            exists = cursor.fetchone()
            
            # リストの長さを3に調整
            while len(summaries) < 3:
                summaries.append("")
            summaries = summaries[:3]  # 最大3つまで
            
            if exists:
                # 既存なら更新
                cursor.execute(
                    """
                    UPDATE review_cache
                    SET summary1 = ?, summary2 = ?, summary3 = ?, updated_at = ?
                    WHERE product_id = ?
                    """,
                    (summaries[0], summaries[1], summaries[2], now, product_id)
                )
            else:
                # 新規なら挿入
                cursor.execute(
                    """
                    INSERT INTO review_cache
                    (product_id, summary1, summary2, summary3, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (product_id, summaries[0], summaries[1], summaries[2], now)
                )
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"レビュー保存エラー: {str(e)}")
            return False
    
    def get_reviews(self, product_id: str) -> Optional[Dict[str, str]]:
        """
        製品レビュー要約を取得
        
        Args:
            product_id: 製品ID
            
        Returns:
            レビュー情報辞書、なければNone
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                """
                SELECT summary1, summary2, summary3, updated_at
                FROM review_cache
                WHERE product_id = ?
                """,
                (product_id,)
            )
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    "summaries": [row["summary1"], row["summary2"], row["summary3"]],
                    "updated_at": row["updated_at"]
                }
            else:
                return None
        except Exception as e:
            logger.error(f"レビュー取得エラー: {str(e)}")
            return None
