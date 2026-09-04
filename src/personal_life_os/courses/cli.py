from __future__ import annotations

import argparse
import json
import os
from datetime import date, timedelta
from pathlib import Path

from .importers import import_schedule_file
from .school import EmptyClassroomImporter, HebmuBrowserImporter, fetch_courses_and_classroom_usage
from .empty_room_worker import WechatEmptyRoomWorker
from .bridge import serve_bridge
from .direct_probe import DEFAULT_BUILDINGS, DirectEmptyRoomWorker, probe_direct_classroom
from .storage import FinalScheduleStore


def _store_path() -> Path:
    configured = os.environ.get("PERSONAL_LIFE_OS_SCHEDULE_PATH")
    if configured:
        return Path(configured)
    return Path.home() / ".personal-life-os" / "final_schedule.json"


def _date(value: str) -> date:
    return date.fromisoformat(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Import and store the final course schedule")
    parser.add_argument("--store", type=Path, default=_store_path(), help="final schedule JSON path")
    commands = parser.add_subparsers(dest="command", required=True)

    file_command = commands.add_parser("file", help="import a JSON, HTML or CSV schedule")
    file_command.add_argument("path", type=Path)
    file_command.add_argument("--semester")

    school_command = commands.add_parser("hebmu", help="open a browser and import after manual campus login")
    school_command.add_argument("--semester", required=True)
    school_command.add_argument("--start", required=True, type=_date)
    school_command.add_argument("--end", required=True, type=_date)
    school_command.add_argument("--week", default="")

    room_command = commands.add_parser("empty-room", help="fetch classroom usage after manual campus login")
    room_command.add_argument("--building-code", required=True)
    room_command.add_argument("--building-name", required=True)
    room_command.add_argument("--date", required=True, type=_date)

    direct_command = commands.add_parser("empty-room-direct-probe", help="test direct classroom API access using environment credentials")
    direct_command.add_argument("--building-code", default="103966187")
    direct_command.add_argument("--building-name", default="中山校区.东教学楼")
    direct_command.add_argument("--date", required=True, type=_date)

    direct_poll_command = commands.add_parser("empty-room-direct", help="fetch classroom usage directly without browser or Fiddler")
    direct_poll_command.add_argument("--building-code", default="103966187")
    direct_poll_command.add_argument("--building-name", default="中山校区.东教学楼")
    direct_poll_command.add_argument("--output", type=Path, required=True)
    direct_poll_command.add_argument("--date", type=_date)
    direct_poll_command.add_argument("--days-ahead", type=int, default=1)
    direct_poll_command.add_argument("--all-buildings", action="store_true", help="抓取中山、建华校区全部已配置楼栋")

    cookie_command = commands.add_parser("empty-room-cookie-check", help="检查校园网 Cookie 是否仍然有效")
    cookie_command.add_argument("--date", type=_date, default=date.today(), help="用于验证的查询日期，默认今天")

    all_command = commands.add_parser("hebmu-all", help="fetch courses and classroom usage after one campus login")
    all_command.add_argument("--semester", required=True)
    all_command.add_argument("--start", required=True, type=_date)
    all_command.add_argument("--end", required=True, type=_date)
    all_command.add_argument("--week", default="")
    all_command.add_argument("--building-code", required=True)
    all_command.add_argument("--building-name", required=True)
    all_command.add_argument("--date", required=True, type=_date)

    worker_command = commands.add_parser("empty-room-poll", help="poll empty-room usage with a persistent WeChat browser profile")
    worker_command.add_argument("--user-data-dir", type=Path, required=True)
    worker_command.add_argument("--login-url", default=os.environ.get("HEBMU_WECHAT_LOGIN_URL", "https://jwweb.hebmu.edu.cn/app/#/work"))
    worker_command.add_argument("--building-code", default="103966187")
    worker_command.add_argument("--building-name", default="中山校区.东教学楼")
    worker_command.add_argument("--output", type=Path, required=True)
    worker_command.add_argument("--days-ahead", type=int, default=1)
    worker_command.add_argument("--once", action="store_true")
    worker_command.add_argument("--headless", action="store_true")

    bridge_command = commands.add_parser("empty-room-bridge", help="receive classroom responses from Fiddler on localhost")
    bridge_command.add_argument("--port", type=int, default=8765)
    bridge_command.add_argument("--output", type=Path, required=True)
    bridge_command.add_argument("--remote-url", default=os.environ.get("EMPTY_ROOM_REMOTE_URL"))

    args = parser.parse_args()
    if args.command == "file":
        courses = import_schedule_file(args.path, semester=args.semester)
        FinalScheduleStore(args.store).replace(courses)
        print(f"已写入 {len(courses)} 门课程：{args.store}")
    elif args.command == "hebmu":
        courses = HebmuBrowserImporter().fetch_courses(
            semester=args.semester, start=args.start, end=args.end, week=args.week
        )
        FinalScheduleStore(args.store).replace(courses)
        print(f"已写入 {len(courses)} 门课程：{args.store}")
    elif args.command == "hebmu-all":
        courses, classroom_payloads = fetch_courses_and_classroom_usage(
            semester=args.semester, start=args.start, end=args.end, week=args.week,
            building_code=args.building_code, building_name=args.building_name, query_dates=[args.date, args.date + timedelta(days=1)],
        )
        FinalScheduleStore(args.store).replace(courses)
        print(f"已写入 {len(courses)} 门课程：{args.store}")
        print(f"空教室模块已查询 {len(classroom_payloads)} 天")
    elif args.command == "empty-room-poll":
        with WechatEmptyRoomWorker(
            user_data_dir=args.user_data_dir, login_url=args.login_url,
            building_code=args.building_code, building_name=args.building_name,
            output_path=args.output, headless=args.headless,
        ) as worker:
            if args.once:
                result = worker.poll(days_ahead=args.days_ahead)
                print(f"已写入 {len(result['days'])} 天空教室数据：{args.output}")
            else:
                print("空教室轮询已启动：每天 06:00—21:00 每小时执行一次")
                worker.run_forever(days_ahead=args.days_ahead)
    elif args.command == "empty-room-direct-probe":
        result = probe_direct_classroom(
            building_code=args.building_code, building_name=args.building_name, query_date=args.date,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "empty-room-direct":
        result = DirectEmptyRoomWorker(
            building_code=args.building_code, building_name=args.building_name, output_path=args.output,
            buildings=DEFAULT_BUILDINGS if args.all_buildings else None,
        ).poll(start_date=args.date, days_ahead=args.days_ahead)
        if args.all_buildings:
            print(f"已抓取 {len(result.get('buildings', []))} 个楼栋，写入脱敏快照：{args.output}")
        else:
            print(f"已直接抓取 {len(result['days'])} 天，写入脱敏快照：{args.output}")
    elif args.command == "empty-room-cookie-check":
        result = probe_direct_classroom(
            building_code="103966187", building_name="中山校区.东教学楼", query_date=args.date,
        )
        endpoint = result.get("classroom_endpoint", {})
        valid = bool(result.get("token_endpoint", {}).get("has_token")
                     and endpoint.get("http_status") == 200
                     and endpoint.get("msg") == "app_retrun_success_public")
        print("COOKIE有效" if valid else "COOKIE已失效")
        print(f"token接口：HTTP {result.get('token_endpoint', {}).get('http_status')}，教室接口：HTTP {endpoint.get('http_status')}，msg={endpoint.get('msg')}")
        return 0 if valid else 2
    elif args.command == "empty-room-bridge":
        serve_bridge(port=args.port, output_path=args.output, remote_url=args.remote_url)
    else:
        rooms = EmptyClassroomImporter().fetch_classroom_names(
            building_code=args.building_code, building_name=args.building_name, query_date=args.date
        )
        print(f"查询到 {len(rooms)} 个有使用记录的教室：")
        for room in rooms:
            print(room)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
