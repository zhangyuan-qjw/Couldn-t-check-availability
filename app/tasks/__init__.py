# -*- coding: utf-8 -*-
"""任务包：静态导入保证 PyInstaller 打包后任务模块仍然可被发现。

【新增功能模块三步走】
1. 在 app/tasks/ 下新建 .py 文件，写 BaseTask 子类并加 @register 装饰器；
2. 在本文件加一行 import；
3. 重新打包。
"""
from . import copy_task        # 复制文件夹/压缩包、复制替换文件
from . import driver_task      # 驱动一键安装（静默安装 + 自动点击向导 + 脚本回放）
from . import shortcut_task    # 桌面快捷方式 + 开机自启（多程序）
from . import printer_task     # 打印机纸张模板 + 默认纸张 + 测试打印
from . import record_task      # 操作录制与回放（勾选脚本随配置执行）
from . import extra_tasks      # 一键运行快捷方式
