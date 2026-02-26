#!/usr/bin/env python3
"""
OpenReview 评审流程爬取脚本

用法:
    python openreview_spider.py <paper_id>
    python openreview_spider.py 5BCFlnfE1g

或者交互式输入:
    python openreview_spider.py
"""

import json
import re
import argparse
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

try:
    import openreview
except ImportError:
    print("请先安装 openreview-py: pip install openreview-py")
    exit(1)


@dataclass
class ReviewNote:
    """评审记录"""
    note_type: str
    note_id: str
    timestamp: int
    timestamp_str: str
    author: Optional[str] = None
    content: Optional[dict] = None
    reply_to: Optional[str] = None


class OpenReviewSpider:
    """OpenReview 评审爬虫"""

    # API v2 和 v1 的 baseurl
    API_V2_URL = "https://api2.openreview.net"
    API_V1_URL = "https://api.openreview.net"

    # Note 类型判断关键词
    NOTE_TYPES = {
        "Submission": ["Submission"],
        "Official_Review": ["Official_Review"],
        "Meta_Review": ["Meta_Review"],
        "Decision": ["Decision"],
        "Rebuttal": ["Rebuttal", "Official_Comment", "Author_Feedback"],
        "Comment": ["Comment", "Public_Comment"]
    }

    def __init__(self, username: str = None, password: str = None):
        self.client_v2 = None
        self.client_v1 = None
        self._init_clients(username, password)

    def _init_clients(self, username: str, password: str):
        """初始化 API 客户端"""
        # 尝试匿名访问 (大部分公开会议支持)
        try:
            self.client_v2 = openreview.api.OpenReviewClient(
                baseurl=self.API_V2_URL,
                username=username,
                password=password
            )
            print("✅ 已连接 OpenReview API v2")
        except Exception as e:
            print(f"⚠️ API v2 连接失败: {e}")

        try:
            self.client_v1 = openreview.Client(
                baseurl=self.API_V1_URL,
                username=username,
                password=password
            )
            print("✅ 已连接 OpenReview API v1")
        except Exception as e:
            print(f"⚠️ API v1 连接失败: {e}")

    def _get_note_type(self, invitation: str) -> str:
        """根据 invitation 判断 Note 类型"""
        if not invitation:
            return "Unknown"

        for note_type, keywords in self.NOTE_TYPES.items():
            for keyword in keywords:
                if keyword in invitation:
                    return note_type
        return "Other"

    def _format_timestamp(self, ts: int) -> str:
        """格式化时间戳"""
        try:
            return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M:%S")
        except:
            return str(ts)

    def _extract_content(self, note) -> dict:
        """提取 Note 内容"""
        content = {}
        if hasattr(note, 'content') and note.content:
            for key, value in note.content.items():
                if isinstance(value, dict) and 'value' in value:
                    content[key] = value['value']
                else:
                    content[key] = value
        return content

    def _extract_author(self, note) -> Optional[str]:
        """提取作者信息"""
        # 尝试从 different signatories 获取
        if hasattr(note, 'signatures') and note.signatures:
            for sig in note.signatures:
                if isinstance(sig, str):
                    # 提取 AnonReviewer 等信息
                    if 'AnonReviewer' in sig:
                        return sig.split('/')[-1]
                    elif 'Area_Chair' in sig:
                        return "Area Chair"
                    elif 'Program_Chairs' in sig:
                        return "Program Chair"
                    elif 'Authors' in sig:
                        return "Authors"
            return note.signatures[0] if note.signatures else None
        return None

    def fetch_paper_reviews(self, paper_id: str) -> tuple:
        """
        获取论文评审流程

        Args:
            paper_id: OpenReview 论文 ID (forum id)

        Returns:
            (submission_info, reviews_list)
        """
        notes = []
        submission_info = None

        # 尝试 API v2
        if self.client_v2:
            try:
                print(f"\n🔍 使用 API v2 获取论文 {paper_id} ...")
                notes = self.client_v2.get_all_notes(
                    forum=paper_id,
                    details='replies'
                )
                if notes:
                    print(f"✅ API v2 成功获取 {len(notes)} 条记录")
            except Exception as e:
                print(f"⚠️ API v2 获取失败: {e}")

        # 如果 v2 失败，尝试 v1
        if not notes and self.client_v1:
            try:
                print(f"\n🔍 使用 API v1 获取论文 {paper_id} ...")
                notes = self.client_v1.get_all_notes(
                    forum=paper_id,
                    details='replies'
                )
                if notes:
                    print(f"✅ API v1 成功获取 {len(notes)} 条记录")
            except Exception as e:
                print(f"⚠️ API v1 获取失败: {e}")

        if not notes:
            print(f"❌ 无法获取论文 {paper_id} 的评审信息")
            return None, []

        # 处理 notes
        reviews = []
        for note in notes:
            note_type = self._get_note_type(getattr(note, 'invitation', ''))
            timestamp = getattr(note, 'tcdate', getattr(note, 'cdate', 0))

            review = ReviewNote(
                note_type=note_type,
                note_id=note.id,
                timestamp=timestamp,
                timestamp_str=self._format_timestamp(timestamp),
                author=self._extract_author(note),
                content=self._extract_content(note),
                reply_to=getattr(note, 'replyto', None)
            )

            if note_type == "Submission":
                submission_info = review
            else:
                reviews.append(review)

        # 按时间排序
        reviews.sort(key=lambda x: x.timestamp)

        return submission_info, reviews

    def _extract_venue_short(self, venue: str) -> str:
        """从 venue 字段提取简称，如 'ICLR 2025 Oral' -> 'ICLR25'"""
        if not venue:
            return "Unknown"

        # 常见会议名称映射
        venue_mapping = {
            "ICLR": "ICLR",
            "NeurIPS": "NeurIPS",
            "ICML": "ICML",
            "ACL": "ACL",
            "EMNLP": "EMNLP",
            "NAACL": "NAACL",
            "CVPR": "CVPR",
            "ICCV": "ICCV",
            "ECCV": "ECCV",
            "AAAI": "AAAI",
            "IJCAI": "IJCAI",
        }

        # 提取会议名称
        for full_name, short_name in venue_mapping.items():
            if full_name in venue:
                # 提取年份
                year_match = re.search(r'20\d{2}', venue)
                if year_match:
                    year_short = year_match.group()[-2:]  # 取后两位
                    return f"{short_name}{year_short}"
                return short_name

        return venue.split()[0] if venue else "Unknown"

    def _extract_title_short(self, title: str) -> str:
        """从标题提取简称，如 'FlexPrefill: A Context-Aware...' -> 'FlexPrefill'"""
        if not title:
            return "Unknown"

        # 如果有冒号，取冒号前的部分
        if ':' in title:
            return title.split(':')[0].strip()

        # 否则取第一个单词（去除特殊字符）
        match = re.match(r'^([\w\-]+)', title)
        if match:
            return match.group(1)

        return title[:20].strip()  # 截取前20个字符

    def _get_filename_base(self, submission: ReviewNote, reviews: list) -> str:
        """构建文件名基础部分，格式: [会议简称]标题简称"""
        venue = None
        title = None

        # 从 submission 获取
        if submission and submission.content:
            venue = submission.content.get('venue', '')
            title = submission.content.get('title', '')

        # 如果 submission 为空，从 reviews 中查找
        if not venue or not title:
            for r in reviews:
                if r.content:
                    if not venue:
                        venue = r.content.get('venue', '')
                    if not title:
                        title = r.content.get('title', '')
                    if venue and title:
                        break

        venue_short = self._extract_venue_short(venue)
        title_short = self._extract_title_short(title)

        return f"[{venue_short}]{title_short}"

    def format_output(self, submission: ReviewNote, reviews: list) -> str:
        """格式化输出"""
        lines = []
        lines.append("=" * 80)
        lines.append("📄 论文信息")
        lines.append("=" * 80)

        if submission:
            lines.append(f"标题: {submission.content.get('title', 'N/A')}")
            lines.append(f"作者: {submission.content.get('authors', 'N/A')}")
            lines.append(f"摘要: {submission.content.get('abstract', 'N/A')[:500]}...")
            lines.append(f"时间: {submission.timestamp_str}")

        lines.append("\n" + "=" * 80)
        lines.append("📝 评审流程")
        lines.append("=" * 80)

        # 按类型分组
        type_map = {}
        for r in reviews:
            if r.note_type not in type_map:
                type_map[r.note_type] = []
            type_map[r.note_type].append(r)

        type_order = ["Official_Review", "Rebuttal", "Meta_Review", "Decision", "Comment", "Other"]
        for note_type in type_order:
            if note_type in type_map:
                type_reviews = type_map[note_type]
                lines.append(f"\n{'─' * 40}")
                lines.append(f"【{note_type}】({len(type_reviews)} 条)")
                lines.append(f"{'─' * 40}")

                for i, r in enumerate(type_reviews, 1):
                    lines.append(f"\n  [{i}] {r.timestamp_str}")
                    lines.append(f"      ID: {r.note_id}")
                    if r.author:
                        lines.append(f"      作者: {r.author}")

                    # 输出关键内容
                    if r.content:
                        lines.append("      内容:")
                        for key, value in r.content.items():
                            value_str = str(value)
                            if len(value_str) > 300:
                                value_str = value_str[:300] + "..."
                            lines.append(f"        - {key}: {value_str}")

        return "\n".join(lines)

    def save_to_json(self, submission: ReviewNote, reviews: list, output_path: str):
        """保存为 JSON"""
        data = {
            "submission": asdict(submission) if submission else None,
            "reviews": [asdict(r) for r in reviews],
            "total_reviews": len(reviews),
            "review_types": {}
        }

        for r in reviews:
            data["review_types"][r.note_type] = data["review_types"].get(r.note_type, 0) + 1

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"\n📁 已保存到: {output_path}")

    def save_to_markdown(self, submission: ReviewNote, reviews: list, output_path: str):
        """保存为 Markdown"""
        lines = []

        # 标题
        if submission and submission.content:
            title = submission.content.get('title', 'Unknown Title')
            lines.append(f"# {title}\n")
            lines.append(f"**论文 ID**: {submission.note_id}\n")
            lines.append(f"**提交时间**: {submission.timestamp_str}\n")

            authors = submission.content.get('authors', [])
            if authors:
                lines.append(f"**作者**: {', '.join(authors) if isinstance(authors, list) else authors}\n")

            abstract = submission.content.get('abstract', '')
            if abstract:
                lines.append(f"## 摘要\n\n{abstract}\n")

        # 评审
        lines.append("\n---\n")
        lines.append("# 评审流程\n")

        # 按类型分组
        type_map = {}
        for r in reviews:
            if r.note_type not in type_map:
                type_map[r.note_type] = []
            type_map[r.note_type].append(r)

        type_names = {
            "Official_Review": "官方评审",
            "Rebuttal": "作者回复",
            "Meta_Review": "Meta Review",
            "Decision": "最终决定",
            "Comment": "评论"
        }

        for note_type, type_reviews in type_map.items():
            type_title = type_names.get(note_type, note_type)
            lines.append(f"\n## {type_title}\n")

            for i, r in enumerate(type_reviews, 1):
                lines.append(f"### {type_title} #{i}\n")
                lines.append(f"- **时间**: {r.timestamp_str}\n")
                lines.append(f"- **ID**: {r.note_id}\n")
                if r.author:
                    lines.append(f"- **作者**: {r.author}\n")

                if r.content:
                    lines.append("\n**内容**:\n")
                    for key, value in r.content.items():
                        value_str = str(value)
                        lines.append(f"\n**{key}**:\n\n{value_str}\n")

                lines.append("\n---\n")

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))

        print(f"📄 已保存 Markdown 到: {output_path}")


