import time
from collections.abc import Mapping
from threading import RLock

from typing import List, Tuple, Dict, Any
from apscheduler.triggers.cron import CronTrigger

from app.sdk.events import Event, eventmanager
from app.schemas.types import EventType
from app.sdk.network import RequestUtils
from app.sdk.logging import logger
from app.sdk.plugin import _PluginBase


class CMSNotify(_PluginBase):
    """合并 V3 云盘整理、刮削事件并通知 CMS 增量同步。"""

    # 插件名称
    plugin_name = "CMS通知"
    # 插件描述
    plugin_desc = "整理完成115里的媒体后，通知CMS进行增量同步（strm生成）"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/imaliang/MoviePilot-Plugins/main/icons/cms.png"
    # 插件版本
    plugin_version = "1.0.0"
    # 插件作者
    plugin_author = "imaliang"
    # 作者主页
    author_url = "https://github.com/imaliang"
    # 插件配置项ID前缀
    plugin_config_prefix = "cmsnotify_"
    # 加载顺序
    plugin_order = 1
    # 可使用的用户级别
    auth_level = 1

    def __init__(self):
        """为每个插件实例建立独立的配置、待通知计数和同步锁。"""
        super().__init__()
        self._lock = RLock()
        self._enabled = False
        self._cms_notify_type = "lift_sync"
        self._cms_domain = ""
        self._cms_api_token = ""
        self._last_event_time = 0
        self._wait_notify_count = 0

    def init_plugin(self, config: dict = None):
        """加载原有配置字段；重复初始化时丢弃旧配置的待通知批次。"""
        config = config or {}
        with self._lock:
            self._enabled = bool(config.get("enabled", False))
            self._cms_notify_type = config.get("cms_notify_type") or "lift_sync"
            self._cms_domain = (config.get("cms_domain") or "").strip().rstrip("/")
            self._cms_api_token = config.get("cms_api_token") or ""
            self._last_event_time = 0
            self._wait_notify_count = 0

    def get_state(self) -> bool:
        """返回当前启用状态。"""
        return self._enabled

    def get_service(self) -> List[Dict[str, Any]]:
        """
        注册插件公共服务
        [{
            "id": "服务ID",
            "name": "服务名称",
            "trigger": "触发器：cron/interval/date/CronTrigger.from_crontab()",
            "func": self.xxx,
            "kwargs": {} # 定时器参数
        }]
        """
        if self._enabled:
            return [{
                "id": "CMSNotify",
                "name": "CMS通知",
                "trigger": CronTrigger.from_crontab("* * * * *"),
                "func": self.__notify_cms,
                "kwargs": {}
            }]
        return []

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """本插件不提供远程命令。"""
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        """本插件不提供额外 API。"""
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页面，需要返回两块数据：1、页面配置；2、数据结构
        """
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
                                    'md': 6
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
                                    'md': 12
                                },
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'model': 'cms_notify_type',
                                            'label': '通知类型',
                                            'items': [
                                                {'title': '增量同步',
                                                    'value': 'lift_sync'},
                                                {'title': '增量同步+自动整理',
                                                    'value': 'auto_organize'},
                                            ]
                                        }
                                    }
                                ]
                            },
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'cms_domain',
                                            'label': 'CMS地址'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'cms_api_token',
                                            'label': 'CMS_API_TOKEN'
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
                                            'text': '收到MP的115整理完成或刮削事件后，会通知CMS进行增量同步（strm生成）；CMS版本需要0.3.5.11及以上：https://wiki.cmscc.cc'
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
                                            'text': '为了防止通知次数过于频繁，会有1-2分钟的等待，只有在此期间再无其它整理或刮削时，才会进行通知'
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
            "cms_notify_type": "lift_sync",
            "cms_api_token": "cloud_media_sync",
            "cms_domain": "http://172.17.0.1:9527"
        }

    def get_page(self) -> List[dict]:
        """本插件不提供详情页。"""
        return []

    @staticmethod
    def _field(value, key, default=None):
        """只读访问 V3 模型或序列化字典，不改写宿主共享事件载荷。"""
        if isinstance(value, Mapping):
            return value.get(key, default)
        return getattr(value, key, default)

    @eventmanager.register([EventType.TransferComplete, EventType.MetadataScrape])
    def monitor(self, event: Event):
        """从 V3 FileItem/TransferInfo 读取目标存储，合并相关云盘事件。"""
        if not event:
            return
        with self._lock:
            if not self._enabled or not self._cms_domain or not self._cms_api_token:
                return
            data = event.event_data
            if event.event_type == EventType.TransferComplete:
                transfer = self._field(data, "transferinfo")
                if not self._field(transfer, "success", False):
                    return
                item = self._field(transfer, "target_item")
                directory = self._field(transfer, "target_diritem")
                storage = self._field(directory, "storage") or self._field(item, "storage")
            elif event.event_type == EventType.MetadataScrape:
                item = self._field(data, "fileitem")
                storage = self._field(item, "storage")
            else:
                return
            if storage not in ("u115", "115网盘Plus", "CloudDrive储存"):
                return
            self._wait_notify_count += 1
            self._last_event_time = int(time.time())
            logger.info(f"收到云盘媒体事件：{self._field(item, 'name') or '未知媒体'}")

    def __notify_cms(self):
        """静默超过60秒或累计超过1000次事件后同步，失败保留批次重试。"""
        # 同步服务由宿主调度；锁避免请求期间新增事件被成功后的清零覆盖。
        with self._lock:
            if not self._enabled or not self._cms_domain or not self._cms_api_token:
                return
            if not self._wait_notify_count:
                return
            if self._wait_notify_count <= 1000 and int(time.time()) - self._last_event_time <= 60:
                return
            try:
                response = RequestUtils(timeout=30).get_res(
                    f"{self._cms_domain}/api/sync/lift_by_token",
                    params={"token": self._cms_api_token, "type": self._cms_notify_type},
                )
                if response is not None and 200 <= response.status_code < 300:
                    logger.info("通知CMS执行增量同步成功")
                    self._wait_notify_count = 0
                elif response is not None:
                    logger.error(f"通知CMS失败，状态码：{response.status_code}")
                else:
                    logger.error("通知CMS失败，未获取到返回信息")
            except Exception as error:
                # 请求异常可能包含带令牌的完整URL，仅记录异常类型。
                logger.error(f"通知CMS发生异常：{type(error).__name__}")

    def stop_service(self):
        """禁用后阻止遗留的调度回调发送，并清理当前待通知批次。"""
        with self._lock:
            self._enabled = False
            self._wait_notify_count = 0
            self._last_event_time = 0
