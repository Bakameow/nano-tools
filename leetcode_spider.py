#!/usr/bin/env python3
"""
爬取 LeetCode 题单中的所有题目
题单地址: https://leetcode.cn/discuss/post/3581838/fen-xiang-gun-ti-dan-dong-tai-gui-hua-ru-007o/
"""

import requests
from bs4 import BeautifulSoup
import re
import json
import time


def fetch_page(url: str, max_retries: int = 3) -> str:
    """获取页面内容"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            print(f"请求失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
    return None


def extract_leetcode_links(html: str) -> list:
    """从HTML中提取LeetCode题目链接"""
    soup = BeautifulSoup(html, "html.parser")
    problems = []

    # 查找所有链接
    links = soup.find_all("a", href=True)

    for link in links:
        href = link.get("href", "")
        text = link.get_text(strip=True)

        # 匹配 LeetCode 题目链接
        # 格式如: https://leetcode.cn/problems/xxx/ 或 /problems/xxx/
        if "leetcode.cn/problems/" in href or href.startswith("/problems/"):
            # 提取题目 slug
            match = re.search(r"/problems/([^/]+)/?", href)
            if match:
                slug = match.group(1)

                # 尝试从文本中提取题号
                number_match = re.search(r"(\d+)\s*[\.\、\s]", text)
                problem_number = number_match.group(1) if number_match else ""

                problem = {
                    "number": problem_number,
                    "title": text,
                    "slug": slug,
                    "url": f"https://leetcode.cn/problems/{slug}/",
                }

                # 避免重复
                if problem not in problems:
                    problems.append(problem)

    return problems


def extract_problems_from_content(html: str) -> list:
    """从页面内容中提取题目信息（更全面的方式）"""
    soup = BeautifulSoup(html, "html.parser")
    problems = []

    # 查找文章内容区域
    content_areas = soup.find_all(["div", "article", "section"], class_=re.compile(r"content|article|post|discuss", re.I))

    # 如果找不到特定区域，就在整个页面中搜索
    search_area = soup if not content_areas else content_areas[0]

    # 查找所有包含题目链接的元素
    all_links = search_area.find_all("a", href=True)

    seen_slugs = set()
    for link in all_links:
        href = link.get("href", "")
        text = link.get_text(strip=True)

        # 匹配 LeetCode 题目
        if "/problems/" in href:
            match = re.search(r"/problems/([^/]+)/?", href)
            if match:
                slug = match.group(1)
                if slug in seen_slugs:
                    continue
                seen_slugs.add(slug)

                # 提取题号
                number_match = re.search(r"^(\d+)", text)
                problem_number = number_match.group(1) if number_match else ""

                problems.append({
                    "number": problem_number,
                    "title": text,
                    "slug": slug,
                    "url": f"https://leetcode.cn/problems/{slug}/",
                })

    return problems


def save_to_json(problems: list, filename: str = "leetcode_problems.json"):
    """保存题目列表到JSON文件"""
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(problems, f, ensure_ascii=False, indent=2)
    print(f"已保存 {len(problems)} 道题目到 {filename}")


def save_to_markdown(problems: list, filename: str = "leetcode_problems.md"):
    """保存题目列表到Markdown文件（保持题单原始顺序）"""
    with open(filename, "w", encoding="utf-8") as f:
        f.write("# LeetCode 动态规划题单\n\n")
        f.write(f"共 {len(problems)} 道题目\n\n")

        # 保持题单中的原始顺序，不进行排序
        for i, p in enumerate(problems, 1):
            # number_str = f"{p['number']}. " if p["number"] else ""
            f.write(f"- [ ] [{p['title']}]({p['url']})\n")

    print(f"已保存 {len(problems)} 道题目到 {filename}")


def main():
    url = "https://leetcode.cn/discuss/post/3581838/fen-xiang-gun-ti-dan-dong-tai-gui-hua-ru-007o/"

    print(f"正在获取页面: {url}")
    html = fetch_page(url)

    if not html:
        print("获取页面失败")
        return

    print("正在解析页面...")
    problems = extract_leetcode_links(html)

    if not problems:
        print("未找到题目链接，尝试其他方式...")
        problems = extract_problems_from_content(html)

    if problems:
        print(f"\n找到 {len(problems)} 道题目:")
        for p in problems[:10]:  # 只显示前10个
            print(f"  - {p['number']}: {p['title'][:50]}... ({p['slug']})")
        if len(problems) > 10:
            print(f"  ... 还有 {len(problems) - 10} 道题目")

        save_to_json(problems)
        save_to_markdown(problems)
    else:
        print("未找到任何题目")
        # 保存HTML用于调试
        with open("page_content.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("已保存页面内容到 page_content.html 用于调试")


if __name__ == "__main__":
    main()