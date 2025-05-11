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
from video.voice_utils import generate_narration, get_audio_duration, create_silent_audio
from video.video_maker import VideoMaker

# ロガー設定
logger = logging.getLogger(__name__)

class ChineseVideoMaker(VideoMaker):
    """FFmpegを使用して縦型商品紹介動画を作成するクラス（中国語翻訳付き）"""
    
    # 字幕関連の設定
    SUBTITLE_FONT_SIZE = 70  # フォントサイズを少し大きく
    SUBTITLE_COLOR = (255, 255, 255)  # 白色
    SUBTITLE_POSITION_Y = 0.8  # 画面上から70%の位置に固定
    SUBTITLE_MAX_CHARS_PER_LINE = 14  # 1行あたりの最大文字数
    SUBTITLE_BG_COLOR = (0, 0, 0, 180)  # 背景色: 黒色で70%の不透明度
    
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
            # First try system-wide fonts
            self.chinese_font_path = '/Library/Fonts/MicrosoftYaHeiBold.ttf'
            self.noto_sans_sc_path = '/Library/Fonts/MicrosoftYaHeiBold.ttf'
            self.noto_sans_sc_bold_path = '/Library/Fonts/MicrosoftYaHeiBold.ttf'
            
            if not os.path.exists(self.chinese_font_path):
                home_dir = os.path.expanduser('~')
                self.chinese_font_path = os.path.join(home_dir, 'Library/Fonts/MicrosoftYaHeiBold.ttf')
                self.noto_sans_sc_path = os.path.join(home_dir, 'Library/Fonts/MicrosoftYaHeiBold.ttf')
                self.noto_sans_sc_bold_path = os.path.join(home_dir, 'Library/Fonts/MicrosoftYaHeiBold.ttf')
        else:  # Linux
            self.chinese_font_path = '/usr/share/fonts/opentype/noto/MicrosoftYaHeiBold.ttf'
            self.noto_sans_sc_path = '/usr/share/fonts/opentype/noto/MicrosoftYaHeiBold.ttf'
            self.noto_sans_sc_bold_path = '/usr/share/fonts/opentype/noto/MicrosoftYaHeiBold.ttf'
        
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

    def translate_product_name_to_chinese(self, product_info: Dict[str, Any], rank: int) -> str:
        """
        商品名と関連情報を中国語に適切に翻訳する特別なメソッド
        
        Args:
            product_info: 製品情報（名前、ブランド名などを含む辞書）
            rank: 製品ランキング
            
        Returns:
            str: 中国語に翻訳された自然な商品紹介文
        """
        if not self.client:
            logger.warning("OpenAI APIクライアントが初期化されていません。商品名翻訳をスキップします。")
            # フォールバック：通常のテキスト準備メソッドを使用
            brand_name = product_info.get('brand', '')
            product_name = product_info.get('name', '')
            product_name_for_narration = self._prepare_product_name_for_narration(product_name, brand_name)
            return f"{rank}位、{brand_name}の{product_name_for_narration}"
        
        try:
            # 関連する製品情報を収集
            brand_name = product_info.get('brand', '')
            product_name = product_info.get('name', '')
            product_type = product_info.get('genre', '')  # 製品カテゴリ（美容液、化粧水など）
            product_features = product_info.get('catch_copy', '')  # キャッチコピー
            
            # 製品の特徴を抽出
            product_name_for_narration = self._prepare_product_name_for_narration(product_name, brand_name)
            original_text = f"{rank}位、{brand_name}の{product_name_for_narration}"
            
            # 商品名翻訳用の特別なプロンプト
            prompt = f"""
            以下は日本の化粧品・美容商品のランキング紹介文です。中国語（簡体字）で自然な商品紹介に翻訳してください。
            特にブランド名と商品名は中国の消費者向けに適切かつ魅力的な表現に翻訳することが重要です。

            商品情報:
            - ランキング: {rank}位
            - ブランド名: {brand_name}
            - 商品名: {product_name_for_narration}
            - カテゴリー: {product_type}
            - キャッチコピー: {product_features}

            日本語原文: {original_text}

            指示:
            1. ブランド名は中国でも知られている場合はそのまま音訳し、「品牌」という単語は使わない
            2. 商品名は中国語での一般的な商品表現に合わせて翻訳する
            3. 「○位」は「第○名」と翻訳する
            4. 「の」は「的」または適切な中国語表現に翻訳する
            5. 全体として中国の消費者が理解しやすく、魅力的で自然な中国語表現にすること
            6. 翻訳文のみを出力すること
            """
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
            )
            
            translated_text = response.choices[0].message.content.strip()
            logger.info(f"商品名翻訳: {original_text} -> {translated_text}")
            return translated_text
                
        except Exception as e:
            logger.error(f"商品名翻訳エラー: {str(e)}")
            # エラー時は通常の翻訳メソッドにフォールバック
            brand_name = product_info.get('brand', '')
            product_name = product_info.get('name', '')
            product_name_for_narration = self._prepare_product_name_for_narration(product_name, brand_name)
            product_intro_text = f"{rank}位、{brand_name}の{product_name_for_narration}"
            return self.translate_to_chinese(product_intro_text)

    def create_video_segment_with_subtitle(
        self, 
        image_path: str, 
        audio_path: str, 
        chinese_text: str, 
        output_path: str
    ) -> bool:
        """
        字幕付きビデオセグメントを作成する - 背景なし、縁取りあり、固定位置
        
        Args:
            image_path: スライド画像のパス
            audio_path: 音声ファイルのパス
            chinese_text: 中国語字幕テキスト
            output_path: 出力ビデオパス
            
        Returns:
            bool: 成功したかどうか
        """
        try:
            # 画像の寸法を取得
            img = Image.open(image_path)
            width, height = img.size
            
            # 字幕画像を生成 - 固定位置、縁取りのみ
            subtitle_img = self.create_subtitle_image(
                chinese_text,
                width,
                height
            )
            
            # 字幕画像の保存先
            subtitle_path = os.path.join(os.path.dirname(output_path), f"subtitle_{os.path.basename(output_path)}.png")
            subtitle_img.save(subtitle_path)
            
            # 画像と字幕を合成
            composite_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            composite_img.paste(img.convert("RGBA"), (0, 0))
            composite_img.alpha_composite(subtitle_img)
            
            # 合成画像を保存
            composite_path = os.path.join(os.path.dirname(output_path), f"composite_{os.path.basename(output_path)}.png")
            composite_img.convert("RGB").save(composite_path)
            
            # FFmpegで画像と音声を結合して動画を作成
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", composite_path,
                "-i", audio_path,
                "-c:v", "libx264",
                "-tune", "stillimage",
                "-c:a", "aac",
                "-b:a", "192k",
                "-pix_fmt", "yuv420p",
                "-shortest",
                output_path
            ]
            
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # 一時ファイルを削除
            if os.path.exists(subtitle_path):
                os.remove(subtitle_path)
            if os.path.exists(composite_path):
                os.remove(composite_path)
                
            return True
        except Exception as e:
            logger.error(f"字幕付きビデオセグメント作成エラー: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def create_animation_video_segment_with_subtitle(
        self, 
        animation_video_path: str, 
        chinese_text: str, 
        output_path: str
    ) -> bool:
        """
        アニメーション動画に字幕を追加する - 背景なし、縁取りあり、固定位置
        
        Args:
            animation_video_path: アニメーション動画のパス
            chinese_text: 中国語字幕テキスト
            output_path: 出力ビデオパス
            
        Returns:
            bool: 成功したかどうか
        """
        try:
            # 動画の情報を取得
            probe_cmd = [
                "ffprobe",
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "json",
                animation_video_path
            ]
            
            result = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
            video_info = json.loads(result.stdout)
            
            width = video_info['streams'][0]['width']
            height = video_info['streams'][0]['height']
            
            # 字幕画像を生成 - 固定位置、縁取りのみ
            subtitle_img = self.create_subtitle_image(
                chinese_text,
                width,
                height
            )
            
            # 字幕画像の保存先
            subtitle_path = os.path.join(os.path.dirname(output_path), f"subtitle_{os.path.basename(output_path)}.png")
            subtitle_img.save(subtitle_path)
            
            # FFmpegのフィルタ処理で字幕をオーバーレイ
            cmd = [
                "ffmpeg", "-y",
                "-i", animation_video_path,
                "-i", subtitle_path,
                "-filter_complex",
                "[0:v][1:v]overlay=0:0:format=auto,format=yuv420p[v]",
                "-map", "[v]",
                "-map", "0:a",
                "-c:v", "libx264",
                "-c:a", "copy",
                output_path
            ]
            
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # 一時ファイルを削除
            if os.path.exists(subtitle_path):
                os.remove(subtitle_path)
                
            return True
        except Exception as e:
            logger.error(f"アニメーション字幕付きビデオセグメント作成エラー: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
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

    def wrap_chinese_text(self, text: str, font: ImageFont.FreeTypeFont, draw: ImageDraw.Draw, max_chars: int = 14) -> List[str]:
        """
        中国語テキストを適切な位置で折り返す
        
        Args:
            text: 折り返すテキスト
            font: フォント
            draw: ImageDrawオブジェクト
            max_chars: 1行の最大文字数
            
        Returns:
            List[str]: 折り返された行のリスト
        """
        # 元々のテキストが短い場合はそのまま返す
        if len(text) <= max_chars:
            return [text]
        
        # 折り返し文字（区切り文字）
        break_chars = '，。！？,.!?;；:： '
        
        lines = []
        remain = text
        
        while len(remain) > 0:
            # 残りテキストが最大文字数以下の場合、そのまま追加して終了
            if len(remain) <= max_chars:
                lines.append(remain)
                break
            
            # 最大文字数で一度切る
            line = remain[:max_chars]
            
            # 区切り文字があれば、その位置で切る
            found = False
            for i in range(len(line) - 1, -1, -1):
                if line[i] in break_chars:
                    # 区切り文字の後で切る（区切り文字は含める）
                    lines.append(line[:i + 1])
                    remain = remain[i + 1:]
                    found = True
                    break
            
            # 区切り文字がなければ、そのまま最大文字数で切る
            if not found:
                lines.append(line)
                remain = remain[max_chars:]
        
        return lines
    
    def create_subtitle_image(
        self,
        text: str,
        width: int,
        height: int,
        y_position_ratio: float = None
    ) -> Image.Image:
        """
        字幕画像を作成 - 固定サイズの背景あり（常に表示）、縁取りなし、固定位置
        テキストが1行の場合は背景の縦方向中央に配置
        
        Args:
            text: 字幕テキスト（空文字でも背景は表示）
            width: 画像の幅
            height: 画像の高さ
            y_position_ratio: 画面の下からの位置比率（指定がなければ固定値を使用）
            
        Returns:
            Image.Image: 字幕画像
        """
        # 位置が指定されていない場合はクラス変数の値を使用
        if y_position_ratio is None:
            y_position_ratio = self.SUBTITLE_POSITION_Y
            
        # 透明な画像を作成
        subtitle_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(subtitle_img)
        
        # 中国語フォント
        font = self.get_chinese_font(self.SUBTITLE_FONT_SIZE)
        
        # 行の高さと全体の高さを計算（二行分の固定高さ）
        line_height = int(self.SUBTITLE_FONT_SIZE * 1.3)  # 行間を少し広めに
        fixed_height = line_height * 2  # 二行分の高さを固定
        
        # 字幕の開始Y座標（画面の上から指定された割合の位置）
        base_y = int(height * y_position_ratio) - fixed_height // 2
        
        # 背景色の設定 - 半透明の黒色
        bg_color = self.SUBTITLE_BG_COLOR  # クラス変数から取得
        bg_padding_y = 15  # 垂直方向のパディング
        
        # 背景の描画（画面横幅いっぱい、高さは二行分）
        bg_width = width  # 画面の幅いっぱい
        bg_height = fixed_height + bg_padding_y * 2
        bg_y = base_y - bg_padding_y
        
        # 背景を描画（角丸なし、画面いっぱい）
        draw.rectangle(
            [(0, bg_y), (bg_width, bg_y + bg_height)],
            fill=bg_color
        )
        
        # テキストがある場合のみ描画
        if text:
            # テキストを最大文字数で折り返す
            text_lines = self.wrap_chinese_text(text, font, draw, self.SUBTITLE_MAX_CHARS_PER_LINE)
            
            # テキスト行数に制限（二行まで）
            if len(text_lines) > 2:
                text_lines = text_lines[:2]
            
            # 行数に応じて縦方向の位置を調整
            if len(text_lines) == 1:
                # 1行の場合は背景の中央に配置
                vertical_center = bg_y + bg_height // 2 - line_height // 2
                text_y_positions = [vertical_center]
            else:
                # 複数行の場合は通常の配置
                text_y_positions = [base_y + i * line_height for i in range(len(text_lines))]
            
            # 各行を描画
            for i, line in enumerate(text_lines):
                # テキストの幅を計算して中央揃え
                try:
                    line_width = self.calculate_text_width(line, font, draw)
                except:
                    # 古いPILバージョン用
                    line_width, _ = draw.textsize(line, font=font)
                    
                text_x = (width - line_width) // 2
                text_y = text_y_positions[i]
                
                # メインテキストを描画（縁取りなし）
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
        動画に中国語字幕を追加 - 背景なし、縁取りあり、固定位置
        
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
                    # 中国語字幕画像を作成 - 固定位置、縁取りのみ
                    subtitle_img = self.create_subtitle_image(
                        segment['text'],
                        width,
                        height
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
        # 商品名専用の特化した翻訳メソッドを使用
        chinese_intro = self.translate_product_name_to_chinese(product, rank)
        
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
        - 修正版: 字幕タイミングずれを解消するため、セグメントごとに字幕を同時適用
        
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
        
        # 中国語翻訳付き動画のファイルパス
        if not output_filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_filename = f"video_{timestamp}.mp4"
        
        if not chinese_output_filename:
            filename, ext = os.path.splitext(output_filename)
            chinese_output_filename = f"{filename}_chinese{ext}"
        
        output_path = os.path.join(self.output_dir, output_filename)
        chinese_output_path = os.path.join(self.output_dir, chinese_output_filename)

        narration_speed = 1.0
        
        # 製品リストをシャッフルして順位を割り当て
        shuffled_products = products[:5]
        total_products = len(shuffled_products)
        for i, product in enumerate(shuffled_products):
            product['new_rank'] = total_products - i 
        
        # 動画セグメントのパスリスト（日本語・中国語）
        jp_video_segments = []
        cn_video_segments = []
        
        try:
            # 一時ディレクトリを作成
            with tempfile.TemporaryDirectory() as temp_dir:
                # チャンネルとジャンルの情報を取得
                channel_intro = title.split('で買える')[0] if 'で買える' in title else ""
                genre = title.split('で買える')[-1].replace('ランキング', '').strip() if 'で買える' in title else ""
                
                # 1. イントロスライドとテキストの準備
                main_intro_text = f"一度はマジで使ってみてほしい{channel_intro}で買える神{genre}挙げてく。"
                bookmark_text = "これはブックマーク必須やで"
                intro_title = f"{main_intro_text}{bookmark_text}"
                
                # 中国語翻訳の取得
                intro_translations = self._prepare_intro_translations(channel_intro, genre)
                chinese_main_intro = intro_translations['main_intro']
                chinese_bookmark = intro_translations['bookmark']
                
                # 2. メインイントロスライド作成（「これはブックマーク必須やで」を表示しない）
                main_intro_img = self._create_main_intro_slide(channel, genre)
                main_intro_slide_path = os.path.join(temp_dir, "main_intro_slide.png")
                main_intro_img.save(main_intro_slide_path)
                
                # 3. ブックマークスライド作成（ブックマーク部分だけを強調表示）
                bookmark_intro_img = self._create_bookmark_intro_slide(channel, genre)
                bookmark_intro_slide_path = os.path.join(temp_dir, "bookmark_intro_slide.png")
                bookmark_intro_img.save(bookmark_intro_slide_path)
                
                # 4. イントロ音声生成
                intro_audio_path = os.path.join(temp_dir, "intro_audio.wav")
                intro_success = generate_narration(intro_title, intro_audio_path, "random", narration_speed)
                
                # 効果音パス
                taiko_sound_path = "data/bgm/和太鼓でドドン.mp3"
                syouhin_sound_path = "data/bgm/ニュッ3.mp3"
                
                # 5. 音声処理とセグメント作成
                if os.path.exists(intro_audio_path) and os.path.getsize(intro_audio_path) > 100:
                    # 音声分析
                    audio_duration = get_audio_duration(intro_audio_path)
                    main_part_duration = audio_duration * 0.7  # メインパートは全体の70%と推定
                    bookmark_part_duration = audio_duration - main_part_duration  # 残りの30%をブックマークパート
                    
                    # メインイントロ音声の切り出し
                    main_intro_audio_path = os.path.join(temp_dir, "main_intro_audio.wav")
                    extract_cmd = [
                        "ffmpeg", "-y",
                        "-i", intro_audio_path,
                        "-ss", "0",
                        "-t", str(main_part_duration),
                        "-c:a", "pcm_s16le",
                        main_intro_audio_path
                    ]
                    
                    subprocess.run(extract_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    
                    # 和太鼓効果音を追加
                    main_intro_with_effect_path = os.path.join(temp_dir, "main_intro_with_effect.wav")
                    if os.path.exists(taiko_sound_path):
                        mix_cmd = [
                            "ffmpeg", "-y",
                            "-i", main_intro_audio_path,
                            "-i", taiko_sound_path,
                            "-filter_complex",
                            "[1:a]adelay=0|0,volume=1.2[effect];[0:a][effect]amix=inputs=2:duration=first[aout]",
                            "-map", "[aout]",
                            "-c:a", "pcm_s16le",
                            main_intro_with_effect_path
                        ]
                        
                        subprocess.run(mix_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        main_intro_audio_path = main_intro_with_effect_path
                    
                    # メインイントロの日本語動画を作成（字幕なし）
                    main_intro_jp_path = os.path.join(temp_dir, "main_intro_jp.mp4")
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
                        "-shortest",
                        main_intro_jp_path
                    ]
                    
                    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    jp_video_segments.append(main_intro_jp_path)
                    
                    # メインイントロの中国語字幕付き動画を作成
                    main_intro_cn_path = os.path.join(temp_dir, "main_intro_cn.mp4")
                    self.create_video_segment_with_subtitle(
                        image_path=main_intro_slide_path,
                        audio_path=main_intro_audio_path,
                        chinese_text=chinese_main_intro,
                        output_path=main_intro_cn_path
                    )
                    cn_video_segments.append(main_intro_cn_path)
                    
                    # ブックマーク音声の切り出し
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
                    
                    # ブックマークの日本語動画を作成（字幕なし）
                    bookmark_jp_path = os.path.join(temp_dir, "bookmark_jp.mp4")
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
                        "-shortest",
                        bookmark_jp_path
                    ]
                    
                    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    jp_video_segments.append(bookmark_jp_path)
                    
                    # ブックマークの中国語字幕付き動画を作成
                    bookmark_cn_path = os.path.join(temp_dir, "bookmark_cn.mp4")
                    self.create_video_segment_with_subtitle(
                        image_path=bookmark_intro_slide_path,
                        audio_path=bookmark_audio_path,
                        chinese_text=chinese_bookmark,
                        output_path=bookmark_cn_path
                    )
                    cn_video_segments.append(bookmark_cn_path)
                else:
                    # 音声生成に失敗した場合、デフォルトの無音動画を作成
                    logger.warning("イントロの音声ファイルが存在しないか無効です。デフォルト動画を作成します。")
                    display_duration = 3.0
                    intro_audio_path = os.path.join(temp_dir, "silent_intro.wav")
                    create_silent_audio(intro_audio_path, display_duration)
                    
                    # 日本語イントロ動画（字幕なし）
                    intro_jp_path = os.path.join(temp_dir, "intro_jp.mp4")
                    cmd = [
                        "ffmpeg", "-y",
                        "-loop", "1",
                        "-i", main_intro_slide_path,
                        "-i", intro_audio_path,
                        "-c:v", "libx264",
                        "-tune", "stillimage",
                        "-c:a", "aac",
                        "-b:a", "192k",
                        "-pix_fmt", "yuv420p",
                        "-shortest",
                        intro_jp_path
                    ]
                    
                    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    jp_video_segments.append(intro_jp_path)
                    
                    # 中国語イントロ動画（字幕付き）
                    intro_cn_path = os.path.join(temp_dir, "intro_cn.mp4")
                    self.create_video_segment_with_subtitle(
                        image_path=main_intro_slide_path,
                        audio_path=intro_audio_path,
                        chinese_text=chinese_main_intro,
                        output_path=intro_cn_path
                    )
                    cn_video_segments.append(intro_cn_path)
                
                # 6. 各製品のセグメントを作成
                for product in shuffled_products:
                    rank = product['new_rank']
                    product_name = product['name']
                    brand_name = product.get('brand', '')
                    reviews = product.get('reviews', [])
                    
                    # 製品名とブランド名のナレーション用テキスト
                    product_name_for_narration = self._prepare_product_name_for_narration(product.get('name'), brand_name)
                    product_intro_text = f"{rank}位、{brand_name}の{product_name_for_narration}"
                    
                    # 中国語翻訳
                    product_translations = self._prepare_product_translations(product, rank)
                    chinese_product_intro = product_translations['product_intro']
                    
                    # 製品紹介ナレーション音声を生成
                    product_audio_path = os.path.join(temp_dir, f"product_{rank}_audio.wav")
                    success = generate_narration(product_intro_text, product_audio_path, "random", narration_speed)
                    
                    # 音声の存在チェック
                    if os.path.exists(product_audio_path) and os.path.getsize(product_audio_path) > 100:
                        audio_duration = get_audio_duration(product_audio_path)
                        display_duration = max(audio_duration + 0.2, 1.5)  # 余裕を持たせる
                        
                        # 効果音を追加
                        product_audio_with_effect_path = os.path.join(temp_dir, f"product_{rank}_audio_with_effect.wav")
                        if os.path.exists(syouhin_sound_path):
                            mix_cmd = [
                                "ffmpeg", "-y",
                                "-i", product_audio_path,
                                "-i", syouhin_sound_path,
                                "-filter_complex",
                                "[1:a]adelay=0|0,volume=1.0[effect];[0:a][effect]amix=inputs=2:duration=first[aout]",
                                "-map", "[aout]",
                                "-c:a", "pcm_s16le",
                                product_audio_with_effect_path
                            ]
                            
                            try:
                                subprocess.run(mix_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                                product_audio_path = product_audio_with_effect_path
                            except subprocess.CalledProcessError as e:
                                logger.error(f"製品{rank}の効果音追加に失敗: {e.stderr}")
                    else:
                        logger.warning(f"製品 {rank} の音声ファイルが存在しないか無効です。無音を使用します。")
                        display_duration = 3.0
                        product_audio_path = os.path.join(temp_dir, f"silent_{rank}.wav")
                        create_silent_audio(product_audio_path, display_duration)
                    
                    # アニメーション付き製品紹介動画の作成試行
                    product_jp_animation_path = os.path.join(temp_dir, f"product_{rank}_jp_animation.mp4")
                    animation_success = self._create_product_animation(
                        product, 
                        rank, 
                        product_jp_animation_path,
                        show_name=True,
                        animation_duration=0.05
                    )
                    
                    if animation_success:
                        # アニメーション動画と音声を結合
                        product_jp_path = os.path.join(temp_dir, f"product_{rank}_jp.mp4")
                        cmd = [
                            "ffmpeg", "-y",
                            "-i", product_jp_animation_path,
                            "-i", product_audio_path,
                            "-c:v", "libx264",
                            "-c:a", "aac",
                            "-b:a", "192k",
                            "-pix_fmt", "yuv420p",
                            "-shortest",
                            product_jp_path
                        ]
                        
                        try:
                            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                            jp_video_segments.append(product_jp_path)
                            
                            # 中国語字幕付きアニメーション動画を作成
                            product_cn_path = os.path.join(temp_dir, f"product_{rank}_cn.mp4")
                            self.create_animation_video_segment_with_subtitle(
                                animation_video_path=product_jp_path,
                                chinese_text=chinese_product_intro,
                                output_path=product_cn_path
                            )
                            cn_video_segments.append(product_cn_path)
                        except subprocess.CalledProcessError as e:
                            logger.error(f"製品 {rank} のアニメーション結合エラー: {e.stderr}")
                            # 失敗時は静的画像版にフォールバック
                            animation_success = False
                    
                    if not animation_success:
                        # 静的な製品スライドの作成
                        product_slide = self._create_product_slide(product, rank, brand_name=brand_name, show_name=True)
                        product_slide_path = os.path.join(temp_dir, f"product_{rank}_slide.png")
                        product_slide.save(product_slide_path)
                        
                        # 日本語の静的製品紹介動画
                        product_jp_path = os.path.join(temp_dir, f"product_{rank}_jp.mp4")
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
                            product_jp_path
                        ]
                        
                        try:
                            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                            jp_video_segments.append(product_jp_path)
                            
                            # 中国語字幕付き静的製品紹介動画
                            product_cn_path = os.path.join(temp_dir, f"product_{rank}_cn.mp4")
                            self.create_video_segment_with_subtitle(
                                image_path=product_slide_path,
                                audio_path=product_audio_path,
                                chinese_text=chinese_product_intro,
                                output_path=product_cn_path
                            )
                            cn_video_segments.append(product_cn_path)
                        except subprocess.CalledProcessError as e:
                            logger.error(f"製品 {rank} の静的動画生成エラー: {e.stderr}")
                            continue
                    
                    # レビューコメントがある場合、それぞれのコメントを処理
                    if reviews:
                        # レビューの中国語翻訳を取得
                        translated_product = self.translate_product_reviews(product)
                        chinese_reviews = translated_product.get('chinese_reviews', [])
                        
                        # ベーススライドの作成
                        base_slide = self._create_product_slide(product, rank, brand_name=brand_name, show_name=False)
                        base_slide_path = os.path.join(temp_dir, f"product_{rank}_base_slide.png")
                        base_slide.save(base_slide_path)
                        
                        # 表示済みコメントを保持するスライド
                        accumulated_slide = base_slide.copy()
                        
                        # コメント位置
                        positions = ["top", "middle", "bottom"]
                        
                        # 各レビューを処理
                        for i, (review, chinese_review) in enumerate(zip(reviews[:3], chinese_reviews[:3])):
                            if not review:
                                continue
                            
                            # コメント位置
                            comment_position = positions[i % len(positions)]
                            
                            # コメント用の累積スライドを更新
                            comment_font = self.get_font(
                                self.REVIEW_FONT_SIZE + 30,
                                font_path=self.YASASHISA_GOTHIC if os.path.exists(self.YASASHISA_GOTHIC) else self.noto_sans_jp_path
                            )
                            draw = ImageDraw.Draw(accumulated_slide)
                            
                            # テキスト幅を調整して折り返し
                            max_text_width = int(self.VIDEO_WIDTH * 0.7)
                            lines = self.wrap_text(review, comment_font, draw, max_text_width)
                            
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
                            
                            # バルーン描画
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
                            
                            # 累積スライドを保存
                            comment_slide_path = os.path.join(temp_dir, f"product_{rank}_comment_{i+1}.png")
                            accumulated_slide.save(comment_slide_path)
                            
                            # コメント用の音声を生成
                            comment_audio_path = os.path.join(temp_dir, f"product_{rank}_comment_{i+1}_audio.wav")
                            comment_success = generate_narration(review, comment_audio_path, "random", narration_speed)
                            
                            # 音声ファイルのチェック
                            if not os.path.exists(comment_audio_path) or os.path.getsize(comment_audio_path) < 100:
                                logger.warning(f"製品 {rank} のコメント {i+1} の音声ファイルが無効です。無音を使用します。")
                                comment_audio_path = os.path.join(temp_dir, f"silent_comment_{rank}_{i+1}.wav")
                                create_silent_audio(comment_audio_path, 3.0)
                            
                            # 日本語コメント動画の作成
                            comment_jp_path = os.path.join(temp_dir, f"product_{rank}_comment_{i+1}_jp.mp4")
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
                                "-shortest",
                                comment_jp_path
                            ]
                            
                            try:
                                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                                jp_video_segments.append(comment_jp_path)
                                
                                # 中国語字幕付きコメント動画の作成
                                comment_cn_path = os.path.join(temp_dir, f"product_{rank}_comment_{i+1}_cn.mp4")
                                self.create_video_segment_with_subtitle(
                                    image_path=comment_slide_path,
                                    audio_path=comment_audio_path,
                                    chinese_text=chinese_review,
                                    output_path=comment_cn_path
                                )
                                cn_video_segments.append(comment_cn_path)
                            except subprocess.CalledProcessError as e:
                                logger.error(f"製品 {rank} のコメント {i+1} の動画生成エラー: {e.stderr}")
                                continue
                
                # 7. 日本語動画の連結
                jp_concat_file = os.path.join(temp_dir, "jp_concat.txt")
                with open(jp_concat_file, "w") as f:
                    for segment in jp_video_segments:
                        f.write(f"file '{segment}'\n")
                
                jp_temp_video_path = os.path.join(temp_dir, "no_bgm_jp_output.mp4")
                jp_concat_cmd = [
                    "ffmpeg", "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", jp_concat_file,
                    "-c", "copy",
                    jp_temp_video_path
                ]
                
                try:
                    subprocess.run(jp_concat_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    logger.info("日本語動画セグメントの連結が完了しました")
                except subprocess.CalledProcessError as e:
                    logger.error(f"日本語動画の連結エラー: {e.stderr}")
                    raise
                
                # 8. 中国語動画の連結
                cn_concat_file = os.path.join(temp_dir, "cn_concat.txt")
                with open(cn_concat_file, "w") as f:
                    for segment in cn_video_segments:
                        f.write(f"file '{segment}'\n")
                
                cn_temp_video_path = os.path.join(temp_dir, "no_bgm_cn_output.mp4")
                cn_concat_cmd = [
                    "ffmpeg", "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", cn_concat_file,
                    "-c", "copy",
                    cn_temp_video_path
                ]
                
                try:
                    subprocess.run(cn_concat_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    logger.info("中国語動画セグメントの連結が完了しました")
                except subprocess.CalledProcessError as e:
                    logger.error(f"中国語動画の連結エラー: {e.stderr}")
                    raise
                
                # 9. 動画の長さを取得
                jp_video_duration = self._get_video_duration(jp_temp_video_path)
                cn_video_duration = self._get_video_duration(cn_temp_video_path)
                
                if jp_video_duration <= 0 or cn_video_duration <= 0:
                    logger.warning("動画の長さが取得できませんでした。デフォルト値を使用します。")
                    jp_video_duration = 60.0
                    cn_video_duration = 60.0
                
                # 10. BGMを追加
                bgm_path = os.path.join(self.bgm_dir, "しゅわしゅわハニーレモン.mp3")
                if not os.path.exists(bgm_path):
                    logger.warning(f"BGMファイルが見つかりません: {bgm_path}")
                    logger.info("BGMなしで動画を出力します。")
                    os.rename(jp_temp_video_path, output_path)
                    os.rename(cn_temp_video_path, chinese_output_path)
                else:
                    # 日本語動画にBGMを追加
                    jp_bgm_cmd = [
                        "ffmpeg", "-y",
                        "-i", jp_temp_video_path,
                        "-stream_loop", "-1",
                        "-i", bgm_path,
                        "-filter_complex",
                        f"[1:a]volume=0.25,aloop=loop=-1:size=2e+09[bgm];"
                        "[0:a][bgm]amix=inputs=2:duration=first[aout]",
                        "-map", "0:v",
                        "-map", "[aout]",
                        "-c:v", "copy",
                        "-c:a", "aac",
                        "-shortest",
                        "-t", str(jp_video_duration),
                        output_path
                    ]
                    
                    try:
                        subprocess.run(jp_bgm_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        logger.info(f"日本語動画にBGMを追加しました: {output_path}")
                    except subprocess.CalledProcessError as e:
                        logger.error(f"日本語動画へのBGM追加に失敗: {e.stderr}")
                        # エラーが発生した場合は元の動画を使用
                        os.rename(jp_temp_video_path, output_path)
                        logger.info(f"BGMなしで日本語動画を出力しました: {output_path}")
                    
                    # 中国語動画にBGMを追加
                    cn_bgm_cmd = [
                        "ffmpeg", "-y",
                        "-i", cn_temp_video_path,
                        "-stream_loop", "-1",
                        "-i", bgm_path,
                        "-filter_complex",
                        f"[1:a]volume=0.25,aloop=loop=-1:size=2e+09[bgm];"
                        "[0:a][bgm]amix=inputs=2:duration=first[aout]",
                        "-map", "0:v",
                        "-map", "[aout]",
                        "-c:v", "copy",
                        "-c:a", "aac",
                        "-shortest",
                        "-t", str(cn_video_duration),
                        chinese_output_path
                    ]
                    
                    try:
                        subprocess.run(cn_bgm_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        logger.info(f"中国語動画にBGMを追加しました: {chinese_output_path}")
                    except subprocess.CalledProcessError as e:
                        logger.error(f"中国語動画へのBGM追加に失敗: {e.stderr}")
                        # エラーが発生した場合は元の動画を使用
                        os.rename(cn_temp_video_path, chinese_output_path)
                        logger.info(f"BGMなしで中国語動画を出力しました: {chinese_output_path}")
                
                # 一時ファイルの削除
                if os.path.exists(jp_temp_video_path) and os.path.exists(output_path):
                    os.remove(jp_temp_video_path)
                if os.path.exists(cn_temp_video_path) and os.path.exists(chinese_output_path):
                    os.remove(cn_temp_video_path)
                
                logger.info(f"日本語動画作成完了: {output_path}")
                logger.info(f"中国語字幕付き動画作成完了: {chinese_output_path}")
                
                return output_path, chinese_output_path
                        
        except Exception as e:
            logger.error(f"中国語字幕付き動画作成エラー: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            # エラー時は日本語動画のみを返す
            if os.path.exists(output_path):
                return output_path, ""
            else:
                return "", ""