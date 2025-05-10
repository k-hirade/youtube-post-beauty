"""
@file: video_maker_chinese.py
@desc: FFmpegを直接使用して縦型ショート動画を作成するモジュール (中国語翻訳付き)
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
import time

from openai import OpenAI

# 音声関連のユーティリティをインポート
from video.voice_utils import generate_narration, get_audio_duration, create_silent_audio, merge_audio_files
from video.video_maker import VideoMaker

# ロガー設定
logger = logging.getLogger(__name__)

class ChineseVideoMaker(VideoMaker):
    """FFmpegを使用して縦型商品紹介動画を作成するクラス（中国語翻訳付き）"""
    
    # 字幕関連の設定
    SUBTITLE_FONT_SIZE = 38
    SUBTITLE_COLOR = (255, 255, 255)  # 白色
    SUBTITLE_STROKE_COLOR = (0, 0, 0)  # 黒色
    SUBTITLE_STROKE_WIDTH = 2
    SUBTITLE_BG_COLOR = (0, 0, 0, 180)  # 半透明の黒
    SUBTITLE_PADDING = 10  # 字幕の上下左右のパディング
    SUBTITLE_POSITION_Y = 0.8  # 画面の下から20%の位置
    
    def __init__(
        self,
        output_dir: str = 'data/output',
        temp_dir: str = 'data/temp',
        font_path: Optional[str] = None,
        bgm_dir: str = 'data/bgm',
        api_key: Optional[str] = None,
        model: str = "gpt-4o"
    ):
        """
        初期化
        
        Args:
            output_dir: 出力ディレクトリ
            temp_dir: 一時ファイルディレクトリ
            font_path: フォントファイルのパス
            bgm_dir: BGM用音声ファイルディレクトリ
            api_key: OpenAI APIキー
            model: 使用するモデル名
        """
        # 親クラスの初期化
        super().__init__(output_dir, temp_dir, font_path, bgm_dir)
        
        # 翻訳用のAPIクライアント設定
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            logger.warning("OpenAI APIキーが設定されていません。中国語翻訳機能は無効です。")
        self.model = model
        
        try:
            self.client = OpenAI(api_key=self.api_key)
            logger.info("OpenAI APIクライアント初期化完了")
        except Exception as e:
            logger.error(f"OpenAI APIクライアント初期化エラー: {str(e)}")
            self.client = None
        
        # 中国語フォントの設定
        import platform
        system = platform.system()
        
        if system == 'Darwin':  # macOS
            self.chinese_font_path = '/Library/Fonts/Hiragino Sans GB.ttc'
            self.noto_sans_sc_path = '/Library/Fonts/NotoSansSC-Regular.otf'
            self.noto_sans_sc_bold_path = '/Library/Fonts/NotoSansSC-Bold.otf'
        else:  # Linux
            self.chinese_font_path = '/usr/share/fonts/opentype/noto/NotoSansSC-Regular.otf'
            self.noto_sans_sc_path = '/usr/share/fonts/opentype/noto/NotoSansSC-Regular.otf'
            self.noto_sans_sc_bold_path = '/usr/share/fonts/opentype/noto/NotoSansSC-Bold.otf'
        
        # 中国語フォントが存在するか確認
        if not os.path.exists(self.chinese_font_path):
            logger.warning(f"指定した中国語フォント({self.chinese_font_path})が見つかりません。")
            # 代替フォントを探す
            if os.path.exists(self.noto_sans_sc_path):
                self.chinese_font_path = self.noto_sans_sc_path
                logger.info(f"代替中国語フォントを使用します: {self.noto_sans_sc_path}")
            else:
                logger.warning("中国語フォントが見つかりません。テキストの表示が崩れる可能性があります。")
                self.chinese_font_path = self.font_path
    
    def get_chinese_font(self, size: int) -> ImageFont.FreeTypeFont:
        """
        中国語用のフォントを取得
        
        Args:
            size: フォントサイズ
            
        Returns:
            ImageFont.FreeTypeFont: フォントオブジェクト
        """
        try:
            if os.path.exists(self.chinese_font_path):
                font = ImageFont.truetype(self.chinese_font_path, size)
                return font
            elif os.path.exists(self.noto_sans_sc_path):
                font = ImageFont.truetype(self.noto_sans_sc_path, size)
                return font
            else:
                # 適当な代替フォントを使用
                return self.get_font(size)
        except Exception as e:
            logger.error(f"中国語フォント読み込みエラー: {str(e)}")
            return self.get_font(size)
    
    def translate_to_chinese(self, text: str) -> str:
        """
        テキストを中国語に翻訳
        
        Args:
            text: 翻訳するテキスト
            
        Returns:
            str: 翻訳されたテキスト
        """
        if not self.client:
            logger.warning("OpenAI APIクライアントが初期化されていません。翻訳をスキップします。")
            return text
        
        try:
            prompt = f"""
            以下の日本語テキストを自然な中国語に翻訳してください。
            余計な情報は出力せず、翻訳文だけを出力してください。

            日本語テキスト: {text}
            """
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
            )
            
            translated_text = response.choices[0].message.content.strip()
            logger.info(f"中国語翻訳: {text} -> {translated_text}")
            return translated_text
            
        except Exception as e:
            logger.error(f"翻訳エラー: {str(e)}")
            return text
    
    def create_subtitle_image(
        self,
        text: str,
        width: int,
        height: int,
        y_position_ratio: float = 0.8
    ) -> Image.Image:
        """
        字幕画像を作成
        
        Args:
            text: 字幕テキスト
            width: 画像の幅
            height: 画像の高さ
            y_position_ratio: 画面の下からの位置比率（0.0～1.0）
            
        Returns:
            Image.Image: 字幕画像
        """
        # 透明な画像を作成
        subtitle_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(subtitle_img)
        
        # 中国語フォント
        font = self.get_chinese_font(self.SUBTITLE_FONT_SIZE)
        
        # テキスト計測
        try:
            text_width = self.calculate_text_width(text, font, draw)
        except:
            # 古いPILバージョン用
            text_width, _ = draw.textsize(text, font=font)
        
        # テキストが長すぎる場合は折り返す（単純な処理）
        max_width = width * 0.9  # 画面幅の90%
        text_lines = []
        
        if text_width > max_width:
            # 簡易的な折り返し処理（文字数で半分に分割）
            half = len(text) // 2
            # 句読点で区切れる位置を探す
            separator_positions = []
            for i, char in enumerate(text):
                if char in "，。！？,.!?,;；":
                    separator_positions.append(i)
            
            # 中間点に最も近い区切り位置を見つける
            best_pos = half
            if separator_positions:
                best_pos = min(separator_positions, key=lambda x: abs(x - half))
            
            text_lines.append(text[:best_pos+1])
            text_lines.append(text[best_pos+1:])
        else:
            text_lines.append(text)
        
        # 字幕の背景を描画
        padding = self.SUBTITLE_PADDING
        line_height = self.SUBTITLE_FONT_SIZE + padding
        
        # 字幕の位置（画面下部）
        base_y = int(height * y_position_ratio)
        
        for i, line in enumerate(text_lines):
            # テキスト幅を再計算
            try:
                line_width = self.calculate_text_width(line, font, draw)
            except:
                line_width, _ = draw.textsize(line, font=font)
            
            text_x = (width - line_width) // 2
            text_y = base_y - (len(text_lines) - i) * line_height
            
            # 背景ボックスを描画
            bg_x0 = text_x - padding
            bg_y0 = text_y - padding
            bg_x1 = text_x + line_width + padding
            bg_y1 = text_y + line_height
            
            # 半透明の背景
            draw.rectangle(
                [(bg_x0, bg_y0), (bg_x1, bg_y1)],
                fill=self.SUBTITLE_BG_COLOR
            )
            
            # 文字の縁取り効果（アウトライン）
            for dx in range(-self.SUBTITLE_STROKE_WIDTH, self.SUBTITLE_STROKE_WIDTH + 1):
                for dy in range(-self.SUBTITLE_STROKE_WIDTH, self.SUBTITLE_STROKE_WIDTH + 1):
                    if dx*dx + dy*dy <= self.SUBTITLE_STROKE_WIDTH*self.SUBTITLE_STROKE_WIDTH:
                        draw.text(
                            (text_x + dx, text_y + dy),
                            line,
                            font=font,
                            fill=self.SUBTITLE_STROKE_COLOR
                        )
            
            # メインテキストを描画
            draw.text(
                (text_x, text_y),
                line,
                font=font,
                fill=self.SUBTITLE_COLOR
            )
        
        return subtitle_img
    
    def add_chinese_subtitles(
        self,
        video_path: str,
        output_path: str,
        subtitle_segments: List[Dict[str, Any]]
    ) -> bool:
        """
        動画に中国語字幕を追加
        
        Args:
            video_path: 元の動画パス
            output_path: 出力動画パス
            subtitle_segments: 字幕セグメントのリスト[{
                'text': 字幕テキスト,
                'start_time': 開始時間（秒）,
                'end_time': 終了時間（秒）
            }]
            
        Returns:
            bool: 成功したかどうか
        """
        try:
            # 元の動画から情報を取得
            probe_cmd = [
                "ffprobe",
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,r_frame_rate",
                "-of", "json",
                video_path
            ]
            
            result = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
            video_info = json.loads(result.stdout)
            
            # 動画の幅、高さ、フレームレートを取得
            stream = video_info['streams'][0]
            width = stream['width']
            height = stream['height']
            fps_parts = stream['r_frame_rate'].split('/')
            fps = int(fps_parts[0]) / int(fps_parts[1])
            
            # 字幕用の一時ディレクトリを作成
            with tempfile.TemporaryDirectory() as temp_dir:
                # 各セグメントに字幕を追加
                subtitle_filter = ""
                subtitle_inputs = []
                
                for i, segment in enumerate(subtitle_segments):
                    # 中国語字幕画像を作成
                    subtitle_img = self.create_subtitle_image(
                        segment['text'],
                        width,
                        height,
                        self.SUBTITLE_POSITION_Y
                    )
                    
                    # 字幕画像を保存
                    subtitle_path = os.path.join(temp_dir, f"subtitle_{i}.png")
                    subtitle_img.save(subtitle_path)
                    
                    # 字幕フィルタに追加
                    start_time = segment['start_time']
                    end_time = segment['end_time']
                    subtitle_inputs.append(f"-i {subtitle_path}")
                    
                    # オーバーレイフィルタを追加
                    subtitle_filter += f"[{i+1}:v]format=rgba,setpts=PTS-STARTPTS+(({start_time})/TB)[s{i}];"
                    subtitle_filter += f"[tmp{i}][s{i}]overlay=0:0:enable='between(t,{start_time},{end_time})'[tmp{i+1}];"
                
                # FFmpegコマンドの構築
                if subtitle_inputs:
                    # 初期ストリーム設定
                    subtitle_filter = f"[0:v]setpts=PTS-STARTPTS[tmp0];" + subtitle_filter
                    
                    # 最後のストリームの処理
                    last_idx = len(subtitle_segments)
                    subtitle_filter = subtitle_filter.replace(f"[tmp{last_idx}]", "[v]")
                    
                    # コマンド構築
                    cmd = [
                        "ffmpeg", "-y",
                        "-i", video_path
                    ]
                    
                    # 字幕入力の追加
                    for input_path in subtitle_inputs:
                        cmd.extend(input_path.split())
                    
                    # フィルタ設定
                    cmd.extend([
                        "-filter_complex", subtitle_filter,
                        "-map", "[v]",
                        "-map", "0:a",
                        "-c:v", "libx264",
                        "-c:a", "copy",
                        "-shortest",
                        output_path
                    ])
                    
                    # コマンド実行
                    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    logger.info(f"中国語字幕付き動画の作成に成功: {output_path}")
                    return True
                else:
                    logger.warning("字幕セグメントがありません。元の動画をコピーします。")
                    shutil.copy(video_path, output_path)
                    return True
                
        except subprocess.CalledProcessError as e:
            logger.error(f"字幕追加中にFFmpegエラーが発生: {e.stderr}")
            return False
        except Exception as e:
            logger.error(f"字幕追加中にエラーが発生: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def translate_product_reviews(self, product: Dict[str, Any]) -> Dict[str, Any]:
        """
        製品レビューを中国語に翻訳
        
        Args:
            product: 製品情報辞書
            
        Returns:
            Dict[str, Any]: 翻訳されたレビューを含む製品情報辞書のコピー
        """
        translated_product = product.copy()
        
        if 'reviews' in product and product['reviews']:
            translated_reviews = []
            for review in product['reviews']:
                translated_review = self.translate_to_chinese(review)
                translated_reviews.append(translated_review)
                # API呼び出しの間隔を空ける
                time.sleep(0.5)
            
            translated_product['chinese_reviews'] = translated_reviews
        else:
            translated_product['chinese_reviews'] = []
        
        return translated_product
    
    def _prepare_intro_translations(self, channel: str, genre: str) -> Dict[str, str]:
        """
        イントロテキストの中国語翻訳を準備
        
        Args:
            channel: チャンネル名
            genre: ジャンル名
            
        Returns:
            Dict[str, str]: 中国語翻訳のディクショナリ
        """
        # 翻訳が必要な日本語テキスト
        main_intro_text = f"一度はマジで使ってみてほしい{channel}で買える神{genre}挙げてく。"
        bookmark_text = "これはブックマーク必須やで"
        
        # 中国語に翻訳
        chinese_main_intro = self.translate_to_chinese(main_intro_text)
        chinese_bookmark = self.translate_to_chinese(bookmark_text)
        
        # 翻訳結果を格納
        return {
            'main_intro': chinese_main_intro,
            'bookmark': chinese_bookmark
        }
    
    def _prepare_product_translations(
        self, 
        product: Dict[str, Any], 
        rank: int
    ) -> Dict[str, str]:
        """
        製品情報の中国語翻訳を準備
        
        Args:
            product: 製品情報
            rank: 順位
            
        Returns:
            Dict[str, str]: 中国語翻訳のディクショナリ
        """
        brand_name = product.get('brand', '')
        product_name = product.get('name', '')
        
        # ナレーション用テキストを準備
        product_name_for_narration = self._prepare_product_name_for_narration(product_name, brand_name)
        product_intro_text = f"{rank}位、{brand_name}の{product_name_for_narration}"
        
        # 中国語に翻訳
        chinese_intro = self.translate_to_chinese(product_intro_text)
        
        return {
            'product_intro': chinese_intro
        }
    
    def create_video_with_chinese(
            self,
            products: List[Dict[str, Any]],
            title: str,
            channel: str,
            output_filename: Optional[str] = None,
            chinese_output_filename: Optional[str] = None
        ) -> Tuple[str, str]:
        """
        製品リストからショート動画を作成（日本語+中国語翻訳）
        
        Args:
            products: 製品情報リスト
            title: 動画タイトル
            channel: チャンネル名
            output_filename: 出力ファイル名（日本語）
            chinese_output_filename: 出力ファイル名（中国語）
        
        Returns:
            Tuple[str, str]: 作成した日本語動画と中国語動画のパス
        """
        logger.info(f"中国語字幕付き動画作成開始: {title}")
        
        # まず、通常の日本語動画を作成
        output_path = super().create_video(
            products=products,
            title=title,
            channel=channel,
            output_filename=output_filename
        )
        
        # 中国語翻訳付き動画のファイルパス
        if not chinese_output_filename:
            filename, ext = os.path.splitext(output_filename)
            chinese_output_filename = f"{filename}_chinese{ext}"
        chinese_output_path = os.path.join(self.output_dir, chinese_output_filename)
        
        # 中国語動画の情報を格納する一時ディレクトリ
        with tempfile.TemporaryDirectory() as temp_dir:
            # 翻訳情報を格納するリスト
            subtitle_segments = []
            
            # 現在のセグメントの開始時間（秒）
            current_time = 0.0
            
            # 1. イントロテキストを翻訳
            channel_intro = title.split('で買える')[0] if 'で買える' in title else ""
            genre = title.split('で買える')[-1].replace('ランキング', '').strip() if 'で買える' in title else ""
            intro_translations = self._prepare_intro_translations(channel_intro, genre)
            
            # イントロ音声の長さを取得
            intro_audio_path = os.path.join(temp_dir, "intro_audio.wav")
            intro_title = f"一度はマジで使ってみてほしい{channel_intro}で買える神{genre}挙げてく。これはブックマーク必須やで"
            generate_narration(intro_title, intro_audio_path, "random")
            
            if os.path.exists(intro_audio_path) and os.path.getsize(intro_audio_path) > 100:
                # 音声ファイルの長さを取得
                audio_duration = get_audio_duration(intro_audio_path)
                
                # 音声分析（簡易的な方法として、全体の長さから推定）
                main_part_duration = audio_duration * 0.7  # メインパートは全体の70%と推定
                bookmark_part_duration = audio_duration - main_part_duration  # 残りの30%をブックマークパート
                
                # メインイントロの字幕
                subtitle_segments.append({
                    'text': intro_translations['main_intro'],
                    'start_time': current_time,
                    'end_time': current_time + main_part_duration
                })
                current_time += main_part_duration
                
                # ブックマーク部分の字幕
                subtitle_segments.append({
                    'text': intro_translations['bookmark'],
                    'start_time': current_time,
                    'end_time': current_time + bookmark_part_duration
                })
                current_time += bookmark_part_duration
            else:
                # 音声がない場合はデフォルト値
                subtitle_segments.append({
                    'text': intro_translations['main_intro'],
                    'start_time': current_time,
                    'end_time': current_time + 2.0
                })
                current_time += 2.0
                
                subtitle_segments.append({
                    'text': intro_translations['bookmark'],
                    'start_time': current_time,
                    'end_time': current_time + 2.0
                })
                current_time += 2.0
            
            # 2. 製品リストをシャッフルして順位を割り当て
            shuffled_products = products[:7]  # 最大7製品
            total_products = len(shuffled_products)
            
            # 3. 各製品のナレーションの翻訳と時間の計算
            for i, product in enumerate(shuffled_products):
                rank = total_products - i
                product['new_rank'] = rank
                
                # 製品紹介のナレーション翻訳
                product_translations = self._prepare_product_translations(product, rank)
                
                # 製品紹介ナレーション音声を生成して長さを取得
                product_audio_path = os.path.join(temp_dir, f"product_{rank}_audio.wav")
                brand_name = product.get("brand", "")
                product_name_for_narration = self._prepare_product_name_for_narration(product.get('name'), brand_name)
                product_intro_text = f"{rank}位、{brand_name}の{product_name_for_narration}"
                
                generate_narration(product_intro_text, product_audio_path, "random")
                
                if os.path.exists(product_audio_path) and os.path.getsize(product_audio_path) > 100:
                    # 音声の長さを取得
                    audio_duration = get_audio_duration(product_audio_path)
                    display_duration = max(audio_duration + 0.2, 1.5)  # 少し余裕を持たせる
                else:
                    # デフォルト値
                    display_duration = 3.0
                
                # 製品紹介の字幕
                subtitle_segments.append({
                    'text': product_translations['product_intro'],
                    'start_time': current_time,
                    'end_time': current_time + display_duration
                })
                current_time += display_duration
                
                # レビューの翻訳と字幕
                if 'reviews' in product and product['reviews']:
                    reviews = product['reviews']
                    
                    for j, review in enumerate(reviews[:3]):  # 最大3つのレビュー
                        if not review:
                            continue
                        
                        # レビューを中国語に翻訳
                        chinese_review = self.translate_to_chinese(review)
                        
                        # レビュー音声の長さを取得
                        review_audio_path = os.path.join(temp_dir, f"product_{rank}_review_{j+1}_audio.wav")
                        generate_narration(review, review_audio_path, "random")
                        
                        if os.path.exists(review_audio_path) and os.path.getsize(review_audio_path) > 100:
                            # 音声の長さを取得
                            audio_duration = get_audio_duration(review_audio_path)
                            review_duration = max(audio_duration + 0.2, 1.5)  # 少し余裕を持たせる
                        else:
                            # デフォルト値
                            review_duration = 3.0
                        
                        # レビューの字幕
                        subtitle_segments.append({
                            'text': chinese_review,
                            'start_time': current_time,
                            'end_time': current_time + review_duration
                        })
                        current_time += review_duration
            
            # 4. 元の動画に字幕を追加
            subtitle_result = self.add_chinese_subtitles(
                video_path=output_path,
                output_path=chinese_output_path,
                subtitle_segments=subtitle_segments
            )
            
            if subtitle_result:
                logger.info(f"中国語字幕付き動画の作成に成功: {chinese_output_path}")
                return output_path, chinese_output_path
            else:
                logger.error("中国語字幕付き動画の作成に失敗しました")
                return output_path, ""