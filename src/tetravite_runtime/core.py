"""Reference executor for trusted local Tetravite packages; NOT a sandbox."""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

import yaml
from jsonschema import Draft202012Validator, FormatChecker

MAX_ZIP_BYTES = 30_000_000
MAX_FILE_BYTES = 10_000_000
MAX_FILES = 200
MAX_STDOUT_BYTES = 2_000_000

class RuntimeFailure(Exception):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(message)


def _safe_path(root: Path, value: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute() or '\\' in value:
        raise RuntimeFailure('invalid_path', f'Unsafe package path: {value!r}')
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise RuntimeFailure('invalid_path', f'Path escapes package: {value!r}')
    return path


def unpack_archive(archive: Path, dest: Path) -> Path:
    if archive.stat().st_size > MAX_ZIP_BYTES:
        raise RuntimeFailure('archive_limit', 'ZIP exceeds compressed size limit')
    with zipfile.ZipFile(archive) as z:
        entries = z.infolist()
        if len(entries) > MAX_FILES or sum(i.file_size for i in entries) > MAX_ZIP_BYTES:
            raise RuntimeFailure('archive_limit', 'ZIP exceeds file count or expanded size limit')
        for item in entries:
            name = item.filename
            if not name or '\\' in name or name.startswith('/') or re.match(r'^[A-Za-z]:', name):
                raise RuntimeFailure('invalid_archive', 'Unsafe archive entry')
            if (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise RuntimeFailure('invalid_archive', 'Symbolic links are forbidden')
            target = _safe_path(dest, name)
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if item.file_size > MAX_FILE_BYTES:
                raise RuntimeFailure('archive_limit', 'Oversized archive member')
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(item) as src, target.open('wb') as out:
                shutil.copyfileobj(src, out)
    manifests = list(dest.rglob('tetravite.yaml'))
    if len(manifests) != 1:
        raise RuntimeFailure('invalid_archive', 'ZIP must contain exactly one tetravite.yaml')
    return manifests[0].parent


def load_package(package: Path) -> tuple[Path, dict]:
    root = package.resolve()
    if root.is_file() and root.name == 'tetravite.yaml':
        root = root.parent
    manifest_file = root / 'tetravite.yaml'
    if not manifest_file.is_file():
        raise RuntimeFailure('missing_manifest', 'Missing tetravite.yaml')
    try:
        manifest = yaml.safe_load(manifest_file.read_text(encoding='utf-8'))
    except (OSError, yaml.YAMLError) as exc:
        raise RuntimeFailure('invalid_manifest', str(exc)) from exc
    if not isinstance(manifest, dict) or manifest.get('apiVersion') != 'tetravite.dev/v1alpha1' or manifest.get('kind') != 'Tool':
        raise RuntimeFailure('invalid_manifest', 'Unsupported apiVersion/kind')
    spec = manifest.get('spec')
    if not isinstance(spec, dict) or spec.get('runtime') != 'python':
        raise RuntimeFailure('invalid_manifest', 'Only Python runtime is supported')
    tetra = spec.get('tetra')
    if not isinstance(tetra, dict) or any(k not in tetra for k in ('contract','execution','trust','composition')):
        raise RuntimeFailure('invalid_manifest', 'All four TETRA pillars are required')
    if spec.get('command') != tetra['execution'].get('command') or spec.get('runtime') != tetra['execution'].get('runtime'):
        raise RuntimeFailure('invalid_manifest', 'Execution declaration mismatch')
    if tetra['contract'].get('inputSchema') != spec.get('inputSchema') or tetra['contract'].get('outputSchema') != spec.get('outputSchema'):
        raise RuntimeFailure('invalid_manifest', 'Contract declaration mismatch')
    if tetra['contract'].get('interface') != 'json-stdin-stdout':
        raise RuntimeFailure('invalid_manifest', 'Unsupported interface')
    for key in ('inputSchema', 'outputSchema'):
        if not isinstance(spec.get(key), str) or not _safe_path(root, spec[key]).is_file():
            raise RuntimeFailure('invalid_manifest', f'Missing {key}')
    return root, manifest


def _schema(root: Path, relative: str) -> dict:
    try:
        schema = json.loads(_safe_path(root, relative).read_text(encoding='utf-8'))
        Draft202012Validator.check_schema(schema)
        return schema
    except (ValueError, OSError, Exception) as exc:
        raise RuntimeFailure('invalid_schema', str(exc)) from exc


def _validate(schema: dict, payload: object, label: str):
    issues = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload), key=lambda e: str(e.path))
    if issues:
        raise RuntimeFailure(f'invalid_{label}', '; '.join(e.message for e in issues[:5]))


def execute(package: Path, payload: object, *, allow_execution: bool = False, python: str | None = None) -> dict:
    """Execute only explicitly trusted code. No network, filesystem or process sandbox."""
    if not allow_execution:
        raise RuntimeFailure('execution_not_authorized', 'Pass --allow-execution only for packages you trust')
    with tempfile.TemporaryDirectory(prefix='tetravite-') as tmp:
        source = Path(package)
        if source.is_file() and source.suffix.lower() == '.zip':
            root = unpack_archive(source, Path(tmp) / 'package')
        else:
            root = source
        root, manifest = load_package(root)
        spec = manifest['spec']
        _validate(_schema(root, spec['inputSchema']), payload, 'input')
        entrypoint = spec.get('entrypoint', '')
        if not isinstance(entrypoint, str) or not re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*', entrypoint):
            raise RuntimeFailure('invalid_manifest', 'Invalid Python entrypoint')
        module, func = entrypoint.split(':', 1)
        # Import the declared callable in a subprocess; never import package code into the host.
        script = ("import importlib,sys; sys.path.insert(0,sys.argv[3]); m=importlib.import_module(sys.argv[1]); "
                  "f=getattr(m,sys.argv[2]); r=f(); sys.exit(r if isinstance(r,int) else 0)")
        limits = spec.get('limits', {})
        timeout = limits.get('timeoutSeconds', 20) if isinstance(limits, dict) else 20
        if not isinstance(timeout, int) or not 1 <= timeout <= 120:
            raise RuntimeFailure('invalid_manifest', 'timeoutSeconds must be 1..120')
        env = os.environ.copy()
        src = root / 'src'
        env['PYTHONPATH'] = os.pathsep.join([str(src if src.is_dir() else root)])
        try:
            proc = subprocess.Popen([python or sys.executable, '-I', '-c', script, module, func, str(src if src.is_dir() else root)],
                                    cwd=root, env=env, stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            # -I ignores PYTHONPATH; use explicit sys.path insertion via trusted launcher instead.
            data = (json.dumps(payload, ensure_ascii=False) + '\n').encode('utf-8')
            stdout, stderr = proc.communicate(data, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            proc.kill(); proc.communicate()
            raise RuntimeFailure('timeout', f'Execution exceeded {timeout}s') from exc
        except OSError as exc:
            raise RuntimeFailure('spawn_failed', str(exc)) from exc
        if len(stdout) > MAX_STDOUT_BYTES or len(stderr) > MAX_STDOUT_BYTES:
            raise RuntimeFailure('output_limit', 'Process output exceeds limit')
        if proc.returncode:
            raise RuntimeFailure('execution_failed', f'Exit {proc.returncode}: {stderr.decode("utf-8", "replace")[:2000]}')
        try:
            result = json.loads(stdout)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeFailure('invalid_output', 'Expected one JSON document on stdout') from exc
        _validate(_schema(root, spec['outputSchema']), result, 'output')
        return {'status':'success', 'package':manifest['metadata']['name'], 'version':manifest['metadata']['version'], 'result':result}
