import json
import re
from datetime import datetime, timedelta

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.plugins import _PluginBase
from typing import Any, List, Dict, Tuple, Optional
from app.log import logger
from app.schemas import NotificationType
from app.utils.http import RequestUtils
from bs4 import BeautifulSoup


class cnlangsignin(_PluginBase):
    # 插件名称
    plugin_name = "cnlangsignin"
    # 插件描述
    plugin_desc = "国语世界签到。"
    # 插件图标
    plugin_icon = "invites.png"
    # 主题色
    plugin_color = "#FFFFFF"
    # 插件版本
    plugin_version = "1.0"
    # 插件作者
    plugin_author = "imaliang"
    # 作者主页
    author_url = "https://github.com/imaliang"
    # 插件配置项ID前缀
    plugin_config_prefix = "cnlangsignin_"
    # 加载顺序
    plugin_order = 24
    # 可使用的用户级别
    auth_level = 2

    # 私有属性
    _enabled = False
    # 任务执行间隔
    _cron = None
    _cookie = None
    _onlyonce = False
    _notify = False

    # 定时器
    _scheduler: Optional[BackgroundScheduler] = None

    def init_plugin(self, config: dict = None):
        # 停止现有任务
        self.stop_service()

        if config:
            self._enabled = config.get("enabled")
            self._cron = config.get("cron")
            self._cookie = config.get("cookie")
            self._notify = config.get("notify")
            self._onlyonce = config.get("onlyonce")

            # 加载模块
        if self._enabled:
            # 定时服务
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)

            if self._cron:
                try:
                    self._scheduler.add_job(func=self.__signin,
                                            trigger=CronTrigger.from_crontab(
                                                self._cron),
                                            name="国语世界签到")
                except Exception as err:
                    logger.error(f"定时任务配置错误：{str(err)}")

            if self._onlyonce:
                logger.info(f"国语世界签到服务启动，立即运行一次")
                self._scheduler.add_job(func=self.__signin, trigger='date',
                                        run_date=datetime.now(tz=pytz.timezone(
                                            settings.TZ)) + timedelta(seconds=3),
                                        name="国语世界签到")
                # 关闭一次性开关
                self._onlyonce = False
                self.update_config({
                    "onlyonce": False,
                    "cron": self._cron,
                    "enabled": self._enabled,
                    "cookie": self._cookie,
                    "notify": self._notify,
                })

            # 启动任务
            if self._scheduler.get_jobs():
                self._scheduler.print_jobs()
                self._scheduler.start()

    def __signin(self):
        """
        国语世界签到
        """

        flb_url = "cnlang.org"
        headers = {'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                   'Accept - Encoding': 'gzip, deflate, br',
                   'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
                   'cache-control': 'max-age=0',
                   'Upgrade-Insecure-Requests': '1',
                   'Host': flb_url,
                   'Cookie': self._cookie,
                   'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36 Edg/97.0.1072.62'}

        # 访问Pc主页
        print(flb_url)

        res = RequestUtils(headers=headers).get_res(
            url='https://' + flb_url + '/dsu_paulsign-sign.html?mobile=no')
        if not res or res.status_code != 200:
            logger.error("请求国语世界错误")
            return

        # 获取user_name
        pattern = r'title="访问我的空间">(.*?)</a>'
        user_name = re.findall(pattern, res.text)
        if not user_name:
            logger.error("获取user_name失败")
            return

        user_name = user_name[0]
        logger.info(f"获取user_name成功 {user_name}")

        # 解析 HTML 页面
        soup = BeautifulSoup(res.text, 'html.parser')

        # 找到 name 为 formhash 的 input 标签
        formhash_input = soup.find('input', {'name': 'formhash'})

        # 从 input 标签中提取 formhash 的值
        formhash_value = re.search(
            r'value="(.+?)"', str(formhash_input)).group(1)

        # 随机获取心情
        xq = RequestUtils(headers={}).get_res(
            url='https://v1.hitokoto.cn/?encode=text').text

        # 保证字数符合要求
        logger.info("想说的话：" + xq)
        while (len(xq) < 6 | len(xq) > 50):
            xq = RequestUtils(headers={}).get_res(
                url='https://v1.hitokoto.cn/?encode=text').text

            logger.info("想说的话：" + xq)
        # if user_name:
        #     logger.info("登录用户名为：" + user_name.group(1))
        #     logger.info("环境用户名为：" + username)
        # else:
        #     logger.info("未获取到用户名")
        # if user_name is None or (user_name.group(1) != username):
        #     raise Exception("【国语视界】cookie失效")
        # 获取签到链接,并签到
        qiandao_url = 'plugin.php?id=dsu_paulsign:sign&operation=qiandao&infloat=1'

        # 签到
        payload = dict(formhash=formhash_value, qdxq='kx',
                       qdmode='1', todaysay=xq, fastreply='0')
        # qdjg = s.post('https://' + flb_url + '/' + qiandao_url, headers=headers,data= payload).text

        qdjg = RequestUtils(headers=headers).post_res(
            url=f"https://{flb_url}/{qiandao_url}", json=payload).text

        html = qdjg

        soup = BeautifulSoup(html, 'html.parser')
        div = soup.find('div', {'class': 'c'})  # 找到 class 为 clash，id 为 c 的 div
        content = div.text  # 获取 div 的文本内容
        logger.info(content)
        # 获取积分

        user_info = RequestUtils(headers=headers).get_res(
            url=f"https://{flb_url}/home.php?mod=spacecp&ac=credit&showcredit=1&inajax=1&ajaxtarget=extcreditmenu_menu").text

        # user_info = s.get('https://' + flb_url + '/home.php?mod=spacecp&ac=credit&showcredit=1&inajax=1&ajaxtarget=extcreditmenu_menu', headers=headers).text
        current_money = re.search(
            r'<span id="hcredit_2">(\d+)</span>', user_info).group(1)
        log_info = content + "当前大洋余额{}".format(current_money)
        logger.info(log_info)
        # send("签到结果", log_info)

        # if not res or res.status_code != 200:
        #     logger.error("国语世界签到失败")
        #     return

        # sign_dict = json.loads(res.text)
        # money = sign_dict['data']['attributes']['money']
        # totalContinuousCheckIn = sign_dict['data']['attributes']['totalContinuousCheckIn']

        # 发送通知
        if self._notify:
            self.post_message(
                mtype=NotificationType.SiteMessage,
                title="【国语世界签到任务完成】",
                text=f"签到结果 {content} \n"
                     f"当前大洋余额 {current_money}")

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
                                            'model': 'notify',
                                            'label': '开启通知',
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
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'cron',
                                            'label': '签到周期'
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
                                            'model': 'cookie',
                                            'label': '国语视界cookie'
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
                                            'text': '整点定时签到失败？不妨换个时间试试'
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
            "notify": False,
            "cookie": "",
            "cron": "0 9 * * *"
        }

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
