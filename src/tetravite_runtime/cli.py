import argparse
import json
from pathlib import Path
import sys
from .core import execute, load_package, RuntimeFailure

def main():
    p = argparse.ArgumentParser(description='TETRAVITE reference runtime (trusted packages only)')
    sub = p.add_subparsers(dest='action', required=True)
    inspect = sub.add_parser('inspect'); inspect.add_argument('package', type=Path)
    run = sub.add_parser('run'); run.add_argument('package', type=Path)
    run.add_argument('--input', type=str, default='-', help='JSON input file, or - for stdin')
    run.add_argument('--allow-execution', action='store_true', help='Explicitly trust and execute package code')
    try:
        args = p.parse_args()
        if args.action == 'inspect':
            _, m = load_package(args.package)
            print(json.dumps({'metadata':m['metadata'],'spec':m['spec']}, indent=2))
        else:
            raw = sys.stdin.read() if args.input == '-' else Path(args.input).read_text(encoding='utf-8')
            payload = json.loads(raw)
            print(json.dumps(execute(args.package, payload, allow_execution=args.allow_execution), ensure_ascii=False, indent=2))
        return 0
    except (RuntimeFailure, ValueError, OSError) as exc:
        code = exc.code if isinstance(exc, RuntimeFailure) else 'invalid_request'
        print(json.dumps({'status':'error','code':code,'message':str(exc)}), file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
