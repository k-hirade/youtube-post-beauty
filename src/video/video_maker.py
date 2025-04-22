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
    TEXT_COLOR = (0, 0, 0) 
    SHADOW_COLOR = (100, 100, 100)
    RANK_COLOR = (0, 0, 0) 
    TITLE_COLOR = (0, 0, 0) 
    
    BG_COLOR = (30, 30, 30)  # ダークグレー
    
    TEXT_BG_COLOR = (255, 255, 255)

    # 背景用画像パス
    BACKGROUND_IMAGE_PATH = "data/assets/繁華街背景.png"

    SOURCE_HAN_SERIF_HEAVY = "/Library/Fonts/SourceHanSerif-Heavy.otf"
    
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
            else:  # Linux
                self.font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
                self.noto_sans_jp_path = '/usr/share/fonts/opentype/noto/NotoSansJP-Regular.otf'
                self.noto_sans_jp_bold_path = '/usr/share/fonts/opentype/noto/NotoSansCJKjp-Bold.otf'
        
        # フォントが存在するか確認
        if not os.path.exists(self.font_path):
            logger.warning(f"指定したフォント({self.font_path})が見つかりません。代替フォントを使用します。")
            self.font_path = None


    def _draw_text_italic(
        self,
        base: Image.Image,
        text: str,
        y: int,                       # ←   文字の上端
        font: ImageFont.FreeTypeFont,
        **kw,
    ) -> None:
        """ draw_text_effect → X 方向シアーで疑似イタリック """


        xmin, ymin, xmax, ymax = font.getbbox(text)
        w = xmax - xmin
        h = ymax - ymin
        shear = 0.15                 # 傾き tanθ
        # 変形後の幅
        w_after = w + shear * h
        # 変形後の左端を画面中央に合わせたい
        left_after = (self.VIDEO_WIDTH - w_after) // 2
        # 変形で x′ = x + shear·Y になるので、描画時に −shear·y を先に引く
        x = int(left_after - shear * y) + 300

        tmp = Image.new("RGBA", (self.VIDEO_WIDTH+70, base.height), (0, 0, 0, 0))
        self.draw_text_effect(tmp, text, (x, y), font, **kw)

        # 4) X 方向にシアー
        tmp = tmp.transform(
            tmp.size,
            Image.AFFINE,
            (1, shear, 0,   0, 1, 0),          # [[1, shear, 0], [0, 1, 0]]
            resample=Image.BICUBIC,
            fillcolor=(0, 0, 0, 0),
        )

        # 5) 合成
        base.alpha_composite(tmp)

    def draw_text_effect(
        self,
        base: Image.Image,
        text: str,
        xy: tuple[int, int],
        font: ImageFont.FreeTypeFont,
        *,
        fill: tuple[int, int, int] = (255, 255, 255),
        stroke_width: int = 0,
        stroke_fill: tuple[int, int, int] | None = None,
        inner_stroke_width: int | None = None,
        inner_stroke_fill: tuple[int, int, int] | None = None,
        gradient: list[tuple[int, int, int]] | None = None,
        glow_radius: int = 0,
        glow_opacity: float = 0.3,
        bevel: bool = False
    ) -> None:
        """
        1 回の呼び出しで “二重ストローク＋グラデ＋グロー” までまとめて描画
        Pillow だけで完結させるために
        - グラデはマスク描画
        - グローは blur
        - ベベルは上下 1px シフト描画
        """
        from PIL import ImageFilter, ImageChops

        txt_layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(txt_layer)

        # 外側ストローク
        if stroke_width and stroke_fill:
            for dx in range(-stroke_width, stroke_width + 1):
                for dy in range(-stroke_width, stroke_width + 1):
                    if dx*dx + dy*dy <= stroke_width*stroke_width:
                        d.text((xy[0] + dx, xy[1] + dy), text, font=font, fill=stroke_fill)

        # 内側ストローク（Photoshop の「線‑内側」っぽく見せるため、少し縮小したマスクを使う）
        if inner_stroke_width and inner_stroke_fill:
            mask = Image.new("L", base.size, 0)
            mdraw = ImageDraw.Draw(mask)
            mdraw.text(xy, text, font=font, fill=255)
            # マスクを縮小して内側分を確保
            mask = mask.filter(ImageFilter.MaxFilter(inner_stroke_width*2+1))
            ishape = Image.new("RGBA", base.size, (*inner_stroke_fill, 255))
            txt_layer = Image.composite(ishape, txt_layer, mask)

        # 本体塗り（グラデ or 単色）
        if gradient:
            top, *mid, bottom = gradient
            grad = Image.new("RGB", (1, font.size), color=0)
            for y in range(grad.height):
                ratio = y / (grad.height - 1)
                # 線形補間（中間色がある場合も雑に線形補間）
                if len(gradient) == 2:
                    c1, c2 = top, bottom
                else:
                    # 3 色の場合
                    c1, c2 = (top, bottom) if ratio > .5 else (top, mid[0])
                    ratio = ratio*2 if ratio <= .5 else (ratio-.5)*2
                grad.putpixel((0, y), tuple(int(c1[i] + (c2[i]-c1[i])*ratio) for i in range(3)))
            grad = grad.resize((base.width, base.height))
            mask = Image.new("L", base.size, 0)
            mdraw = ImageDraw.Draw(mask)
            mdraw.text(xy, text, font=font, fill=255)
            txt_layer = Image.composite(grad, txt_layer, mask)
        else:
            d.text(xy, text, font=font, fill=fill)

        # ベベル＆エンボス（簡易）：ハイライトとシャドウを 1px ずらして描画
        if bevel:
            bevel_layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
            bd = ImageDraw.Draw(bevel_layer)
            # ハイライト
            bd.text((xy[0]-1, xy[1]-1), text, font=font, fill=(255, 255, 255, int(255*0.75)))
            # シャドウ
            bd.text((xy[0]+1, xy[1]+1), text, font=font, fill=(158, 122, 0, int(255*0.5)))
            txt_layer = Image.alpha_composite(txt_layer, bevel_layer)

        # 外側グロー
        if glow_radius:
            glow = txt_layer.split()[-1].filter(ImageFilter.GaussianBlur(glow_radius))
            glow = ImageChops.multiply(glow, Image.new("L", glow.size, int(255*glow_opacity)))
            glow_layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
            glow_layer.putalpha(glow)
            base.alpha_composite(glow_layer)

        base.alpha_composite(txt_layer)
    
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

    def _get_common_background(self) -> Image.Image:
        """
        共通背景を取得して返す。
        ・読み込み失敗時は単色 (BG_COLOR) で代替
        毎回ディスク I/O しないように 1 度だけ読み込んでキャッシュする
        """
        if not hasattr(self, "_cached_bg"):
            try:
                if os.path.exists(self.BACKGROUND_IMAGE_PATH):
                    bg = Image.open(self.BACKGROUND_IMAGE_PATH).convert("RGBA")
                    bg = self.resize_image_to_fill(bg, self.VIDEO_WIDTH, self.VIDEO_HEIGHT)
                else:
                    raise FileNotFoundError("背景画像が見つかりません")
            except Exception as e:
                logger.warning(f"背景画像の読み込みに失敗: {e}")
                bg = Image.new("RGBA", (self.VIDEO_WIDTH, self.VIDEO_HEIGHT),
                            (*self.BG_COLOR, 255))
            # 読みやすさ確保のために暗色オーバーレイを被せる
            overlay = Image.new("RGBA", bg.size, (15, 15, 35, 180))
            bg.alpha_composite(overlay)
            self._cached_bg = bg
        # 呼び出し側で書き換えないようコピーを返す
        return self._cached_bg.copy()

    
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
        # 画像サイズチェック（小さすぎる場合の対策）
        img_width, img_height = img.size
        
        # 小さい画像（180x180など）の場合は、そのまま使用して拡大する
        if img_width <= 200 and img_height <= 200:
            # 画面の80%の幅に拡大
            target_width = int(self.VIDEO_WIDTH * 0.8)
            target_height = int(target_width * img_height / img_width)
            return img.resize((target_width, target_height), Image.LANCZOS)
        
        # 通常の画像処理
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
        img  = self._get_common_background().convert("RGB") 
        draw = ImageDraw.Draw(img)
        
        # 画像読み込みの準備
        img_loaded = False
        product_img = None
        
        # 1. ローカルに保存された画像パスを確認（スクレイパーからダウンロード済み）
        if 'local_image_path' in product and product['local_image_path']:
            local_path = product['local_image_path']
            if os.path.exists(local_path):
                try:
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
        
        # フォント設定
        rank_font = self.get_font(self.TITLE_FONT_SIZE * 1.3, self.noto_sans_jp_bold_path)
        name_font = self.get_font(self.TITLE_FONT_SIZE, self.noto_sans_jp_bold_path)
        brand_font = self.get_font(self.BRAND_FONT_SIZE, self.noto_sans_jp_path)
        
        # 順位表示（上部中央に配置）
        rank_text = f"{rank}位"
        rank_width = self.calculate_text_width(rank_text, rank_font, draw)
        rank_x = (self.VIDEO_WIDTH - rank_width) // 2  # 中央揃え
        rank_y = 50
        
        # 順位表示の背景（白色の四角形）
        rank_padding = 20
        rank_bg_width = rank_width + rank_padding * 2
        rank_bg_height = self.TITLE_FONT_SIZE * 1.3 + rank_padding
        
        # 背景の四角形を描画
        draw.rectangle(
            [(rank_x - rank_padding, rank_y - rank_padding // 2), 
            (rank_x + rank_width + rank_padding, rank_y + rank_bg_height)],
            fill=self.TEXT_BG_COLOR  # 白色背景
        )
        
        # 順位テキストを描画
        self.apply_text_outline(
            draw=draw,
            text=rank_text,
            x=rank_x,
            y=rank_y,
            font=rank_font,
            text_color=self.RANK_COLOR,
            outline_color=self.SHADOW_COLOR,
            outline_width=2
        )
        
        # 商品名を表示（中央揃え、少し下に配置）
        product_name = product.get('name', 'No Name')
        brand_name = product.get('brand', 'No Brand')
        
        # 商品名の表示位置（中央揃え）
        name_y = 250  # もっと下に配置
        name_width = self.calculate_text_width(product_name, name_font, draw)
        name_x = (self.VIDEO_WIDTH - name_width) // 2
        
        # 商品名の背景（白色の四角形）
        name_padding = 20
        name_bg_width = name_width + name_padding * 2
        name_bg_height = self.TITLE_FONT_SIZE + name_padding
        
        # 背景の四角形を描画
        draw.rectangle(
            [(name_x - name_padding, name_y - name_padding // 2), 
            (name_x + name_width + name_padding, name_y + name_bg_height)],
            fill=self.TEXT_BG_COLOR  # 白色背景
        )
        
        # 商品名を表示
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
        brand_y = name_y + self.TITLE_FONT_SIZE + 20
        brand_width = self.calculate_text_width(brand_name, brand_font, draw)
        brand_x = (self.VIDEO_WIDTH - brand_width) // 2
        
        # ブランド名の背景（白色の四角形）
        brand_padding = 15
        brand_bg_width = brand_width + brand_padding * 2
        brand_bg_height = self.BRAND_FONT_SIZE + brand_padding
        
        # 背景の四角形を描画
        draw.rectangle(
            [(brand_x - brand_padding, brand_y - brand_padding // 2), 
            (brand_x + brand_width + brand_padding, brand_y + brand_bg_height)],
            fill=self.TEXT_BG_COLOR  # 白色背景
        )
        
        # ブランド名を表示
        draw.text(
            (brand_x, brand_y),
            brand_name,
            font=brand_font,
            fill=(50, 50, 50)  # ダークグレー
        )
        
        # 画像を中央下部に配置
        try:
            # 画像サイズチェック
            img_width, img_height = product_img.size
            logger.info(f"元の画像サイズ: {img_width}x{img_height}")
            
            # 縦横比の計算
            aspect_ratio = img_width / img_height if img_height > 0 else 1
            
            # 幅を画面の80%に設定（常に）
            new_width = int(self.VIDEO_WIDTH * 0.8)
            new_height = int(new_width / aspect_ratio)
            
            # ログ出力
            logger.info(f"リサイズ後の画像サイズ: {new_width}x{new_height}")
            
            # リサイズ
            product_img = product_img.resize((new_width, new_height), Image.LANCZOS)
            
            # 画像をブランド名の下に配置（さらに下に）
            img_x = (self.VIDEO_WIDTH - new_width) // 2
            img_y = brand_y + self.BRAND_FONT_SIZE + 70  # さらに下に配置
            
            # 画像貼り付け
            img.paste(product_img, (img_x, img_y))
        except Exception as e:
            logger.error(f"画像処理エラー: {str(e)}")
        
        return img
    
    def _create_improved_intro_slide(self, title: str) -> Image.Image:
        bg = self._get_common_background()
        # 背景のぼかし入り写真があるならここで合成しても OK
        y = int(self.VIDEO_HEIGHT * 0.06)

        # 共通フォント
        heavy130  = ImageFont.truetype(self.SOURCE_HAN_SERIF_HEAVY, 130)
        heavy220  = ImageFont.truetype(self.SOURCE_HAN_SERIF_HEAVY, 220)
        heavy150  = ImageFont.truetype(self.SOURCE_HAN_SERIF_HEAVY, 150)
        heavy180  = ImageFont.truetype(self.SOURCE_HAN_SERIF_HEAVY, 180)
        heavy80   = ImageFont.truetype(self.SOURCE_HAN_SERIF_HEAVY, 80)
        heavy60   = ImageFont.truetype(self.SOURCE_HAN_SERIF_HEAVY, 60)

        # ① 一度は
        w = self.calculate_text_width("一度は", heavy130, ImageDraw.Draw(bg))
        self.draw_text_effect(
            bg, "一度は", ((self.VIDEO_WIDTH-w)//2, y),
            heavy130,
            fill=(255, 255, 255),
            stroke_width=8, stroke_fill=(0, 0, 0),
            glow_radius=15, glow_opacity=0.3
        )
        y += 100

        # ② マジで使ってみて欲しい（4 行構成でも OK）
        w = self.calculate_text_width("マジで", heavy220, ImageDraw.Draw(bg))
        self.draw_text_effect(
            bg, "マジで", ((self.VIDEO_WIDTH-w)//2, y),
            heavy220,
            gradient=[(215, 85, 79), (130, 22, 22)],
            inner_stroke_width=4, inner_stroke_fill=(255, 255, 255),
            stroke_width=10, stroke_fill=(0, 0, 0),
            glow_radius=15, glow_opacity=0.5
        )
        y += 230

        for line in ["使ってみて", "欲しい"]:
            w = self.calculate_text_width(line, heavy150, ImageDraw.Draw(bg))
            self.draw_text_effect(
                bg, line, ((self.VIDEO_WIDTH-w)//2, y),
                heavy150,
                gradient=[(215, 85, 79), (130, 22, 22)],
                inner_stroke_width=4, inner_stroke_fill=(255, 255, 255),
                stroke_width=10, stroke_fill=(0, 0, 0),
                glow_radius=15, glow_opacity=0.5
            )
            y += 150

        y += 50   # 行間を広めに

        # ③ 薬局で買える
        text = "薬局で買える"
        w = self.calculate_text_width(text, heavy150, ImageDraw.Draw(bg))
        self._draw_text_italic(
            bg, text, y,
            heavy150,
            gradient=[(255, 246, 194), (255, 216, 74), (199, 154, 5)],
            stroke_width=8, stroke_fill=(0, 0, 0),
            bevel=True,
            glow_radius=12, glow_opacity=0.4
        )
        y += 150

        # ④ 神商品（少し大きめ）
        text = "神商品"
        w = self.calculate_text_width(text, heavy180, ImageDraw.Draw(bg))
        self._draw_text_italic(
            bg, text, y,
            heavy180,
            gradient=[(255, 246, 194), (255, 216, 74), (199, 154, 5)],
            stroke_width=8, stroke_fill=(0, 0, 0),
            bevel=True,
            glow_radius=12, glow_opacity=0.4
        )
        y += 230

        # ⑤ 挙げてくw
        w = self.calculate_text_width("挙げてくw", heavy80, ImageDraw.Draw(bg))
        self.draw_text_effect(
            bg, "挙げてくw", ((self.VIDEO_WIDTH-w)//2, y),
            heavy80,
            fill=(255, 255, 255),
            stroke_width=5, stroke_fill=(0, 0, 0),
            glow_radius=10, glow_opacity=0.2
        )
        y += 100

        # ⑥ フッタ
        text = "※これはブックマーク必須やで"
        w = self.calculate_text_width(text, heavy60, ImageDraw.Draw(bg))
        self.draw_text_effect(
            bg, text, ((self.VIDEO_WIDTH-w)//2, y),
            heavy60,
            fill=(199, 22, 22),
            inner_stroke_width=2, inner_stroke_fill=(158, 0, 0),
            glow_radius=20, glow_opacity=0.7
        )

        assets = [
            ("data/assets/atsugesyou.png", "left"),   # 左下
            ("data/assets/building_medical_pharmacy.png", "right"),  # 右下
        ]

        pad_x = int(self.VIDEO_WIDTH * 0.02)   # 画面端から 2% だけ余白
        pad_y = int(self.VIDEO_HEIGHT * 0.02)

        for path, side in assets:
            if not os.path.exists(path):
                logger.warning(f"装飾画像が見つかりません: {path}")
                continue
            try:
                deco = Image.open(path).convert("RGBA")

                # 画像を大きすぎないサイズ（画面幅 25%・高さ 25% 以内）に収める
                max_w = int(self.VIDEO_WIDTH * 0.25)
                max_h = int(self.VIDEO_HEIGHT * 0.25)
                dw, dh = deco.size
                scale = min(max_w / dw, max_h / dh, 1.0)
                deco = deco.resize((int(dw*scale), int(dh*scale)), Image.LANCZOS)

                # 貼り付け位置
                if side == "left":
                    pos = (pad_x, self.VIDEO_HEIGHT - deco.height - pad_y)
                else:  # right
                    pos = (self.VIDEO_WIDTH - deco.width - pad_x,
                        self.VIDEO_HEIGHT - deco.height - pad_y)

                bg.alpha_composite(deco, dest=pos)
            except Exception as e:
                logger.error(f"装飾画像の読み込み/貼り付けに失敗: {path} - {e}")

        # ------------------------------------------------------------------

        return bg.convert("RGB")


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
        既存のスライドにコメントを追加する（商品名とブランド名を削除）
        参考画像のようなデザインに改良
        
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
        # スライドのコピーを作成
        slide = base_slide.copy()
        draw = ImageDraw.Draw(slide)
        
        # 商品名の位置情報（上書き用）
        name_y = 250  # _create_product_slide と同じ値
        name_font = self.get_font(self.TITLE_FONT_SIZE, self.noto_sans_jp_bold_path)
        product_name = product.get('name', 'No Name')
        name_width = self.calculate_text_width(product_name, name_font, draw)
        name_x = (self.VIDEO_WIDTH - name_width) // 2
        
        # 商品名の背景サイズ
        name_padding = 20
        name_bg_width = name_width + name_padding * 2
        name_bg_height = self.TITLE_FONT_SIZE + name_padding
        
        # 商品名とその背景のみを黒い背景で上書き（削除）
        draw.rectangle(
            [(name_x - name_padding, name_y - name_padding // 2), 
            (name_x + name_width + name_padding, name_y + name_bg_height)],
            fill=self.BG_COLOR  # 黒色背景で上書き
        )
        
        # ブランド名の位置情報（上書き用）
        brand_y = name_y + self.TITLE_FONT_SIZE + 20  # _create_product_slide と同じ値
        brand_font = self.get_font(self.BRAND_FONT_SIZE, self.noto_sans_jp_path)
        brand_name = product.get('brand', 'No Brand')
        brand_width = self.calculate_text_width(brand_name, brand_font, draw)
        brand_x = (self.VIDEO_WIDTH - brand_width) // 2
        
        # ブランド名の背景サイズ
        brand_padding = 15
        brand_bg_width = brand_width + brand_padding * 2
        brand_bg_height = self.BRAND_FONT_SIZE + brand_padding
        
        # ブランド名とその背景も黒い背景で上書き（削除）
        draw.rectangle(
            [(brand_x - brand_padding, brand_y - brand_padding // 2), 
            (brand_x + brand_width + brand_padding, brand_y + brand_bg_height)],
            fill=self.BG_COLOR  # 黒色背景で上書き
        )
        
        # ランク表示は残す（消去された場合に備えて再描画）
        rank_font = self.get_font(self.TITLE_FONT_SIZE * 1.7, self.noto_sans_jp_bold_path)  # ランクを少し大きく
        rank_text = f"第{rank}位"  # "第"を追加
        rank_width = self.calculate_text_width(rank_text, rank_font, draw)
        rank_x = (self.VIDEO_WIDTH - rank_width) // 2  # 中央揃え
        rank_y = 50
        
        # ランク表示のスタイル変更（背景なし、白文字に黒の太い縁取り）
        self.apply_text_outline(
            draw=draw,
            text=rank_text,
            x=rank_x,
            y=rank_y,
            font=rank_font,
            text_color=(255, 255, 255),  # 白色
            outline_color=(0, 0, 0),      # 黒色
            outline_width=10              # 太い縁取り
        )
        
        # フォント設定
        # 画像を参考に、より太くて大きいフォントを使用
        try:
            comment_font = ImageFont.truetype("rounded-mplus-1c-extrabold.ttf", self.REVIEW_FONT_SIZE + 12)
        except:
            # フォントが見つからない場合は代替フォント
            comment_font = self.get_font(self.REVIEW_FONT_SIZE + 12, self.noto_sans_jp_bold_path)
        
        # コメントインデックスに応じて色を設定（参考画像に合わせる）
        if comment_index == 0:
            box_bg_color = (255, 255, 255)  # 白背景
            border_color = (255, 50, 50)    # 赤枠
        elif comment_index == 1:
            box_bg_color = (255, 255, 255)  # 白背景
            border_color = (50, 255, 50)    # 緑枠
        else:
            box_bg_color = (255, 255, 255)  # 白背景
            border_color = (50, 50, 255)    # 青枠
        
        # コメント位置の決定
        y_pos_mapping = {
            "top": int(self.VIDEO_HEIGHT * 0.25),      # 上部
            "middle": int(self.VIDEO_HEIGHT * 0.45),   # 中央（少し上に）
            "bottom": int(self.VIDEO_HEIGHT * 0.65)    # 下部（少し上に）
        }
        y_pos = y_pos_mapping[comment_position]
        
        # コメント幅の設定（画面の85%）
        max_width = int(self.VIDEO_WIDTH * 0.85)
        
        # 改行を削除してフラットなテキストに
        comment_text = comment.replace("\n", " ").strip()
        comment_width = self.calculate_text_width(comment_text, comment_font, draw)
        
        # コメントが長い場合は折り返し
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
            line_height = int(self.REVIEW_FONT_SIZE * 1.6)  # 行間を少し広く
            comment_height = line_height * len(lines)
            
            # コメント位置の調整（中央揃え）
            comment_y = y_pos - comment_height // 2
            
            # 背景の四角を描画（参考画像に合わせて白背景に色付き枠線）
            padding_v = 15  # 上下のパディング
            padding_h = 25  # 左右のパディング
            box_top = comment_y - padding_v
            box_bottom = comment_y + comment_height + padding_v
            box_left = (self.VIDEO_WIDTH - max_width) // 2 - padding_h
            box_right = (self.VIDEO_WIDTH + max_width) // 2 + padding_h
            
            # 1. まず白い背景を描画
            draw.rectangle(
                [(box_left, box_top), (box_right, box_bottom)],
                fill=box_bg_color
            )
            
            # 2. 次に色付きの枠線を描画（枠線の幅を5pxに設定）
            border_width = 5
            for i in range(border_width):
                draw.rectangle(
                    [(box_left + i, box_top + i), (box_right - i, box_bottom - i)],
                    outline=border_color
                )
            
            # 各行を描画（黒色テキスト）
            for i, line in enumerate(lines):
                line_y = comment_y + i * line_height
                line_width = self.calculate_text_width(line, comment_font, draw)
                line_x = (self.VIDEO_WIDTH - line_width) // 2
                
                draw.text(
                    (line_x, line_y),
                    line,
                    font=comment_font,
                    fill=(0, 0, 0)  # 黒テキスト
                )
        else:
            # 1行のコメント
            comment_y = y_pos - self.REVIEW_FONT_SIZE // 2
            comment_x = (self.VIDEO_WIDTH - comment_width) // 2
            
            # 背景の四角を描画（参考画像に合わせて白背景に色付き枠線）
            padding_v = 15  # 上下のパディング
            padding_h = 25  # 左右のパディング
            box_width = comment_width + padding_h * 2
            box_height = self.REVIEW_FONT_SIZE + padding_v * 2
            
            box_left = comment_x - padding_h
            box_right = comment_x + comment_width + padding_h
            box_top = comment_y - padding_v
            box_bottom = comment_y + box_height - padding_v
            
            # 1. まず白い背景を描画
            draw.rectangle(
                [(box_left, box_top), (box_right, box_bottom)],
                fill=box_bg_color
            )
            
            # 2. 次に色付きの枠線を描画（枠線の幅を5pxに設定）
            border_width = 5
            for i in range(border_width):
                draw.rectangle(
                    [(box_left + i, box_top + i), (box_right - i, box_bottom - i)],
                    outline=border_color
                )
            
            # コメントを描画（黒色テキスト）
            draw.text(
                (comment_x, comment_y),
                comment_text,
                font=comment_font,
                fill=(0, 0, 0)  # 黒テキスト
            )
        
        return slide
    
    def create_video(
            self,
            products: List[Dict[str, Any]],
            title: str,
            output_filename: Optional[str] = None
        ) -> str:
            """
            製品リストからショート動画を作成（BGM追加機能対応）
            
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
            shuffled_products = shuffled_products[:7]
            for i, product in enumerate(shuffled_products):
                product['new_rank'] = i + 1  # 1位から順に割り当て
            
            try:
                # 一時ディレクトリを作成
                with tempfile.TemporaryDirectory() as temp_dir:
                    # 動画セグメントのパスリスト
                    video_segments = []
                    
                    # イントロスライド作成
                    intro_title = None
                    for product in shuffled_products:
                        if 'channel' in product and 'genre' in product:
                            intro_title = f"{product['channel']}で買える{product['genre']}7選！"
                            break
                    
                    if not intro_title:
                        # main.pyからタイトルを構築
                        channel = title.split('で買える')[0] if 'で買える' in title else ""
                        genre = title.split('で買える')[-1].replace('ランキング', '').strip() if 'で買える' in title else ""
                        intro_title = f"{channel}で買える{genre}7選！"

                    intro_img = self._create_improved_intro_slide(intro_title)
                    intro_slide_path = os.path.join(temp_dir, "intro_slide.png")
                    intro_img.save(intro_slide_path)
                    
                    # イントロ音声生成
                    intro_audio_path = os.path.join(temp_dir, "intro_audio.wav")
                    intro_success = generate_narration(intro_title, intro_audio_path, "random")
                    
                    # イントロ動画セグメント作成
                    intro_video_path = os.path.join(temp_dir, "intro_video.mp4")
                    
                    # ナレーション音声があれば使用、なければ3秒間の無音
                    if os.path.exists(intro_audio_path) and os.path.getsize(intro_audio_path) > 100:
                        audio_duration = get_audio_duration(intro_audio_path)
                        display_duration = max(audio_duration + 1.0, 3.0)  # 少し余裕を持たせる
                    else:
                        logger.warning(f"イントロの音声ファイルが存在しないか無効です。無音を使用します。")
                        display_duration = 3.0
                        intro_audio_path = os.path.join(temp_dir, "silent_intro.wav")
                        create_silent_audio(intro_audio_path, display_duration)
                    
                    # イントロスライドを動画に変換
                    cmd = [
                        "ffmpeg", "-y",
                        "-loop", "1",
                        "-i", intro_slide_path,
                        "-i", intro_audio_path,
                        "-c:v", "libx264",
                        "-tune", "stillimage",
                        "-c:a", "aac",
                        "-b:a", "192k",
                        "-pix_fmt", "yuv420p",
                        "-shortest"
                    ]
                    
                    cmd.append(intro_video_path)
                    try:
                        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True)
                        video_segments.append(intro_video_path)
                    except subprocess.CalledProcessError as e:
                        logger.error(f"イントロ動画生成エラー: {e.stderr}")
                        
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
                        except subprocess.CalledProcessError as e:
                            logger.error(f"製品 {rank} の動画生成エラー: {e.stderr}")
                            raise
                        
                        video_segments.append(product_video_path)
                        
                        # コメントを順番に追加していく
                        if reviews:
                            # コメント用のベースとなるスライド（商品名とブランド名を削除済み）を作成
                            base_slide = product_slide.copy()
                            draw = ImageDraw.Draw(base_slide)
                            
                            # 商品名の位置情報
                            name_y = 250  # _create_product_slide と同じ値
                            name_font = self.get_font(self.TITLE_FONT_SIZE, self.noto_sans_jp_bold_path)
                            name_width = self.calculate_text_width(product_name, name_font, draw)
                            name_x = (self.VIDEO_WIDTH - name_width) // 2
                            
                            # 商品名の背景サイズ
                            name_padding = 20
                            name_bg_width = name_width + name_padding * 2
                            name_bg_height = self.TITLE_FONT_SIZE + name_padding
                            
                            # 商品名をマスクする（黒色背景で上書き）
                            draw.rectangle(
                                [(name_x - name_padding, name_y - name_padding // 2), 
                                (name_x + name_width + name_padding, name_y + name_bg_height)],
                                fill=self.BG_COLOR  # 黒色背景
                            )
                            
                            # ブランド名の位置情報
                            brand_y = name_y + self.TITLE_FONT_SIZE + 20  # _create_product_slide と同じ値
                            brand_font = self.get_font(self.BRAND_FONT_SIZE, self.noto_sans_jp_path)
                            brand_width = self.calculate_text_width(brand_name, brand_font, draw)
                            brand_x = (self.VIDEO_WIDTH - brand_width) // 2
                            
                            # ブランド名の背景サイズ
                            brand_padding = 15
                            brand_bg_width = brand_width + brand_padding * 2
                            brand_bg_height = self.BRAND_FONT_SIZE + brand_padding
                            
                            # ブランド名もマスクする（黒色背景で上書き）
                            draw.rectangle(
                                [(brand_x - brand_padding, brand_y - brand_padding // 2), 
                                (brand_x + brand_width + brand_padding, brand_y + brand_bg_height)],
                                fill=self.BG_COLOR  # 黒色背景
                            )
                            
                            # 順位表示を再描画（中央揃えで）
                            rank_font = self.get_font(self.TITLE_FONT_SIZE * 1.3, self.noto_sans_jp_bold_path)
                            rank_text = f"{rank}位"
                            rank_width = self.calculate_text_width(rank_text, rank_font, draw)
                            rank_x = (self.VIDEO_WIDTH - rank_width) // 2  # 中央揃え
                            rank_y = 50
                            
                            # 順位表示の背景（白色の四角形）
                            rank_padding = 20
                            rank_bg_width = rank_width + rank_padding * 2
                            rank_bg_height = self.TITLE_FONT_SIZE * 1.3 + rank_padding
                            
                            # 背景の四角形を描画
                            draw.rectangle(
                                [(rank_x - rank_padding, rank_y - rank_padding // 2), 
                                (rank_x + rank_width + rank_padding, rank_y + rank_bg_height)],
                                fill=self.TEXT_BG_COLOR  # 白色背景
                            )
                            
                            # 順位テキストを描画
                            self.apply_text_outline(
                                draw=draw,
                                text=rank_text,
                                x=rank_x,
                                y=rank_y,
                                font=rank_font,
                                text_color=self.RANK_COLOR,
                                outline_color=self.SHADOW_COLOR,
                                outline_width=2
                            )
                            
                            # ベーススライドを保存
                            base_slide_path = os.path.join(temp_dir, f"product_{rank}_base_slide.png")
                            base_slide.save(base_slide_path)
                            
                            # 表示済みコメントを保持するスライド
                            accumulated_slide = base_slide.copy()
                            
                            # コメント位置を定義
                            positions = ["top", "middle", "bottom"]
                            
                            # コメントを順番に表示・読み上げる
                            for i, review in enumerate(reviews[:3]):
                                if not review:
                                    continue
                                
                                # コメント位置
                                comment_position = positions[i % len(positions)]
                                
                                # コメントを累積スライドに追加
                                comment_font = self.get_font(self.REVIEW_FONT_SIZE+ 15, self.noto_sans_jp_path)
                                draw = ImageDraw.Draw(accumulated_slide)
                                
                                comment_text = f"{review}"
                                comment_width = self.calculate_text_width(comment_text, comment_font, draw)
                                
                                # コメントインデックスに応じて色を設定
                                if i == 0:
                                    border_color = (255, 50, 50)  # 赤色
                                elif i == 1:
                                    border_color = (50, 255, 50)  # 緑色
                                else:
                                    border_color = (50, 50, 255)  # 青色
                                
                                # コメント表示位置
                                if comment_position == "top":
                                    y_pos = int(self.VIDEO_HEIGHT * 0.25)
                                elif comment_position == "middle":
                                    y_pos = int(self.VIDEO_HEIGHT * 0.5)
                                else:  # bottom
                                    y_pos = int(self.VIDEO_HEIGHT * 0.75)
                                
                                # コメント描画（長い場合は折り返し）
                                max_width = int(self.VIDEO_WIDTH * 0.8)
                                if comment_width > max_width:
                                    # 折り返し処理
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
                                    
                                    # 複数行の描画
                                    line_height = int(self.REVIEW_FONT_SIZE * 1.5)
                                    comment_height = line_height * len(lines)
                                    
                                    if comment_position == "top":
                                        comment_y = y_pos
                                    elif comment_position == "middle":
                                        comment_y = y_pos - comment_height // 2
                                    else:  # bottom
                                        comment_y = y_pos - comment_height
                                    
                                    # 背景の四角を描画
                                    padding = 25
                                    box_top = comment_y - padding
                                    box_bottom = comment_y + comment_height + padding
                                    box_left = (self.VIDEO_WIDTH - max_width) // 2 - padding
                                    box_right = (self.VIDEO_WIDTH + max_width) // 2 + padding
                                    
                                    draw.rectangle(
                                        [(box_left, box_top), (box_right, box_bottom)],
                                        fill=self.TEXT_BG_COLOR,
                                        outline=border_color,
                                        width=5
                                    )
                                    
                                    # 各行を描画
                                    for j, line in enumerate(lines):
                                        line_y = comment_y + j * line_height
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
                                        fill=self.TEXT_BG_COLOR,
                                        outline=border_color,
                                        width=5
                                    )
                                    
                                    # コメントを描画
                                    draw.text(
                                        (comment_x, comment_y),
                                        comment_text,
                                        font=comment_font,
                                        fill=self.TEXT_COLOR
                                    )
                                
                                # 現在の累積スライドを保存（コメント追加後）
                                comment_slide_path = os.path.join(temp_dir, f"product_{rank}_comment_{i+1}.png")
                                accumulated_slide.save(comment_slide_path)
                                
                                # コメント用の音声を生成
                                comment_audio_path = os.path.join(temp_dir, f"product_{rank}_comment_{i+1}_audio.wav")
                                comment_success = generate_narration(review, comment_audio_path, "random")
                                
                                # コメントの音声が存在するか確認
                                if not os.path.exists(comment_audio_path) or os.path.getsize(comment_audio_path) < 100:
                                    logger.warning(f"製品 {rank} のコメント {i+1} の音声ファイルが存在しないか無効です。無音を使用します。")
                                    comment_audio_path = os.path.join(temp_dir, f"silent_comment_{rank}_{i+1}.wav")
                                    create_silent_audio(comment_audio_path, 3.0)
                                
                                # 個別のコメントスライドを動画に変換
                                comment_video_path = os.path.join(temp_dir, f"product_{rank}_comment_{i+1}_video.mp4")
                                
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
                                except subprocess.CalledProcessError as e:
                                    logger.error(f"製品 {rank} のコメント {i+1} の動画生成エラー: {e.stderr}")
                                    raise
                                
                                # 動画セグメントに追加
                                video_segments.append(comment_video_path)
                    
                    # すべての動画セグメントを連結するファイル作成
                    concat_file = os.path.join(temp_dir, "concat.txt")
                    with open(concat_file, "w") as f:
                        for segment in video_segments:
                            f.write(f"file '{segment}'\n")
                    
                    # まずBGMなしで動画を連結
                    temp_video_path = os.path.join(temp_dir, "no_bgm_output.mp4")
                    concat_cmd = [
                        "ffmpeg", "-y",
                        "-f", "concat",
                        "-safe", "0",
                        "-i", concat_file,
                        "-c", "copy",
                        temp_video_path
                    ]
                    
                    try:
                        result = subprocess.run(concat_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True)
                    except subprocess.CalledProcessError as e:
                        logger.error(f"最終動画の連結エラー: {e.stderr}")
                        raise
                    
                    # 動画の長さを取得
                    video_duration = self._get_video_duration(temp_video_path)
                    if video_duration <= 0:
                        logger.warning("動画の長さが取得できませんでした。デフォルト値を使用します。")
                        video_duration = 60.0
                    
                    # BGMを追加
                    bgm_path = os.path.join(self.bgm_dir, "しゅわしゅわハニーレモン.mp3")
                    if not os.path.exists(bgm_path):
                        logger.warning(f"BGMファイルが見つかりません: {bgm_path}")
                        logger.info("BGMなしで動画を出力します。")
                        os.rename(temp_video_path, output_path)
                    else:
                        # BGMを追加するコマンド
                        bgm_cmd = [
                            "ffmpeg", "-y",
                            "-i", temp_video_path,  # 元の動画
                            "-stream_loop", "-1",   # BGMをループ再生
                            "-i", bgm_path,         # BGMファイル
                            "-filter_complex",
                            # BGMの音量を0.3に調整し、無限ループ
                            f"[1:a]volume=0.3,aloop=loop=-1:size=2e+09[bgm];"
                            # 元の音声とBGMをミックス
                            "[0:a][bgm]amix=inputs=2:duration=first[aout]",
                            "-map", "0:v",          # 元の動画の映像
                            "-map", "[aout]",       # ミックスした音声
                            "-c:v", "copy",
                            "-c:a", "aac",
                            "-shortest",            # 最短の入力に合わせる
                            "-t", str(video_duration),  # 元の動画の長さを維持
                            output_path
                        ]
                        
                        try:
                            result = subprocess.run(bgm_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True)
                            logger.info(f"BGM付き動画を作成しました: {output_path}")
                        except subprocess.CalledProcessError as e:
                            logger.error(f"BGM追加中にエラー: {e.stderr}")
                            # エラーが発生した場合は元の動画を使用
                            os.rename(temp_video_path, output_path)
                            logger.info(f"BGMなしで動画を出力しました: {output_path}")
                    
                    # 一時ファイルの削除
                    if os.path.exists(temp_video_path) and os.path.exists(output_path):
                        os.remove(temp_video_path)
                    
                    logger.info(f"動画作成完了: {output_path}")
                    return output_path
                    
            except Exception as e:
                logger.error(f"動画作成エラー: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                raise

    def _get_video_duration(self, video_path):
        """動画ファイルの長さを取得する"""
        try:
            cmd = [
                "ffprobe", 
                "-v", "error", 
                "-show_entries", "format=duration", 
                "-of", "default=noprint_wrappers=1:nokey=1", 
                video_path
            ]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            duration = float(result.stdout.strip())
            return duration
        except Exception as e:
            logger.error(f"動画長さ取得例外: {e}")
            return 0