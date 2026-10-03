#!/usr/bin/env python3
"""Start LocalDeal locally; keep all existing database records."""
import argparse
from pathlib import Path

from backend.database import DEFAULT_DB
from backend.server import create_server


def main():
    parser = argparse.ArgumentParser(description='Run the LocalDeal local full-stack demo')
    parser.add_argument('--port',type=int,default=8787)
    parser.add_argument('--db',type=Path,default=DEFAULT_DB)
    parser.add_argument('--verbose',action='store_true')
    args = parser.parse_args()
    if not 1<=args.port<=65535:
        parser.error('Port must be between 1 and 65535')
    try:
        server = create_server(args.db,args.port,quiet=not args.verbose)
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
