import os
import hashlib
import collections
import re

SERIAL_PATTERN = re.compile(r'^\s*\d+\s*;\s*serial\s*$', re.IGNORECASE)
UUID_PATTERN = re.compile(r'version\s+\d+\s+TXT\s+[0-9a-f]{8}-([0-9a-f]{4}-){3}[0-9a-f]{12}', re.IGNORECASE)

def get_files_dict(directory):
    """遍历目录并返回文件特征字典"""
    files = {}
    for root, dirs, filenames in os.walk(directory):
        relative_path = os.path.relpath(root, directory)
        for filename in filenames:
            file_path = os.path.join(root, filename)
            if os.path.islink(file_path):
                continue
            rel_file = os.path.join(relative_path, filename)
            try:
                files[rel_file] = hash_file(file_path)
            except (IOError, OSError) as e:
                print(f"无法读取文件 {file_path}: {e}")
    return files

def normalize_line(line_bytes):
    """规范化行内容：去除首尾空格，合并中间连续空格"""
    try:
        # 解码为字符串并处理
        line_str = line_bytes.decode('utf-8').strip()
        # 合并所有连续空白字符为单个空格
        line_normalized = re.sub(r'\s+', ' ', line_str)
        return line_normalized.encode('utf-8')
    except UnicodeDecodeError:
        # 保持二进制行不变
        return line_bytes

def hash_file(filepath):
    """计算文件特征值（包含规范化处理）"""
    try:
        with open(filepath, 'rb') as f:
            content = f.read()
            content.decode('utf-8')
        is_text = True
    except UnicodeDecodeError:
        is_text = False

    if is_text:
        lines = []
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line_bytes = line.encode('utf-8')
                if should_ignore_line(line_bytes):
                    continue
                normalized = normalize_line(line_bytes)
                lines.append(normalized)
        lines.sort()
        hasher = hashlib.md5()
        for line in lines:
            hasher.update(line)
        return hasher.hexdigest()
    else:
        with open(filepath, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()

def compare_file_lines(file1, file2):
    def filtered_counter(filepath):
        try:
            with open(filepath, 'rb') as f:
                content = f.read()
                content.decode('utf-8')
            is_text = True
        except UnicodeDecodeError:
            is_text = False

        if is_text:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = [
                    normalize_line(line.encode('utf-8'))
                    for line in f
                    if not should_ignore_line(line.encode('utf-8'))
                ]
        else:
            with open(filepath, 'rb') as f:
                lines = [f.read()]

        return collections.Counter(lines)
    counter1 = filtered_counter(file1)
    counter2 = filtered_counter(file2)

    # 判断是否存在有效差异
    if counter1 == counter2:
        return False, None  # 无实质差异

    # 初始化差异字典
    diff_result = {
        'dir1_only': {},
        'dir2_only': {},
        'common_diff': {}
    }

    # 处理源目录特有行
    for line, count1 in counter1.items():
        count2 = counter2.get(line, 0)
        if count2 == 0:
            diff_result['dir1_only'][line] = count1
        elif count1 != count2:
            diff_result['common_diff'][line] = (count1, count2)

    # 处理目标目录特有行
    for line, count2 in counter2.items():
        if line not in counter1:
            diff_result['dir2_only'][line] = count2
    return True, diff_result

def compare_directories(dir1, dir2):
    """比较目录并过滤无效差异"""
    files1 = get_files_dict(dir1)
    files2 = get_files_dict(dir2)

    modified_details = {}
    for f in set(files1.keys()) & set(files2.keys()):
        if files1[f] != files2[f]:  # 特征值不同才比较细节
            file1_path = os.path.join(dir1, f)
            file2_path = os.path.join(dir2, f)
            has_diff, diff = compare_file_lines(file1_path, file2_path)
            if has_diff:  # 仅保留有效差异
                modified_details[f] = diff
    return {
        'added': set(files2.keys()) - set(files1.keys()),
        'removed': set(files1.keys()) - set(files2.keys()),
        'modified': modified_details,  # 已过滤无实质差异的文件
        'common': set(files1.keys()) & set(files2.keys())
    }

def read_lines(filepath):
    """读取文件的所有行（二进制模式）"""
    with open(filepath, 'rb') as f:
        return list(f)

def should_ignore_line(line_bytes):
    """判断是否应该忽略该行"""
    try:
        line = line_bytes.decode('utf-8').strip()
    except UnicodeDecodeError:
        return False  # 不忽略二进制行

    return bool(
        SERIAL_PATTERN.match(line) or
        UUID_PATTERN.search(line)
    )

def format_line(line_bytes, max_length=80):
    """格式化单行内容为可读字符串"""
    try:
        stripped = line_bytes.rstrip(b'\n\r')
        decoded = stripped.decode('utf-8')
        if len(decoded) > max_length:
            return decoded[:max_length] + '...'
        return decoded
    except UnicodeDecodeError:
        hash_md5 = hashlib.md5(line_bytes).hexdigest()
        return f"<二进制行 MD5:{hash_md5} 长度:{len(line_bytes)}>"

def print_results(results):
    """格式化输出比较结果，包括详细的行差异"""
    print("\n对比结果：")
    print(f"新增文件 ({len(results['added'])})：")
    for f in sorted(results['added']):
        print(f"  + {f}")

    print(f"\n缺失文件 ({len(results['removed'])})：")
    for f in sorted(results['removed']):
        print(f"  - {f}")

    print(f"\n内容不同的文件 ({len(results['modified'])})：")
    for f in sorted(results['modified']):
        print(f"  * {f}")
        diff_info = results['modified'][f]

        dir1_only = diff_info['dir1_only']
        if dir1_only:
            print("    仅在源目录中存在的行：")
            for line, count in dir1_only.items():
                line_str = format_line(line)
                print(f"      - 出现 {count} 次： {line_str}")

        dir2_only = diff_info['dir2_only']
        if dir2_only:
            print("    仅在目标目录中存在的行：")
            for line, count in dir2_only.items():
                line_str = format_line(line)
                print(f"      + 出现 {count} 次： {line_str}")

        common_diff = diff_info['common_diff']
        if common_diff:
            print("    行出现次数不同：")
            for line, (c1, c2) in common_diff.items():
                line_str = format_line(line)
                print(f"      * 行 '{line_str}': 源目录 {c1} 次 vs 目标目录 {c2} 次")

        print()  # 空行分隔不同文件

    common_count = len(results['common']) - len(results['modified'])
    print(f"\n相同文件 ({common_count})")
import sys
if __name__ == "__main__":
    #dir1 = "/usr/home/houbo/"
    #dir2 = "/var/named/"
    dir1 = sys.argv[1]
    dir2 = sys.argv[2]
    if not os.path.isdir(dir1):
        print(f"错误：目录 {dir1} 不存在")
        exit(1)
    if not os.path.isdir(dir2):
        print(f"错误：目录 {dir2} 不存在")
        exit(1)

    results = compare_directories(dir1, dir2)
    print_results(results)