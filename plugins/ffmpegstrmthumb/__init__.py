import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event as ThreadEvent
from typing import List, Tuple, Dict, Any

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.log import logger
from app.plugins import _PluginBase
from app.utils.system import SystemUtils
from app.schemas import Notification, NotificationType, MessageChannel

ffmpeg_lock = threading.Lock()


class FFmpegStrmThumb(_PluginBase):
    # 插件名称
    plugin_name = "FFmpegStrm缩略图"
    # 插件描述
    plugin_desc = "TheMovieDb没有背景图片时使用FFmpeg截取strm视频文件缩略图。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/imaliang/MoviePilot-Plugins/main/icons/ffmpegstrm.png"
    # 插件版本
    plugin_version = "0.6"
    # 插件作者
    plugin_author = "imaliang"
    # 作者主页
    author_url = "https://github.com/imaliang"
    # 插件配置项ID前缀
    plugin_config_prefix = "ffmpegstrmthumb_"
    # 加载顺序
    plugin_order = 3
    # 可使用的用户级别
    user_level = 1

    # 私有属性
    _scheduler = None
    _enabled = False
    _onlyonce = False
    _cron = None
    _timeline = "00:03:01"
    _scan_paths = ""
    _exclude_paths = ""
    _overlay = False
    _gen_strategy = "100=60"
    _gen_strategy_count = 0
    _gen_strategy_max_count = 100
    _gen_strategy_delay = 60
    # 退出事件
    _event = ThreadEvent()

    def init_plugin(self, config: dict = None):
        # 读取配置
        if config:
            self._enabled = config.get("enabled")
            self._onlyonce = config.get("onlyonce")
            self._cron = config.get("cron")
            self._timeline = config.get("timeline")
            self._scan_paths = config.get("scan_paths") or ""
            self._exclude_paths = config.get("exclude_paths") or ""
            self._overlay = config.get("overlay") or False
            self._gen_strategy = config.get("gen_strategy") or "100=60"
            gen_strategy = self._gen_strategy.split("=")
            self._gen_strategy_max_count = int(gen_strategy[0])
            self._gen_strategy_delay = int(gen_strategy[1])

        # 停止现有任务
        self.stop_service()

        # 启动定时任务 & 立即运行一次
        if self._enabled or self._onlyonce:
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            if self._cron:
                logger.info(f"FFmpegStrm缩略图服务启动，周期：{self._cron}")
                try:

                    self._scheduler.add_job(func=self.__libraryscan,
                                            trigger=CronTrigger.from_crontab(self._cron),
                                            name="FFmpegStrm缩略图",
                                            args=[False])
                except Exception as e:
                    logger.error(f"FFmpegStrm缩略图服务启动失败，原因：{str(e)}")
                    self.systemmessage.put(f"FFmpegStrm缩略图服务启动失败，原因：{str(e)}", title="FFmpegStrm缩略图")
            if self._onlyonce:
                logger.info(f"FFmpegStrm缩略图服务，立即运行一次")
                is_overlay = self._overlay
                self._scheduler.add_job(func=self.__libraryscan, trigger='date',
                                        run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                                        name="FFmpegStrm缩略图",
                                        args=[is_overlay])
                # 关闭一次性开关
                self._onlyonce = False
                self.update_config({
                    "onlyonce": False,
                    "enabled": self._enabled,
                    "cron": self._cron,
                    "timeline": self._timeline,
                    "scan_paths": self._scan_paths,
                    "exclude_paths": self._exclude_paths,
                    "overlay": self._overlay,
                    "gen_strategy": self._gen_strategy,
                })
            if self._scheduler.get_jobs():
                # 启动服务
                self._scheduler.print_jobs()
                self._scheduler.start()

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        pass

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'onlyonce',
                                            'label': '立即运行一次',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'overlay',
                                            'label': '覆盖生成',
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'timeline',
                                            'label': '截取时间',
                                            'placeholder': '00:03:01'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'gen_strategy',
                                            'label': '生成策略',
                                            'placeholder': '100=60'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'cron',
                                            'label': '定时扫描周期',
                                            'placeholder': '5位cron表达式，留空关闭'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12
                                },
                                'content': [
                                    {
                                        'component': 'VTextarea',
                                        'props': {
                                            'model': 'scan_paths',
                                            'label': '定时扫描路径',
                                            'rows': 5,
                                            'placeholder': '每一行一个目录'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12
                                },
                                'content': [
                                    {
                                        'component': 'VTextarea',
                                        'props': {
                                            'model': 'exclude_paths',
                                            'label': '定时扫描排除路径',
                                            'rows': 2,
                                            'placeholder': '每一行一个目录'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                },
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal',
                                            'text': '默认情况下，只会生成缺失的缩略图。如果打开覆盖生成，会对所有文件重新生成缩略图。请谨慎打开。覆盖生成只对立即运行一次生效。'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                },
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal',
                                            'text': '生成策略 100=60 表示每生成100个缩略图就暂停60s，以防被风控。'
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": False,
            "cron": "",
            "timeline": "00:03:01",
            "scan_paths": "",
            "err_hosts": "",
            "overlay": False,
            "gen_strategy": "100=60",
        }

    def get_page(self) -> List[dict]:
        pass

    def __libraryscan(self, is_overlay=False):
        """
        开始扫描媒体库
        """
        if not self._scan_paths:
            return
        # 排除目录
        exclude_paths = self._exclude_paths.split("\n")
        # 已选择的目录
        paths = self._scan_paths.split("\n")
        for path in paths:
            if not path:
                continue
            scan_path = Path(path)
            if not scan_path.exists():
                logger.warning(f"FFmpegStrm缩略图扫描路径不存在：{path}")
                continue
            logger.info(f"开始FFmpegStrm缩略图扫描：{path} ...")
            # 遍历目录下的所有文件
            for file_path in SystemUtils.list_files(scan_path, extensions=['.strm']):
                if self._event.is_set():
                    logger.info(f"FFmpegStrm缩略图扫描服务停止")
                    return
                # 排除目录
                exclude_flag = False
                for exclude_path in exclude_paths:
                    try:
                        if file_path.is_relative_to(Path(exclude_path)):
                            exclude_flag = True
                            break
                    except Exception as err:
                        print(str(err))
                if exclude_flag:
                    logger.debug(f"{file_path} 在排除目录中，跳过 ...")
                    continue
                # 开始处理文件
                self.gen_file_thumb(file_path, is_overlay)
            logger.info(f"目录 {path} 扫描完成")

    def gen_file_thumb(self, file_path: Path, is_overlay):
        """
        处理一个文件
        """
        # 单线程处理
        with ffmpeg_lock:
            try:
                if not is_overlay:
                    thumb_path = file_path.with_name(file_path.stem + "-thumb.jpg")
                    if thumb_path.exists():
                        logger.debug(f"缩略图已存在：{thumb_path}")
                        return
                with open(file_path, 'r', encoding='utf-8') as file:
                    strm_path = file.read()
                self._gen_strategy_count += 1
                if self._gen_strategy_count > self._gen_strategy_max_count:
                    logger.info(f"暂停{self._gen_strategy_delay}秒...")
                    time.sleep(self._gen_strategy_delay)
                    self._gen_strategy_count = 0  # 重置计数器
                if self.get_thumb(strm_path=str(strm_path),
                                  image_path=str(thumb_path), frames=self._timeline):
                    logger.info(f"{file_path} 缩略图已生成：{thumb_path}")
            except Exception as err:
                logger.error(f"FFmpegStrm处理文件 {file_path} 时发生错误：{str(err)}")

    def get_thumb(self, strm_path: str, image_path: str, frames: str = None):
        """
        使用ffmpeg从视频文件中截取缩略图
        """
        if not frames:
            frames = "00:03:01"
        if not strm_path or not image_path:
            return False
        cmd = 'ffmpeg -ss {frames} -i "{strm_path}" -vframes 1 -f image2 "{image_path}"'.format(strm_path=strm_path,
                                                                                                frames=frames,
                                                                                                image_path=image_path)
        result = self.execute(cmd)
        if result:
            return True
        return False

    def execute(self, cmd: str) -> str:
        """
        执行命令，获得返回结果
        """
        try:
            result = subprocess.run(cmd, check=True, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True)
            output = result.stdout.strip() if result.stdout else result.stderr.strip()
            # logger.info(f"ffmpeg日志: {output}")
            return output
        except subprocess.CalledProcessError as err:
            logger.error(f"ffmpeg执行命令 '{cmd}' 失败-error: {err.stderr}")
            return ""

    def stop_service(self):
        """
        退出插件
        """
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._event.set()
                    self._scheduler.shutdown()
                    self._event.clear()
                self._scheduler = None
        except Exception as e:
            print(str(e))

    def post_message(self, channel: MessageChannel = None, mtype: NotificationType = None, title: str = None,
                     text: str = None, image: str = None, link: str = None, userid: str = None):
        """
        发送消息
        """
        self.chain.post_message(Notification(
            channel=channel, mtype=mtype, title=title, text=text,
            image=image, link=link, userid=userid
        ))
