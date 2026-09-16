"""Run narration only within a conservative measured-temperature window."""
from pathlib import Path
import json
import math
import os
import signal
import subprocess
import sys
import time
from runtime_settings import DEFAULTS, validate

CODE = Path(__file__).resolve().parent
ROOT = Path(os.environ['AUDIOBOOK_PROJECT']).resolve()
WORK = ROOT / 'kokoro-heart-build'
SENSORS = Path(os.environ['AUDIOBOOK_SENSORS']).resolve()
PYTHON = Path(sys.executable)

def start_guard_watchdog():
    import threading
    guard = int(os.environ['KOKORO_THERMAL_GUARD_PID'])
    expected = int(os.environ.get('KOKORO_PARENT_PID', str(guard)))
    def watch():
        while True:
            try:
                fresh = time.time() - (WORK / 'temperature-status.json').stat().st_mtime < 15
                os.kill(guard, 0)
                if os.getppid() != expected or not fresh:
                    os.killpg(os.getpgrp(), signal.SIGTERM)
                    return
            except OSError:
                os.killpg(os.getpgrp(), signal.SIGTERM)
                return
            time.sleep(0.5)
    threading.Thread(target=watch, daemon=True).start()

class Gate:
    def __init__(self):
        self.settings = dict(DEFAULTS)
        self.running = False
        self.rest_until = 0.0
        self.cool_since = None
        self.work_since = None
        self.reason = 'Waiting for cool readings'

    def update(self, now, temperature, valid=True, gpu_temperature=None):
        valid = valid and temperature is not None and math.isfinite(temperature)
        valid = valid and (gpu_temperature is None or math.isfinite(gpu_temperature))
        gpu_hot = gpu_temperature is not None and gpu_temperature >= self.settings['gpu_pause_c']
        gpu_warm = gpu_temperature is not None and gpu_temperature >= self.settings['gpu_resume_c']
        if not valid:
            self.running = False
            self.cool_since = None
            self.rest_until = max(self.rest_until, now + self.settings['rest_seconds'])
            self.reason = 'Temperature reading unavailable'
        elif self.running and (temperature >= self.settings['pause_c'] or gpu_hot):
            self.running = False
            self.cool_since = None
            self.rest_until = now + self.settings['rest_seconds']
            self.reason = (f"GPU reached {self.settings['gpu_pause_c']:g} C" if gpu_hot
                           else f"CPU reached {self.settings['pause_c']:g} C")
        elif self.running and now - self.work_since >= self.settings['work_seconds']:
            self.running = False
            self.cool_since = None
            self.rest_until = now + self.settings['rest_seconds']
            self.reason = 'Scheduled cooling break'
        elif not self.running:
            if temperature >= self.settings['resume_c'] or gpu_warm:
                self.cool_since = None
                self.reason = (f"Waiting for GPU below {self.settings['gpu_resume_c']:g} C" if gpu_warm
                               else f"Waiting for CPU below {self.settings['resume_c']:g} C")
            else:
                if self.cool_since is None:
                    self.cool_since = now
                if now >= self.rest_until and now - self.cool_since >= self.settings['stable_seconds']:
                    self.running = True
                    self.work_since = now
                    self.reason = 'Processing'
        return self.running

def read_temperatures(keys):
    result = subprocess.run([str(SENSORS / 'read_sensors'), *keys],
                            capture_output=True, text=True, timeout=2)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or 'Sensor read failed')
    values = json.loads(result.stdout)
    if not set(values).issubset(keys) or not all(isinstance(v, (int, float)) and math.isfinite(v) and 20 <= v <= 150 for v in values.values()):
        raise RuntimeError('Incomplete or invalid sensor readings')
    if sum(k.startswith('Tp') for k in values) < 1 or sum(k.startswith('Tg') for k in values) < 1 or not any(k.startswith('Te') for k in values):
        raise RuntimeError('Live CPU or GPU sensor group is unavailable')
    return values

