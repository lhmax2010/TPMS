# TPMS snapshot
来源：提交 36017e7e9，加原工作区中运行所需的未跟踪代码；不带原仓库历史。
内存严格模式在 standalone/tpms_cfg_10.0-tv-kantsu2e.json 的 memory_rigor 节打开。
其它 profile 保持其原始配置；本快照没有修改已有代码或配置内容。
第三方 Python 依赖见 requirements.txt；运行前应在本地 Python 环境安装这些依赖。
Python 3 和 Node.js 用于以下离线测试；在本仓库根目录串行执行：
```bash
taskset -c 0 nice -n 19 python3 -m unittest discover -s tests -v
taskset -c 0 nice -n 19 node --max-old-space-size=64 --v8-pool-size=1 tests/test_memory_ui.js
PYTHONPATH=tests taskset -c 0 nice -n 19 python3 -m unittest -v test_memory_legacy.LegacyCompatibilityTests.test_legacy_output_bytes_both_images test_memory_legacy.LegacyComparisonTests.test_old_comparison_json_byte_identical
```
最后一条覆盖六份内存解析输出和一份旧比较 JSON，共七例逐字节核对。
checktap 的额外离线 mock 单测需要 PyUSB，可单独运行：
```bash
taskset -c 0 nice -n 19 python3 -m unittest discover -s standalone/checktap -p '*_unittest.py' -v
```
已排除 memdiff 历史回放及其旧入口，故不要调用 run_memory_rigor_offline.sh。
本快照不含历史数据库、结果、安装包、编译后二进制或多媒体素材。
部分非内存旧工具仍含 Python 2 语法；本次没有迁移它们。
上板运行需要 sdb、设备 root 权限，以及匹配的板子配置和目标工具。
请先核对板子身份；离线测试不会连接或重启开发板。
