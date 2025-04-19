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
        製品スライドの作成（画像のみ表示）
        
        Args:
            product: 製品情報
            rank: 順位
        
        Returns:
            Image.Image: 製品スライド画像
        """
        # 背景画像を作成
        img = Image.new('RGB', (self.VIDEO_WIDTH, self.VIDEO_HEIGHT), self.BG_COLOR)
        draw = ImageDraw.Draw(img)
        
        # 画像が存在する場合
        if 'image_url' in product and product['image_url']:
            try:
                # 画像を一時保存（既に保存済みならその画像を使用）
                img_path = os.path.join(self.temp_dir, f"{product['product_id']}.jpg")
                
                # 画像がなければダミー画像を使用
                if not os.path.exists(img_path):
                    img_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'assets', 'dummy_product.jpg')
                    
                    if not os.path.exists(img_path):
                        # ダミー画像もなければ作成
                        self._create_dummy_image(img_path, product['name'])
                
                # 画像読み込み
                product_img = Image.open(img_path)
                
                # リサイズ（アスペクト比保持、最大サイズ調整）
                img_width, img_height = product_img.size
                aspect_ratio = img_width / img_height
                
                # 画面の60%を最大高さとする
                max_height = int(self.VIDEO_HEIGHT * 0.6)
                new_height = min(max_height, img_height)
                new_width = int(new_height * aspect_ratio)
                
                if new_width > self.VIDEO_WIDTH * 0.8:
                    new_width = int(self.VIDEO_WIDTH * 0.8)
                    new_height = int(new_width / aspect_ratio)
                
                product_img = product_img.resize((new_width, new_height), Image.LANCZOS)
                
                # 画像配置（中央）
                img_x = (self.VIDEO_WIDTH - new_width) // 2
                img_y = (self.VIDEO_HEIGHT - new_height) // 2
                
                # 画像貼り付け
                img.paste(product_img, (img_x, img_y))
                
            except Exception as e:
                logger.error(f"画像読み込みエラー: {str(e)}")
        
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
        comment_position: str = "top"  # "top", "middle", "bottom"
    ) -> Image.Image:
        """
        レビューコメント付きの製品スライドを作成
        
        Args:
            product: 製品情報
            rank: 順位
            comment: コメントテキスト
            comment_position: コメントの位置
            
        Returns:
            Image.Image: レビューコメント付き製品スライド
        """
        # 背景画像を作成
        img = Image.new('RGB', (self.VIDEO_WIDTH, self.VIDEO_HEIGHT), self.BG_COLOR)
        draw = ImageDraw.Draw(img)
        
        # 画像が存在する場合
        if 'image_url' in product and product['image_url']:
            try:
                # 画像を一時保存（既に保存済みならその画像を使用）
                img_path = os.path.join(self.temp_dir, f"{product['product_id']}.jpg")
                
                # 画像がなければダミー画像を使用
                if not os.path.exists(img_path):
                    img_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'assets', 'dummy_product.jpg')
                    
                    if not os.path.exists(img_path):
                        # ダミー画像もなければ作成
                        self._create_dummy_image(img_path, product['name'])
                
                # 画像読み込み
                product_img = Image.open(img_path)
                
                # リサイズ（アスペクト比保持、サイズ調整）
                img_width, img_height = product_img.size
                aspect_ratio = img_width / img_height
                
                # コメントの位置に応じて画像サイズと位置を調整
                if comment_position == "top":
                    # 画像を画面下部に配置
                    max_height = int(self.VIDEO_HEIGHT * 0.4)  # 画面の40%
                    img_y = self.VIDEO_HEIGHT - max_height - 100  # 下部配置（余白あり）
                elif comment_position == "bottom":
                    # 画像を画面上部に配置
                    max_height = int(self.VIDEO_HEIGHT * 0.4)  # 画面の40%
                    img_y = 100  # 上部配置（余白あり）
                else:  # middle
                    # 画像を小さめに表示
                    max_height = int(self.VIDEO_HEIGHT * 0.3)  # 画面の30%
                    img_y = int(self.VIDEO_HEIGHT * 0.2)  # 上部20%の位置
                
                new_height = min(max_height, img_height)
                new_width = int(new_height * aspect_ratio)
                
                if new_width > self.VIDEO_WIDTH * 0.8:
                    new_width = int(self.VIDEO_WIDTH * 0.8)
                    new_height = int(new_width / aspect_ratio)
                
                product_img = product_img.resize((new_width, new_height), Image.LANCZOS)
                
                # 画像配置（横中央）
                img_x = (self.VIDEO_WIDTH - new_width) // 2
                
                # 画像貼り付け
                img.paste(product_img, (img_x, img_y))
                
            except Exception as e:
                logger.error(f"画像読み込みエラー: {str(e)}")
        
        # フォント設定
        rank_font = self.get_font(self.TITLE_FONT_SIZE, self.noto_sans_jp_bold_path)
        comment_font = self.get_font(self.REVIEW_FONT_SIZE, self.noto_sans_jp_path)
        
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
        
        # コメントを四角で囲んで表示
        comment_text = f"「{comment}」"
        comment_width = self.calculate_text_width(comment_text, comment_font, draw)
        
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
                comment_y = 150
            elif comment_position == "bottom":
                comment_y = self.VIDEO_HEIGHT - comment_height - 150
            else:  # middle
                comment_y = (self.VIDEO_HEIGHT - comment_height) // 2
            
            # 背景の四角を描画
            padding = 20
            box_top = comment_y - padding
            box_bottom = comment_y + comment_height + padding
            box_left = (self.VIDEO_WIDTH - max_width) // 2 - padding
            box_right = (self.VIDEO_WIDTH + max_width) // 2 + padding
            
            draw.rectangle(
                [(box_left, box_top), (box_right, box_bottom)],
                fill=(0, 0, 0, 128),  # 半透明黒
                outline=(255, 255, 255),  # 白枠
                width=3
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
                comment_y = 150
            elif comment_position == "bottom":
                comment_y = self.VIDEO_HEIGHT - 150
            else:  # middle
                comment_y = self.VIDEO_HEIGHT // 2
            
            comment_x = (self.VIDEO_WIDTH - comment_width) // 2
            
            # 背景の四角を描画
            padding = 20
            box_width = comment_width + padding * 2
            box_height = self.REVIEW_FONT_SIZE + padding * 2
            
            draw.rectangle(
                [(comment_x - padding, comment_y - padding), 
                 (comment_x + comment_width + padding, comment_y + box_height - padding)],
                fill=(0, 0, 0, 128),  # 半透明黒
                outline=(255, 255, 255),  # 白枠
                width=3
            )
            
            # コメントを描画
            draw.text(
                (comment_x, comment_y),
                comment_text,
                font=comment_font,
                fill=self.TEXT_COLOR
            )
        
        return img
    
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
                        
                        # 1. 製品画像のみのスライド
                        product_slide = self._create_product_slide(product, rank)
                        product_slide_path = os.path.join(temp_dir, f"product_{rank}_slide.png")
                        product_slide.save(product_slide_path)
                        
                        # 製品紹介ナレーション音声を生成
                        product_audio_path = os.path.join(temp_dir, f"product_{rank}_audio.wav")
                        
                        # 必ず音声を生成するか確認するためのログ
                        logger.info(f"製品 {rank} の音声生成開始: {product_intro_text}")
                        success = generate_narration(product_intro_text, product_audio_path, "random")
                        logger.info(f"製品 {rank} の音声生成結果: {success}, ファイル存在: {os.path.exists(product_audio_path)}")
                        
                        # 製品画像の動画セグメントを作成
                        product_video_path = os.path.join(temp_dir, f"product_{rank}_video.mp4")
                        
                        # ナレーション音声があれば使用、なければ3秒間の無音
                        if os.path.exists(product_audio_path) and os.path.getsize(product_audio_path) > 100:
                            audio_duration = get_audio_duration(product_audio_path)
                            logger.info(f"製品 {rank} の音声の長さ: {audio_duration}秒")
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
                        
                        # 2. レビューコメントを順番に表示して読み上げる
                        for i, review in enumerate(reviews[:3]):
                            if not review:
                                continue
                            
                            # コメント位置決定
                            positions = ["top", "middle", "bottom"]
                            comment_position = positions[i % len(positions)]
                            
                            # コメント付きスライド作成
                            comment_slide = self._create_review_comment_slide(
                                product, rank, review, comment_position
                            )
                            comment_slide_path = os.path.join(temp_dir, f"product_{rank}_comment_{i+1}.png")
                            comment_slide.save(comment_slide_path)
                            
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