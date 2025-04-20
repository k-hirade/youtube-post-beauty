"""
@file: video_maker.py
@desc: FFmpegを直接使用して縦型ショート動画を作成するモジュール
"""

import os
import logging
import random
import tempfile
import subprocess
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import shutil
import re
import sys

# 音声関連のユーティリティをインポート
# sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from video.voice_utils import generate_narration, get_audio_duration, create_silent_audio, merge_audio_files

# ロガー設定
logger = logging.getLogger(__name__)

class VideoMaker:
    """FFmpegを使用して縦型商品紹介動画を作成するクラス"""
    
    # 縦型動画の基本サイズ
    VIDEO_WIDTH = 1080
    VIDEO_HEIGHT = 1920
    
    # フォント設定
    DEFAULT_FONT_SIZE = 48
    TITLE_FONT_SIZE = 64
    BRAND_FONT_SIZE = 36
    REVIEW_FONT_SIZE = 42
    
    # テキストカラー
    TEXT_COLOR = (255, 255, 255)  # white
    SHADOW_COLOR = (0, 0, 0)  # black
    RANK_COLOR = (255, 215, 0)  # gold
    TITLE_COLOR = (255, 255, 255)  # white
    
    # 背景カラー
    BG_COLOR = (30, 30, 30)  # ダークグレー
    
    def __init__(
        self,
        output_dir: str = 'data/output',
        temp_dir: str = 'data/temp',
        font_path: Optional[str] = None,
        bgm_dir: str = 'data/bgm'
    ):
        """
        初期化
        
        Args:
            output_dir: 出力ディレクトリ
            temp_dir: 一時ファイルディレクトリ
            font_path: フォントファイルのパス
            bgm_dir: BGM用音声ファイルディレクトリ
        """
        self.output_dir = output_dir
        self.temp_dir = temp_dir
        self.font_path = font_path
        self.bgm_dir = bgm_dir
        
        # ディレクトリ作成
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(temp_dir, exist_ok=True)
        
        # フォントファイルが指定されていない場合は、デフォルトを使用
        if not self.font_path:
            # デフォルトフォントの設定（OSによって異なる）
            import platform
            system = platform.system()

            if system == 'Darwin':  # macOS
                self.font_path = '/System/Library/Fonts/Supplemental/Arial Unicode.ttf'
                self.noto_sans_jp_path = '/Library/Fonts/NotoSansJP-Regular.otf'
                self.noto_sans_jp_bold_path = '/Library/Fonts/NotoSansCJKjp-Bold.otf'
            elif system == 'Windows':  # Windows
                self.font_path = 'C:\\Windows\\Fonts\\arial.ttf'
                self.noto_sans_jp_path = 'C:\\Windows\\Fonts\\NotoSansJP-Regular.otf'
                self.noto_sans_jp_bold_path = 'C:\\Windows\\Fonts\\NotoSansCJKjp-Bold.otf'
            else:  # Linux
                self.font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
                self.noto_sans_jp_path = '/usr/share/fonts/opentype/noto/NotoSansJP-Regular.otf'
                self.noto_sans_jp_bold_path = '/usr/share/fonts/opentype/noto/NotoSansCJKjp-Bold.otf'
        
        # フォントが存在するか確認
        if not os.path.exists(self.font_path):
            logger.warning(f"指定したフォント({self.font_path})が見つかりません。代替フォントを使用します。")
            self.font_path = None
    
    def get_font(self, size: int, font_path: str = None) -> ImageFont.FreeTypeFont:
        """
        適切なフォントを取得
        
        Args:
            size: フォントサイズ
            font_path: フォントパス
            
        Returns:
            ImageFont.FreeTypeFont: フォントオブジェクト
        """
        if font_path and os.path.exists(font_path):
            try:
                font = ImageFont.truetype(font_path, size)
                return font
            except Exception as e:
                logger.warning(f"指定されたフォントを読み込めませんでした: {font_path} - {e}")
        
        # Noto Sans JP Bold を試行
        if hasattr(self, 'noto_sans_jp_bold_path') and os.path.exists(self.noto_sans_jp_bold_path):
            try:
                font = ImageFont.truetype(self.noto_sans_jp_bold_path, size)
                return font
            except Exception as e:
                logger.warning(f"Noto Sans JP Bold を読み込めませんでした: {e}")
        
        # デフォルトフォントを試行
        try:
            font = ImageFont.truetype(self.font_path, size)
            return font
        except Exception as e:
            logger.warning(f"デフォルトフォントを読み込めませんでした: {e}")
        
        # 代替フォントを試行
        font_paths = [
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/Library/Fonts/Arial.ttf",
            "C:\\Windows\\Fonts\\arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
        ]
        
        for path in font_paths:
            if os.path.exists(path):
                try:
                    font = ImageFont.truetype(path, size)
                    logger.info(f"代替フォントを使用します: {path}")
                    return font
                except:
                    pass
        
        # すべて失敗した場合はデフォルトフォントを使用
        logger.warning("システムフォントが見つかりません。デフォルトフォントを使用します。")
        return ImageFont.load_default()
    
    def apply_text_outline(
        self, 
        draw: ImageDraw.Draw, 
        text: str, 
        x: int, 
        y: int, 
        font: ImageFont.FreeTypeFont, 
        text_color: Tuple, 
        outline_color: Tuple = None, 
        outline_width: int = 5
    ) -> None:
        """
        テキストに縁取り効果を適用
        
        Args:
            draw: ImageDrawオブジェクト
            text: 描画するテキスト
            x: X座標
            y: Y座標
            font: フォント
            text_color: テキスト色 (R, G, B)
            outline_color: 縁取り色 (R, G, B)
            outline_width: 縁取り幅
        """
        if outline_color is None:
            draw.text((x, y), text, font=font, fill=text_color)
            return

        step_size = max(1, outline_width // 10)
        
        for offset_x in range(-outline_width, outline_width + 1, step_size):
            for offset_y in range(-outline_width, outline_width + 1, step_size):
                if abs(offset_x) + abs(offset_y) <= outline_width * 1.5:  # 縁取りの形状を調整
                    draw.text((x + offset_x, y + offset_y), text, font=font, fill=outline_color)
        
        # メインテキストを描画
        draw.text((x, y), text, font=font, fill=text_color)
    
    def calculate_text_width(
        self, 
        text: str, 
        font: ImageFont.FreeTypeFont, 
        draw: ImageDraw.Draw
    ) -> int:
        """
        テキストの幅を計算
        
        Args:
            text: テキスト
            font: フォント
            draw: ImageDrawオブジェクト
            
        Returns:
            int: テキストの幅（ピクセル）
        """
        try:
            width = draw.textlength(text, font=font)
            return width
        except AttributeError:
            # 古いPILバージョン用
            try:
                width = font.getlength(text)
                return width
            except AttributeError:
                # さらに古いバージョン用
                width, _ = draw.textsize(text, font=font)
                return width
    
    def resize_image_to_fill(
        self, 
        img: Image.Image, 
        width: int, 
        height: int
    ) -> Image.Image:
        """
        画像をリサイズして指定サイズを満たすようにする
        
        Args:
            img: 元の画像
            width: 目標幅
            height: 目標高さ
            
        Returns:
            Image.Image: リサイズされた画像
        """
        img_width, img_height = img.size
        img_aspect = img_width / img_height
        frame_aspect = width / height
        
        if img_aspect > frame_aspect:
            # 画像が横長の場合、中央から切り抜く
            new_width = int(img_height * frame_aspect)
            left = (img_width - new_width) // 2
            img = img.crop((left, 0, left + new_width, img_height))
        elif img_aspect < frame_aspect:
            # 画像が縦長の場合、上部から切り抜く
            new_height = int(img_width / frame_aspect)
            top = 0  # 上詰め
            img = img.crop((0, top, img_width, top + new_height))
        
        # 目標サイズにリサイズ
        return img.resize((width, height), Image.LANCZOS)
    
    def _create_product_slide(
        self,
        product: Dict[str, Any],
        rank: int
    ) -> Image.Image:
        """
        製品スライドの作成（画像と商品名のみ表示）
        
        Args:
            product: 製品情報
            rank: 順位
        
        Returns:
            Image.Image: 製品スライド画像
        """
        # 背景画像を作成
        img = Image.new('RGB', (self.VIDEO_WIDTH, self.VIDEO_HEIGHT), self.BG_COLOR)
        draw = ImageDraw.Draw(img)
        
        # 画像読み込みの準備
        img_loaded = False
        product_img = None
        
        # 1. ローカルに保存された画像パスを確認（スクレイパーからダウンロード済み）
        if 'local_image_path' in product and product['local_image_path']:
            local_path = product['local_image_path']
            if os.path.exists(local_path):
                try:
                    logger.info(f"ローカル画像を読み込み中: {local_path}")
                    product_img = Image.open(local_path)
                    img_loaded = True
                except Exception as e:
                    logger.error(f"ローカル画像読み込みエラー: {local_path} - {str(e)}")
                    img_loaded = False
        
        # 2. 製品IDから一時ディレクトリの画像を確認
        if not img_loaded and 'product_id' in product:
            img_path = os.path.join(self.temp_dir, f"{product['product_id']}.jpg")
            if os.path.exists(img_path):
                try:
                    logger.info(f"一時ディレクトリの画像を読み込み中: {img_path}")
                    product_img = Image.open(img_path)
                    img_loaded = True
                except Exception as e:
                    logger.error(f"一時ディレクトリの画像読み込みエラー: {img_path} - {str(e)}")
                    img_loaded = False
        
        # 3. image_urlから直接ダウンロード（最終手段）
        if not img_loaded and 'image_url' in product and product['image_url']:
            image_url = product['image_url']
            try:
                logger.info(f"画像をURLから直接ダウンロード中: {image_url}")
                # 一時保存先
                img_path = os.path.join(self.temp_dir, f"{product['product_id']}.jpg")
                os.makedirs(os.path.dirname(img_path), exist_ok=True)
                
                # リクエスト送信（シンプルな実装）
                import requests
                response = requests.get(image_url, timeout=30)
                response.raise_for_status()
                
                # 画像を保存
                with open(img_path, 'wb') as f:
                    f.write(response.content)
                    
                # 保存した画像を読み込み
                product_img = Image.open(img_path)
                img_loaded = True
                logger.info(f"画像を直接ダウンロードして保存: {img_path}")
            except Exception as e:
                logger.error(f"画像ダウンロードエラー: {str(e)}")
                img_loaded = False
        
        # 4. ダミー画像を使用
        if not img_loaded:
            try:
                # まずプロジェクトのダミー画像を試す
                dummy_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'assets', 'dummy_product.jpg')
                
                # ダミー画像がなければ作成
                if not os.path.exists(dummy_path):
                    logger.info(f"ダミー画像を作成: {dummy_path}")
                    self._create_dummy_image(dummy_path, product.get('name', 'No Image'))
                
                product_img = Image.open(dummy_path)
                img_loaded = True
                logger.info(f"ダミー画像を使用: {dummy_path}")
            except Exception as e:
                logger.error(f"ダミー画像読み込みエラー: {str(e)}")
                # ここでは何もせず、下でメモリ上にダミー画像を作成
        
        # 5. どの方法でも失敗した場合、メモリ上にダミー画像を作成
        if not img_loaded or product_img is None:
            logger.warning("すべての画像取得方法が失敗したため、メモリ上にダミー画像を作成します")
            width, height = 800, 800
            product_img = Image.new('RGB', (width, height), color=(200, 200, 200))
            draw_dummy = ImageDraw.Draw(product_img)
            
            # テキストを描画
            dummy_text = product.get('name', 'No Image')
            try:
                font = self.get_font(60, self.noto_sans_jp_path)
            except Exception:
                font = ImageFont.load_default()
            
            text_width = self.calculate_text_width(dummy_text, font, draw_dummy)
            text_height = int(60 * 1.2)  # 概算
            position = ((width - text_width) // 2, (height - text_height) // 2)
            draw_dummy.text(position, dummy_text, fill=(100, 100, 100), font=font)
        
        # 画像のリサイズと配置
        try:
            # リサイズ（アスペクト比保持、最大サイズ調整）
            img_width, img_height = product_img.size
            aspect_ratio = img_width / img_height
            
            # 画面の40%を最大高さとする
            max_height = int(self.VIDEO_HEIGHT * 0.4)
            new_height = min(max_height, img_height)
            new_width = int(new_height * aspect_ratio)
            
            if new_width > self.VIDEO_WIDTH * 0.8:
                new_width = int(self.VIDEO_WIDTH * 0.8)
                new_height = int(new_width / aspect_ratio)
            
            product_img = product_img.resize((new_width, new_height), Image.LANCZOS)
            
            # 画像を上部（画面の35%位置）に配置して、画像と下部のテキストの間が画面中央になるようにする
            img_x = (self.VIDEO_WIDTH - new_width) // 2
            img_y = int(self.VIDEO_HEIGHT * 0.35) - (new_height // 2)
            
            # 画像貼り付け
            img.paste(product_img, (img_x, img_y))
            
            # 商品名を画像の下に表示
            product_name = product.get('name', 'No Name')
            brand_name = product.get('brand', 'No Brand')
            name_font = self.get_font(self.TITLE_FONT_SIZE, self.noto_sans_jp_bold_path)
            brand_font = self.get_font(self.BRAND_FONT_SIZE, self.noto_sans_jp_path)
            
            # 商品名の表示位置（中央に配置）
            name_y = int(self.VIDEO_HEIGHT * 0.5)  # 画面の中央
            
            # 商品名を中央揃えで表示
            name_width = self.calculate_text_width(product_name, name_font, draw)
            name_x = (self.VIDEO_WIDTH - name_width) // 2
            
            # 商品名を表示（白色で縁取り）
            self.apply_text_outline(
                draw=draw,
                text=product_name,
                x=name_x,
                y=name_y,
                font=name_font,
                text_color=self.TITLE_COLOR,
                outline_color=self.SHADOW_COLOR,
                outline_width=2
            )
            
            # ブランド名の表示位置（商品名の下）
            brand_y = name_y + self.TITLE_FONT_SIZE + 10
            
            # ブランド名を中央揃えで表示
            brand_width = self.calculate_text_width(brand_name, brand_font, draw)
            brand_x = (self.VIDEO_WIDTH - brand_width) // 2
            
            # ブランド名を表示（グレーで）
            draw.text(
                (brand_x, brand_y),
                brand_name,
                font=brand_font,
                fill=(200, 200, 200)  # ライトグレー
            )
        except Exception as e:
            logger.error(f"画像処理エラー: {str(e)}")
        
        # フォント設定
        rank_font = self.get_font(self.TITLE_FONT_SIZE * 1.3, self.noto_sans_jp_bold_path)
        
        # 順位表示
        rank_text = f"{rank}位"
        self.apply_text_outline(
            draw=draw,
            text=rank_text,
            x=50,
            y=50,
            font=rank_font,
            text_color=self.RANK_COLOR,
            outline_color=self.SHADOW_COLOR,
            outline_width=2
        )
        
        return img

    def _create_review_comment_slide(
        self,
        product: Dict[str, Any],
        rank: int,
        comment: str,
        comment_position: str = "top",  # "top", "middle", "bottom"
        comment_index: int = 0  # 0, 1, 2 (コメントのインデックス)
    ) -> Image.Image:
        """
        レビューコメント付きの製品スライドを作成
        
        Args:
            product: 製品情報
            rank: 順位
            comment: コメントテキスト
            comment_position: コメントの位置
            comment_index: コメントのインデックス（色分け用）
            
        Returns:
            Image.Image: レビューコメント付き製品スライド
        """
        # 製品スライドを基本として作成し、その上にコメントを追加する
        img = self._create_product_slide(product, rank)
        draw = ImageDraw.Draw(img)
        
        # フォント設定
        comment_font = self.get_font(self.REVIEW_FONT_SIZE, self.noto_sans_jp_path)
        
        # コメントを四角で囲んで表示
        comment_text = f"「{comment}」"
        comment_width = self.calculate_text_width(comment_text, comment_font, draw)
        
        # コメントインデックスに応じて色を設定
        if comment_index == 0:
            border_color = (255, 50, 50)  # 赤色
        elif comment_index == 1:
            border_color = (50, 255, 50)  # 緑色
        else:
            border_color = (50, 50, 255)  # 青色
        
        # コメントが長い場合は折り返し
        max_width = int(self.VIDEO_WIDTH * 0.8)
        if comment_width > max_width:
            # 適当な位置で折り返し
            words = list(comment_text)
            lines = []
            current_line = ""
            
            for word in words:
                test_line = current_line + word
                test_width = self.calculate_text_width(test_line, comment_font, draw)
                
                if test_width <= max_width:
                    current_line = test_line
                else:
                    lines.append(current_line)
                    current_line = word
            
            if current_line:
                lines.append(current_line)
            
            # 複数行のコメントを描画
            line_height = int(self.REVIEW_FONT_SIZE * 1.5)
            comment_height = line_height * len(lines)
            
            # コメント位置の決定
            if comment_position == "top":
                # 上部に表示（画面上部から10%の位置）
                comment_y = int(self.VIDEO_HEIGHT * 0.1)
            elif comment_position == "middle":
                # 中央に表示（画面の中央）
                comment_y = int(self.VIDEO_HEIGHT * 0.5) - (comment_height // 2)
            else:  # bottom
                # 下部に表示（画面下部から10%上の位置）
                comment_y = int(self.VIDEO_HEIGHT * 0.9) - comment_height
            
            # 背景の四角を描画
            padding = 20
            box_top = comment_y - padding
            box_bottom = comment_y + comment_height + padding
            box_left = (self.VIDEO_WIDTH - max_width) // 2 - padding
            box_right = (self.VIDEO_WIDTH + max_width) // 2 + padding
            
            draw.rectangle(
                [(box_left, box_top), (box_right, box_bottom)],
                fill=(0, 0, 0, 128),  # 半透明黒
                outline=border_color,  # インデックスに応じた色の枠
                width=5  # 太い枠線
            )
            
            # 各行を描画
            for i, line in enumerate(lines):
                line_y = comment_y + i * line_height
                line_width = self.calculate_text_width(line, comment_font, draw)
                line_x = (self.VIDEO_WIDTH - line_width) // 2
                
                draw.text(
                    (line_x, line_y),
                    line,
                    font=comment_font,
                    fill=self.TEXT_COLOR
                )
        else:
            # 1行のコメント
            # コメント位置の決定
            if comment_position == "top":
                # 上部に表示（画面上部から10%の位置）
                comment_y = int(self.VIDEO_HEIGHT * 0.1)
            elif comment_position == "middle":
                # 中央に表示（画面の中央）
                comment_y = int(self.VIDEO_HEIGHT * 0.5) - (self.REVIEW_FONT_SIZE // 2)
            else:  # bottom
                # 下部に表示（画面下部から10%上の位置）
                comment_y = int(self.VIDEO_HEIGHT * 0.9) - self.REVIEW_FONT_SIZE
            
            comment_x = (self.VIDEO_WIDTH - comment_width) // 2
            
            # 背景の四角を描画
            padding = 20
            box_width = comment_width + padding * 2
            box_height = self.REVIEW_FONT_SIZE + padding * 2
            
            draw.rectangle(
                [(comment_x - padding, comment_y - padding), 
                (comment_x + comment_width + padding, comment_y + box_height - padding)],
                fill=(0, 0, 0, 128),  # 半透明黒
                outline=border_color,  # インデックスに応じた色の枠
                width=5  # 太い枠線
            )
            
            # コメントを描画
            draw.text(
                (comment_x, comment_y),
                comment_text,
                font=comment_font,
                fill=self.TEXT_COLOR
            )
        
        return img

    def _add_comment_to_slide(
            self,
            base_slide: Image.Image,
            product: Dict[str, Any],
            rank: int,
            comment: str,
            comment_position: str,
            comment_index: int
        ) -> Image.Image:
            """
            既存のスライドにコメントを追加する
            
            Args:
                base_slide: ベースとなるスライド画像
                product: 製品情報
                rank: 順位
                comment: コメントテキスト
                comment_position: コメントの位置 ("top", "middle", "bottom")
                comment_index: コメントのインデックス（色分け用）
                
            Returns:
                Image.Image: コメントが追加されたスライド画像
            """
            # スライドのコピーを作成して編集
            slide = base_slide.copy()
            draw = ImageDraw.Draw(slide)
            
            # フォント設定
            comment_font = self.get_font(self.REVIEW_FONT_SIZE, self.noto_sans_jp_path)
            
            # コメントを「」で囲む
            comment_text = f"「{comment}」"
            comment_width = self.calculate_text_width(comment_text, comment_font, draw)
            
            # コメントインデックスに応じて色を設定
            if comment_index == 0:
                border_color = (255, 50, 50)  # 赤色
            elif comment_index == 1:
                border_color = (50, 255, 50)  # 緑色
            else:
                border_color = (50, 50, 255)  # 青色
            
            # コメント位置の決定
            if comment_position == "top":
                # 上部に表示（画面上部から10%の位置）
                y_pos = int(self.VIDEO_HEIGHT * 0.1)
            elif comment_position == "middle":
                # 中央に表示（画面の中央）
                y_pos = int(self.VIDEO_HEIGHT * 0.5)
            else:  # bottom
                # 下部に表示（画面下部から10%上の位置）
                y_pos = int(self.VIDEO_HEIGHT * 0.9)
            
            # コメントが長い場合は折り返し
            max_width = int(self.VIDEO_WIDTH * 0.8)
            if comment_width > max_width:
                # 適当な位置で折り返し
                words = list(comment_text)
                lines = []
                current_line = ""
                
                for word in words:
                    test_line = current_line + word
                    test_width = self.calculate_text_width(test_line, comment_font, draw)
                    
                    if test_width <= max_width:
                        current_line = test_line
                    else:
                        lines.append(current_line)
                        current_line = word
                
                if current_line:
                    lines.append(current_line)
                
                # 複数行のコメントを描画
                line_height = int(self.REVIEW_FONT_SIZE * 1.5)
                comment_height = line_height * len(lines)
                
                # コメント位置の調整（中央揃え）
                if comment_position == "top":
                    comment_y = y_pos
                elif comment_position == "middle":
                    comment_y = y_pos - comment_height // 2
                else:  # bottom
                    comment_y = y_pos - comment_height
                
                # 背景の四角を描画
                padding = 20
                box_top = comment_y - padding
                box_bottom = comment_y + comment_height + padding
                box_left = (self.VIDEO_WIDTH - max_width) // 2 - padding
                box_right = (self.VIDEO_WIDTH + max_width) // 2 + padding
                
                draw.rectangle(
                    [(box_left, box_top), (box_right, box_bottom)],
                    fill=(0, 0, 0, 128),  # 半透明黒
                    outline=border_color,  # インデックスに応じた色の枠
                    width=5  # 太い枠線
                )
                
                # 各行を描画
                for i, line in enumerate(lines):
                    line_y = comment_y + i * line_height
                    line_width = self.calculate_text_width(line, comment_font, draw)
                    line_x = (self.VIDEO_WIDTH - line_width) // 2
                    
                    draw.text(
                        (line_x, line_y),
                        line,
                        font=comment_font,
                        fill=self.TEXT_COLOR
                    )
            else:
                # 1行のコメント
                # コメント位置の調整（中央揃え）
                if comment_position == "top":
                    comment_y = y_pos
                elif comment_position == "middle":
                    comment_y = y_pos - self.REVIEW_FONT_SIZE // 2
                else:  # bottom
                    comment_y = y_pos - self.REVIEW_FONT_SIZE
                
                comment_x = (self.VIDEO_WIDTH - comment_width) // 2
                
                # 背景の四角を描画
                padding = 20
                box_width = comment_width + padding * 2
                box_height = self.REVIEW_FONT_SIZE + padding * 2
                
                draw.rectangle(
                    [(comment_x - padding, comment_y - padding), 
                    (comment_x + comment_width + padding, comment_y + box_height - padding)],
                    fill=(0, 0, 0, 128),  # 半透明黒
                    outline=border_color,  # インデックスに応じた色の枠
                    width=5  # 太い枠線
                )
                
                # コメントを描画
                draw.text(
                    (comment_x, comment_y),
                    comment_text,
                    font=comment_font,
                    fill=self.TEXT_COLOR
                )
            
            return slide
    
    def _create_dummy_image(self, path: str, text: str = "No Image"):
        """
        ダミー画像の作成
        
        Args:
            path: 保存パス
            text: 表示テキスト
        """
        # ディレクトリ作成
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        # 画像サイズ
        width, height = 800, 800
        
        # 画像作成
        img = Image.new('RGB', (width, height), color=(200, 200, 200))
        draw = ImageDraw.Draw(img)
        
        # フォント設定
        try:
            font = self.get_font(60, self.noto_sans_jp_path)
        except Exception:
            font = ImageFont.load_default()
        
        # テキスト描画
        text_width = self.calculate_text_width(text, font, draw)
        text_height = int(60 * 1.2)  # 概算
        position = ((width - text_width) // 2, (height - text_height) // 2)
        draw.text(position, text, fill=(100, 100, 100), font=font)
        
        # 保存
        img.save(path)
    
    def create_video(
            self,
            products: List[Dict[str, Any]],
            title: str,
            output_filename: Optional[str] = None
        ) -> str:
            """
            製品リストからショート動画を作成
            
            Args:
                products: 製品情報リスト
                title: 動画タイトル
                output_filename: 出力ファイル名
            
            Returns:
                str: 作成した動画のパス
            """
            logger.info(f"動画作成開始: {title}")
            
            # 出力ファイル名が指定されていない場合は生成
            if not output_filename:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                safe_title = ''.join(c if c.isalnum() else '_' for c in title)
                output_filename = f"{safe_title}_{timestamp}.mp4"
            
            output_path = os.path.join(self.output_dir, output_filename)
            
            # 製品リストをシャッフルして順位を割り当て
            shuffled_products = random.sample(products, len(products))
            for i, product in enumerate(shuffled_products):
                product['new_rank'] = i + 1  # 1位から順に割り当て
            
            try:
                # 一時ディレクトリを作成
                with tempfile.TemporaryDirectory() as temp_dir:
                    # 動画セグメントのパスリスト
                    video_segments = []
                    
                    # 各製品ごとに動画セグメントを作成
                    for product in shuffled_products:
                        rank = product['new_rank']
                        product_name = product['name']
                        brand_name = product['brand']
                        reviews = product.get('reviews', [])
                        
                        # 製品名・ブランド名だけのナレーション用テキスト
                        product_intro_text = f"{rank}位、{brand_name}の{product_name}"
                        
                        # 1. 製品画像と商品名のみを表示したスライド生成
                        product_slide = self._create_product_slide(product, rank)
                        product_slide_path = os.path.join(temp_dir, f"product_{rank}_slide.png")
                        product_slide.save(product_slide_path)
                        
                        # 製品紹介ナレーション音声を生成
                        product_audio_path = os.path.join(temp_dir, f"product_{rank}_audio.wav")
                        
                        # 必ず音声を生成するか確認するためのログ
                        success = generate_narration(product_intro_text, product_audio_path, "random")
                        
                        # 製品画像の動画セグメントを作成
                        product_video_path = os.path.join(temp_dir, f"product_{rank}_video.mp4")
                        
                        # ナレーション音声があれば使用、なければ3秒間の無音
                        if os.path.exists(product_audio_path) and os.path.getsize(product_audio_path) > 100:
                            audio_duration = get_audio_duration(product_audio_path)
                            display_duration = max(audio_duration + 0.5, 3.0)  # 少し余裕を持たせる
                        else:
                            logger.warning(f"製品 {rank} の音声ファイルが存在しないか無効です。無音を使用します。")
                            display_duration = 3.0
                            product_audio_path = os.path.join(temp_dir, f"silent_{rank}.wav")
                            create_silent_audio(product_audio_path, display_duration)
                        
                        # 製品スライドを動画に変換
                        cmd = [
                            "ffmpeg", "-y",
                            "-loop", "1",
                            "-i", product_slide_path,
                            "-i", product_audio_path,
                            "-c:v", "libx264",
                            "-tune", "stillimage",
                            "-c:a", "aac",
                            "-b:a", "192k",
                            "-pix_fmt", "yuv420p",
                            "-shortest"
                        ]
                        
                        cmd.append(product_video_path)
                        try:
                            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True)
                            logger.info(f"製品 {rank} の動画生成成功")
                        except subprocess.CalledProcessError as e:
                            logger.error(f"製品 {rank} の動画生成エラー: {e.stderr}")
                            raise
                        
                        video_segments.append(product_video_path)
                        
                        # コメントスライドのベース作成（最後のフレームに複数のコメントを追加していく）
                        base_slide = None
                        
                        # 2. レビューコメントを順番に表示して読み上げる
                        for i, review in enumerate(reviews[:3]):
                            if not review:
                                continue
                            
                            # コメント位置決定（順番に異なる位置に表示）
                            positions = ["top", "middle", "bottom"]
                            comment_position = positions[i % len(positions)]
                            
                            # 初回の場合、製品画像スライドをベースにする
                            if base_slide is None:
                                base_slide = product_slide.copy()
                            
                            # コメントを追加したスライド作成
                            # コメントをベースに追加（既存のコメントはそのまま）
                            base_slide = self._add_comment_to_slide(
                                base_slide, product, rank, review, comment_position, i
                            )
                            comment_slide_path = os.path.join(temp_dir, f"product_{rank}_comment_{i+1}.png")
                            base_slide.save(comment_slide_path)
                            
                            # コメントナレーション音声を生成
                            comment_audio_path = os.path.join(temp_dir, f"product_{rank}_comment_{i+1}_audio.wav")
                            
                            # 必ず音声を生成するか確認するためのログ
                            logger.info(f"製品 {rank} のコメント {i+1} の音声生成開始: {review}")
                            success = generate_narration(review, comment_audio_path, "random")
                            logger.info(f"製品 {rank} のコメント {i+1} の音声生成結果: {success}, ファイル存在: {os.path.exists(comment_audio_path)}")
                            
                            # コメントスライドの動画セグメントを作成
                            comment_video_path = os.path.join(temp_dir, f"product_{rank}_comment_{i+1}_video.mp4")
                            
                            # ナレーション音声があれば使用、なければ3秒間の無音
                            if os.path.exists(comment_audio_path) and os.path.getsize(comment_audio_path) > 100:
                                audio_duration = get_audio_duration(comment_audio_path)
                                logger.info(f"製品 {rank} のコメント {i+1} の音声の長さ: {audio_duration}秒")
                                display_duration = max(audio_duration + 0.5, 3.0)  # 少し余裕を持たせる
                            else:
                                logger.warning(f"製品 {rank} のコメント {i+1} の音声ファイルが存在しないか無効です。無音を使用します。")
                                display_duration = 3.0
                                comment_audio_path = os.path.join(temp_dir, f"silent_comment_{rank}_{i+1}.wav")
                                create_silent_audio(comment_audio_path, display_duration)
                            
                            # コメントスライドを動画に変換
                            cmd = [
                                "ffmpeg", "-y",
                                "-loop", "1",
                                "-i", comment_slide_path,
                                "-i", comment_audio_path,
                                "-c:v", "libx264",
                                "-tune", "stillimage",
                                "-c:a", "aac",
                                "-b:a", "192k",
                                "-pix_fmt", "yuv420p",
                                "-shortest"
                            ]
                            
                            cmd.append(comment_video_path)
                            try:
                                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True)
                                logger.info(f"製品 {rank} のコメント {i+1} の動画生成成功")
                            except subprocess.CalledProcessError as e:
                                logger.error(f"製品 {rank} のコメント {i+1} の動画生成エラー: {e.stderr}")
                                raise
                            
                            video_segments.append(comment_video_path)
                    
                    # すべての動画セグメントを連結
                    concat_file = os.path.join(temp_dir, "concat.txt")
                    with open(concat_file, "w") as f:
                        for segment in video_segments:
                            f.write(f"file '{segment}'\n")
                    
                    # 最終動画を作成
                    cmd = [
                        "ffmpeg", "-y",
                        "-f", "concat",
                        "-safe", "0",
                        "-i", concat_file,
                        "-c", "copy",
                        output_path
                    ]
                    
                    try:
                        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True)
                        logger.info(f"最終動画の作成成功: {output_path}")
                    except subprocess.CalledProcessError as e:
                        logger.error(f"最終動画の作成エラー: {e.stderr}")
                        raise
                    
                    logger.info(f"動画作成完了: {output_path}")
                    return output_path
                    
            except Exception as e:
                logger.error(f"動画作成エラー: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                raise