#!/usr/bin/env python3
"""to_hant.py — convert the site's Chinese text from Simplified to Traditional (ruling 17, 2026-10-07: 全部使用繁體字).

OpenCC s2t character conversion + a small vocabulary table, applied ONLY to Chinese text: Japanese text is left alone
(segments inside lang="ja" elements, any segment carrying kana, and a protect-list of kana-free Japanese words such as
写真 / 見頃 / 正面横 / 状態). Works on HTML pages (text nodes + title/placeholder/content/alt/aria-label attributes),
JS files (string literals), Python (string literals) and the two data JSON files (named fields).
Usage: python3 scripts/to_hant.py <files…>      (idempotent — Traditional text passes through unchanged)
"""
import json
import re
import sys

import opencc

CC = opencc.OpenCC('s2t')
KANA = re.compile('[぀-ヿ]')
HAN = re.compile('[一-鿿]')
# kana-free Japanese words that OpenCC would mangle (写 → 寫, 横 → 橫, 状 → 狀 …)
PROTECT = ['写真', '正面横', '状態', '根元', '幹周', '見頃', '節気', '比例', '枝ぶり', '成約実績', '応談', '輸送', '樹種について', '四季の姿',
           '関東の名園出品', '免責事項', '下書き', '銘品', '供給者', '管理者', '樹木', '撮影予定', '撮影', '環視', '提出',
           # Japanese words that sit inside Chinese sentences (tree forms, titles, UI words)
           '株立ち', '枝垂れ', '箒立ち', '段作り', '玉散らし', '門かぶり', '模様木', '根回し', '寄せ植え', 'もみじ', '紅葉狩り', 'サンプル',
           'お問い合わせ', '根元の写真をお願いします', '盆栽・植木の輸出検疫について', '供給者ページ', 'ログイン', 'ログアウト', '輸出検疫']
# vocabulary after the character pass: mainland computer / business words → the Traditional-world word
VOCAB = [('發佈', '發布'), ('裏', '裡'), ('覈', '核'), ('臺', '台'), ('登錄', '登入'), ('退出', '登出'), ('視頻', '影片'), ('數據庫', '資料庫'),
         ('環境變量', '環境變數'), ('軟件', '軟體'), ('默認', '預設'), ('保存', '儲存'), ('搜索', '搜尋'), ('鏈接', '連結'), ('正文', '內文'),
         ('信息', '資訊'), ('點擊', '點選'), ('隊列', '清單'), ('示例', '範例'), ('聯繫', '聯絡'), ('用戶', '使用者'), ('設置', '設定'),
         ('文件', '檔案'), ('郵箱', '電郵'), ('網絡', '網路'), ('支持', '支援'), ('屏幕', '螢幕'), ('加載', '載入'), ('存儲', '儲存'), ('賬號', '帳號'),
         ('未連接', '未連線'), ('數據', '資料'),
         # OpenCC's orthodox forms → the forms Taiwan / Hong Kong readers expect
         ('爲', '為'), ('衆', '眾'), ('羣', '群'), ('峯', '峰'), ('汙', '污'), ('祕', '秘'), ('僞', '偽'), ('麪', '麵'), ('牀', '床'), ('佔', '佔')]


def han(text):
    """Convert one Chinese text segment (no tags). Japanese segments pass through."""
    if not HAN.search(text):
        return text
    keep = {}
    for i, w in enumerate(PROTECT):
        if w in text:
            k = f'\x00{i}\x00'
            keep[k] = w
            text = text.replace(w, k)
    if KANA.search(text):                     # an unknown Japanese phrase: keep every kana run and its neighbouring kanji
        for j, run in enumerate(re.findall(r'[\u4e00-\u9fff]{0,2}[\u3040-\u30fa\u30fc-\u30ff]+[\u4e00-\u9fff]{0,2}', text)):
            k = f'\x01{j}\x01'
            keep[k] = run
            text = text.replace(run, k, 1)
    out = CC.convert(text)
    for a, b in VOCAB:
        out = out.replace(a, b)
    for k, w in keep.items():
        out = out.replace(k, w)
    return out


