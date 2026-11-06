# CMSNotify V3 回归测试

在仓库根目录运行（建议使用独立虚拟环境）：

```bash
python -m pip install pytest 'APScheduler>=3.10,<4'
python -m pytest tests/v3/cmsnotify -q
python -m compileall -q plugins.v3/cmsnotify
git diff --check
```

测试通过生产命名空间 `app.plugins.cmsnotify` 加载插件，使用真实 APScheduler，
以局部替身隔离 MoviePilot SDK 和 CMS HTTP 请求，不访问真实 CMS、站点或数据库。
覆盖 V3 对象/字典事件载荷、云盘过滤、静默合并、批次阈值、请求失败重试及停用重载。
这些测试不等同于宿主集成测试。

迁移合同核对来源：

- `jxxghp/MoviePilot-Plugins`：`3b1677f93a11d029cb9b3f150aa6892bbcf14007` 的
  `docs/Plugin_Development.md`、`docs/V3_Plugin_Adaptation.md` 和 `docs/Repository_Guide.md`。
- `jxxghp/MoviePilot` 的 `v3` 分支：`d0f590ded557387c70adb8c8333bb0f117b6ecec` 的
  `app/sdk/network.py`、`app/runtime/events.py`、`app/schemas/event.py` 和
  `app/chain/transfer/scrape.py`。

发布前还应在具有完整依赖的 MoviePilot V3（Python 3.14）中安装并启用插件，确认配置
保存、事件订阅、每分钟服务注册和停用正常；使用测试 CMS 验证真实整理/刮削事件的
通知和重试。开启宿主 `DEBUG` 可检查旧导入兼容警告。此联调不会由离线测试自动执行。
