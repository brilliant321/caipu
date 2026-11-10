# -*- coding: utf-8 -*-
"""把菜品文件里「## 参考链接」区块的图文/视频链接，按专业程度拆分到
初学版 / 进阶版 / 大厨版 三档章节末尾。

用法：
    python redistribute_links.py            # dry-run：打印统计 + 前 N 个文件全文预览
    python redistribute_links.py --apply    # 实际写回文件

分类规则（取该链接覆盖的「最低」专业档，向上兼容）：
    - 标注含「初学」              -> 初学版
    - 否则含「进阶」              -> 进阶版
    - 否则含「大厨」              -> 大厨版
    - 无任何档位标注 -> 关键词兜底 -> 初学版
"""
import glob
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = sorted(glob.glob(os.path.join(BASE, '**', '菜品', '*.md'), recursive=True))

ANCHORS = ['## 初学版', '## 进阶版', '## 大厨版', '## 参考链接', '## 🔒']


def classify(line):
    if '初学' in line:
        return '初学'
    if '进阶' in line:
        return '进阶'
    if '大厨' in line:
        return '大厨'
    if any(k in line for k in ['易学', '新手', '小白', '保姆级', '简单', '家常',
                               '家庭', '合集', '多版本', '查配料', '零失败',
                               '经典', '基础']):
        return '初学'
    if any(k in line for k in ['酒店', '国宴', '专业']):
        return '大厨'
    if any(k in line for k in ['小高姐', '讲解细致', '讲解清晰', '蒸焖', '挤花',
                               '复刻', '锅气']):
        return '进阶'
    return '初学'


LEVEL_TITLES = {
    '初学': '## 初学版',
    '进阶': '## 进阶版',
    '大厨': '## 大厨版',
}


def parse_ref_links(refblock):
    """从参考链接区块解析出 (level, raw_line) 列表。"""
    links = []
    for line in refblock.splitlines():
        s = line.strip()
        if s.startswith('- ['):
            links.append((classify(s), s))
    return links


def build_block(lines):
    if not lines:
        return ''
    body = '\n'.join(lines)
    return ('**参考链接（图文 / 视频，点开前请核对内容）**\n\n'
            + body)


def redistribute(text):
    # 定位锚点
    pos = {}
    for a in ANCHORS:
        m = re.search(r'^' + re.escape(a), text, re.M)
        if not m:
            raise ValueError('缺锚点: ' + a)
        pos[a] = m.start()

    header = text[0:pos['## 初学版']]
    s1 = text[pos['## 初学版']:pos['## 进阶版']]
    s2 = text[pos['## 进阶版']:pos['## 大厨版']]
    s3 = text[pos['## 大厨版']:pos['## 参考链接']]
    refblock = text[pos['## 参考链接']:pos['## 🔒']]
    tail = text[pos['## 🔒']:]

    links = parse_ref_links(refblock)
    by_level = {'初学': [], '进阶': [], '大厨': []}
    for lvl, raw in links:
        by_level[lvl].append(raw)

    sections = {'初学': s1, '进阶': s2, '大厨': s3}

    def inject(section, lvl):
        lines = by_level[lvl]
        if not lines:
            return section
        # 在章节结尾的 '---' 分隔线之前插入链接块
        # 章节内部不含其他 '---'，结尾必有一个 '---'
        core, sep, rest = section.rpartition('\n---')
        block = build_block(lines)
        return core + '\n\n' + block + '\n' + sep + rest

    s1 = inject(sections['初学'], '初学')
    s2 = inject(sections['进阶'], '进阶')
    s3 = inject(sections['大厨'], '大厨')

    return header + s1 + s2 + s3 + tail


def main():
    apply_mode = '--apply' in sys.argv
    preview_n = 2
    stats = {'初学': 0, '进阶': 0, '大厨': 0}
    changed = 0
    for i, f in enumerate(FILES):
        with open(f, encoding='utf-8') as fh:
            text = fh.read()
        new = redistribute(text)
        # 统计
        refblock = text[text.index('## 参考链接'):text.index('## 🔒')]
        for _, raw in parse_ref_links(refblock):
            stats[classify(raw)] += 1
        if new != text:
            changed += 1
            if apply_mode:
                with open(f, 'w', encoding='utf-8') as fh:
                    fh.write(new)
        if not apply_mode and i < preview_n:
            rel = os.path.relpath(f, BASE)
            print('=' * 70)
            print('预览:', rel)
            print('=' * 70)
            print(new)

    print('-' * 70)
    print('文件总数:', len(FILES), '| 发生变更:', changed)
    print('链接按档分布:', stats)
    if not apply_mode:
        print('（dry-run 未写入。确认无误后加 --apply 执行。）')


if __name__ == '__main__':
    main()
