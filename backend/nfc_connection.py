"""NFC接続の寿命と、ローカルCLI間のリーダー共有を管理する。"""
from __future__ import annotations

import hashlib
import os
import tempfile
import time
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any, Iterator

from smartcard.CardConnection import CardConnection
from smartcard.Exceptions import CardConnectionException
from smartcard.scard import SCARD_LEAVE_CARD


@contextmanager
def card_connection(reader: Any) -> Iterator[Any]:
    """明示的に接続を解放し、次の操作のためにカードの電源を保持する。"""
    connection = reader.createConnection()
    try:
        options = {"disposition": SCARD_LEAVE_CARD}
        # RC-S300はT=0を受け付けないため、対応するT=1を指定する。
        if "rc-s300" in str(reader).lower():
            options["protocol"] = CardConnection.T1_protocol
        connection.connect(**options)
        yield connection
    finally:
        # カードの離脱や接続失敗でも、元の例外を上書きせずリソースを解放する。
        with suppress(CardConnectionException):
            connection.release()


@contextmanager
def nfc_operation(timeout: float = 2.0) -> Iterator[None]:
    """受付・クイズのCLI操作をOSのロックで直列化する。"""
    project = str(Path(__file__).resolve().parent.parent)
    key = hashlib.sha256(project.encode()).hexdigest()[:16]
    lock_path = Path(tempfile.gettempdir()) / f"picoresq-nfc-{key}.lock"
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    locked = False
    with os.fdopen(descriptor, "r+b") as lock_file:
        if os.name == "nt":
            import msvcrt

            if os.fstat(lock_file.fileno()).st_size == 0:
                lock_file.write(b"\0")
                lock_file.flush()
        else:
            import fcntl

        deadline = time.monotonic() + timeout
        while not locked:
            try:
                if os.name == "nt":
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("NFCリーダーは使用中です。少し待って再試行してください")
                time.sleep(0.05)
        try:
            yield
        finally:
            if os.name == "nt":
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    # 同じファイルを待つ別プロセスがあるため、ロックファイルは削除しない。
