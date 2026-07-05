import json
import shutil
from pathlib import Path

def fix_opencode_config(config_path):
    # 1. 路径处理（兼容旧版Python）
    config_path = Path(config_path)
    if not config_path.exists():
        print(f"❌ 错误：文件不存在 {config_path}")
        return

    # 2. 备份原文件（防止数据丢失）
    backup_path = config_path.with_suffix(".json.bak")
    shutil.copy2(config_path, backup_path)
    print(f"✅ 已备份原文件到：{backup_path}")

    # 3. 读取并解析 JSON
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ JSON 格式错误：{e}，请检查原文件语法")
        return

    # 4. 移除不兼容的字段
    removed = []
    for key in ["name", "env"]:
        if key in data:
            del data[key]
            removed.append(key)
    if removed:
        print(f"✅ 已移除不兼容字段：{', '.join(removed)}")
    else:
        print("ℹ️  未找到需要移除的字段，文件可能已经是兼容格式")

    # 5. 写回修复后的配置
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✅ 修复完成！文件已保存到：{config_path}")

if __name__ == "__main__":
    # 这里替换成你自己的文件路径
    config_file = r"C:\Users\Rofis\Desktop\opencode.json"
    fix_opencode_config(config_file)