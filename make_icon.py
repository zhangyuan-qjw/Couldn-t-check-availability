# -*- coding: utf-8 -*-
"""生成 icon.ico（打包前运行一次，或直接使用仓库中已生成的 icon.ico）"""
from PIL import Image, ImageDraw

S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# 蓝色渐变底色
for y in range(S):
    t = y / S
    color = (int(37 + (96 - 37) * t), int(99 + (165 - 99) * t), int(235 + (255 - 235) * t), 255)
    d.line([(0, y), (S, y)], fill=color)

# 圆角遮罩
mask = Image.new("L", (S, S), 0)
md = ImageDraw.Draw(mask)
md.rounded_rectangle([6, 6, S - 6, S - 6], radius=52, fill=255)
img.putalpha(mask)

# 白色纸张
d = ImageDraw.Draw(img)
d.rounded_rectangle([56, 40, 200, 216], radius=16, fill=(255, 255, 255, 255))
# 纸张上的装饰线
d.rectangle([78, 58, 178, 68], fill=(203, 213, 225, 255))
d.rectangle([78, 80, 178, 90], fill=(203, 213, 225, 255))
# 蓝色“部署”箭头
d.rectangle([114, 96, 142, 176], fill=(29, 78, 216, 255))
d.polygon([(96, 176), (128, 116), (160, 176)], fill=(29, 78, 216, 255))

img.save("icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                            (128, 128), (256, 256)])
print("icon.ico 已生成")
