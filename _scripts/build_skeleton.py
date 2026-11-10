# -*- coding: utf-8 -*-
"""
烹饪储备库 —— 目录骨架生成器。
可重复运行（幂等）：已存在的文件不会覆盖。
用法：python build_skeleton.py
"""
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CATEGORIES = {
    "01_蔬菜": ["西红柿", "土豆", "黄瓜", "白菜", "菠菜", "茄子", "青椒",
               "胡萝卜", "西兰花", "冬瓜", "南瓜", "芹菜", "韭菜", "洋葱", "豆角"],
    "02_水果": ["苹果", "香蕉", "橙子", "柠檬", "草莓", "芒果", "西瓜", "梨", "葡萄", "猕猴桃"],
    "03_肉类": ["猪肉", "鸡肉", "牛肉", "羊肉", "鸭肉", "排骨", "培根"],
    "04_蛋类": ["鸡蛋", "鸭蛋", "鹌鹑蛋", "皮蛋"],
    "05_奶制品": ["牛奶", "酸奶", "奶酪", "黄油", "淡奶油"],
    "06_水产海鲜": ["草鱼", "鲫鱼", "鲈鱼", "带鱼", "虾", "螃蟹", "蛤蜊", "鱿鱼"],
    "07_豆制品": ["豆腐", "豆干", "腐竹", "豆浆", "豆皮"],
    "08_主食谷物": ["大米", "面粉", "面条", "米粉", "玉米", "红薯", "燕麦", "小米"],
    "09_菌菇": ["香菇", "金针菇", "杏鲍菇", "平菇", "口蘑", "木耳"],
    "10_调味香料": ["葱", "姜", "蒜", "辣椒", "花椒", "八角", "桂皮", "香菜", "孜然"],
    "11_干货": ["香菇干", "海带", "粉丝", "虾皮", "紫菜", "银耳"],
    "12_坚果干果": ["花生", "核桃", "芝麻", "杏仁", "腰果", "红枣", "枸杞", "葡萄干"],
}


def write(path, text):
    if os.path.exists(path):
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return True


def display(cat):
    return cat.split("_", 1)[1]


for d in ["00_入门总纲", "20_复盘日志"]:
    os.makedirs(os.path.join(BASE, d), exist_ok=True)

n_cat = n_ing = 0
for cat, ings in CATEGORIES.items():
    cat_dir = os.path.join(BASE, cat)
    os.makedirs(cat_dir, exist_ok=True)
    title = display(cat)
    body = ["# {}".format(title), "",
            "> 「{}」类原料目录。".format(title), "",
            "## 食材清单", "",
            "（共 {} 种）".format(len(ings)), ""]
    for ing in ings:
        body.append("- [[{}]]".format(ing))
    body.append("")
    if write(os.path.join(cat_dir, title + ".md"), "\n".join(body)):
        n_cat += 1

    for ing in ings:
        ing_dir = os.path.join(cat_dir, ing)
        os.makedirs(ing_dir, exist_ok=True)
        # 每个食材目录下预留「菜品」子目录，归放以该食材为主料的各道菜
        os.makedirs(os.path.join(ing_dir, "菜品"), exist_ok=True)
        ing_body = ["# {}".format(ing), "",
                    "> 🥘 菜品做法正在陆续录入。", "",
                    "## 以「{}」为主要原料的菜品".format(ing), "",
                    "- （暂无，待录入）", ""]
        if write(os.path.join(ing_dir, ing + ".md"), "\n".join(ing_body)):
            n_ing += 1

print("分类索引新建：{} 个；食材笔记新建：{} 个".format(n_cat, n_ing))
print("BASE = {}".format(BASE))
