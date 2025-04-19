"""
@file: voice_utils.py
@desc: VOICEVOXを使用した音声合成ユーティリティ
"""

import os
import subprocess
import logging
import json
import random
import requests
import wave
import re

# ログ設定
logger = logging.getLogger(__name__)

# 音声合成エンジンのパス設定
VOICEVOX_ENGINE_URL = os.getenv("VOICEVOX_ENGINE_URL", "http://localhost:50021")  # VOICEVOXのAPIエンドポイント

# 音声キャラクター用ID設定
VOICEVOX_CHARS = [
    {"id": 8, "name": "春日部つむぎ"},  # 春日部つむぎのID
    {"id": 29, "name": "No.7"},        # No.7のID
    {"id": 13, "name": "青山龍星"},      # 青山龍星のID
    {"id": 11,"name": "玄野武宏"}    # 玄野武宏のID
]

# 音声合成エンジンの動作チェック
def check_voicevox_available():
    """VOICEVOXエンジンが利用可能かチェック"""
    try:
        response = requests.get(f"{VOICEVOX_ENGINE_URL}/version")
        return response.status_code == 200
    except:
        logger.warning("VOICEVOXエンジンに接続できません。音声なしで続行します。")
        return False

def get_audio_duration(audio_file_path: str) -> float:
    """
    オーディオファイルの再生時間（秒）を取得する
    
    Parameters:
    audio_file_path (str): オーディオファイルのパス
    
    Returns:
    float: オーディオの長さ（秒）、エラー時は0.0
    """
    try:
        # FFmpegを使用して長さを取得
        cmd = [
            "ffprobe", 
            "-v", "error", 
            "-show_entries", "format=duration", 
            "-of", "default=noprint_wrappers=1:nokey=1", 
            audio_file_path
        ]
        
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        if result.returncode == 0:
            duration = float(result.stdout.strip())
            return duration
        
        # FFmpegが失敗した場合、WAVファイルなら直接読み込む
        if audio_file_path.lower().endswith('.wav'):
            with wave.open(audio_file_path, 'rb') as wf:
                # フレーム数/サンプルレートで秒数を計算
                duration = wf.getnframes() / wf.getframerate()
                return duration
                
        logger.warning(f"オーディオファイルの長さを取得できませんでした: {audio_file_path}")
        return 0.0
        
    except Exception as e:
        logger.error(f"オーディオ長さ取得エラー: {e}")
        return 0.0

def generate_narration(text: str, output_path: str, voice_type: str = "default") -> bool:
    """
    テキストから音声ナレーションを生成する
    
    Parameters:
    text (str): 音声化するテキスト
    output_path (str): 音声ファイルの出力パス
    voice_type (str): 音声タイプ (default, male, female, random, etc.)
    
    Returns:
    bool: 生成が成功したかどうか
    """
    try:
        # テキストの前処理（長すぎる場合は分割など）
        processed_text = preprocess_text_for_speech(text)
        
        # 出力ディレクトリが存在することを確認
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # VOICEVOXが利用可能かチェック
        if check_voicevox_available():
            return generate_with_voicevox(processed_text, output_path, voice_type)
        else:
            # 音声合成エンジンがない場合は無音ファイルを作成
            logger.warning("音声合成を行わず、無音ファイルを作成します")
            return create_silent_audio(output_path, 5.0)  # 5秒間の無音
    except Exception as e:
        logger.error(f"音声生成エラー: {e}")
        return create_silent_audio(output_path, 5.0)  # エラー時も無音ファイルを作成

def create_silent_audio(output_path: str, duration: float = 1.0) -> bool:
    """
    無音のWAVファイルを作成（改良版）
    
    Parameters:
    output_path (str): 出力パス
    duration (float): 長さ（秒）
    
    Returns:
    bool: 成功したかどうか
    """
    try:
        # 出力ディレクトリが存在することを確認
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # ffmpegコマンドを構築（エラー出力の詳細な記録を追加）
        cmd = [
            "ffmpeg",
            "-y",
            "-f", "lavfi",
            "-i", f"anullsrc=r=44100:cl=stereo",
            "-t", str(duration),
            "-c:a", "pcm_s16le",  # 明示的にPCM形式を指定
            output_path
        ]
        
        # コマンドをログに記録
        logger.info(f"無音ファイル作成コマンド: {' '.join(cmd)}")
        
        # サブプロセスを実行
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # 結果の確認
        if process.returncode != 0:
            logger.error(f"無音ファイル作成エラー: {process.stderr}")
            # 代替方法を試みる
            try:
                # pythonで直接無音のwavファイルを生成
                import wave
                import struct
                
                frames = int(44100 * duration)
                with wave.open(output_path, 'wb') as wf:
                    wf.setnchannels(2)  # ステレオ
                    wf.setsampwidth(2)  # 16-bit
                    wf.setframerate(44100)
                    wf.setnframes(frames)
                    wf.writeframes(struct.pack('<' + 'h' * frames * 2, *([0] * frames * 2)))
                
                logger.info(f"Python wave モジュールで無音ファイルを作成: {output_path}")
                return os.path.exists(output_path)
            except Exception as e:
                logger.error(f"代替無音ファイル作成エラー: {e}")
                return False
        
        # 作成されたファイルの存在確認
        if os.path.exists(output_path):
            # ファイルサイズの確認
            file_size = os.path.getsize(output_path)
            logger.info(f"無音ファイル作成成功: {output_path}, サイズ={file_size}バイト")
            
            # ファイルが適切なサイズであることを確認
            if file_size < 100:  # 極端に小さなファイル
                logger.warning(f"作成された無音ファイルのサイズが小さすぎます: {file_size}バイト")
                return False
            
            return True
        else:
            logger.error(f"無音ファイルが作成されませんでした: {output_path}")
            return False
            
    except Exception as e:
        logger.error(f"無音ファイル作成エラー: {e}")
        return False

