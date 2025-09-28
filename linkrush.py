import re
from typing import List

import re
from typing import List

def extract_links_from_file(file_path: str) -> List[str]:
    """
    从指定路径的txt文件中提取所有链接。

    参数:
        file_path (str): txt文件的路径。

    返回:
        List[str]: 提取到的链接列表。
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"文件未找到: {file_path}")
        return []
    except Exception as e:
        print(f"读取文件出错: {e}")
        return []

    # 正则表达式匹配常见的链接格式（http、https）
    link_pattern = r'https?://[^\s)>\]}\'"<>]+'
    links = re.findall(link_pattern, content)

    return links
