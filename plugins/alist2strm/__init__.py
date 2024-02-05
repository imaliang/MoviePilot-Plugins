import os
import time
from datetime import datetime, timedelta

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.utils.http import RequestUtils
from app.core.config import settings
from app.plugins import _PluginBase
from typing import Any, List, Dict, Tuple, Optional
from app.log import logger
import xml.dom.minidom
from app.utils.dom import DomUtils


def retry(ExceptionToCheck: Any,
          tries: int = 3, delay: int = 3, backoff: int = 1, logger: Any = None, ret: Any = None):
    """
    :param ExceptionToCheck: 需要捕获的异常
    :param tries: 重试次数
    :param delay: 延迟时间
    :param backoff: 延迟倍数
    :param logger: 日志对象
    :param ret: 默认返回
    """

    def deco_retry(f):
        def f_retry(*args, **kwargs):
            mtries, mdelay = tries, delay
            while mtries > 0:
                try:
                    return f(*args, **kwargs)
                except ExceptionToCheck as e:
                    msg = f"未获取到文件信息，{mdelay}秒后重试 ...ex={e}"
                    if logger:
                        logger.warn(msg)
                    else:
                        print(msg)
                    time.sleep(mdelay)
                    mtries -= 1
                    mdelay *= backoff
            if logger:
                logger.warn('请确保当前配置是否正确')
            return ret

        return f_retry

    return deco_retry


