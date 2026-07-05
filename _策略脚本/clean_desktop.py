import os
import shutil
from pathlib import Path

# -------------------------- 配置区（可按需修改） --------------------------
# 桌面路径（Windows默认）
DESKTOP = Path.home() / "Desktop"
# 备份文件夹（清理前会把文件移到这里，不会直接删除）
BACKUP_DIR = DESKTOP / "_桌面清理备份"

# 要清理的文件/文件夹关键词列表
CLEAN_KEYWORDS = [
    "test_",         # 所有测试文件
    "backtest_",     # 回测相关
    "a股",           # 股票看板临时文件
    "cache",         # 缓存文件夹
    "_tmp",          # 临时文件
    "_srv_err",      # 错误日志
    "_srv_out",      # 输出日志
    ".pycache",      # Python缓存
    "新建文本文档",   # 无命名文档
    "README.md",     # 项目说明文件
    ".gitignore",    # Git配置（不用Git的话）
    "3.13加入截图",  # 临时截图文件
    "20d941c9",      # 随机命名文件
    "game py_files", # 游戏相关临时文件
    "game_files",
    "同花顺安装",    # 已安装软件的安装包
    "开盘啦安装",
    "CrystalDisk"    # 已安装工具的安装包
]

# 必须保留的关键词（匹配到这些的文件不会被清理）
KEEP_KEYWORDS = [
    "OpenCode",
    "opencode.json",
    "opencode.json.bak",
    "fix_opencode.py",
    "国金QMT",
    "东方财富",
    "华泰网上交易",
    "微信",
    "企业微信",
    "Edge",
    "联想浏览器",
    "QQ浏览器",
    "WPS",
    "爱奇艺",
    "汽水音乐",
    "芒果TV",
    "Clash",
    "超级互联",
    "桌面清理备份"
]
# -----------------------------------------------------------------------

def is_keep_file(name: str) -> bool:
    """判断文件是否需要保留"""
    return any(kw in name for kw in KEEP_KEYWORDS)

def should_clean(name: str) -> bool:
    """判断文件是否应该被清理"""
    return any(kw in name for kw in CLEAN_KEYWORDS)

def main():
    print("=== 桌面冗余文件清理工具 ===")
    print(f"桌面路径：{DESKTOP}")
    print(f"备份文件夹：{BACKUP_DIR}")
    print("=" * 30)

    # 创建备份文件夹
    BACKUP_DIR.mkdir(exist_ok=True)

    # 遍历桌面文件
    cleaned_count = 0
    for item in DESKTOP.iterdir():
        name = item.name
        # 跳过要保留的文件
        if is_keep_file(name):
            print(f"✅ 保留：{name}")
            continue
        # 判断是否要清理
        if should_clean(name):
            try:
                # 移动到备份文件夹
                dest = BACKUP_DIR / name
                # 如果目标已存在，先重命名
                if dest.exists():
                    dest = BACKUP_DIR / f"{name}_{cleaned_count}"
                shutil.move(str(item), str(dest))
                print(f"🗑️  已移动到备份：{name}")
                cleaned_count += 1
            except Exception as e:
                print(f"❌ 移动失败：{name}，错误：{e}")
        else:
            print(f"ℹ️  跳过（未匹配清理规则）：{name}")

    print("=" * 30)
    print(f"清理完成！共移动 {cleaned_count} 个文件/文件夹到备份目录")
    print(f"备份位置：{BACKUP_DIR}")
    print("确认无误后，可手动删除备份文件夹；若有误删，可从备份中恢复。")

if __name__ == "__main__":
    main()