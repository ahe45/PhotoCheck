"""Persistent local inference process: native model failures cannot kill the UI."""
import multiprocessing
import os
import time


def _model_loop(connection, criteria=None):
    if os.name == "nt":
        import ctypes
        ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
    analyzer = None
    try:
        from PIL import Image
        from .analysis import Analyzer
        analyzer = Analyzer(criteria)
        connection.send(("ready", analyzer.version))
        while True:
            request = connection.recv()
            if request is None:
                break
            size, raw, result = request
            try:
                with Image.frombytes("RGB", size, raw) as image:
                    analyzer.analyze(image, result)
                connection.send(("result", result))
            except Exception as error:
                connection.send(("error", f"{type(error).__name__}: {error}"))
    except (EOFError, BrokenPipeError):
        pass
    except Exception as error:
        try:
            connection.send(("error", f"{type(error).__name__}: {error}"))
        except (OSError, EOFError):
            pass
    finally:
        if analyzer:
            analyzer.close()
        connection.close()


class ProcessAnalyzer:
    def __init__(self, timeout=20.0, _target=_model_loop, criteria=None):
        from .criteria import Criteria
        self.criteria = criteria or Criteria()
        self.timeout, self.target = timeout, _target
        self.process = self.connection = None
        self.version = "unavailable"
        self._start()

    def _discard(self):
        if self.process:
            if self.process.pid is not None:
                if self.process.is_alive():
                    self.process.terminate()
                self.process.join(timeout=2)
                if self.process.is_alive():
                    self.process.kill()
                    self.process.join(timeout=2)
            self.process.close()
            self.process = None
        if self.connection:
            self.connection.close()
            self.connection = None

    def _receive(self):
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if self.connection.poll(0.05):
                try:
                    return self.connection.recv()
                except (EOFError, OSError):
                    break
            if not self.process.is_alive():
                break
        code = self.process.exitcode
        self._discard()
        if code is None:
            raise RuntimeError("분석 응답 시간 초과; 해당 파일은 확인 필요로 유지")
        raise RuntimeError(f"분석 엔진 비정상 종료 (코드 {code}); 다음 파일에서 자동 복구")

    def _start(self):
        self._discard()
        context = multiprocessing.get_context("spawn")
        self.connection, child = context.Pipe()
        args = (child, self.criteria) if self.target is _model_loop else (child,)
        self.process = context.Process(target=self.target, args=args, daemon=True)
        try:
            self.process.start()
            child.close()
            kind, data = self._receive()
            if kind != "ready":
                raise RuntimeError(f"로컬 분석 엔진 준비 실패: {data}")
            self.version = data
        except Exception:
            child.close()
            self._discard()
            raise

    def analyze(self, image, result):
        if self.process is None or not self.process.is_alive():
            self._start()
        result.model_version = self.version
        try:
            self.connection.send((image.size, image.tobytes(), result))
            kind, data = self._receive()
        except (OSError, EOFError) as error:
            self._discard()
            raise RuntimeError("분석 엔진 통신 오류; 다음 파일에서 자동 복구") from error
        if kind == "error":
            raise RuntimeError(data)
        if kind != "result":
            self._discard()
            raise RuntimeError("분석 응답 형식 오류")
        result.__dict__.update(data.__dict__)

    def close(self):
        if self.process and self.process.is_alive():
            try:
                self.connection.send(None)
                self.process.join(timeout=2)
            except (OSError, EOFError):
                pass
        self._discard()
