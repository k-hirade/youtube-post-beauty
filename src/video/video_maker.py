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
import unicodedata

# 音声関連のユーティリティをインポート
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

    YASASHISA_GOTHIC = "data/assets/やさしさゴシック.ttf"

    COMMENT_COLORS = [
        (0xFF, 0x4E, 0x45),   # 赤  (#ff4e45)
        (0x45, 0xFF, 0x86),   # 緑  (#45ff86)
        (0x48, 0x45, 0xFF),   # 青  (#4845ff)
    ]
    COMMENT_BORDER_PX   = 6     # 枠線の太さ
    COMMENT_CORNER_RADIUS = 0

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
        1 回の呼び出しで "二重ストローク＋グラデ＋グロー" までまとめて描画
        Pillow だけで完結させるために
        - グラデはマスク描画
        - グローは blur
        - ベベルは上下 1px シフト描画
        """
        # if gradient:
        #     logger.info(f"Applying gradient with colors: {gradient}")
        # else:
        #     logger.info(f"Using solid fill: {fill}")
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
            # テキストマスクを作成
            mask = Image.new("L", base.size, 0)
            mdraw = ImageDraw.Draw(mask)
            mdraw.text(xy, text, font=font, fill=255)
            
            # グラデーションのための修正：RGBモードの画像を準備
            top, *mid, bottom = gradient
            grad = Image.new("RGB", (base.width, base.height), color=0)
            
            # 垂直グラデーションを描画
            for y in range(grad.height):
                ratio = y / (grad.height - 1) if grad.height > 1 else 0
                c1, c2 = top, bottom
                color = tuple(int(c1[i] + (c2[i]-c1[i])*ratio) for i in range(3))
                ImageDraw.Draw(grad).line((0, y, grad.width, y), fill=color)
            
            # グラデーションをRGBAに変換
            grad_rgba = grad.convert("RGBA")
            
            # マスクを使用してグラデーションテキストを作成 - 修正ポイント
            gradient_text = Image.new("RGBA", base.size, (0, 0, 0, 0))
            
            # 修正：ImageChops.multiplyを使用して、マスクとグラデーションを正しく組み合わせる
            mask_rgba = Image.new("RGBA", base.size, (0, 0, 0, 0))
            mask_rgba.putalpha(mask)
            
            # グラデーションをマスクに適用（新しいアプローチ）
            for y in range(base.size[1]):
                for x in range(base.size[0]):
                    if mask.getpixel((x, y)) > 0:  # マスクが非ゼロの場合
                        r, g, b, _ = grad_rgba.getpixel((x, y))
                        gradient_text.putpixel((x, y), (r, g, b, mask.getpixel((x, y))))
            
            # 修正：グラデーションテキストをtxt_layerに合成
            txt_layer = Image.alpha_composite(txt_layer, gradient_text)
            # logging.info("gradientを適応しました")
        else:
            d.text(xy, text, font=font, fill=fill)
            # logging.warning("gradientが存在しません")

        # ベベル＆エンボス：ハイライトとシャドウを 1px ずらして描画
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

    def _prepare_product_name(self, raw: str, brand_name: str = "") -> list[str]:
        """
        1) () または <> （半角／全角）で囲まれた部分を丸ごと削除  
        2) 全角スペース→半角スペースに揃え、連続スペースを 1 個に  
        3) ブランド名が含まれている場合、それを削除
        4) 半角スペースでいったんトークン分割  
        5) トークンを左から詰め、**8 文字**を超えない範囲で行を生成  
        6) 先頭 2 行を返す（行が足りなければそのまま）
        """
        if not raw:
            return ["No Name"]

        # ① ()<> を削除（全角・半角両対応）
        raw = re.sub(r"[（(＜<].*?[）)>＞>]", "", raw)

        # ② スペース正規化
        raw = re.sub(r"\s+", " ", raw.replace("　", " ")).strip()
        if not raw:
            return ["No Name"]
        
        # ③ ブランド名を削除（大文字小文字を区別しない）
        if brand_name:
            # 半角スペースが前後にある場合のブランド名
            if f" {brand_name} " in raw:
                raw = raw.replace(f" {brand_name} ", " ")
            # 文字列の先頭にあるブランド名
            elif raw.startswith(f"{brand_name} "):
                raw = raw[len(brand_name)+1:]
            # 文字列の末尾にあるブランド名
            elif raw.endswith(f" {brand_name}"):
                raw = raw[:-len(brand_name)-1]
            # 単独でブランド名と一致する場合
            elif raw == brand_name:
                return ["No Name"]
            # スペースなしでも出現する可能性があるため
            raw = raw.replace(brand_name, "")
            
        # 最終的な正規化（二重スペースなどの修正）
        raw = re.sub(r"\s+", " ", raw).strip()
        if not raw:
            return ["No Name"]

        # ④ 半角スペースでトークン化
        tokens = raw.split(" ")

        # ⑤ 8 文字以内で行を組み立て
        lines, current = [], ""
        for tok in tokens:
            if len(current + tok) <= 8:
                current += tok
            else:
                if current:
                    lines.append(current)
                current = tok
            if len(lines) == 2:
                break
        if current and len(lines) < 2:
            lines.append(current)

        return lines if lines else ["No Name"]

    def _name_font_size(self, text_len: int) -> int:
        """
        文字数でサイズを粗く段階分け  
        （基準 ≒ 8 文字のとき self.TITLE_FONT_SIZE * 1.9）
        """
        base = int(self.TITLE_FONT_SIZE * 1.9)   # 現行サイズ
        if text_len <= 6:
            return base + 20          # 少ない ⇒ 大
        elif text_len <= 8:
            return base              # 標準
        elif text_len <= 11:
            return base - 30           # やや小
        elif text_len <= 15:
            return base - 50          # やや小
        else:
            return base - 70          # もっと小

    def _brand_font_size(self, text_len: int) -> int:
        """
        ブランド名の文字数でサイズを段階分け
        """
        base = self.BRAND_FONT_SIZE + 70  # 元のベースサイズ
        if text_len <= 4:
            return base + 20          # 少ない ⇒ 大
        elif text_len <= 6:
            return base              # 標準
        elif text_len <= 8:
            return base - 10           # やや小
        elif text_len <= 10:
            return base - 20          # 小
        elif text_len <= 12:
            return base - 30          # 小
        else:
            return base - 40          # もっと小
        
    def _calc_name_block_bottom(self, start_y: int, lines: list[str]) -> int:
        """商品名ブロックの下端 Y 座標を返す"""
        total_h = 0
        for idx, line in enumerate(lines):
            fs = self._name_font_size(len(line.replace(" ", "")))
            total_h += fs
            if idx < len(lines) - 1:
                total_h += 80          # 行間
        return start_y + total_h
    
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

    def save_thumbnail(self, channel: str, genre: str, output_path: str) -> str:
        try:
            # ブックマーク表示ありのイントロスライドを作成
            thumbnail_img = self._create_bookmark_intro_slide(channel, genre)
            
            # 出力ディレクトリの確認
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # PNG形式で保存
            thumbnail_img.save(output_path, "PNG")
            logger.info(f"サムネイル画像を保存しました: {output_path}")
            
            return output_path
        except Exception as e:
            logger.error(f"サムネイル作成エラー: {str(e)}")
            return ""
    
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
        if img_width <= 400 and img_height <= 400:
            # 画面の70%の幅に拡大
            target_width = int(self.VIDEO_WIDTH * 0.7)
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
        rank: int,
        brand_name: str,
        show_name: bool = True,
    ) -> Image.Image:
        """
        製品スライドの作成（画像と商品名のみ表示）
        
        Args:
            product: 製品情報
            rank: 順位
        
        Returns:
            Image.Image: 製品スライド画像
        """
        img  = self._get_common_background() 
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
    
        # ランク
        rank_font = ImageFont.truetype(self.SOURCE_HAN_SERIF_HEAVY,
                                    int(self.TITLE_FONT_SIZE * 2.0))   # 少し大きめ
        rank_text = f"第{rank}位"

        w = self.calculate_text_width(rank_text, rank_font, draw)
        x = (self.VIDEO_WIDTH - w) // 2
        y = 150

        # 塗り＋外側ストローク＋ドロップシャドウ（=glow_radius で代用）
        self.draw_text_effect(
            img, rank_text, (x, y), rank_font,
            fill=(0xF7, 0xF7, 0xF7),
            stroke_width=10, stroke_fill=(0, 0, 0),
            glow_radius=8,  glow_opacity=0.35
        )
        
        # ブランド名の取得と準備
        name_lines = self._prepare_product_name(product.get("name"), brand_name)
        # 表示位置の調整 - ブランド名を追加したので開始位置を上にシフト
        start_y = 350 - (len(name_lines)-1)*40  # 以前は400
        # ブランド名のためのフォントサイズと空間
        brand_text_len = len(brand_name.replace(" ", ""))
        brand_font_size = self._brand_font_size(brand_text_len)  # サイズを動的に設定
        brand_space = 20
        # ブランド名のフォント
        brand_font = ImageFont.truetype(self.SOURCE_HAN_SERIF_HEAVY, brand_font_size)
        # ブランド名を表示
        if show_name and brand_name:
            w_brand = self.calculate_text_width(brand_name, brand_font, draw)
            x_brand = (self.VIDEO_WIDTH - w_brand) // 2
            # ブランド名テキストを描画
            self.draw_text_effect(
                img, brand_name, (x_brand, start_y), brand_font,
                fill=(0x66, 0x1A, 0x1A),  # 濃い赤色
                gradient=[(0xD7, 0x55, 0x4F), (0x82, 0x16, 0x16)], 
                inner_stroke_width=4,  inner_stroke_fill=(255, 255, 255),
                stroke_width=10, stroke_fill=(0, 0, 0),
                glow_radius=15, glow_opacity=0.50
            )
            logging.info("ブランド名を挿入")
        empty_height = 10
        # 位置調整（ブランド名の下に配置）
        if show_name and brand_name:
            current_y = start_y + brand_font_size + brand_space
        else:
            current_y = start_y + brand_font_size + brand_space
        # 商品名ブロックの下端計算
        name_block_bottom = self._calc_name_block_bottom(current_y, name_lines)

        # 商品名
        if show_name:
            for line in name_lines:
                text_len  = len(line.replace(" ", ""))
                font_size = self._name_font_size(text_len)
                name_font = ImageFont.truetype(self.SOURCE_HAN_SERIF_HEAVY, font_size)

                w = self.calculate_text_width(line, name_font, draw)
                x = (self.VIDEO_WIDTH - w) // 2
                y = current_y
                self.draw_text_effect(
                    img, line, (x, y), name_font,
                    fill=(0xB5, 0x2E, 0x2E),
                    gradient=[(0xD7, 0x55, 0x4F), (0x82, 0x16, 0x16)], 
                    inner_stroke_width=4,  inner_stroke_fill=(255, 255, 255),
                    stroke_width=10, stroke_fill=(0, 0, 0),
                    glow_radius=15, glow_opacity=0.50
                )
                current_y += font_size + empty_height

        else:
            # show_name=False の分岐はそのままで OK
            for line in name_lines:
                text_len  = len(line.replace(" ", ""))
                font_size = self._name_font_size(text_len)
                current_y += font_size + empty_height
        
        # 画像を中央下部に配置
        try:
            # 画像サイズチェック
            img_width, img_height = product_img.size
            logger.info(f"元の画像サイズ: {img_width}x{img_height}")
            
            # 縦横比の計算
            aspect_ratio = img_width / img_height if img_height > 0 else 1
            
            # 幅を画面の80%に設定（常に）
            new_width = int(self.VIDEO_WIDTH * 0.7)
            new_height = int(new_width / aspect_ratio)
            
            # ログ出力
            logger.info(f"リサイズ後の画像サイズ: {new_width}x{new_height}")
            
            # リサイズ
            product_img = product_img.resize((new_width, new_height), Image.LANCZOS)
            
            # 画像をブランド名と商品名の下に配置
            img_x = (self.VIDEO_WIDTH - new_width) // 2
            img_y = name_block_bottom + 100
            
            # 画像貼り付け
            img.paste(product_img, (img_x, img_y))
        except Exception as e:
            logger.error(f"画像処理エラー: {str(e)}")
        
        return img.convert("RGB")
    
    def _create_main_intro_slide(self, channel: str, genre: str) -> Image.Image:
        bg = self._get_common_background()
        # 背景のぼかし入り写真があるならここで合成しても OK
        y = int(self.VIDEO_HEIGHT * 0.06)

        channel_name = f"{channel}で" if channel else "お店で"

        # 共通フォント
        heavy220  = ImageFont.truetype(self.SOURCE_HAN_SERIF_HEAVY, 220)
        heavy180  = ImageFont.truetype(self.SOURCE_HAN_SERIF_HEAVY, 180)
        heavy150  = ImageFont.truetype(self.SOURCE_HAN_SERIF_HEAVY, 150)
        heavy130  = ImageFont.truetype(self.SOURCE_HAN_SERIF_HEAVY, 130)
        heavy110  = ImageFont.truetype(self.SOURCE_HAN_SERIF_HEAVY, 110)
        heavy100   = ImageFont.truetype(self.SOURCE_HAN_SERIF_HEAVY, 100)
        heavy90  = ImageFont.truetype(self.SOURCE_HAN_SERIF_HEAVY, 90)
        heavy80   = ImageFont.truetype(self.SOURCE_HAN_SERIF_HEAVY, 80)

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

        # ② マジで使ってみて欲しい
        w = self.calculate_text_width("マジで", heavy220, ImageDraw.Draw(bg))
        self.draw_text_effect(
            bg, "マジで", ((self.VIDEO_WIDTH-w)//2, y),
            heavy220,
            gradient=[(0x82, 0x16, 0x16), (0x82, 0x16, 0x16)],
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
                gradient=[(0x82, 0x16, 0x16), (0x82, 0x16, 0x16)],
                inner_stroke_width=4, inner_stroke_fill=(255, 255, 255),
                stroke_width=10, stroke_fill=(0, 0, 0),
                glow_radius=15, glow_opacity=0.5
            )
            y += 150

        y += 50   # 行間を広めに

        # ③ {購入場所}で買える
        text = f"{channel_name}買える"
        text_len = len(text)
        # フォントを長さで切り替え
        if text_len >= 10:
            heavy_font = heavy80
        elif text_len >= 8:
            heavy_font = heavy110
        else: 
            heavy_font = heavy130
        w = self.calculate_text_width(text, heavy150, ImageDraw.Draw(bg))
        self._draw_text_italic(
            bg, text, y,
            heavy_font,
            gradient=[(255, 246, 194), (255, 216, 74), (199, 154, 5)],
            stroke_width=8, stroke_fill=(0, 0, 0),
            bevel=True,
            glow_radius=12, glow_opacity=0.4
        )
        if text_len >= 10:
            y += 100
        elif text_len >= 8:
            y += 120
        else: 
            y += 150

        # ④ 神商品（少し大きめ）
        text = f"神{genre}"
        text_len_shohin = len(text)  
        if text_len_shohin >= 12:
            heavy_font = heavy80
        elif text_len_shohin >= 10:
            heavy_font = heavy90
        elif text_len_shohin >= 9:
            heavy_font = heavy100
        elif text_len_shohin >= 8:
            heavy_font = heavy110
        elif text_len_shohin >= 6:
            heavy_font = heavy130
        else: 
            heavy_font = heavy180
        w = self.calculate_text_width(text, heavy180, ImageDraw.Draw(bg))
        self._draw_text_italic(
            bg, text, y,
            heavy_font,
            gradient=[(255, 246, 194), (255, 216, 74), (199, 154, 5)],
            stroke_width=8, stroke_fill=(0, 0, 0),
            bevel=True,
            glow_radius=12, glow_opacity=0.4
        )
        if text_len_shohin >= 10:
            y += 180
        elif text_len_shohin >= 6:
            y += 200
        else: 
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
        # y += 100

        assets = [
            ("data/assets/atsugesyou.png", "left"),   # 左下
            ("data/assets/building_medical_pharmacy.png", "right"),  # 右下
        ]

        pad_x = int(self.VIDEO_WIDTH * 0.1)   # 画面端から 2% だけ余白
        pad_y = int(self.VIDEO_HEIGHT * 0.1)

        for path, side in assets:
            if not os.path.exists(path):
                logger.warning(f"装飾画像が見つかりません: {path}")
                continue
            try:
                deco = Image.open(path).convert("RGBA")

                # 画像を大きすぎないサイズ（画面幅 40%・高さ 20% 以内）に収める
                max_w = int(self.VIDEO_WIDTH * 0.4)
                max_h = int(self.VIDEO_HEIGHT * 0.2)
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

        return bg.convert("RGB")

    def _create_bookmark_intro_slide(self, channel: str, genre: str) -> Image.Image:
        """
        ブックマーク部分を強調したイントロスライドを作成
        """
        bg = self._create_main_intro_slide(channel, genre).convert("RGBA")
        draw = ImageDraw.Draw(bg)
        
        heavy70 = ImageFont.truetype(self.SOURCE_HAN_SERIF_HEAVY, 70)
        text = "※これはブックマーク必須やで"
        
        # 中央配置
        w = self.calculate_text_width(text, heavy70, draw)
        x = (self.VIDEO_WIDTH - w) // 2
        y = self.VIDEO_HEIGHT - 700
        
        self.draw_text_effect(
            bg, text, (x, y),
            heavy70,
            fill=(199, 22, 22),
            stroke_width=1, stroke_fill=(255, 226, 82),
            # inner_stroke_width=1, inner_stroke_fill=(158, 0, 0),
            glow_radius=20, glow_opacity=0.7
        )
        
        # 最後に RGB モードに戻す (元のメソッドと同じ)
        return bg.convert("RGB")
        
    def _create_product_animation(
        self, 
        product: Dict[str, Any], 
        rank: int, 
        output_path: str, 
        show_name: bool = True,
        animation_duration: float = 0.1
    ) -> bool:
        """
        商品情報のアニメーション付き動画を作成
        
        Args:
            product: 製品情報
            rank: 順位
            output_path: 出力動画のパス
            show_name: 商品名を表示するかどうか
            animation_duration: アニメーション時間（秒）
                
        Returns:
            bool: 成功したかどうか
        """
        try:
            # ベース画像の作成 - 全てのフレームに共通
            base_img = self._get_common_background()
            draw = ImageDraw.Draw(base_img)
            
            # 画像読み込みの準備
            img_loaded = False
            product_img = None
            
            # 画像の読み込み処理（既存のコードと同様）
            if 'local_image_path' in product and product['local_image_path']:
                local_path = product['local_image_path']
                if os.path.exists(local_path):
                    try:
                        product_img = Image.open(local_path)
                        img_loaded = True
                    except Exception as e:
                        logger.error(f"ローカル画像読み込みエラー: {local_path} - {str(e)}")
                        img_loaded = False
            
            if not img_loaded and 'product_id' in product:
                img_path = os.path.join(self.temp_dir, f"{product['product_id']}.jpg")
                if os.path.exists(img_path):
                    try:
                        product_img = Image.open(img_path)
                        img_loaded = True
                    except Exception as e:
                        logger.error(f"一時ディレクトリの画像読み込みエラー: {img_path} - {str(e)}")
                        img_loaded = False
            
            if not img_loaded and 'image_url' in product and product['image_url']:
                image_url = product['image_url']
                try:
                    logger.info(f"画像をURLから直接ダウンロード中: {image_url}")
                    img_path = os.path.join(self.temp_dir, f"{product['product_id']}.jpg")
                    os.makedirs(os.path.dirname(img_path), exist_ok=True)
                    
                    import requests
                    response = requests.get(image_url, timeout=30)
                    response.raise_for_status()
                    
                    with open(img_path, 'wb') as f:
                        f.write(response.content)
                        
                    product_img = Image.open(img_path)
                    img_loaded = True
                    logger.info(f"画像を直接ダウンロードして保存: {img_path}")
                except Exception as e:
                    logger.error(f"画像ダウンロードエラー: {str(e)}")
                    img_loaded = False

            # ブランド名の取得と準備
            brand_name = product.get("brand", "")
            # 商品名の準備
            name_lines = self._prepare_product_name(product.get("name"), brand_name)
            start_y = 350 - (len(name_lines)-1)*40
            brand_text_len = len(brand_name.replace(" ", ""))
            brand_font_size = self._brand_font_size(brand_text_len)
            brand_space = 20
            empty_height = 20
            name_block_bottom = self._calc_name_block_bottom(start_y + brand_font_size + brand_space, name_lines)
            
            # 画像サイズ設定
            if img_loaded:
                img_width, img_height = product_img.size
                logger.info(f"元の画像サイズ: {img_width}x{img_height}")
                aspect_ratio = img_width / img_height if img_height > 0 else 1
                
                new_width = int(self.VIDEO_WIDTH * 0.7)
                new_height = int(new_width / aspect_ratio)
                
                logger.info(f"リサイズ後の画像サイズ: {new_width}x{new_height}")
                
                # リサイズ
                product_img = product_img.resize((new_width, new_height), Image.LANCZOS)
                
                # 画像の最終位置（アニメーション後）
                img_x = (self.VIDEO_WIDTH - new_width) // 2
                img_y = name_block_bottom + 100
            else:
                new_width = int(self.VIDEO_WIDTH * 0.7)
                new_height = int(new_width)
                img_x = (self.VIDEO_WIDTH - new_width) // 2
                img_y = name_block_bottom + 100

            # ランク表示用のフォント
            rank_font = ImageFont.truetype(self.SOURCE_HAN_SERIF_HEAVY, int(self.TITLE_FONT_SIZE * 2.0))
            rank_text = f"第{rank}位"
            
            # ブランド名用のフォント
            brand_font = ImageFont.truetype(self.SOURCE_HAN_SERIF_HEAVY, brand_font_size)
            
            # アニメーションの一時ディレクトリ
            with tempfile.TemporaryDirectory() as animation_dir:
                # フレーム数の設定
                fps = 30
                frame_count = max(int(fps * animation_duration), 3)  # 最低3フレーム
                
                # アニメーションフレームの生成
                frame_paths = []
                
                # アニメーションフレーム
                for frame in range(frame_count + 1):  # +1で最終フレームを含める
                    progress = frame / frame_count  # 0.0 から 1.0 の進行度
                    
                    # 現在のフレームの画像を作成
                    frame_img = self._get_common_background()
                    draw = ImageDraw.Draw(frame_img)
                    
                    # ランクのアニメーション（上から下へ）
                    if show_name:
                        w = self.calculate_text_width(rank_text, rank_font, draw)
                        x = (self.VIDEO_WIDTH - w) // 2
                        
                        # 開始位置は画面上部の外（-100px）、終了位置は150px
                        start_rank_y = -100
                        end_rank_y = 150
                        current_rank_y = int(start_rank_y + (end_rank_y - start_rank_y) * progress)
                        
                        # ランクテキストを描画
                        self.draw_text_effect(
                            frame_img, rank_text, (x, current_rank_y), rank_font,
                            fill=(0xF7, 0xF7, 0xF7),
                            stroke_width=10, stroke_fill=(0, 0, 0),
                            glow_radius=8, glow_opacity=0.35
                        )
                        
                        # ブランド名のアニメーション（上から下へ）
                        w_brand = self.calculate_text_width(brand_name, brand_font, draw)
                        x_brand = (self.VIDEO_WIDTH - w_brand) // 2
                        
                        start_brand_y = -200
                        end_brand_y = start_y
                        current_brand_y = int(start_brand_y + (end_brand_y - start_brand_y) * progress)
                        
                        # ブランド名テキストを描画
                        self.draw_text_effect(
                            frame_img, brand_name, (x_brand, current_brand_y), brand_font,
                            fill=(0x66, 0x1A, 0x1A),  # 濃い赤色
                            gradient=[(0xD7, 0x55, 0x4F), (0x82, 0x16, 0x16)], 
                            inner_stroke_width=4,  inner_stroke_fill=(255, 255, 255),
                            stroke_width=10, stroke_fill=(0, 0, 0),
                            glow_radius=15, glow_opacity=0.50
                        )
                        
                        # 商品名のアニメーション（上から下へ）
                        current_y = start_y + brand_font_size + brand_space  # ブランド名の下に配置
                        for line in name_lines:
                            text_len = len(line.replace(" ", ""))
                            font_size = self._name_font_size(text_len)
                            name_font = ImageFont.truetype(self.SOURCE_HAN_SERIF_HEAVY, font_size)
                            
                            w = self.calculate_text_width(line, name_font, draw)
                            x = (self.VIDEO_WIDTH - w) // 2
                            
                            # 開始位置は画面上部の外（-200px）、終了位置は現在のy座標
                            start_name_y = -200
                            end_name_y = current_y
                            current_name_y = int(start_name_y + (end_name_y - start_name_y) * progress)
                            
                            # 商品名テキストを描画
                            self.draw_text_effect(
                                frame_img, line, (x, current_name_y), name_font,
                                fill=(0xB5, 0x2E, 0x2E),
                                gradient=[(0xD7, 0x55, 0x4F), (0x82, 0x16, 0x16)],
                                inner_stroke_width=4, inner_stroke_fill=(255, 255, 255),
                                stroke_width=10, stroke_fill=(0, 0, 0),
                                glow_radius=15, glow_opacity=0.50
                            )
                            current_y += font_size + empty_height
                    
                    # 商品画像のアニメーション（下から上へ）
                    if img_loaded:
                        # 開始位置は画面下部の外（self.VIDEO_HEIGHT + 100px）、終了位置はimg_y
                        start_img_y = self.VIDEO_HEIGHT + 100
                        end_img_y = img_y
                        current_img_y = int(start_img_y + (end_img_y - start_img_y) * progress)
                        
                        # 画像貼り付け
                        frame_img.paste(product_img, (img_x, current_img_y))
                    
                    # フレームを保存
                    frame_path = os.path.join(animation_dir, f"frame_{frame:03d}.png")
                    frame_img = frame_img.convert("RGB")
                    frame_img.save(frame_path)
                    frame_paths.append(frame_path)
                
                # 最終フレーム（アニメーション後の静的な状態）
                final_frame = frame_paths[-1]
                static_frame_path = os.path.join(animation_dir, "static_frame.png")
                shutil.copy(final_frame, static_frame_path)
                
                # フレームリストファイルの作成（アニメーションフレーム）
                anim_frames_list_path = os.path.join(animation_dir, "anim_frames.txt")
                with open(anim_frames_list_path, "w") as f:
                    for i, frame_path in enumerate(frame_paths):
                        f.write(f"file '{frame_path}'\n")
                        # 最後のフレーム以外は1/fpsの持続時間
                        if i < len(frame_paths) - 1:
                            f.write(f"duration {1/fps}\n")
                        else:
                            # 最後のフレームには特別な持続時間を指定しない（最後のフレームはoutfileの生成に使われるため）
                            f.write(f"duration {1/fps}\n")
                
                # 一時的なアニメーション部分のみの動画を作成
                temp_anim_path = os.path.join(animation_dir, "temp_anim.mp4")
                anim_cmd = [
                    "ffmpeg", "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", anim_frames_list_path,
                    "-vsync", "vfr",
                    "-pix_fmt", "yuv420p",
                    temp_anim_path
                ]
                
                try:
                    subprocess.run(anim_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    logger.info(f"アニメーション部分の動画を作成しました: {temp_anim_path}")
                    
                    # 最終フレームを静止画として出力
                    static_video_path = os.path.join(animation_dir, "static_frame.mp4")
                    
                    # 最終フレームを5秒間（後で音声に合わせて調整するための十分な長さ）の静止動画として作成
                    static_cmd = [
                        "ffmpeg", "-y",
                        "-loop", "1",
                        "-i", static_frame_path,
                        "-c:v", "libx264",
                        "-t", "5",  # 十分な長さ（音声に合わせて後でカットされる）
                        "-pix_fmt", "yuv420p",
                        static_video_path
                    ]
                    
                    subprocess.run(static_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    logger.info(f"静止画部分の動画を作成しました: {static_video_path}")
                    
                    # 最後に両方を結合
                    list_file_path = os.path.join(animation_dir, "final_list.txt")
                    with open(list_file_path, "w") as f:
                        f.write(f"file '{temp_anim_path}'\n")
                        f.write(f"file '{static_video_path}'\n")
                    
                    final_cmd = [
                        "ffmpeg", "-y",
                        "-f", "concat",
                        "-safe", "0",
                        "-i", list_file_path,
                        "-c", "copy",
                        output_path
                    ]
                    
                    subprocess.run(final_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    logger.info(f"アニメーション付き動画を作成しました: {output_path}")
                    return True
                    
                except subprocess.CalledProcessError as e:
                    logger.error(f"FFmpeg実行エラー: {e}")
                    return False
                    
            return True
        except Exception as e:
            logger.error(f"アニメーション作成中にエラー: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def wrap_text(self, text, font, draw, max_width):
        """
        テキストを適切な位置で折り返す（最大2行まで対応）
        """
        # 短いテキストはそのまま1行で返す
        if len(text) <= 12:
            return [text]
        
        # テキスト幅を計算
        def calculate_text_width(text_to_measure):
            try:
                return self.calculate_text_width(text_to_measure, font, draw)
            except AttributeError:
                return draw.textsize(text_to_measure, font=font)[0]
        
        # テキスト幅が最大幅を超えない場合は1行で返す
        if calculate_text_width(text) <= max_width:
            return [text]
        
        # 折り返しの基準となる文字と助詞
        break_chars = '、。，．,.!?！？ 　'
        break_words = ['で', 'が', 'を', 'は', 'に', 'へ', 'と', 'や', 'の', 'から']
        
        # 文字列の半分あたりから適切な区切り位置を探す
        middle_pos = len(text) // 2
        search_range = 2  # 検索範囲
        best_position = middle_pos  # デフォルト位置
        
        # 適切な区切り位置を前後に探索
        for offset in range(search_range + 1):
            # 前方向に探索
            if middle_pos - offset >= 0:
                check_pos = middle_pos - offset
                if text[check_pos] in break_chars:
                    best_position = check_pos + 1
                    break
                elif check_pos > 0 and text[check_pos-1] in break_words:
                    best_position = check_pos
                    break
            
            # 後方向に探索
            if middle_pos + offset < len(text):
                check_pos = middle_pos + offset
                if text[check_pos] in break_chars:
                    best_position = check_pos + 1
                    break
                elif check_pos > 0 and text[check_pos-1] in break_words:
                    best_position = check_pos
                    break
        
        # 行を分割
        first_line = text[:best_position]
        second_line = text[best_position:]
        
        return [first_line, second_line]

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
        
    def _prepare_product_name_for_narration(self, product_name, brand_name):
        """
        ナレーション用に商品名からブランド名と重複している部分を除去する
        表示用の _prepare_product_name と同様のロジックで処理
        """
        if not product_name or not brand_name:
            return product_name
            
        # スペース正規化
        product_name = re.sub(r"\s+", " ", product_name.replace("　", " ")).strip()
        
        # ブランド名を削除（大文字小文字を区別しない）
        if f" {brand_name} " in product_name:
            product_name = product_name.replace(f" {brand_name} ", " ")
        elif product_name.startswith(f"{brand_name} "):
            product_name = product_name[len(brand_name)+1:]
        elif product_name.endswith(f" {brand_name}"):
            product_name = product_name[:-len(brand_name)-1]
        elif product_name == brand_name:
            return "商品"
        product_name = product_name.replace(brand_name, "")
        
        product_name = re.sub(r"\s+", " ", product_name).strip()
        if not product_name:
            return "商品"
            
        return product_name

    def create_video(
            self,
            products: List[Dict[str, Any]],
            title: str,
            channel: str,
            output_filename: Optional[str] = None
        ) -> str:
        """
        製品リストからショート動画を作成（BGM追加機能対応、アニメーション機能追加）
        
        Args:
            products: 製品情報リスト
            title: 動画タイトル
            channel: チャンネル名
            output_filename: 出力ファイル名
        
        Returns:
            str: 作成した動画のパス
        """
        logger.info(f"動画作成開始: {title}")
        
        output_path = os.path.join(self.output_dir, output_filename)
        
        # 製品リストをシャッフルして順位を割り当て
        shuffled_products = random.sample(products, len(products))
        shuffled_products = shuffled_products[:7]
        total_products = len(shuffled_products)
        for i, product in enumerate(shuffled_products):
            product['new_rank'] = total_products - i 
        
        try:
            # 一時ディレクトリを作成
            with tempfile.TemporaryDirectory() as temp_dir:
                # 動画セグメントのパスリスト
                video_segments = []
                
                # イントロスライド作成
                intro_title = None
                channel_intro = title.split('で買える')[0] if 'で買える' in title else ""
                genre = title.split('で買える')[-1].replace('ランキング', '').strip() if 'で買える' in title else ""
                for product in shuffled_products:
                    if 'channel' in product and 'genre' in product:
                        intro_title = f"一度はマジで使ってみてほしい{channel_intro}で買える神{genre}挙げてく。これはブックマーク必須やで"
                        break
                
                if not intro_title:
                    # main.pyからタイトルを構築
                    genre = title.split('で買える')[-1].replace('ランキング', '').strip() if 'で買える' in title else ""
                    intro_title = f"一度はマジで使ってみてほしい{channel_intro}で買える神{genre}挙げてく。これはブックマーク必須やで"

                # イントロタイトルを前半と後半に分割（「これはブックマーク必須やで」の部分を分ける）
                main_intro_text = f"一度はマジで使ってみてほしい{channel_intro}で買える神{genre}挙げてく。"
                bookmark_text = "これはブックマーク必須やで"
                
                # メインイントロスライド作成（「これはブックマーク必須やで」を表示しない）
                main_intro_img = self._create_main_intro_slide(channel, genre)
                main_intro_slide_path = os.path.join(temp_dir, "main_intro_slide.png")
                main_intro_img.save(main_intro_slide_path)
                
                # ブックマークスライド作成（ブックマーク部分だけを強調表示）
                bookmark_intro_img = self._create_bookmark_intro_slide(channel, genre)
                bookmark_intro_slide_path = os.path.join(temp_dir, "bookmark_intro_slide.png")
                bookmark_intro_img.save(bookmark_intro_slide_path)
                
                # イントロ音声生成
                intro_audio_path = os.path.join(temp_dir, "intro_audio.wav")
                intro_success = generate_narration(intro_title, intro_audio_path, "random")
                
                taiko_sound_path = "data/bgm/和太鼓でドドン.mp3"
                syouhin_sound_path = "data/bgm/ニュッ3.mp3"
                                
                # 音声ファイルの分析と分割（ブックマーク部分のタイミングを特定）
                if os.path.exists(intro_audio_path) and os.path.getsize(intro_audio_path) > 100:
                    # 音声ファイルの長さを取得
                    audio_duration = get_audio_duration(intro_audio_path)
                    
                    # 音声分析（簡易的な方法として、全体の長さから推定）
                    main_part_duration = audio_duration * 0.7  # メインパートは全体の70%と推定
                    bookmark_part_duration = audio_duration - main_part_duration  # 残りの30%をブックマークパート
                    
                    # 1. メインイントロ部分の動画作成
                    main_intro_audio_path = os.path.join(temp_dir, "main_intro_audio.wav")
                    extract_cmd = [
                        "ffmpeg", "-y",
                        "-i", intro_audio_path,
                        "-ss", "0",
                        "-t", str(main_part_duration),
                        "-c:a", "pcm_s16le",
                        main_intro_audio_path
                    ]
                    
                    try:
                        subprocess.run(extract_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        logger.info(f"メインイントロ音声を切り出しました: {main_intro_audio_path}")
                        
                        # メインイントロに和太鼓効果音をミックス
                        main_intro_with_effect_path = os.path.join(temp_dir, "main_intro_with_effect.wav")
                        
                        if os.path.exists(taiko_sound_path):
                            # 効果音と音声をミックスするFFmpegコマンド
                            mix_cmd = [
                                "ffmpeg", "-y",
                                "-i", main_intro_audio_path,  # メインナレーション
                                "-i", taiko_sound_path,  # 和太鼓効果音
                                "-filter_complex",
                                "[1:a]adelay=0|0,volume=1.2[effect];[0:a][effect]amix=inputs=2:duration=first[aout]",
                                "-map", "[aout]",
                                "-c:a", "pcm_s16le",
                                main_intro_with_effect_path
                            ]
                            
                            try:
                                subprocess.run(mix_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                                logger.info(f"メインイントロに和太鼓効果音を追加しました")
                                main_intro_audio_path = main_intro_with_effect_path
                            except subprocess.CalledProcessError as e:
                                logger.error(f"和太鼓効果音の追加に失敗: {e.stderr}")
                        
                        # メインイントロ動画の作成
                        main_intro_video_path = os.path.join(temp_dir, "main_intro_video.mp4")
                        cmd = [
                            "ffmpeg", "-y",
                            "-loop", "1",
                            "-i", main_intro_slide_path,
                            "-i", main_intro_audio_path,
                            "-c:v", "libx264",
                            "-tune", "stillimage",
                            "-c:a", "aac",
                            "-b:a", "192k",
                            "-pix_fmt", "yuv420p",
                            "-shortest"
                        ]
                        
                        cmd.append(main_intro_video_path)
                        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        video_segments.append(main_intro_video_path)
                        
                        # 2. ブックマーク部分の動画作成
                        # ブックマーク用の音声を切り出し
                        bookmark_audio_path = os.path.join(temp_dir, "bookmark_audio.wav")
                        extract_cmd = [
                            "ffmpeg", "-y",
                            "-i", intro_audio_path,
                            "-ss", str(main_part_duration),
                            "-t", str(bookmark_part_duration),
                            "-c:a", "pcm_s16le",
                            bookmark_audio_path
                        ]
                        
                        subprocess.run(extract_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        logger.info(f"ブックマーク音声を切り出しました: {bookmark_audio_path}")
                        
                        # ブックマーク動画の作成
                        bookmark_video_path = os.path.join(temp_dir, "bookmark_video.mp4")
                        cmd = [
                            "ffmpeg", "-y",
                            "-loop", "1",
                            "-i", bookmark_intro_slide_path,
                            "-i", bookmark_audio_path,
                            "-c:v", "libx264",
                            "-tune", "stillimage",
                            "-c:a", "aac",
                            "-b:a", "192k",
                            "-pix_fmt", "yuv420p",
                            "-shortest"
                        ]
                        
                        cmd.append(bookmark_video_path)
                        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        video_segments.append(bookmark_video_path)
                        
                    except subprocess.CalledProcessError as e:
                        logger.error(f"イントロ音声の分割・動画作成エラー: {e.stderr}")
                        
                        # エラーが発生した場合、通常の方法でイントロ動画を作成
                        logger.warning("通常方法でイントロ動画を作成します")
                        intro_img = self._create_improved_intro_slide(channel)
                        intro_slide_path = os.path.join(temp_dir, "intro_slide.png")
                        intro_img.save(intro_slide_path)
                        
                        intro_video_path = os.path.join(temp_dir, "intro_video.mp4")
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
                        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        video_segments.append(intro_video_path)
                else:
                    # 音声生成に失敗した場合、通常の方法でイントロ動画を作成
                    logger.warning(f"イントロの音声ファイルが存在しないか無効です。通常方法でイントロ動画を作成します。")
                    display_duration = 3.0
                    intro_audio_path = os.path.join(temp_dir, "silent_intro.wav")
                    create_silent_audio(intro_audio_path, display_duration)
                    
                    intro_img = self._create_main_intro_slide(channel, genre)
                    intro_slide_path = os.path.join(temp_dir, "intro_slide.png")
                    intro_img.save(intro_slide_path)
                    
                    intro_video_path = os.path.join(temp_dir, "intro_video.mp4")
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
                    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    video_segments.append(intro_video_path)
                    
                # 各製品ごとに動画セグメントを作成
                for product in shuffled_products:
                    rank = product['new_rank']
                    product_name = product['name']
                    brand_name = product['brand']
                    reviews = product.get('reviews', [])
                    
                    # 製品名・ブランド名だけのナレーション用テキスト
                    product_name_for_narration = self._prepare_product_name_for_narration(product.get('name'), brand_name)
                    product_intro_text = f"{rank}位、{brand_name}の{product_name_for_narration}"
                    
                    # 製品紹介ナレーション音声を生成
                    product_audio_path = os.path.join(temp_dir, f"product_{rank}_audio.wav")
                    success = generate_narration(product_intro_text, product_audio_path, "random")
                    
                    # ナレーション音声があれば使用、なければ3秒間の無音
                    if os.path.exists(product_audio_path) and os.path.getsize(product_audio_path) > 100:
                        audio_duration = get_audio_duration(product_audio_path)
                        display_duration = max(audio_duration + 0.5, 3.0)  # 少し余裕を持たせる
                        
                        # 各製品紹介に和太鼓効果音をミックス
                        product_audio_with_effect_path = os.path.join(temp_dir, f"product_{rank}_audio_with_effect.wav")
                        
                        if os.path.exists(syouhin_sound_path):
                            # 効果音と音声をミックスするFFmpegコマンド
                            mix_cmd = [
                                "ffmpeg", "-y",
                                "-i", product_audio_path,  # ナレーション
                                "-i", syouhin_sound_path,  # 和太鼓効果音
                                "-filter_complex",
                                "[1:a]adelay=0|0,volume=1.0[effect];[0:a][effect]amix=inputs=2:duration=first[aout]",
                                "-map", "[aout]",
                                "-c:a", "pcm_s16le",
                                product_audio_with_effect_path
                            ]
                            
                            try:
                                subprocess.run(mix_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                                logger.info(f"製品{rank}の紹介に和太鼓効果音を追加しました")
                                product_audio_path = product_audio_with_effect_path  # 効果音入りのパスに置き換え
                            except subprocess.CalledProcessError as e:
                                logger.error(f"製品{rank}の和太鼓効果音の追加に失敗: {e.stderr}")
                        else:
                            logger.warning(f"和太鼓効果音ファイルが見つかりません: {taiko_sound_path}")
                    else:
                        logger.warning(f"製品 {rank} の音声ファイルが存在しないか無効です。無音を使用します。")
                        display_duration = 3.0
                        product_audio_path = os.path.join(temp_dir, f"silent_{rank}.wav")
                        create_silent_audio(product_audio_path, display_duration)
                    
                    # アニメーション付き商品紹介動画を作成
                    product_video_path = os.path.join(temp_dir, f"product_{rank}_video.mp4")
                    
                    # アニメーション付き動画作成
                    animation_success = self._create_product_animation(
                        product, 
                        rank, 
                        os.path.join(temp_dir, f"product_{rank}_animation.mp4"), 
                        show_name=True,
                        animation_duration=0.1  # 0.1秒のアニメーション
                    )

                    if animation_success:
                        # アニメーション動画と音声を結合
                        cmd = [
                            "ffmpeg", "-y",
                            "-i", os.path.join(temp_dir, f"product_{rank}_animation.mp4"),
                            "-i", product_audio_path,
                            "-c:v", "libx264",
                            "-c:a", "aac",
                            "-b:a", "192k",
                            "-pix_fmt", "yuv420p",
                            "-shortest",
                            product_video_path
                        ]
                        
                        try:
                            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True)
                            logger.info(f"製品 {rank} のアニメーション動画生成成功")
                        except subprocess.CalledProcessError as e:
                            logger.error(f"製品 {rank} のアニメーション動画生成エラー: {e.stderr}")
                            
                            # アニメーション失敗時のフォールバック: 通常の静止画動画を作成
                            logger.warning(f"製品 {rank} の通常の静止画動画を作成します")
                            
                            # 1. 製品画像と商品名のみを表示したスライド生成
                            product_slide = self._create_product_slide(product, rank, brand_name=product['brand'], show_name=True)
                            product_slide_path = os.path.join(temp_dir, f"product_{rank}_slide.png")
                            product_slide.save(product_slide_path)
                            
                            # 製品スライドを動画に変換
                            cmd = [
                                "ffmpeg", "-y",
                                "-i", os.path.join(temp_dir, f"product_{rank}_animation.mp4"),
                                "-i", product_audio_path,
                                "-filter_complex",
                                "[0:v]setpts=PTS-STARTPTS[v];[1:a]asetpts=PTS-STARTPTS[a]",
                                "-map", "[v]",
                                "-map", "[a]",
                                "-c:v", "libx264",
                                "-c:a", "aac",
                                "-b:a", "192k",
                                "-pix_fmt", "yuv420p",
                                product_video_path
                            ]
                            
                            try:
                                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True)
                            except subprocess.CalledProcessError as e:
                                logger.error(f"製品 {rank} の動画生成エラー: {e.stderr}")
                                raise
                    else:
                        # アニメーション作成失敗時は通常の静止画動画を作成
                        logger.warning(f"製品 {rank} のアニメーション作成に失敗。通常の静止画動画を作成します")
                        
                        # 1. 製品画像と商品名のみを表示したスライド生成
                        product_slide = self._create_product_slide(product, rank, brand_name=product['brand'], show_name=True)
                        product_slide_path = os.path.join(temp_dir, f"product_{rank}_slide.png")
                        product_slide.save(product_slide_path)
                        
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
                            "-shortest",
                            product_video_path
                        ]
                        
                        try:
                            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True)
                        except subprocess.CalledProcessError as e:
                            logger.error(f"製品 {rank} の動画生成エラー: {e.stderr}")
                            raise
                    
                    video_segments.append(product_video_path)
                    
                    # コメントを順番に追加していく
                    if reviews:
                        base_slide = self._create_product_slide(product, rank, brand_name=product['brand'], show_name=False)
                        draw = ImageDraw.Draw(base_slide)
                        
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
                            comment_text = str(review) 
                            # コメント位置
                            comment_position = positions[i % len(positions)]
                            
                            # コメントを累積スライドに追加
                            comment_font = self.get_font(
                                self.REVIEW_FONT_SIZE + 30,
                                font_path=self.YASASHISA_GOTHIC if os.path.exists(self.YASASHISA_GOTHIC) else self.noto_sans_jp_path
                            )
                            draw = ImageDraw.Draw(accumulated_slide)

                            # テキスト幅を調整して折り返し
                            max_text_width = int(self.VIDEO_WIDTH * 0.7)  # コメント内テキスト幅（ボックス幅の少し小さめ）
                            # テキストを折り返す
                            lines = self.wrap_text(comment_text, comment_font, draw, max_text_width)

                            # バルーンサイズ計算
                            line_h = int((self.REVIEW_FONT_SIZE + 15) * 1.4)
                            text_h = line_h * len(lines)
                            text_w = max(self.calculate_text_width(l, comment_font, draw) for l in lines)
                            pad_x, pad_y = 40, 30
                            
                            # ボックス幅を画面幅の90%に固定
                            box_w = int(self.VIDEO_WIDTH * 0.9)
                            box_h = text_h + pad_y * 2

                            # 位置決定
                            center_x = self.VIDEO_WIDTH // 2
                            if comment_position == "top":
                                box_y = int(self.VIDEO_HEIGHT * 0.25)
                            elif comment_position == "middle":
                                box_y = int(self.VIDEO_HEIGHT * 0.5) - box_h // 2
                            else:  # bottom
                                box_y = int(self.VIDEO_HEIGHT * 0.75) - box_h

                            box_x = center_x - box_w // 2

                            # バルーン（角丸長方形）を描画
                            border_col = self.COMMENT_COLORS[i % 3]
                            rect = [
                                (box_x, box_y),
                                (box_x + box_w, box_y + box_h)
                            ]
                            # Pillow ≥ 9.2 なら rounded_rectangle が使える
                            draw.rounded_rectangle(
                                rect,
                                radius=self.COMMENT_CORNER_RADIUS,
                                fill=(255, 255, 255),
                                outline=border_col,
                                width=self.COMMENT_BORDER_PX
                            )

                            # テキスト描画
                            for idx, line in enumerate(lines):
                                tx = center_x - self.calculate_text_width(line, comment_font, draw) // 2
                                ty = box_y + pad_y + idx * line_h
                                draw.text((tx, ty), line, font=comment_font, fill=(0, 0, 0))
                            
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
                        # BGMの音量を0.25に調整し、無限ループ
                        f"[1:a]volume=0.25,aloop=loop=-1:size=2e+09[bgm];"
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