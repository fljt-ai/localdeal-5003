#!/usr/bin/env python3
"""Start LocalDeal locally; keep all existing database records."""
import argparse
import importlib.util
from pathlib import Path

from backend.database import DEFAULT_DB
from backend.server import create_server


def main():
    parser = argparse.ArgumentParser(description='Run the LocalDeal local full-stack demo')
    parser.add_argument('--port',type=int,default=8787)
    parser.add_argument('--db',type=Path)
    parser.add_argument('--smart-demo',action='store_true',help='Use a separate, richer fictional demonstration database; preserve existing files')
    parser.add_argument('--verbose',action='store_true')
    parser.add_argument('--engine',choices=('auto','fastapi','legacy'),default='auto',help='Prefer FastAPI when dependencies are installed; legacy is the dependency-free fallback')
    parser.add_argument('--container',action='store_true',help='Bind inside Docker only; publish the container port to host loopback')
    args = parser.parse_args()
    if not 1<=args.port<=65535:
        parser.error('Port must be between 1 and 65535')
    ready=all(importlib.util.find_spec(name) is not None for name in ('fastapi','pydantic','uvicorn'))
    fastapi=args.engine=='fastapi' or (args.engine=='auto' and ready)
    if fastapi and not ready:
        parser.error('Install FastAPI dependencies first: python -m pip install -r requirements.txt')
    if args.container and not fastapi:
        parser.error('--container requires --engine fastapi')
    try:
        path=args.db or (DEFAULT_DB.with_name('localdeal-smart.db') if args.smart_demo else DEFAULT_DB)
        if args.smart_demo:
            from backend.smart_demo import create_smart_demo
            create_smart_demo(path)
        if fastapi:
            import uvicorn
            from backend.fastapi_app import create_app
            app=create_app(path,args.port)
            print(f'LocalDeal (FastAPI): http://127.0.0.1:{args.port}',flush=True)
            print(f'API docs: http://127.0.0.1:{args.port}/docs',flush=True)
            print(f'Database: {app.state.database_path}',flush=True)
            uvicorn.run(app,host='0.0.0.0' if args.container else '127.0.0.1',port=args.port,
                        proxy_headers=False,access_log=args.verbose,log_level='info')
            return
        server = create_server(path,args.port,quiet=not args.verbose)
    except OSError as error:
        parser.exit(1,f'LocalDeal could not start: {error}\nChoose another --port if the port is occupied.\n')
    print(f'LocalDeal (legacy compatibility): http://127.0.0.1:{server.server_port}',flush=True)
    if args.engine=='auto':print('For FastAPI and Swagger docs: python -m pip install -r requirements.txt',flush=True)
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
