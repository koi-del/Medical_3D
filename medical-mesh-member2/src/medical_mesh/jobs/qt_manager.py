import json
import codecs
import os
from pathlib import Path
import signal
import sys
from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal
from medical_mesh.core.model import write_json


class JobManager(QObject):
    progress = Signal(str, str)
    event = Signal(dict)
    finished = Signal(dict)
    busy_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.request = None
        self.buffer = ""
        self.interrupted = None
        self.log_error = None
        self.stdout_decoder=codecs.getincrementaldecoder('utf-8')('replace')
        self.stderr_decoder=codecs.getincrementaldecoder('utf-8')('replace')
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(lambda: self.cancel("timeout"))

    @property
    def busy(self):
        return self.process is not None

    def submit(self, request, timeout_ms=180000):
        if self.busy:
            raise RuntimeError("已有任务运行，请等待或取消")
        self.request, self.interrupted, self.buffer = request, None, ""
        self.log_error=None
        self.stdout_decoder.reset(); self.stderr_decoder.reset()
        directory = Path(request["output_dir"])
        directory.mkdir(parents=True, exist_ok=True)
        write_json(directory / "launch_request.json", request)
        process = QProcess(self)
        self.process = process
        process.setProgram(sys.executable)
        environment = QProcessEnvironment.systemEnvironment()
        source_root = str(Path(__file__).resolve().parents[2])
        environment.insert("PYTHONPATH", source_root + os.pathsep + environment.value("PYTHONPATH", ""))
        process.setProcessEnvironment(environment)
        process.setArguments(["-m", "medical_mesh.jobs.worker", str((directory / "launch_request.json").resolve())])
        process.readyReadStandardOutput.connect(self._read)
        process.started.connect(lambda: self._stop_process() if self.interrupted else None)
        process.readyReadStandardError.connect(self._read_error)
        process.finished.connect(self._finished)
        process.errorOccurred.connect(self._error)
        process.start()
        self.timer.start(timeout_ms)
        self.busy_changed.emit(True)

    def _read(self):
        chunk = self.stdout_decoder.decode(bytes(self.process.readAllStandardOutput()))
        directory = Path(self.request["output_dir"])
        self._log_chunk(directory/"stdout.log",chunk)
        self.buffer += chunk
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            try:
                value = json.loads(line)
                if value.get("event") == "progress":
                    self.progress.emit(value["stage"], value["message"])
                    self.event.emit(value)
            except (ValueError, KeyError, AttributeError):
                pass

    def _read_error(self):
        chunk = self.stderr_decoder.decode(bytes(self.process.readAllStandardError()))
        self._log_chunk(Path(self.request["output_dir"])/"stderr.log",chunk)

    def _log_chunk(self,path,chunk):
        if not chunk or self.log_error:
            return
        try:
            with path.open('a',encoding='utf-8') as stream:stream.write(chunk)
        except OSError as error:
            self.log_error=str(error)
            self.progress.emit('log_error','日志写入失败，正在停止本次任务：'+str(error))
            self.cancel('failed')

    def cancel(self, reason="cancelled"):
        if not self.busy or self.interrupted:
            return
        self.interrupted = reason
        self._stop_process()

    def _stop_process(self):
        if self.process is None:
            return
        pid = self.process.processId()
        if os.name == "posix" and pid:
            try:
                if os.getpgid(pid) == pid:
                    os.killpg(pid, signal.SIGTERM)
                    QTimer.singleShot(800, lambda: self._kill_group(pid))
                    return
            except ProcessLookupError:
                return
        self.process.terminate()
        process = self.process
        QTimer.singleShot(800, lambda: process.kill() if self.process is process and process.state() != QProcess.NotRunning else None)

    @staticmethod
    def _kill_group(pid):
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def _error(self, error):
        if error == QProcess.FailedToStart:
            self._finished(-1, QProcess.CrashExit)

    def _finished(self, exit_code, _exit_status):
        if self.process is None:
            return
        self.timer.stop()
        self._read(); self._read_error()
        directory = Path(self.request["output_dir"])
        path = directory / "result.json"
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
            if result.get("run_id") != directory.name:
                raise ValueError("run_id mismatch")
            if exit_code != 0 and result.get("status") == "completed":
                raise ValueError("nonzero worker exit despite completed result")
        except (OSError, ValueError) as error:
            result = {"status": "failed", "errors": [str(error)], "decision": "rejected", "quality_status": "unverified"}
        if self.interrupted:
            result.update(status=self.interrupted, decision="rejected", quality_status="unverified",
                          errors=[f"job {self.interrupted}"], output_version=None)
            if self.request["operation"] == "convert":
                result.update(geometry_status="not_completed", preview_assets=None)
        if self.log_error:
            result.update(status='failed',decision='rejected',quality_status='unverified',errors=[self.log_error])
        result.update(run_id=directory.name, output_dir=str(directory), operation=self.request["operation"])
        from medical_mesh.reporting import render_report
        try:
            if self.request["operation"] == "patella_demo":
                from medical_mesh.experiments.demo import finalize_demo
                result=finalize_demo(result,directory)
            if result.get("operation") == "patella_demo" and result["status"] == "completed" and (directory/"report.html").is_file():
                write_json(directory/"result.json",result)
            else:
                render_report(result, directory)
        except Exception as error:
            result.update(status="failed", decision="rejected", quality_status="unverified", report_error=str(error))
            self.progress.emit("report_error", "报告写入失败：" + str(error))
        process = self.process
        self.process = None
        process.deleteLater()
        self.busy_changed.emit(False)
        self.finished.emit(result)