class Alist2Strm(_PluginBase):
    # 插件名称
    plugin_name = "Alist2Strm"
    # 插件描述
    plugin_desc = "自动获取Alist视频信息，生成strm文件，mp刮削入库，emby直接播放，免去下载，轻松拥有一个番剧媒体库"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/alist-org/docs/main/docs/.vuepress/public/logo.png"
    # 插件版本
    plugin_version = "1.6"
    # 插件作者
    plugin_author = "imaliang"
    # 作者主页
    author_url = "https://github.com/imaliang"
    # 插件配置项ID前缀
    plugin_config_prefix = "alist2strm_"
    # 加载顺序
    plugin_order = 1
    # 可使用的用户级别
    auth_level = 2

    # 私有属性
    _enabled = False
    # 任务执行间隔
    _cron = None
    _onlyonce = False
    _monitor_dirs = None
    _storageplace = None

    _alist_domain = None
    _strm_domain = None
    _token = None

    # 定时器
    _scheduler: Optional[BackgroundScheduler] = None

    def init_plugin(self, config: dict = None):
        # 停止现有任务
        self.stop_service()

        if config:
            self._enabled = config.get("enabled")
            self._cron = config.get("cron")
            self._onlyonce = config.get("onlyonce")
            self._monitor_dirs = config.get("monitor_dirs")
            self._storageplace = config.get("storageplace")

            self._alist_domain = config.get("alist_domain")
            self._strm_domain = config.get("strm_domain")
            self._token = config.get("token")
            # 加载模块
        if self._enabled or self._onlyonce:
            # 定时服务
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)

            if self._enabled and self._cron:
                try:
                    self._scheduler.add_job(func=self.__task,
                                            trigger=CronTrigger.from_crontab(
                                                self._cron),
                                            name="Alist2Strm文件创建")
                    logger.info(f'Alist2Strm定时任务创建成功：{self._cron}')
                except Exception as err:
                    logger.error(f"定时任务配置错误：{str(err)}")

            if self._onlyonce:
                logger.info(f"Alist2Strm服务启动，立即运行一次")
                self._scheduler.add_job(func=self.__task, trigger='date',
                                        run_date=datetime.now(tz=pytz.timezone(
                                            settings.TZ)) + timedelta(seconds=3),
                                        name="Alist2Strm文件创建")
                # 关闭一次性开关 全量转移
                self._onlyonce = False
            self.__update_config()

            # 启动任务
            if self._scheduler.get_jobs():
                self._scheduler.print_jobs()
                self._scheduler.start()

    # @retry(Exception, tries=3, logger=logger, ret=[])
    def get_fs_list(self, path) -> List:
        logger.info(f'11111-path={path}')
        addr = f'{self._alist_domain}/api/fs/list'
        logger.info(f'22222-addr={addr}')
        data = {
            "path": path,
            # "page": 1,
            # "per_page": 0,
            "refresh": true
        }
        logger.info(f'333333-data={data}')
        ret = RequestUtils(ua=settings.USER_AGENT if settings.USER_AGENT else None,
                           proxies=settings.PROXY if settings.PROXY else None,
                           content_type="application/json"
                           ).post_res(url=addr, json=data)
        logger.info(f'ret={ret}')
        content = ret.json()['data']['content']
        return content

    def __touch_strm_file(self, file_name, mon_path, strm_path) -> bool:
        src_url = f'{self.strm_domain}/{mon_path}/{file_name}'
        file_path = f'{strm_path}/{mon_path}/{file_name}.strm'
        if os.path.exists(file_path):
            logger.debug(f'{file_name}.strm 文件已存在')
            return False
        try:
            with open(file_path, 'w') as file:
                file.write(src_url)
                logger.debug(f'创建 {file_name}.strm 文件成功')
                return True
        except Exception as e:
            logger.error('创建strm源文件失败：' + str(e))
            return False

    def __task(self):
        # 读取目录配置
        monitor_dirs = self._monitor_dirs.split("\n")
        if not monitor_dirs:
            return

        for mon_path in monitor_dirs:
            # 格式源目录:目的目录
            if not mon_path:
                continue

            # 自定义strm地址
            _strm_path = "/media/strm"
            if mon_path.count(":") == 1:
                _strm_path = mon_path.split(":")[1]
                mon_path = mon_path.split(":")[0]

            # 增量添加更新

            self.process_files(mon_path, _strm_path)

    def process_files(self, mon_path, strm_path):
        fs_list = self.get_fs_list(mon_path)
        logger.info(f'本次处理 {len(fs_list)} 个文件(夹)')
        for fs_info in fs_list:
            if fs_info['is_dir']:
                # 如果是文件夹，递归遍历
                self.process_files(os.path.join(
                    mon_path, fs_info['name']), strm_path)
            else:
                # 如果是文件，输出文件名
                # 获取文件后缀
                file_name = fs_info['name']
                file_extension = os.path.splitext(file_name)[1]
                if file_extension in ['.mkv', '.mp4', '.ts']:
                    self.__touch_strm_file(
                        file_name=file_name, mon_path=mon_path, strm_path=strm_path)
                elif file_extension in ['.jpg', '.png']:
                    # 执行逻辑2
                    pass

    def get_state(self) -> bool:
        return self._enabled

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
                                            'model': 'alist_domain',
                                            'label': 'API域名',
                                            'placeholder': 'http://127.0.0.1:5244'
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
                                            'model': 'strm_domain',
                                            'label': 'Strm域名',
                                            'placeholder': 'http://127.0.0.1:5244/d'
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
                                            'model': 'token',
                                            'label': '访问令牌',
                                            'placeholder': 'alist-xxxxxxxxxxxxxxxxxxx'
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
                                            'label': '执行周期',
                                            'placeholder': '0 0 ? ? ?'
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
                                            'model': 'storageplace',
                                            'label': 'Strm存储地址',
                                            'placeholder': '/downloads/strm'
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
                                    'cols': 12
                                },
                                'content': [
                                    {
                                        'component': 'VTextarea',
                                        'props': {
                                            'model': 'monitor_dirs',
                                            'label': '监控目录',
                                            'rows': 5,
                                            'placeholder': '每一行一个目录，格式如下：\n'
                                            '监控目录:Strm创建目录\n'
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
                                            'text': '自动从open ANi抓取下载直链生成strm文件，免去人工订阅下载' + '\n' +
                                                    '配合目录监控使用，strm文件创建在/downloads/strm' + '\n' +
                                                    '通过目录监控转移到link媒体库文件夹 如/downloads/link/strm  mp会完成刮削',
                                            'style': 'white-space: pre-line;'
                                        }
                                    },
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal',
                                            'text': 'emby容器需要设置代理，docker的环境变量必须要有http_proxy代理变量，大小写敏感，具体见readme.' + '\n' +
                                                    'https://github.com/honue/MoviePilot-Plugins',
                                            'style': 'white-space: pre-line;'
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
            "onlyonce": False,
            "storageplace": '/downloads/strm',
            "cron": "*/20 22,23,0,1 * * *",
        }

    def __update_config(self):
        self.update_config({
            "onlyonce": self._onlyonce,
            "cron": self._cron,
            "enabled": self._enabled,
            "monitor_dirs": self._monitor_dirs,
            "storageplace": self._storageplace,
            "alist_domain": self._alist_domain,
            "strm_domain": self._strm_domain,
            "token": self._token,
        })

    def get_page(self) -> List[dict]:
        pass

    def stop_service(self):
        """
        退出插件
        """
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._scheduler.shutdown()
                self._scheduler = None
        except Exception as e:
            logger.error("退出插件失败：%s" % str(e))


# if __name__ == "__main__":
#     alist2Strm = Alist2Strm()
#     name_list = alist2Strm.get_latest_list()
#     print(name_list)
