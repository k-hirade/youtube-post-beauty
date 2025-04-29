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
        self.logger = logging.getLogger(__name__)
    
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
                        product.get("product_url", ""),
                        product.get("brand_url", ""),
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
                        product.get("product_url", ""),
                        product.get("brand_url", ""),
                        product["rank"],
                        now
                    )
                )
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            self.logger.error(f"製品保存エラー: {str(e)}")
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
                thumbnail_gs_uri TEXT,
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
            
            # テーブル作成
            conn.executescript(schema_sql)
            
            # ランキングタイプカラムが存在するか確認
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(runs)")
            columns = cursor.fetchall()
            column_names = [column['name'] for column in columns]
            
            # ランキングタイプカラムが存在しない場合は追加
            if 'ranking_type' not in column_names:
                try:
                    conn.execute("ALTER TABLE runs ADD COLUMN ranking_type TEXT DEFAULT '最新'")
                    logger.info("runs テーブルに ranking_type カラムを追加しました")
                except sqlite3.OperationalError:
                    # カラムが既に存在する場合は無視
                    pass
            
            # thumbnail_gs_uri カラムが存在しない場合は追加
            if 'thumbnail_gs_uri' not in column_names:
                try:
                    conn.execute("ALTER TABLE runs ADD COLUMN thumbnail_gs_uri TEXT")
                    logger.info("runs テーブルに thumbnail_gs_uri カラムを追加しました")
                except sqlite3.OperationalError:
                    # カラムが既に存在する場合は無視
                    pass
            
            conn.commit()
            conn.close()
            logger.info("データベース初期化完了")
        except Exception as e:
            logger.error(f"データベース初期化エラー: {str(e)}")
            raise
    
    def _add_products_to_spreadsheet(
        self,
        spreadsheet: Any,
        video_id: int,
        products: List[Dict[str, Any]]
    ) -> bool:
        """
        「使用製品」ワークシートに製品情報を追加
        
        Args:
            spreadsheet: スプレッドシートオブジェクト
            video_id: 動画ID
            products: 製品情報のリスト
            
        Returns:
            成功したかどうか
        """
        try:
            # 「使用製品」ワークシートを取得（なければ作成）
            try:
                worksheet = spreadsheet.worksheet("使用製品")
            except gspread.exceptions.WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet(
                    title="使用製品",
                    rows=1000,
                    cols=6  # カラム数を7から6に変更（ランク列を削除）
                )
                
                # ヘッダー設定（ランク列を削除）
                header = [
                    "動画ID", "製品ID", "製品名", "ブランド", "画像URL", "製品URL"
                ]
                worksheet.append_row(header)
            
            # 既存の製品IDを取得して、重複チェックに使用
            existing_product_ids = []
            try:
                # すべての行を取得
                all_rows = worksheet.get_all_values()
                # ヘッダー行をスキップし、製品IDのインデックス（1）から値を取得
                for row in all_rows[1:]:  # ヘッダー行をスキップ
                    if len(row) > 1:  # 行に十分な列があるか確認
                        existing_product_ids.append(row[1])  # 製品IDは2列目（インデックス1）
            except Exception as e:
                logger.warning(f"既存製品ID取得エラー: {str(e)}")
                # エラーが発生しても処理を続行
            
            # 各製品情報を追加（既存の製品はスキップ）
            added_count = 0
            skipped_count = 0
            
            for product in products:
                product_id = product.get("product_id", "")
                
                # 製品IDが既に存在する場合はスキップ
                if product_id in existing_product_ids:
                    logger.info(f"製品ID {product_id} は既に存在するためスキップします")
                    skipped_count += 1
                    continue
                
                # 新規製品の場合は追加
                row = [
                    str(video_id),
                    product_id,
                    product.get("name", ""),
                    product.get("brand", ""),
                    product.get("image_url", ""),
                    product.get("url", "")
                ]
                
                worksheet.append_row(row)
                existing_product_ids.append(product_id)  # 追加した製品IDをリストに追加
                added_count += 1
            
            logger.info(f"使用製品情報をスプレッドシートに追加成功: 動画ID {video_id}, 追加: {added_count}件, スキップ: {skipped_count}件")
            return True
            
        except Exception as e:
            logger.error(f"製品情報追加エラー: {str(e)}")
            return False
    
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
        thumbnail_gs_uri: Optional[str] = None
    ) -> bool:
        """
        実行レコードのステータスを更新
        
        Args:
            run_id: 実行ID
            status: 新しいステータス
            video_gs_uri: 動画のGCS URI（完了時）
            thumbnail_gs_uri: サムネイルのGCS URI（完了時）
            
        Returns:
            更新成功したかどうか
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Check if updated_at column exists in runs table
            cursor.execute("PRAGMA table_info(runs)")
            columns = cursor.fetchall()
            column_names = [column['name'] for column in columns]
            
            # Determine column name for primary key (could be 'id' or 'run_id')
            id_column = 'run_id'  # Default to run_id
            if 'id' in column_names and 'run_id' not in column_names:
                id_column = 'id'
                
            # Check if updated_at exists
            has_updated_at = 'updated_at' in column_names
            
            # Prepare SQL based on available columns and parameters
            if video_gs_uri and thumbnail_gs_uri:
                if has_updated_at:
                    sql = f"""
                        UPDATE runs 
                        SET status = ?, updated_at = ?, video_gs_uri = ?, thumbnail_gs_uri = ?
                        WHERE {id_column} = ?
                    """
                    cursor.execute(sql, (status, datetime.now().isoformat(), video_gs_uri, thumbnail_gs_uri, run_id))
                else:
                    # If updated_at doesn't exist, don't include it
                    sql = f"""
                        UPDATE runs 
                        SET status = ?, video_gs_uri = ?, thumbnail_gs_uri = ?
                        WHERE {id_column} = ?
                    """
                    cursor.execute(sql, (status, video_gs_uri, thumbnail_gs_uri, run_id))
            elif video_gs_uri:
                if has_updated_at:
                    sql = f"""
                        UPDATE runs 
                        SET status = ?, updated_at = ?, video_gs_uri = ?
                        WHERE {id_column} = ?
                    """
                    cursor.execute(sql, (status, datetime.now().isoformat(), video_gs_uri, run_id))
                else:
                    sql = f"""
                        UPDATE runs 
                        SET status = ?, video_gs_uri = ?
                        WHERE {id_column} = ?
                    """
                    cursor.execute(sql, (status, video_gs_uri, run_id))
            else:
                if has_updated_at:
                    sql = f"""
                        UPDATE runs 
                        SET status = ?, updated_at = ?
                        WHERE {id_column} = ?
                    """
                    cursor.execute(sql, (status, datetime.now().isoformat(), run_id))
                else:
                    sql = f"""
                        UPDATE runs 
                        SET status = ?
                        WHERE {id_column} = ?
                    """
                    cursor.execute(sql, (status, run_id))
            
            conn.commit()
            conn.close()
            
            self.logger.info(f"実行ID {run_id} のステータスを '{status}' に更新しました")
            return True
            
        except Exception as e:
            self.logger.error(f"実行ステータス更新エラー: {str(e)}")
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