def preprocess_text_for_speech(text: str) -> str:
    """
    音声合成に適したテキスト形式に前処理する
    
    Parameters:
    text (str): 入力テキスト
    
    Returns:
    str: 前処理されたテキスト
    """
    # テキストから不要な記号を除去
    text = text.replace('「', '').replace('」', '')
    text = text.replace('『', '').replace('』', '')
    
    # カテゴリタグ（<xxx>）を削除
    text = re.sub(r'<[^>]+>', '', text)
    
    # URLや特殊記号を適切に処理
    text = re.sub(r'https?://\S+', 'URL', text)
    
    # 長いテキストの場合は適切に分割
    max_length = 500  # 一般的な音声合成エンジンの制限値
    if len(text) > max_length:
        # 長いテキストは文単位で分割
        sentences = text.split('。')
        short_text = ""
        for sentence in sentences:
            if len(short_text) + len(sentence) <= max_length:
                short_text += sentence + "。"
            else:
                break
        return short_text
        
    return text

def generate_with_voicevox(text: str, output_path: str, voice_type: str) -> bool:
    """VOICEVOX を使用して音声を生成する（ランダムキャラクター選択版）"""
    try:
        # 入力テキストが空でないか確認
        if not text or text.strip() == "":
            logger.warning("音声合成するテキストが空です")
            return create_silent_audio(output_path, 1.0)  # 1秒の無音を生成
            
        # voice_typeに基づいてキャラクターを選択
        if voice_type == "random" or voice_type == "default":
            char_info = random.choice(VOICEVOX_CHARS)
        else:
            # voice_typeに応じた選択ロジックを追加（必要に応じて）
            # 例: "male"なら男性キャラ、"female"なら女性キャラ
            char_info = random.choice(VOICEVOX_CHARS)
            
        character_id = char_info["id"]
        character_name = char_info["name"]
        logger.info(f"選択したVOICEVOXキャラクター: {character_name} (ID: {character_id})")
        
        # テキストから音声合成用クエリを生成
        try:
            # テキストを適切な長さに制限
            if len(text) > 1000:
                text = text[:997] + "..."
            
            response = requests.post(
                f"{VOICEVOX_ENGINE_URL}/audio_query",
                params={"text": text, "speaker": character_id},
                timeout=30  # タイムアウトを増やす
            )
            
            if response.status_code != 200:
                logger.error(f"VOICEVOX クエリ生成失敗: {response.text}")
                return False
                
            query_json = response.json()
            query_json["volumeScale"] = 2.8  # 音量調整
            
            # 音声合成リクエスト
            response = requests.post(
                f"{VOICEVOX_ENGINE_URL}/synthesis",
                params={"speaker": character_id},
                data=json.dumps(query_json),
                headers={"Content-Type": "application/json"},
                timeout=60  # 長いテキストの場合は時間がかかるため、タイムアウトを増やす
            )
            
            if response.status_code != 200:
                logger.error(f"VOICEVOX 音声合成失敗: {response.text}")
                return False
                
            # 音声ファイルを保存
            with open(output_path, "wb") as f:
                f.write(response.content)
            
            logger.info(f"VOICEVOX 音声生成成功: {output_path}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"VOICEVOX APIリクエストエラー: {e}")
            return create_silent_audio(output_path, 5.0)  # エラー時は無音ファイル
            
    except Exception as e:
        logger.error(f"VOICEVOX 音声生成エラー: {e}")
        return create_silent_audio(output_path, 5.0)  # エラー時は無音ファイル

def merge_audio_files(audio_files: list, output_path: str) -> bool:
    """
    複数の音声ファイルを1つに結合する
    
    Parameters:
    audio_files (list): 結合する音声ファイルのリスト
    output_path (str): 出力先のパス
    
    Returns:
    bool: 結合が成功したかどうか
    """
    try:
        if not audio_files:
            return False
            
        # 音声ファイルが1つだけなら、そのままコピー
        if len(audio_files) == 1:
            import shutil
            shutil.copy(audio_files[0], output_path)
            return True
            
        # FFmpegを使用して音声ファイルを連結
        concat_file = os.path.join(os.path.dirname(output_path), "concat_list.txt")
        
        with open(concat_file, "w") as f:
            for audio_file in audio_files:
                f.write(f"file '{audio_file}'\n")
                
        cmd = [
            "ffmpeg",
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            output_path
        ]
        
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # 一時ファイルを削除
        if os.path.exists(concat_file):
            os.remove(concat_file)
            
        return process.returncode == 0
        
    except Exception as e:
        logger.error(f"音声ファイル結合エラー: {e}")
        return False