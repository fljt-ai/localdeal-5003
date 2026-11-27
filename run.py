#!/usr/bin/env python3
"""Start LocalDeal locally; keep all existing database records."""
import argparse
from pathlib import Path

from backend.database import DEFAULT_DB
from backend.server import create_server


def main():
    parser = argparse.ArgumentParser(description='Run the LocalDeal local full-stack demo')
    parser.add_argument('--port',type=int,default=8787)
    parser.add_argument('--db',type=Path)
    parser.add_argument('--smart-demo',action='store_true',help='Use a separate, richer fictional demonstration database; preserve existing files')
    parser.add_argument('--verbose',action='store_true')
    args = parser.parse_args()
    if not 1<=args.port<=65535:
        parser.error('Port must be between 1 and 65535')
    try:
        path=args.db or (DEFAULT_DB.with_name('localdeal-smart.db') if args.smart_demo else DEFAULT_DB)
        if args.smart_demo:
            from backend.smart_demo import create_smart_demo
            create_smart_demo(path)
        server = create_server(path,args.port,quiet=not args.verbose)
    except OSError as error:
        parser.exit(1,f'LocalDeal could not start: {error}\nChoose another --port if the port is occupied.\n')
    print(f'LocalDeal 已启动：http://127.0.0.1:{server.server_port}',flush=True)
    print('数据库已保存至：'+str(server.database_path),flush=True)
    print('按 Control+C 停止；重新启动会保留数据。',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nLocalDeal 已停止。')
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
