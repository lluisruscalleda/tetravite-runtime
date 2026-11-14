import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from tetravite_runtime.core import execute, load_package, unpack_archive, RuntimeFailure

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / 'examples' / 'hello-tetravite'

class RuntimeTests(unittest.TestCase):
    def test_manifest(self):
        _, manifest = load_package(EXAMPLE)
        self.assertEqual(manifest['metadata']['name'], 'hello-tetravite')

    def test_execution_requires_opt_in(self):
        with self.assertRaises(RuntimeFailure) as ctx:
            execute(EXAMPLE, {'name':'Ada'})
        self.assertEqual(ctx.exception.code, 'execution_not_authorized')

    def test_valid_execution(self):
        result = execute(EXAMPLE, {'name':'Ada'}, allow_execution=True)
        self.assertEqual(result['result'], {'greeting':'Hello, Ada'})

    def test_invalid_input(self):
        with self.assertRaises(RuntimeFailure) as ctx:
            execute(EXAMPLE, {'bad':'Ada'}, allow_execution=True)
        self.assertEqual(ctx.exception.code, 'invalid_input')

    def test_zip_execution(self):
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td)/'fixture.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                for f in EXAMPLE.rglob('*'):
                    if f.is_file():
                        z.write(f, f.relative_to(EXAMPLE))
            self.assertEqual(execute(archive, {'name':'Zip'}, allow_execution=True)['result']['greeting'], 'Hello, Zip')

    def test_reject_zip_traversal(self):
        with tempfile.TemporaryDirectory() as td:
            archive=Path(td)/'bad.zip'
            with zipfile.ZipFile(archive,'w') as z: z.writestr('../escape', 'bad')
            with self.assertRaises(RuntimeFailure): unpack_archive(archive, Path(td)/'out')

    def test_invalid_output(self):
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td)/'package'
            shutil.copytree(EXAMPLE,dest)
            (dest/'src/hello/main.py').write_text('def main():\n print("not-json")\n')
            with self.assertRaises(RuntimeFailure) as ctx:
                execute(dest, {'name':'Ada'}, allow_execution=True)
            self.assertEqual(ctx.exception.code, 'invalid_output')

if __name__ == '__main__': unittest.main()
