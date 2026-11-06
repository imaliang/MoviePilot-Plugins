    MoviePilot-Plugin

MoviePilot 三方插件市场：https://github.com/imaliang/MoviePilot-Plugins/

## 插件合集

- CMS 通知
- 国语视界论坛签到
- SSDForum 论坛签到
- FFmpegStrm 缩略图
- 自定义命令自用版

## CMS通知（MoviePilot V3）

V3 实现位于 `plugins.v3/cmsnotify`，市场索引为 `package.v3.json`，插件版本为
`1.0.0`，要求 MoviePilot `>=3.0.0`。V2 实现继续保留，V3 不再回退加载该旧版。
升级保留插件 ID 与 `enabled`、`cms_notify_type`、`cms_domain`、`cms_api_token`
配置字段，无须重填配置。

支持 `u115`、`115网盘Plus` 和 `CloudDrive储存` 的整理完成与刮削事件。每分钟检查
待通知批次，最后一次事件超过 60 秒或累计超过 1000 次时通知 CMS；请求失败后保留
批次供下次重试。刮削事件代表宿主发起刮削，并不保证全部刮削任务已完成。

迁移依据：[V3 开发指南](https://github.com/jxxghp/MoviePilot-Plugins/blob/main/docs/Plugin_Development.md)
和 [V2 → V3 迁移说明](https://github.com/jxxghp/MoviePilot-Plugins/blob/main/docs/V3_Plugin_Adaptation.md)。
离线回归测试与宿主联调范围见 [测试说明](tests/README.md)。

## 感谢

[jxxghp](https://github.com/jxxghp)、[thsrite](https://github.com/thsrite)、[InfinityPacer](https://github.com/InfinityPacer)
