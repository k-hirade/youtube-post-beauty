"""
@file: twitter_poster.py
@desc: X API v2 で動画を投稿するモジュール（Free tier対応）
"""

import os
import time
import mimetypes
import logging
import math
from typing import Optional, Dict, Any

import requests
from requests_oauthlib import OAuth1
import tweepy   # v4.14 以降推奨

logger = logging.getLogger(__name__)

BASE_UPLOAD_URL = "https://api.x.com/2/media/upload"
CHUNK_SIZE = 4 * 1024 * 1024 
PROCESSING_POLL_SECS = 5 
PROCESSING_TIMEOUT = 180


class TwitterPoster:
    """動画付きポストを行うユーティリティ（/2/media/upload 版）"""
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        access_token: Optional[str] = None,
        access_token_secret: Optional[str] = None,
        bearer_token: Optional[str] = None,
    ):
        # 認証情報
        self.api_key = api_key or os.getenv("TWITTER_API_KEY")
        self.api_secret = api_secret or os.getenv("TWITTER_API_SECRET")
        self.access_token = access_token or os.getenv("TWITTER_ACCESS_TOKEN")
        self.access_token_secret = (
            access_token_secret or os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
        )
        self.bearer_token = bearer_token or os.getenv("TWITTER_BEARER_TOKEN")

        if not all(
            [self.api_key, self.api_secret, self.access_token, self.access_token_secret]
        ):
            raise RuntimeError("Twitter API の認証情報が不足しています。")

        # Tweepy v2 Client（ツイート投稿用）
        self.client = tweepy.Client(
            bearer_token=self.bearer_token,
            consumer_key=self.api_key,
            consumer_secret=self.api_secret,
            access_token=self.access_token,
            access_token_secret=self.access_token_secret,
        )

        # OAuth1 署名ヘルパ（メディアアップロード用）
        self.oauth1 = OAuth1(
            self.api_key,
            self.api_secret,
            self.access_token,
            self.access_token_secret,
            signature_type="AUTH_HEADER",
        )

        logger.info("TwitterPoster: 初期化完了")

    def post_text(self, text: str) -> Dict[str, Any]:
        """テキストのみのポスト"""
        try:
            res = self.client.create_tweet(text=text)
            tweet_id = res.data["id"]
            username = self._get_username()
            return {
                "success": True,
                "tweet_id": tweet_id,
                "url": f"https://x.com/{username}/status/{tweet_id}",
            }
        except Exception as e:
            logger.error(f"テキスト投稿失敗: {e}")
            return {"success": False, "error": str(e)}

    def post_video(
        self,
        video_path: str,
        text: str = "",
        media_category: str = "tweet_video",
    ) -> Dict[str, Any]:
        """
        動画をアップロードしてポスト
        1) /2/media/upload で動画をチャンクアップロード
        2) 完了後 /2/tweets で media_id を添付してポスト
        """
        try:
            media_id = self._upload_video(video_path, media_category)
            if not media_id:
                return {
                    "success": False,
                    "error": "media_id が取得できませんでした",
                }

            res = self.client.create_tweet(text=text, media_ids=[media_id])
            tweet_id = res.data["id"]
            username = self._get_username()

            logger.info(f"動画付きツイート投稿成功: {tweet_id}")
            return {
                "success": True,
                "tweet_id": tweet_id,
                "url": f"https://x.com/{username}/status/{tweet_id}",
            }

        except Exception as e:
            logger.exception("動画投稿で例外発生")
            return {"success": False, "error": str(e)}

    def _upload_video(self, path: str, media_category: str) -> Optional[str]:
        """
        v2 /2/media/upload を使ったチャンクアップロード。
        成功すれば media_id を返す。
        """

        file_size = os.path.getsize(path)
        mime_type, _ = mimetypes.guess_type(path)
        mime_type = mime_type or "video/mp4"

        logger.info(f"INIT: size={file_size}, mime={mime_type}")

        init_resp = requests.post(
            BASE_UPLOAD_URL,
            auth=self.oauth1,
            data={
                "command": "INIT",
                "media_type": mime_type,
                "total_bytes": file_size,
                "media_category": media_category,
            },
        )
        init_resp.raise_for_status()
        media_id = init_resp.json()["data"]["id"]

        with open(path, "rb") as f:
            seg_index = 0
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break

                files = {"media": chunk}
                data = {
                    "command": "APPEND",
                    "media_id": media_id,
                    "segment_index": seg_index,
                }
                resp = requests.post(
                    BASE_UPLOAD_URL,
                    auth=self.oauth1,
                    data=data,
                    files=files,
                )
                resp.raise_for_status()
                logger.debug(f"APPEND {seg_index}: {len(chunk)} bytes OK")
                seg_index += 1

        fin_resp = requests.post(
            BASE_UPLOAD_URL,
            auth=self.oauth1,
            data={"command": "FINALIZE", "media_id": media_id},
        )
        fin_resp.raise_for_status()
        processing_info = fin_resp.json().get("data", {}).get("processing_info")

        if processing_info:
            if not self._wait_processing(media_id, processing_info):
                raise RuntimeError("動画エンコードが失敗しました")

        logger.info(f"UPLOAD 完了 media_id={media_id}")
        return media_id

    def _wait_processing(
        self, media_id: str, processing_info: Dict[str, Any]
    ) -> bool:
        """STATUS でエンコード完了を待機"""
        start = time.time()

        state = processing_info.get("state")
        check_after = processing_info.get("check_after_secs", PROCESSING_POLL_SECS)
        time.sleep(check_after)

        while state in ("pending", "in_progress"):
            if time.time() - start > PROCESSING_TIMEOUT:
                logger.error("動画処理タイムアウト")
                return False

            status_resp = requests.get(
                BASE_UPLOAD_URL,
                auth=self.oauth1,
                params={"command": "STATUS", "media_id": media_id},
            )
            status_resp.raise_for_status()
            processing_info = status_resp.json().get("data", {}).get(
                "processing_info", {}
            )
            state = processing_info.get("state")

            logger.debug(f"STATUS {media_id}: {state}")

            if state == "succeeded":
                return True
            elif state == "failed":
                logger.error(f"動画処理失敗: {processing_info}")
                return False

            time.sleep(processing_info.get("check_after_secs", PROCESSING_POLL_SECS))

        return state == "succeeded"

    def _get_username(self) -> str:
        """自アカウントの @username をキャッシュ取得"""
        if not hasattr(self, "_cached_username"):
            me = self.client.get_me(user_fields=["username"])
            self._cached_username = me.data.username
        return self._cached_username
