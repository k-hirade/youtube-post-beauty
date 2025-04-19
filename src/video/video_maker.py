"""
@file: video_maker.py
@desc: FFmpegを直接使用して縦型ショート動画を作成するモジュール
"""

import os
import logging
import random
import tempfile
import subprocess
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

# ロガー設定
logger = logging.getLogger(__name__)

class VideoMaker:
    """FFmpegを使用して縦型ショート動画を作成するクラス"""
    
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
    
    # スライド表示時間（秒）
    SLIDE_DURATION = 2.5
    
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
    
    def create_silent_audio(self, output_path: str, duration: float) -> bool:
        """
        無音のオーディオファイルを作成
        
        Args:
            output_path: 出力パス
            duration: 長さ（秒）
            
        Returns:
            bool: 成功したかどうか
        """
        try:
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"anullsrc=r=44100:cl=stereo",
                "-t", str(duration),
                "-c:a", "pcm_s16le",
                output_path
            ]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            return os.path.exists(output_path)
        except Exception as e:
            logger.error(f"無音ファイル作成エラー: {e}")
            return False
    
    def get_audio_duration(self, audio_path: str) -> float:
        """
        オーディオファイルの長さを取得
        
        Args:
            audio_path: オーディオファイルのパス
            
        Returns:
            float: オーディオの長さ（秒）
        """
        try:
            cmd = [
                "ffprobe", 
                "-v", "error", 
                "-show_entries", "format=duration", 
                "-of", "default=noprint_wrappers=1:nokey=1", 
                audio_path
            ]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            return float(result.stdout.strip())
        except Exception as e:
            logger.error(f"オーディオ長さ取得エラー: {e}")
            return 0.0
    
    def _create_title_slide(
        self,
        title: str,
        subtitle: str
    ) -> Image.Image:
        """
        タイトルスライドの作成
        
        Args:
            title: メインタイトル
            subtitle: サブタイトル
        
        Returns:
            Image.Image: タイトルスライド画像
        """
        # 背景画像を作成
        img = Image.new('RGB', (self.VIDEO_WIDTH, self.VIDEO_HEIGHT), self.BG_COLOR)
        draw = ImageDraw.Draw(img)
        
        # フォント設定
        title_font = self.get_font(self.TITLE_FONT_SIZE * 1.5, self.noto_sans_jp_bold_path)
        subtitle_font = self.get_font(self.TITLE_FONT_SIZE, self.noto_sans_jp_path)
        date_font = self.get_font(self.BRAND_FONT_SIZE, self.noto_sans_jp_path)
        
        # タイトルテキスト描画
        # タイトルの幅を計算
        title_width = self.calculate_text_width(title, title_font, draw)
        title_x = (self.VIDEO_WIDTH - title_width) // 2
        title_y = self.VIDEO_HEIGHT // 3
        
        # 縁取り付きでタイトル描画
        self.apply_text_outline(
            draw=draw,
            text=title,
            x=title_x,
            y=title_y,
            font=title_font,
            text_color=self.TITLE_COLOR,
            outline_color=self.SHADOW_COLOR,
            outline_width=int(self.TITLE_FONT_SIZE * 0.07)
        )
        
        # サブタイトル描画
        subtitle_width = self.calculate_text_width(subtitle, subtitle_font, draw)
        subtitle_x = (self.VIDEO_WIDTH - subtitle_width) // 2
        subtitle_y = self.VIDEO_HEIGHT // 2
        
        self.apply_text_outline(
            draw=draw,
            text=subtitle,
            x=subtitle_x,
            y=subtitle_y,
            font=subtitle_font,
            text_color=(200, 200, 200),  # lightgray
            outline_color=self.SHADOW_COLOR,
            outline_width=int(self.TITLE_FONT_SIZE * 0.05)
        )
        
        # 日付描画
        today = datetime.now().strftime('%Y/%m/%d')
        date_text = f"作成: {today}"
        date_width = self.calculate_text_width(date_text, date_font, draw)
        date_x = (self.VIDEO_WIDTH - date_width) // 2
        date_y = self.VIDEO_HEIGHT - 200
        
        draw.text(
            (date_x, date_y),
            date_text,
            font=date_font,
            fill=(128, 128, 128)  # gray
        )
        
        # 出典表示
        source_text = "出典: アットコスメPチャンネルランキング"
        source_width = self.calculate_text_width(source_text, date_font, draw)
        source_x = (self.VIDEO_WIDTH - source_width) // 2
        source_y = self.VIDEO_HEIGHT - 120
        
        draw.text(
            (source_x, source_y),
            source_text,
            font=date_font,
            fill=(128, 128, 128)  # gray
        )
        
        return img
    
    def _create_product_slide(
        self,
        product: Dict[str, Any],
        rank: int
    ) -> Image.Image:
        """
        製品スライドの作成
        
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
                
                # リサイズ（縦800px上限、アスペクト比保持）
                img_width, img_height = product_img.size
                aspect_ratio = img_width / img_height
                new_height = min(800, self.VIDEO_HEIGHT // 2)
                new_width = int(new_height * aspect_ratio)
                
                if new_width > self.VIDEO_WIDTH * 0.8:
                    new_width = int(self.VIDEO_WIDTH * 0.8)
                    new_height = int(new_width / aspect_ratio)
                
                product_img = product_img.resize((new_width, new_height), Image.LANCZOS)
                
                # 画像配置（中央）
                img_x = (self.VIDEO_WIDTH - new_width) // 2
                img_y = self.VIDEO_HEIGHT // 3 - new_height // 2
                
                # 画像貼り付け
                img.paste(product_img, (img_x, img_y))
                
            except Exception as e:
                logger.error(f"画像読み込みエラー: {str(e)}")
        
        # フォント設定
        rank_font = self.get_font(self.TITLE_FONT_SIZE * 1.3, self.noto_sans_jp_bold_path)
        brand_font = self.get_font(self.BRAND_FONT_SIZE, self.noto_sans_jp_path)
        name_font = self.get_font(self.TITLE_FONT_SIZE, self.noto_sans_jp_bold_path)
        review_font = self.get_font(self.REVIEW_FONT_SIZE, self.noto_sans_jp_path)
        
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
        
        # ブランド名
        brand_text = product['brand']
        brand_width = self.calculate_text_width(brand_text, brand_font, draw)
        brand_x = (self.VIDEO_WIDTH - brand_width) // 2
        brand_y = self.VIDEO_HEIGHT // 2 + 50
        
        draw.text(
            (brand_x, brand_y),
            brand_text,
            font=brand_font,
            fill=(200, 200, 200)  # lightgray
        )
        
        # 商品名
        name_text = product['name']
        name_width = self.calculate_text_width(name_text, name_font, draw)
        name_x = (self.VIDEO_WIDTH - name_width) // 2
        
        # ブランド名のフォントの高さを概算
        brand_height = int(self.BRAND_FONT_SIZE * 1.2)  # 概算
        name_y = brand_y + brand_height + 30
        
        self.apply_text_outline(
            draw=draw,
            text=name_text,
            x=name_x,
            y=name_y,
            font=name_font,
            text_color=self.TITLE_COLOR,
            outline_color=self.SHADOW_COLOR,
            outline_width=int(self.TITLE_FONT_SIZE * 0.05)
        )
        
        # 商品名のフォントの高さを概算
        name_height = int(self.TITLE_FONT_SIZE * 1.2)  # 概算
        
        # レビュー
        if 'reviews' in product and product['reviews']:
            review_y = name_y + name_height + 80
            
            for i, review in enumerate(product['reviews'][:3]):
                if not review:
                    continue
                
                review_text = f"「{review}」"
                review_width = self.calculate_text_width(review_text, review_font, draw)
                review_x = (self.VIDEO_WIDTH - review_width) // 2
                
                # 前のレビューのフォントの高さを概算（2つ目以降のレビュー用）
                if i > 0:
                    review_height = int(self.REVIEW_FONT_SIZE * 1.2)  # 概算
                    review_y += review_height + 20
                
                draw.text(
                    (review_x, review_y),
                    review_text,
                    font=review_font,
                    fill=self.TEXT_COLOR
                )
        
        return img
    
    def _create_outro_slide(
        self,
        text: str = "Thank you for watching!"
    ) -> Image.Image:
        """
        エンドスライドの作成
        
        Args:
            text: テキスト
        
        Returns:
            Image.Image: エンドスライド画像
        """
        # 背景画像を作成
        img = Image.new('RGB', (self.VIDEO_WIDTH, self.VIDEO_HEIGHT), self.BG_COLOR)
        draw = ImageDraw.Draw(img)
        
        # フォント設定
        text_font = self.get_font(self.TITLE_FONT_SIZE, self.noto_sans_jp_bold_path)
        notice_font = self.get_font(self.BRAND_FONT_SIZE, self.noto_sans_jp_path)
        
        # テキスト描画
        text_width = self.calculate_text_width(text, text_font, draw)
        text_x = (self.VIDEO_WIDTH - text_width) // 2
        text_y = self.VIDEO_HEIGHT // 2
        
        self.apply_text_outline(
            draw=draw,
            text=text,
            x=text_x,
            y=text_y,
            font=text_font,
            text_color=self.TITLE_COLOR,
            outline_color=self.SHADOW_COLOR,
            outline_width=int(self.TITLE_FONT_SIZE * 0.05)
        )
        
        # AI生成コンテンツであることの表示
        notice_text = "※レビューはAIによる生成コンテンツです"
        notice_width = self.calculate_text_width(notice_text, notice_font, draw)
        notice_x = (self.VIDEO_WIDTH - notice_width) // 2
        notice_y = self.VIDEO_HEIGHT - 200
        
        draw.text(
            (notice_x, notice_y),
            notice_text,
            font=notice_font,
            fill=(128, 128, 128)  # gray
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
    
    def _get_bgm(self) -> Optional[str]:
        """
        BGMの取得
        
        Returns:
            Optional[str]: BGMファイルパス
        """
        if not os.path.exists(self.bgm_dir):
            logger.warning(f"BGMディレクトリが見つかりません: {self.bgm_dir}")
            return None
        
        # BGMファイルリスト
        bgm_files = [
            f for f in os.listdir(self.bgm_dir)
            if f.endswith(('.mp3', '.wav', '.m4a'))
        ]
        
        if not bgm_files:
            logger.warning(f"BGMファイルが見つかりません: {self.bgm_dir}")
            return None
        
        # ランダム選択
        bgm_file = random.choice(bgm_files)
        return os.path.join(self.bgm_dir, bgm_file)
    
    def create_video(
        self,
        products: List[Dict[str, Any]],
        title: str,
        subtitle: str,
        output_filename: Optional[str] = None
    ) -> str:
        """
        製品リストからショート動画を作成
        
        Args:
            products: 製品情報リスト
            title: 動画タイトル
            subtitle: 動画サブタイトル
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
        
        try:
            # 一時ディレクトリを作成
            with tempfile.TemporaryDirectory() as temp_dir:
                # スライドファイルの一覧
                slide_files = []
                durations = []
                
                # 1. タイトルスライド
                title_slide = self._create_title_slide(title, subtitle)
                title_slide_path = os.path.join(temp_dir, "title_slide.png")
                title_slide.save(title_slide_path)
                slide_files.append(title_slide_path)
                durations.append(3.0)  # 3秒表示
                
                # 2. 製品スライド
                for i, product in enumerate(products):
                    rank = product.get('new_rank', 0)
                    if rank > 0:
                        product_slide = self._create_product_slide(product, rank)
                        product_slide_path = os.path.join(temp_dir, f"product_slide_{i}.png")
                        product_slide.save(product_slide_path)
                        slide_files.append(product_slide_path)
                        durations.append(self.SLIDE_DURATION)  # 2.5秒表示
                
                # 3. エンドスライド
                outro_slide = self._create_outro_slide("今回のランキングは以上です！")
                outro_slide_path = os.path.join(temp_dir, "outro_slide.png")
                outro_slide.save(outro_slide_path)
                slide_files.append(outro_slide_path)
                durations.append(3.0)  # 3秒表示
                
                # 一時的なスライド動画を作成
                segment_videos = []
                
                for i, (slide_path, duration) in enumerate(zip(slide_files, durations)):
                    slide_video_path = os.path.join(temp_dir, f"slide_video_{i}.mp4")
                    
                    # 無音音声を作成
                    silent_audio_path = os.path.join(temp_dir, f"silent_audio_{i}.wav")
                    self.create_silent_audio(silent_audio_path, duration)
                    
                    # スライド→動画変換
                    cmd = [
                        "ffmpeg", "-y",
                        "-loop", "1",
                        "-i", slide_path,
                        "-i", silent_audio_path,
                        "-c:v", "libx264",
                        "-tune", "stillimage",
                        "-c:a", "aac",
                        "-b:a", "192k",
                        "-pix_fmt", "yuv420p",
                        "-shortest",
                        slide_video_path
                    ]
                    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                    
                    segment_videos.append(slide_video_path)
                
                # 動画セグメントを連結
                concat_file = os.path.join(temp_dir, "concat.txt")
                with open(concat_file, "w") as f:
                    for video in segment_videos:
                        f.write(f"file '{video}'\n")
                
                # セグメントなし動画を作成
                video_without_bgm = os.path.join(temp_dir, "video_without_bgm.mp4")
                cmd = [
                    "ffmpeg", "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", concat_file,
                    "-c", "copy",
                    video_without_bgm
                ]
                subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                
                # BGMを取得
                bgm_path = self._get_bgm()
                
                if bgm_path and os.path.exists(bgm_path):
                    # 動画の長さを取得
                    cmd = [
                        "ffprobe", 
                        "-v", "error", 
                        "-show_entries", "format=duration", 
                        "-of", "default=noprint_wrappers=1:nokey=1", 
                        video_without_bgm
                    ]
                    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
                    video_duration = float(result.stdout.strip())
                    
                    # BGMを追加
                    cmd = [
                        "ffmpeg", "-y",
                        "-i", video_without_bgm,
                        "-i", bgm_path,
                        "-filter_complex",
                        f"[1:a]volume=0.3,aloop=loop=-1:size=2e+09[bgm];[0:a][bgm]amix=inputs=2:duration=first[aout]",
                        "-map", "0:v",
                        "-map", "[aout]",
                        "-c:v", "copy",
                        "-c:a", "aac",
                        "-b:a", "192k",
                        "-t", str(video_duration),
                        output_path
                    ]
                    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                else:
                    # BGMなしでそのまま出力
                    os.rename(video_without_bgm, output_path)
                
                logger.info(f"動画作成完了: {output_path}")
                return output_path
                
        except Exception as e:
            logger.error(f"動画作成エラー: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            raise