"""Official Agora AccessToken2 (Token007) generator for RTC and Conversational AI Agent services.

Implements the official Agora AccessToken2 specification:
- Version prefix '007'
- HMAC-SHA256 hierarchical signing
- ServiceRtc (type 1) and ServiceRtm (type 2) support
- Zlib compression + Base64 encoding
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from typing import Any, Dict, List, Tuple
import zlib


def pack_uint16(x: int) -> bytes:
    """Pack unsigned 16-bit integer in little-endian format."""
    return struct.pack("<H", x)


def pack_uint32(x: int) -> bytes:
    """Pack unsigned 32-bit integer in little-endian format."""
    return struct.pack("<I", x)


def pack_string(string: str | bytes) -> bytes:
    """Pack length-prefixed UTF-8 string."""
    if isinstance(string, str):
        string = string.encode("utf-8")
    return pack_uint16(len(string)) + string


def pack_map_uint32(m: Dict[int, int]) -> bytes:
    """Pack sorted map of uint16 -> uint32."""
    res = pack_uint16(len(m))
    for k in sorted(m.keys()):
        res += pack_uint16(k) + pack_uint32(m[k])
    return res


class AccessToken2:
    """Official Agora AccessToken2 (Token007) builder."""

    def __init__(
        self,
        app_id: str,
        app_certificate: str,
        issue_ts: int = 0,
        expire: int = 86400,
    ) -> None:
        self.app_id = (app_id or "").strip()
        self.app_certificate = (app_certificate or "").strip()
        self.issue_ts = issue_ts if issue_ts != 0 else int(time.time())
        self.expire = expire
        self.salt = secrets.SystemRandom().randint(1, 99999999)
        self.services: List[Tuple[int, bytes]] = []

    def add_rtc_service(
        self,
        channel_name: str,
        uid: int | str = 0,
        expire: int = 86400,
    ) -> None:
        """Add RTC Service (type=1) with kPrivilegeJoinChannel privilege."""
        # ServiceRtc: type=1, privs={1: expire}
        s = pack_uint16(1)
        s += pack_map_uint32({1: expire})
        s += pack_string(channel_name)
        uid_str = b"" if uid == 0 or str(uid) == "0" or uid == "" else str(uid).encode("utf-8")
        s += pack_string(uid_str)
        self.services.append((1, s))

    def add_rtm_service(
        self,
        user_id: int | str,
        expire: int = 86400,
    ) -> None:
        """Add RTM Service (type=2) with kPrivilegeLogin privilege."""
        # ServiceRtm: type=2, privs={1: expire}
        s = pack_uint16(2)
        s += pack_map_uint32({1: expire})
        s += pack_string(str(user_id))
        self.services.append((2, s))

    def build(self) -> str:
        """Build the full '007' token string."""
        if not self.app_id or not self.app_certificate or not self.services:
            return ""

        # Derive signing key
        cert_bytes = self.app_certificate.encode("utf-8")
        signing = hmac.new(pack_uint32(self.issue_ts), cert_bytes, hashlib.sha256).digest()
        signing = hmac.new(pack_uint32(self.salt), signing, hashlib.sha256).digest()

        # Sort services by type
        services_sorted = sorted(self.services, key=lambda x: x[0])
        app_id_bytes = self.app_id.encode("utf-8")
        signing_info = (
            pack_string(app_id_bytes)
            + pack_uint32(self.issue_ts)
            + pack_uint32(self.expire)
            + pack_uint32(self.salt)
            + pack_uint16(len(services_sorted))
        )
        for _, s in services_sorted:
            signing_info += s

        signature = hmac.new(signing, signing_info, hashlib.sha256).digest()
        full_buf = pack_string(signature) + signing_info
        return "007" + base64.b64encode(zlib.compress(full_buf)).decode("utf-8")


class RtcTokenBuilder2:
    """Helper for generating Agora AccessToken2 RTC tokens."""

    @staticmethod
    def build_token_with_uid(
        app_id: str,
        app_certificate: str,
        channel_name: str,
        uid: int | str = 0,
        role: int = 1,
        expire_seconds: int = 86400,
        rtm_user_id: Optional[str] = None,
    ) -> str:
        """Build a unified RTC + RTM Token007 with UID/Account."""
        token = AccessToken2(app_id, app_certificate, expire=expire_seconds)
        token.add_rtc_service(channel_name, uid, expire=expire_seconds)
        effective_rtm_user = rtm_user_id or (str(uid) if uid and str(uid) != "0" else f"cand_{channel_name}")
        token.add_rtm_service(effective_rtm_user, expire=expire_seconds)
        return token.build()


    @staticmethod
    def build_agent_token(
        app_id: str,
        app_certificate: str,
        channel_name: str,
        agent_rtc_uid: int | str,
        expire_seconds: int = 86400,
    ) -> str:
        """Build an AccessToken2 matching Agora Agent Studio token layout.

        - ServiceRtc: Wildcard UID (empty UID) on dynamic channel.
        - ServiceRtm: user_id = str(agent_rtc_uid) dynamically supplied.
        """
        token = AccessToken2(app_id, app_certificate, expire=expire_seconds)
        token.add_rtc_service(channel_name, 0, expire=expire_seconds)
        token.add_rtm_service(str(agent_rtc_uid), expire=expire_seconds)
        return token.build()
