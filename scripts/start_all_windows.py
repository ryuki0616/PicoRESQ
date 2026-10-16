"""Windowsで受付・クイズを同時起動し、子孫プロセスもまとめて終了する。"""
from __future__ import annotations

import ctypes
import hashlib
import os
import time
from pathlib import Path
from typing import Any


class BasicLimits(ctypes.Structure):
    """Windowsのジョブ制限情報のメモリ配置。"""

    _fields_ = [
        ("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
        ("flags", ctypes.c_uint32), ("min_working_set", ctypes.c_size_t),
        ("max_working_set", ctypes.c_size_t), ("active_processes", ctypes.c_uint32),
        ("affinity", ctypes.c_size_t), ("priority", ctypes.c_uint32),
        ("scheduling", ctypes.c_uint32),
    ]


class ExtendedLimits(ctypes.Structure):
    """プロセス終了時のジョブ制限を指定する。"""

    _fields_ = [
        ("basic", BasicLimits), ("io_counters", ctypes.c_uint64 * 6),
        ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
        ("peak_process_memory", ctypes.c_size_t), ("peak_job_memory", ctypes.c_size_t),
    ]


class StartupInfo(ctypes.Structure):
    """CreateProcessWへ渡す起動情報。"""

    _fields_ = [
        ("size", ctypes.c_uint32), ("reserved", ctypes.c_wchar_p),
        ("desktop", ctypes.c_wchar_p), ("title", ctypes.c_wchar_p),
        ("x", ctypes.c_uint32), ("y", ctypes.c_uint32),
        ("x_size", ctypes.c_uint32), ("y_size", ctypes.c_uint32),
        ("x_chars", ctypes.c_uint32), ("y_chars", ctypes.c_uint32),
        ("fill", ctypes.c_uint32), ("flags", ctypes.c_uint32),
        ("show", ctypes.c_uint16), ("reserved_size", ctypes.c_uint16),
        ("reserved_data", ctypes.c_void_p), ("stdin", ctypes.c_void_p),
        ("stdout", ctypes.c_void_p), ("stderr", ctypes.c_void_p),
    ]


class ProcessInfo(ctypes.Structure):
    """起動したプロセスと初期スレッドのハンドル。"""

    _fields_ = [
        ("process", ctypes.c_void_p), ("thread", ctypes.c_void_p),
        ("pid", ctypes.c_uint32), ("thread_id", ctypes.c_uint32),
    ]


def windows_api() -> Any:
    """64ビット環境でもハンドルが欠けないよう、Win32 APIの型を指定する。"""
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = ctypes.c_void_p
    dword = ctypes.c_uint32
    signatures = {
        "CreateMutexW": ([handle, ctypes.c_int, ctypes.c_wchar_p], handle),
        "ReleaseMutex": ([handle], ctypes.c_int),
        "CreateJobObjectW": ([handle, ctypes.c_wchar_p], handle),
        "SetInformationJobObject": ([handle, ctypes.c_int, handle, dword], ctypes.c_int),
        "AssignProcessToJobObject": ([handle, handle], ctypes.c_int),
        "WaitForSingleObject": ([handle, dword], dword),
        "GetExitCodeProcess": ([handle, ctypes.POINTER(dword)], ctypes.c_int),
        "ResumeThread": ([handle], dword),
        "TerminateProcess": ([handle, dword], ctypes.c_int),
        "CloseHandle": ([handle], ctypes.c_int),
        "CreateProcessW": ([
            ctypes.c_wchar_p, ctypes.c_wchar_p, handle, handle, ctypes.c_int,
            dword, handle, ctypes.c_wchar_p,
            ctypes.POINTER(StartupInfo), ctypes.POINTER(ProcessInfo),
        ], ctypes.c_int),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(api, name)
        function.argtypes = arguments
        function.restype = result
    return api


def start_app(api: Any, job: int, script: Path, root: Path) -> int:
    """実行前にジョブへ所属させ、取り残される子プロセスの発生を防ぐ。"""
    startup = StartupInfo()
    startup.size = ctypes.sizeof(startup)
    process = ProcessInfo()
    command_processor = os.environ.get("COMSPEC") or str(
        Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "cmd.exe"
    )
    command = ctypes.create_unicode_buffer(f'"{command_processor}" /d /s /c ""{script}""')
    # 一時停止状態で生成し、別プロセスグループにする。Ctrl+Cは親が処理する。
    try:
        if not api.CreateProcessW(
            command_processor, command, None, None, False, 0x00000004 | 0x00000200,
            None, str(root), ctypes.byref(startup), ctypes.byref(process),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        if not api.AssignProcessToJobObject(job, process.process):
            raise ctypes.WinError(ctypes.get_last_error())
        if api.ResumeThread(process.thread) == 0xFFFFFFFF:
            raise ctypes.WinError(ctypes.get_last_error())
        return process.process
    except BaseException:
        if process.process:
            api.TerminateProcess(process.process, 1)
            api.CloseHandle(process.process)
        raise
    finally:
        if process.thread:
            api.CloseHandle(process.thread)


def main(project_root: Path | None = None) -> int:
    """二重起動を防ぎ、いずれかの終了時に受付・クイズを両方停止する。"""
    if os.name != "nt":
        print("このスクリプトはWindows専用です。Linuxでは start_all.sh を使用してください。")
        return 1
    root = (project_root or Path(__file__).resolve().parent.parent).resolve()
    api = windows_api()
    key = hashlib.sha256(str(root).casefold().encode()).hexdigest()[:20]
    mutex = api.CreateMutexW(None, False, f"Local\\PicoRESQ-Start-{key}")
    if not mutex:
        print(f"起動ロックを作成できません: {ctypes.WinError(ctypes.get_last_error())}")
        return 1
    acquired = False
    job = None
    processes = []
    previous_mode = os.environ.get("PICORESQ_COMBINED_START")
    try:
        wait_result = api.WaitForSingleObject(mutex, 0)
        # 通常の取得と、前の起動が異常終了した場合の取得を受け付ける。
        if wait_result not in (0, 0x80):
            if wait_result == 258:
                print("受付・クイズの同時起動スクリプトは、すでに実行中です。")
                return 1
            raise ctypes.WinError(ctypes.get_last_error())
        acquired = True
        job = api.CreateJobObjectW(None, None)
        if not job:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.basic.flags = 0x00002000  # 親終了時にジョブ内の全プロセスを終了する。
        if not api.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise ctypes.WinError(ctypes.get_last_error())
        os.environ["PICORESQ_COMBINED_START"] = "1"
        print("受付とクイズを起動します（バックエンドは起動しません）。", flush=True)
        print("Ctrl+C、または片方のアプリを閉じると、両方を終了します。", flush=True)
        for app in ("reception", "frontend"):
            script = root / "scripts" / f"start_{app}.bat"
            if not script.is_file():
                raise FileNotFoundError(script)
            processes.append(start_app(api, job, script, root))
        while True:
            for process in processes:
                result = api.WaitForSingleObject(process, 0)
                if result == 0:
                    code = ctypes.c_uint32()
                    if not api.GetExitCodeProcess(process, ctypes.byref(code)):
                        raise ctypes.WinError(ctypes.get_last_error())
                    print("一方のアプリが終了したため、残りのアプリも停止します。", flush=True)
                    return code.value
                if result == 0xFFFFFFFF:
                    raise ctypes.WinError(ctypes.get_last_error())
            time.sleep(0.2)
    except KeyboardInterrupt:
        return 130
    except OSError as error:
        print(f"起動エラー: {error}", flush=True)
        return 1
    finally:
        if job:
            api.CloseHandle(job)
        for process in processes:
            api.CloseHandle(process)
        if acquired:
            api.ReleaseMutex(mutex)
        api.CloseHandle(mutex)
        if previous_mode is None:
            os.environ.pop("PICORESQ_COMBINED_START", None)
        else:
            os.environ["PICORESQ_COMBINED_START"] = previous_mode


if __name__ == "__main__":
    raise SystemExit(main())