TAG = re.compile(r'<(/?)([a-zA-Z][a-zA-Z0-9-]*)([^>]*)>', re.S)
ATTRS = ('title', 'placeholder', 'content', 'alt', 'aria-label', 'label')


def html(src):
    """Walk tags; convert text nodes and a few attributes outside lang="ja" subtrees."""
    out, pos, ja_stack = [], 0, []
    for m in TAG.finditer(src):
        text = src[pos:m.start()]
        out.append(text if ja_stack else han(text))
        closing, name, attrs = m.group(1), m.group(2).lower(), m.group(3)
        if closing:
            if ja_stack and ja_stack[-1][0] == name:
                ja_stack[-1][1] -= 1
                if ja_stack[-1][1] == 0:
                    ja_stack.pop()
            out.append(m.group(0))
        else:
            void = attrs.rstrip().endswith('/') or name in ('br', 'img', 'input', 'meta', 'link', 'path', 'circle', 'rect', 'ellipse', 'stop', 'hr')
            tag = m.group(0)
            if not ja_stack:
                tag = re.sub(r'\b(' + '|'.join(ATTRS) + r')="([^"]*)"', lambda a: a.group(1) + '="' + han(a.group(2)) + '"', tag)
            if 'lang="ja"' in attrs and not void:
                ja_stack.append([name, 1])
            elif ja_stack and ja_stack[-1][0] == name and not void:
                ja_stack[-1][1] += 1
            out.append(tag)
        pos = m.end()
    out.append(src[pos:] if ja_stack else han(src[pos:]))
    return ''.join(out)


STR = re.compile(r"'((?:[^'\\\n]|\\.)*)'|\"((?:[^\"\\\n]|\\.)*)\"")


def code(src):
    """Convert string literals; a literal that carries HTML goes through the lang="ja"-aware walker."""
    def one(m):
        q = "'" if m.group(1) is not None else '"'
        body = m.group(1) if m.group(1) is not None else m.group(2)
        if not HAN.search(body):
            return m.group(0)
        return q + (html(body) if '<' in body else han(body)) + q
    return STR.sub(one, src)


def species_json(path):
    d = json.load(open(path, encoding='utf-8'))
    for s in d['species']:
        if 'zhs' not in s:
            s['zhs'] = s['zh']                       # the Simplified name, kept for mainland buyers' searches
        s['zh'] = han(s['zhs'])
        k = (s.get('knowledge') or {}).get('zh') or {}
        for key in list(k):
            k[key] = han(k[key])
        if s.get('best_season_note'):
            s['best_season_note'] = han(s['best_season_note'])
    d['note_hant'] = 'zh = 繁體（ruling 17, 2026-10-07）· zhs = 簡體 · zht = the earlier Traditional proposal (reference)'
    json.dump(d, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    open(path, 'a', encoding='utf-8').write('\n')


def trees_json(path):
    d = json.load(open(path, encoding='utf-8'))
    for t in d['trees']:
        if (t.get('given_name') or {}).get('zh'):
            t['given_name']['zh'] = han(t['given_name']['zh'])
        if (t.get('form') or {}).get('zh'):
            t['form']['zh'] = han(t['form']['zh'])
        zh = (t.get('text') or {}).get('zh') or {}
        for key in list(zh):
            zh[key] = han(zh[key])
        for p in t.get('photos') or []:
            if p.get('caption_zh'):
                p['caption_zh'] = han(p['caption_zh'])
    if d.get('note'):
        d['note'] = han(d['note'])
    json.dump(d, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    open(path, 'a', encoding='utf-8').write('\n')


if __name__ == '__main__':
    for path in sys.argv[1:]:
        if path.endswith('species.json'):
            species_json(path); print('data', path); continue
        if path.endswith('trees.json'):
            trees_json(path); print('data', path); continue
        src = open(path, encoding='utf-8').read()
        out = html(src) if path.endswith('.html') else code(src)
        if path.endswith('.html'):
            out = out.replace('lang="zh-Hans"', 'lang="zh-Hant"')
        changed = sum(1 for a, b in zip(src.splitlines(), out.splitlines()) if a != b)
        open(path, 'w', encoding='utf-8').write(out)
        print(f'{path}: {changed} lines changed')
