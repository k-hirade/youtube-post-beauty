"""
@file: social_media_poster.py
@desc: Social Mediaに動画をアップロードするモジュール
"""
from __future__ import annotations

import os
import json
import logging
import time
import http.client
from pathlib import Path
from typing import Dict, Optional, List

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)

SCOPES: List[str] = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.readonly",
]

class SocialMediaPoster:
    """Upload a short‑form video to YouTube (and optionally TikTok / Instagram)."""

    def __init__(
        self,
        *,
        enable_youtube: bool = True,
        enable_tiktok: bool = False,
        enable_instagram: bool = False,
        youtube_client_secrets: str | None = None,
        youtube_token_path: str | None = None,
        target_channel_id: str | None = None,
    ) -> None:
        self.enable_youtube = enable_youtube
        self.enable_tiktok = enable_tiktok
        self.enable_instagram = enable_instagram

        # ---- YouTube auth files ----
        self.youtube_client_secrets = Path(
            youtube_client_secrets or os.environ.get("YOUTUBE_CLIENT_SECRETS")
        ).expanduser()
        self.youtube_token_path = Path(
            youtube_token_path or os.environ.get("YOUTUBE_TOKEN")
        ).expanduser()
        self.target_channel_id = target_channel_id or os.environ.get("TARGET_CHANNEL_ID", "")

        # ensure paths exist
        self.youtube_client_secrets.parent.mkdir(parents=True, exist_ok=True)
        self.youtube_token_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def post_video(
        self,
        *,
        video_path: str,
        title: str,
        description: str,
        thumbnail_path: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Dict[str, str]]:
        """Upload ``video_path`` as a short video.

        Returns a mapping like::

            {
              "youtube": {"success": True, "id": "abc", "url": "https://..."},
              "tiktok":  {"success": False, "error": "disabled"},
              "instagram": { ... }
            }
        """
        if not Path(video_path).is_file():
            raise FileNotFoundError(video_path)

        results: Dict[str, Dict[str, str]] = {}

        # ---- YouTube ----
        if self.enable_youtube:
            results["youtube"] = self._post_to_youtube(
                video_path, title, description, thumbnail_path, tags or ["Shorts"]
            )
        else:
            results["youtube"] = {"success": False, "error": "disabled"}

        # ---- TikTok (stub) ----
        if self.enable_tiktok:
            results["tiktok"] = self._post_to_tiktok()
        else:
            results["tiktok"] = {"success": False, "error": "disabled"}

        # ---- Instagram (stub) ----
        if self.enable_instagram:
            results["instagram"] = self._post_to_instagram()
        else:
            results["instagram"] = {"success": False, "error": "disabled"}

        return results

    # ------------------------------------------------------------------
    # YouTube implementation
    # ------------------------------------------------------------------
    def _post_to_youtube(
        self,
        video_path: str,
        title: str,
        description: str,
        thumbnail_path: Optional[str],
        tags: List[str],
    ) -> Dict[str, str]:
        try:
            service = self._get_authenticated_youtube_service()
            if service is None:
                return {"success": False, "error": "auth failed"}

            body = {
                "snippet": {
                    "title": title,
                    "description": description,
                    "tags": tags,
                    "categoryId": "22",  # People & Blogs; shorts ignore this mostly
                    "channelId": self.target_channel_id or None,
                },
                "status": {
                    "privacyStatus": "unlisted",
                    "selfDeclaredMadeForKids": False,
                },
            }

            media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
            req = service.videos().insert(part=",".join(body.keys()), body=body, media_body=media)

            response = None
            while response is None:
                _, response = req.next_chunk()

            video_id = response["id"]
            logger.info("YouTube upload complete: %s", video_id)

            # thumbnail optional
            if thumbnail_path and Path(thumbnail_path).is_file():
                service.thumbnails().set(
                    videoId=video_id, media_body=MediaFileUpload(thumbnail_path)
                ).execute()

            return {
                "success": True,
                "id": video_id,
                "url": f"https://youtube.com/shorts/{video_id}",
            }
        except HttpError as e:
            logger.error("YouTube API error: %s", e)
            return {"success": False, "error": str(e)}
        except Exception as e:  # pylint: disable=broad-except
            logger.exception("YouTube upload failed")
            return {"success": False, "error": str(e)}

    def _get_authenticated_youtube_service(self):
        creds: Optional[Credentials] = None
        if self.youtube_token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.youtube_token_path), SCOPES)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())

        if creds is None or not creds.valid:
            if not self.youtube_client_secrets.exists():
                logger.error("Missing client secret file at %s", self.youtube_client_secrets)
                return None

            flow = InstalledAppFlow.from_client_secrets_file(str(self.youtube_client_secrets), SCOPES)
            creds = flow.run_local_server(port=0)
            self.youtube_token_path.write_text(creds.to_json(), encoding="utf‑8")

        return build("youtube", "v3", credentials=creds)

    def _post_to_tiktok(self):  # pragma: no cover – stub
        logger.info("TikTok uploading is not implemented yet.")
        return {"success": False, "error": "not implemented"}

    def _post_to_instagram(self):  # pragma: no cover – stub
        logger.info("Instagram uploading is not implemented yet.")
        return {"success": False, "error": "not implemented"}