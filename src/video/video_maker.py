"""
@file: video_maker.py
@desc: MoviePyを使って縦型ショート動画を作成するモジュール
"""

import os
import logging
import random
import tempfile
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

# 動画編集ライブラリ
from moviepy import (
    TextClip, ImageClip, AudioFileClip, CompositeVideoClip,
    concatenate_videoclips, ColorClip, VideoFileClip
)

from moviepy.video.tools.subtitles import SubtitlesClip
from PIL import Image, ImageDraw, ImageFont

from moviepy.video.VideoClip import VideoClip

# ロガー設定
logger = logging.getLogger(__name__)

class VideoMaker:
    """縦型ショート動画を作成するクラス"""
    
    # 縦型動画の基本サイズ
    VIDEO_WIDTH = 1080
    VIDEO_HEIGHT = 1920
    
    # フォント設定
    DEFAULT_FONT_SIZE = 48
    TITLE_FONT_SIZE = 64
    BRAND_FONT_SIZE = 36
    REVIEW_FONT_SIZE = 42
    
    # テキストカラー
    TEXT_COLOR = 'white'
    SHADOW_COLOR = 'black'
    RANK_COLOR = 'gold'
    TITLE_COLOR = 'white'
    
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
                self.font_path = '/usr/share/fonts/opentype/noto/NotoSansCJKjp-Bold.otf'
            else:  # Linux
                self.font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
        
        # フォントが存在するか確認
        if not os.path.exists(self.font_path):
            logger.warning(f"指定したフォント({self.font_path})が見つかりません。代替フォントを使用します。")
            self.font_path = None
    
    def _create_title_slide(
        self,
        title: str,
        subtitle: str,
        duration: float = 3.0
    ) -> VideoClip:
        """
        タイトルスライドの作成
        
        Args:
            title: メインタイトル
            subtitle: サブタイトル
            duration: 表示時間（秒）
        
        Returns:
            タイトルスライド
        """
        # 背景
        bg = ColorClip(
            size=(self.VIDEO_WIDTH, self.VIDEO_HEIGHT),
            color=self.BG_COLOR,
            duration=duration
        )
        
        # タイトルテキスト
        title_clip = TextClip(
            title,
            fontsize=self.TITLE_FONT_SIZE * 1.5,
            color=self.TITLE_COLOR,
            font=self.font_path,
            method='caption',
            align='center',
            size=(self.VIDEO_WIDTH * 0.9, None)
        )
        title_clip = title_clip.set_position(('center', self.VIDEO_HEIGHT // 3))
        title_clip = title_clip.set_duration(duration)
        
        # サブタイトル
        subtitle_clip = TextClip(
            subtitle,
            fontsize=self.TITLE_FONT_SIZE,
            color='lightgray',
            font=self.font_path,
            method='caption',
            align='center',
            size=(self.VIDEO_WIDTH * 0.8, None)
        )
        subtitle_clip = subtitle_clip.set_position(('center', self.VIDEO_HEIGHT // 2))
        subtitle_clip = subtitle_clip.set_duration(duration)
        
        # 日付
        today = datetime.now().strftime('%Y/%m/%d')
        date_clip = TextClip(
            f"作成: {today}",
            fontsize=self.BRAND_FONT_SIZE,
            color='gray',
            font=self.font_path
        )
        date_clip = date_clip.set_position(('center', self.VIDEO_HEIGHT - 200))
        date_clip = date_clip.set_duration(duration)
        
        # 出典表示
        source_clip = TextClip(
            "出典: アットコスメPチャンネルランキング",
            fontsize=self.BRAND_FONT_SIZE,
            color='gray',
            font=self.font_path
        )
        source_clip = source_clip.set_position(('center', self.VIDEO_HEIGHT - 120))
        source_clip = source_clip.set_duration(duration)
        
        # 合成
        final_clip = CompositeVideoClip([
            bg, title_clip, subtitle_clip, date_clip, source_clip
        ])
        
        return final_clip
    
    def _create_product_slide(
        self,
        product: Dict[str, Any],
        rank: int,
        duration: float = 2.5
    ) -> VideoClip:
        """
        製品スライドの作成
        
        Args:
            product: 製品情報
            rank: 順位
            duration: 表示時間（秒）
        
        Returns:
            製品スライド
        """
        # 背景
        bg = ColorClip(
            size=(self.VIDEO_WIDTH, self.VIDEO_HEIGHT),
            color=self.BG_COLOR,
            duration=duration
        )
        
        clips = [bg]
        
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
                
                # 画像クリップの作成
                img_clip = ImageClip(img_path)
                
                # リサイズ（縦800px上限、アスペクト比保持）
                aspect_ratio = img_clip.w / img_clip.h
                new_height = min(800, self.VIDEO_HEIGHT // 2)
                new_width = int(new_height * aspect_ratio)
                
                if new_width > self.VIDEO_WIDTH * 0.8:
                    new_width = int(self.VIDEO_WIDTH * 0.8)
                    new_height = int(new_width / aspect_ratio)
                
                img_clip = img_clip.resize(height=new_height)
                
                # 配置
                img_clip = img_clip.set_position(('center', self.VIDEO_HEIGHT // 3 - new_height // 2))
                img_clip = img_clip.set_duration(duration)
                
                clips.append(img_clip)
            
            except Exception as e:
                logger.error(f"画像読み込みエラー: {str(e)}")
        
        # 順位表示
        rank_text = f"{rank}位"
        rank_clip = TextClip(
            rank_text,
            fontsize=self.TITLE_FONT_SIZE * 1.3,
            color=self.RANK_COLOR,
            font=self.font_path,
            stroke_color='black',
            stroke_width=2
        )
        rank_clip = rank_clip.set_position((50, 50))
        rank_clip = rank_clip.set_duration(duration)
        clips.append(rank_clip)
        
        # ブランド名
        brand_clip = TextClip(
            product['brand'],
            fontsize=self.BRAND_FONT_SIZE,
            color='lightgray',
            font=self.font_path,
            method='caption',
            align='center',
            size=(self.VIDEO_WIDTH * 0.8, None)
        )
        brand_pos_y = self.VIDEO_HEIGHT // 2 + 50
        brand_clip = brand_clip.set_position(('center', brand_pos_y))
        brand_clip = brand_clip.set_duration(duration)
        clips.append(brand_clip)
        
        # 商品名
        name_clip = TextClip(
            product['name'],
            fontsize=self.TITLE_FONT_SIZE,
            color=self.TITLE_COLOR,
            font=self.font_path,
            method='caption',
            align='center',
            size=(self.VIDEO_WIDTH * 0.8, None)
        )
        name_pos_y = brand_pos_y + brand_clip.h + 30
        name_clip = name_clip.set_position(('center', name_pos_y))
        name_clip = name_clip.set_duration(duration)
        clips.append(name_clip)
        
        # レビュー
        if 'reviews' in product and product['reviews']:
            review_pos_y = name_pos_y + name_clip.h + 80
            
            for i, review in enumerate(product['reviews'][:3]):
                if not review:
                    continue
                
                review_clip = TextClip(
                    f"「{review}」",
                    fontsize=self.REVIEW_FONT_SIZE,
                    color='white',
                    font=self.font_path,
                    method='caption',
                    align='center',
                    size=(self.VIDEO_WIDTH * 0.8, None)
                )
                review_clip = review_clip.set_position(('center', review_pos_y + i * (review_clip.h + 20)))
                review_clip = review_clip.set_duration(duration)
                clips.append(review_clip)
        
        # 合成
        final_clip = CompositeVideoClip(clips)
        
        return final_clip
    
    def _create_outro_slide(
        self,
        text: str = "Thank you for watching!",
        duration: float = 3.0
    ) -> VideoClip:
        """
        エンドスライドの作成
        
        Args:
            text: テキスト
            duration: 表示時間（秒）
        
        Returns:
            エンドスライド
        """
        # 背景
        bg = ColorClip(
            size=(self.VIDEO_WIDTH, self.VIDEO_HEIGHT),
            color=self.BG_COLOR,
            duration=duration
        )
        
        # テキスト
        text_clip = TextClip(
            text,
            fontsize=self.TITLE_FONT_SIZE,
            color=self.TITLE_COLOR,
            font=self.font_path,
            method='caption',
            align='center',
            size=(self.VIDEO_WIDTH * 0.8, None)
        )
        text_clip = text_clip.set_position(('center', self.VIDEO_HEIGHT // 2))
        text_clip = text_clip.set_duration(duration)
        
        # AI生成コンテンツであることの表示
        ai_notice = TextClip(
            "※レビューはAIによる生成コンテンツです",
            fontsize=self.BRAND_FONT_SIZE,
            color='gray',
            font=self.font_path
        )
        ai_notice = ai_notice.set_position(('center', self.VIDEO_HEIGHT - 200))
        ai_notice = ai_notice.set_duration(duration)
        
        # 合成
        final_clip = CompositeVideoClip([bg, text_clip, ai_notice])
        
        return final_clip
    
    def _get_bgm(self) -> Optional[str]:
        """BGMの取得"""
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
            font = ImageFont.truetype(self.font_path, 60) if self.font_path else ImageFont.load_default()
        except Exception:
            font = ImageFont.load_default()
        
        # テキスト描画
        text_width, text_height = draw.textsize(text, font=font) if hasattr(draw, 'textsize') else (400, 60)
        position = ((width - text_width) // 2, (height - text_height) // 2)
        draw.text(position, text, fill=(100, 100, 100), font=font)
        
        # 保存
        img.save(path)
    
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
            作成した動画のパス
        """
        logger.info(f"動画作成開始: {title}")
        
        # 出力ファイル名が指定されていない場合は生成
        if not output_filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_title = ''.join(c if c.isalnum() else '_' for c in title)
            output_filename = f"{safe_title}_{timestamp}.mp4"
        
        output_path = os.path.join(self.output_dir, output_filename)
        
        # スライド作成
        slides = []
        
        # タイトルスライド
        title_slide = self._create_title_slide(title, subtitle, duration=3.0)
        slides.append(title_slide)
        
        # 製品スライド
        for product in products:
            rank = product.get('new_rank', 0)
            if rank > 0:
                slide = self._create_product_slide(product, rank, duration=self.SLIDE_DURATION)
                slides.append(slide)
        
        # エンドスライド
        outro_slide = self._create_outro_slide(
            text=f"今回のランキングは以上です！",
            duration=3.0
        )
        slides.append(outro_slide)
        
        # スライドを連結して動画作成
        final_video = concatenate_videoclips(slides)
        
        # BGM追加
        bgm_path = self._get_bgm()
        if bgm_path and os.path.exists(bgm_path):
            try:
                bgm = AudioFileClip(bgm_path)
                
                # 動画の長さに合わせてループ
                if bgm.duration < final_video.duration:
                    num_loops = int(final_video.duration / bgm.duration) + 1
                    bgm = concatenate_audioclips([bgm] * num_loops)
                
                # 動画の長さに合わせてカット
                bgm = bgm.subclip(0, final_video.duration)
                
                # ボリューム調整
                bgm = bgm.volumex(0.3)
                
                # 音声合成
                final_video = final_video.set_audio(bgm)
                
            except Exception as e:
                logger.error(f"BGM設定エラー: {str(e)}")
        
        # 動画書き出し
        try:
            final_video.write_videofile(
                output_path,
                fps=30,
                codec='libx264',
                audio_codec='aac',
                threads=4,
                preset='medium'
            )
            logger.info(f"動画作成完了: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"動画書き出しエラー: {str(e)}")
            raise
        
        finally:
            # 一時ファイル削除などのクリーンアップ処理
            pass
