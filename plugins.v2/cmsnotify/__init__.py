import time

from typing import List, Tuple, Dict, Any
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.event import eventmanager
from app.schemas.types import EventType
from app.utils.http import RequestUtils
from app.log import logger
from app.plugins import _PluginBase


class CMSNotify(_PluginBase):
    # 插件名称
    plugin_name = "CMS通知"
    # 插件描述
    plugin_desc = "整理完成115里的媒体后，通知CMS进行增量同步（strm生成）"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/imaliang/MoviePilot-Plugins/main/icons/cms.png"
    # 插件版本
    plugin_version = "0.3"
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

    # 私有属性
    _cms_notify_type = None
    _cms_domain = None
    _cms_api_token = None
    _enabled = False
    _last_event_time = 0
    # 等待通知数量
    _wait_notify_count = 0

    def init_plugin(self, config: dict = None):
        if config:
            self._enabled = config.get("enabled")
            self._cms_notify_type = config.get("cms_notify_type")
            self._cms_domain = config.get("cms_domain")
            self._cms_api_token = config.get('cms_api_token')

    def get_state(self) -> bool:
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
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        pass

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
                                            'text': '当MP整理或刮削好115里的媒体后，会通知CMS进行增量同步（strm生成）；CMS版本需要0.3.5.11及以上：https://wiki.cmscc.cc'
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
        pass

    @eventmanager.register(EventType)
    def send(self, event):
        """
        向第三方Webhook发送请求
        """
        if not self._enabled or not self._cms_domain or not self._cms_api_token:
            return

        if not event or not event.event_type:
            return

        def __to_dict(_event):
            """
            递归将对象转换为字典
            """
            if isinstance(_event, dict):
                for k, v in _event.items():
                    _event[k] = __to_dict(v)
                return _event
            elif isinstance(_event, list):
                for i in range(len(_event)):
                    _event[i] = __to_dict(_event[i])
                return _event
            elif isinstance(_event, tuple):
                return tuple(__to_dict(list(_event)))
            elif isinstance(_event, set):
                return set(__to_dict(list(_event)))
            elif hasattr(_event, 'to_dict'):
                return __to_dict(_event.to_dict())
            elif hasattr(_event, '__dict__'):
                return __to_dict(_event.__dict__)
            elif isinstance(_event, (int, float, str, bool, type(None))):
                return _event
            else:
                return str(_event)

        version = getattr(settings, "VERSION_FLAG", "v1")
        event_type = event.event_type if version == "v1" else event.event_type.value
        if event_type not in ["transfer.complete", "metadata.scrape"]:
            return
        event_data = __to_dict(event.event_data)

        # logger.info(f"event_data: {event_data}")
        if event_type == "transfer.complete":
            transferinfo = event_data["transferinfo"]
            success = transferinfo["success"]
            if success:
                storage = transferinfo["target_diritem"]["storage"]
                name = transferinfo["target_item"]["name"]
                if storage == "u115":
                    logger.info(f"115整理完成：{name}")
                    self._wait_notify_count += 1
                    self._last_event_time = self.__get_time()
        elif event_type == "metadata.scrape":
            storage = event_data["fileitem"]
            name = event_data["name"]
            if storage == "u115":
                self._wait_notify_count += 1
                self._last_event_time = self.__get_time()
                logger.info(f"115刮削完成：{name}")

    def __get_time(self):
        return int(time.time())

    def __notify_cms(self):
        try:
            # 当等待通知数量超过1000或者有等待通知且最后事件时间超过60秒时触发通知
            if self._wait_notify_count > 0 and (self._wait_notify_count > 1000 or self.__get_time() - self._last_event_time > 60):
                url = f"{self._cms_domain}/api/sync/lift_by_token?token={self._cms_api_token}&type={self._cms_notify_type}"
                ret = RequestUtils().get_res(url)
                if ret:
                    logger.info("通知CMS执行增量同步成功")
                    self._wait_notify_count = 0
                elif ret is not None:
                    logger.error(
                        f"通知CMS失败，状态码：{ret.status_code}，返回信息：{ret.text} {ret.reason}")
                else:
                    logger.error("通知CMS失败，未获取到返回信息")
            else:
                if self._wait_notify_count > 0:
                    logger.info(
                        f"等待通知数量：{self._wait_notify_count}，最后事件时间：{self._last_event_time}")
        except Exception as e:
            logger.error(f"通知CMS发生异常：{e}")

    def stop_service(self):
        """
        退出插件
        """
        pass