def main():
    def stop(signum, frame):
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    command = sys.argv[1:] or [str(PYTHON), str(CODE / 'parallel_narration.py')]
    keys = json.loads((SENSORS / 'sensor_keys.json').read_text())
    assert sum(k.startswith('Tp') for k in keys) >= 4
    assert sum(k.startswith('Tg') for k in keys) >= 4
    gate = Gate()
    proc = None
    stopped = False
    started = time.monotonic()
    last_report = 0
    last_reason = None
    peak = 0.0
    failure_since = None
    log = (WORK / 'temperature-readings.jsonl').open('a', buffering=1)
    narration_log = (ROOT / 'kokoro-audiobook.log').open('a', buffering=1)
    completed = False
    last_error = None
    try:
        while proc is None or proc.poll() is None:
            now = time.monotonic()
            values, error = {}, None
            try:
                config_path = ROOT/'book.json'
                gate.settings = validate(json.loads(config_path.read_text())) if config_path.exists() else dict(DEFAULTS)
                values = read_temperatures(keys)
                hottest_key = max(values, key=values.get)
                temperature = values[hottest_key]
                peak = max(peak, temperature)
                failure_since = None
            except Exception as exc:
                error = str(exc)
                hottest_key, temperature = None, None
                if failure_since is None:
                    failure_since = now
            # Treat every non-GPU sensor conservatively under the CPU target.
            cpu_temperature = max((v for k,v in values.items() if not k.startswith('Tg')), default=None)
            gpu_temperature = max((v for k,v in values.items() if k.startswith('Tg')), default=None)
            enabled = gate.update(now, cpu_temperature,
                                  valid=error is None and gpu_temperature is not None,
                                  gpu_temperature=gpu_temperature)
            if (ROOT/'pause.request').exists():
                gate.running = enabled = False
                gate.cool_since = None
                gate.reason = 'Paused by you'
            if (ROOT/'stop.request').exists():
                gate.reason = 'Stopped by you'
                break
            if proc is None and enabled:
                env = dict(os.environ, KOKORO_THERMAL_GUARD_PID=str(os.getpid()))
                proc = subprocess.Popen(command,
                    stdout=narration_log, stderr=subprocess.STDOUT, env=env, start_new_session=True)
            elif proc is not None and not enabled and not stopped:
                os.killpg(proc.pid, signal.SIGSTOP)
                stopped = True
            elif proc is not None and enabled and stopped:
                os.killpg(proc.pid, signal.SIGCONT)
                stopped = False
            snapshot = {'time': time.time(), 'running': enabled and proc is not None,
                'reason': gate.reason, 'hottest_sensor': hottest_key, 'temperature_c': temperature,
                'cpu_max_c': cpu_temperature,
                'gpu_max_c': gpu_temperature,
                'gpu_target_c': gate.settings['gpu_ceiling_c'], 'gpu_pause_c': gate.settings['gpu_pause_c'],
                'gpu_resume_below_c': gate.settings['gpu_resume_c'],
                'peak_observed_c': peak, 'error': error, 'guard_pid': os.getpid(),
                'narration_pid': proc.pid if proc else None, 'pause_c': gate.settings['pause_c'], 'resume_below_c': gate.settings['resume_c'], 'user_target_c': gate.settings['ceiling_c'], 'app_controls': True}
            temp = WORK / 'temperature-status.tmp'
            temp.write_text(json.dumps(snapshot, indent=2))
            temp.replace(WORK / 'temperature-status.json')
            if now - last_report >= 5 or gate.reason != last_reason:
                log.write(json.dumps(snapshot) + '\n')
                if gate.reason != last_reason:
                    print(gate.reason, temperature, error or '', flush=True)
                last_reason, last_report = gate.reason, now
            if failure_since is not None and now - failure_since > 60:
                raise RuntimeError('Sensor readings failed for 60 seconds; narration is stopped.')
            if proc is None and len(sys.argv) > 1 and now - started > 600:
                raise RuntimeError('Mac has not reached the restart temperature within 10 minutes; narration remains stopped.')
            time.sleep(0.1)
        if (ROOT/'stop.request').exists():
            return
        if proc and proc.returncode:
            raise RuntimeError(f'Narration exited with status {proc.returncode}; see its log.')
        completed = True
        print('Processing completed. Temperature monitor stopped.', flush=True)
    except BaseException as exc:
        last_error = str(exc)
        raise
    finally:
        if proc is not None and proc.poll() is None:
            os.killpg(proc.pid, signal.SIGTERM)
            os.killpg(proc.pid, signal.SIGCONT)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
        log.close()
        narration_log.close()
        from runtime_settings import atomic_json
        atomic_json(WORK/'temperature-status.json', dict(time=time.time(), running=False,
            complete=completed, reason='Complete' if completed else ('Stopped by you' if (ROOT/'stop.request').exists() else 'Conversion stopped'),
            error=last_error, guard_pid=os.getpid(), narration_pid=None, app_controls=True, peak_observed_c=peak,
            pause_c=gate.settings['pause_c'], resume_below_c=gate.settings['resume_c'], user_target_c=gate.settings['ceiling_c'],
            gpu_target_c=gate.settings['gpu_ceiling_c'], gpu_pause_c=gate.settings['gpu_pause_c'], gpu_resume_below_c=gate.settings['gpu_resume_c']))

if __name__ == '__main__':
    main()