def create_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description="OpenReview 评审流程爬取工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python openreview_spider.py 5BCFlnfE1g
    python openreview_spider.py --id 5BCFlnfE1g --format json
    python openreview_spider.py --id 5BCFlnfE1g --output ./reviews/

从 URL 提取 ID:
    https://openreview.net/forum?id=5BCFlnfE1g
    只需要取 id= 后面的部分: 5BCFlnfE1g
        """
    )

    parser.add_argument(
        'paper_id',
        nargs='?',
        help='论文 ID (OpenReview URL 中 id= 后面的部分)'
    )
    parser.add_argument(
        '--id', '-i',
        dest='paper_id_alt',
        help='论文 ID (另一种指定方式)'
    )
    parser.add_argument(
        '--format', '-f',
        choices=['json', 'markdown', 'both'],
        default='both',
        help='输出格式 (默认: both)'
    )
    parser.add_argument(
        '--output', '-o',
        default='./openreview_reviews',
        help='输出目录 (默认: ./openreview_reviews)'
    )
    parser.add_argument(
        '--username', '-u',
        help='OpenReview 用户名 (可选，用于访问非公开内容)'
    )
    parser.add_argument(
        '--password', '-p',
        help='OpenReview 密码 (可选)'
    )

    return parser


def main():
    args = create_parser().parse_args()

    # 获取 paper_id
    paper_id = args.paper_id or args.paper_id_alt
    if not paper_id:
        paper_id = input("\n请输入论文 ID (OpenReview URL 中 id= 后面的部分): ").strip()

    if not paper_id:
        print("❌ 必须提供论文 ID")
        return

    # 创建输出目录
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 初始化爬虫
    spider = OpenReviewSpider(
        username=args.username,
        password=args.password
    )

    # 获取评审
    submission, reviews = spider.fetch_paper_reviews(paper_id)

    if not reviews and not submission:
        print("❌ 未获取到任何信息")
        return

    # 打印格式化输出
    print("\n" + spider.format_output(submission, reviews))

    # 保存文件
    base_name = spider._get_filename_base(submission, reviews)

    if args.format in ['json', 'both']:
        json_path = output_dir / f"{base_name}.json"
        spider.save_to_json(submission, reviews, str(json_path))

    if args.format in ['markdown', 'both']:
        md_path = output_dir / f"{base_name}.md"
        spider.save_to_markdown(submission, reviews, str(md_path))

    print(f"\n✅ 完成! 共获取 {len(reviews)} 条评审记录")


if __name__ == "__main__":
    main()